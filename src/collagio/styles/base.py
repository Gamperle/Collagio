"""Style interface and registry.

A style turns a photo into a framed RGBA tile of a given size. Rendering is
split in two steps so the renderer can crop the photo to exactly the area the
style leaves for it:

1. `content_box(size, params, ctx)` - where the photo goes inside the tile.
2. `render(content, size, params, ctx)` - draw the tile around the photo.

Size-like parameters are in *style units*: 1/1000 of the canvas short edge.
`StyleContext.unit` converts them to pixels at the current render scale. Random
shapes (torn edges, cut lines, tape) are generated in style units too, so a
style looks the same in a small preview and in a full-resolution export.

Randomness comes from `ctx.rng(purpose)` / `ctx.numpy_rng(purpose)`: a fresh
generator per purpose, derived from the photo's seed. `content_box` and
`render` therefore see the same random values for the same purpose.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
from PIL import Image, ImageColor

from collagio.core.rng import derive_seed
from collagio.errors import StyleError

Box = tuple[int, int, int, int]  # x, y, width, height

STYLE_UNITS_PER_SHORT_EDGE = 1000


@dataclass(frozen=True)
class StyleContext:
    unit: float  # pixels per style unit
    seed: int
    photo_aspect: float | None = None  # width / height of the (upright) photo, if known

    def px(self, units: float) -> int:
        return round(units * self.unit)

    def rng(self, purpose: str) -> random.Random:
        return random.Random(derive_seed(self.seed, purpose))

    def numpy_rng(self, purpose: str) -> np.random.Generator:
        return np.random.default_rng(derive_seed(self.seed, purpose))


class Style(ABC):
    name: ClassVar[str]
    labels: ClassVar[Mapping[str, str]]  # language code -> display name
    defaults: ClassVar[Mapping[str, Any]]
    # Allowed values for text parameters, and inclusive ranges for numbers.
    choices: ClassVar[Mapping[str, tuple[str, ...]]] = {}
    ranges: ClassVar[Mapping[str, tuple[float, float]]] = {}

    def resolve(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Defaults merged with `params`; unknown or invalid parameters are rejected."""
        unknown = set(params) - set(self.defaults)
        if unknown:
            raise StyleError(
                "unknown parameter(s) for style {style!r}: {names}",
                style=self.name,
                names=sorted(unknown),
            )
        resolved = dict(self.defaults)
        for key, value in params.items():
            self._check(key, value)
            resolved[key] = value
        self.validate(resolved)
        return resolved

    def _check(self, key: str, value: Any) -> None:
        default = self.defaults[key]
        if isinstance(default, int | float) and not isinstance(default, bool):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise StyleError(
                    "{style}.{key} must be a number, got {value!r}",
                    style=self.name,
                    key=key,
                    value=value,
                )
            if key not in self.ranges:
                if value < 0:
                    raise StyleError(
                        "{style}.{key} must not be negative, got {value!r}",
                        style=self.name,
                        key=key,
                        value=value,
                    )
                return
            low, high = self.ranges[key]
            if not low <= value <= high:
                raise StyleError(
                    "{style}.{key} must be between {low:g} and {high:g}, got {value!r}",
                    style=self.name,
                    key=key,
                    low=low,
                    high=high,
                    value=value,
                )
        elif isinstance(default, str):
            if not isinstance(value, str):
                raise StyleError(
                    "{style}.{key} must be text, got {value!r}",
                    style=self.name,
                    key=key,
                    value=value,
                )
            if key.endswith("color"):
                try:
                    ImageColor.getrgb(value)
                except ValueError as exc:
                    raise StyleError(
                        "{style}.{key}: invalid colour {value!r}",
                        style=self.name,
                        key=key,
                        value=value,
                    ) from exc
            if key in self.choices and value not in self.choices[key]:
                raise StyleError(
                    "{style}.{key} must be one of {choices}, got {value!r}",
                    style=self.name,
                    key=key,
                    choices=", ".join(self.choices[key]),
                    value=value,
                )

    def validate(self, params: Mapping[str, Any]) -> None:  # noqa: B027 - optional hook
        """Checks across parameters; override in styles that need them."""

    @abstractmethod
    def content_box(
        self, size: tuple[int, int], params: Mapping[str, Any], ctx: StyleContext
    ) -> Box: ...

    @abstractmethod
    def render(
        self,
        content: Image.Image,
        size: tuple[int, int],
        params: Mapping[str, Any],
        ctx: StyleContext,
    ) -> Image.Image: ...


_REGISTRY: dict[str, Style] = {}


def register[S: type[Style]](cls: S) -> S:
    if cls.name in _REGISTRY:
        raise StyleError("style {name!r} is already registered", name=cls.name)
    _REGISTRY[cls.name] = cls()
    return cls


def get_style(name: str) -> Style:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise StyleError(
            "unknown style {name!r}; available: {available}",
            name=name,
            available=", ".join(available_styles()),
        ) from None


def available_styles() -> list[str]:
    return sorted(_REGISTRY)
