"""Style interface and registry.

A style turns a photo into a framed RGBA tile of a given size. Rendering is
split in two steps so the renderer can crop the photo to exactly the area the
style leaves for it:

1. `content_box(size, params, ctx)` - where the photo goes inside the tile.
2. `render(content, size, params, ctx)` - draw the tile around the photo.

Size-like parameters are in *style units*: 1/1000 of the canvas short edge.
`StyleContext.unit` converts them to pixels at the current render scale, so a
style looks the same in a small preview and in a full-resolution export.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from random import Random
from typing import Any, ClassVar

from PIL import Image, ImageColor

from collagio.errors import StyleError

Box = tuple[int, int, int, int]  # x, y, width, height


@dataclass(frozen=True)
class StyleContext:
    unit: float  # pixels per style unit
    rng: Random

    def px(self, units: float) -> int:
        return round(units * self.unit)


class Style(ABC):
    name: ClassVar[str]
    labels: ClassVar[Mapping[str, str]]  # language code -> display name
    defaults: ClassVar[Mapping[str, Any]]

    def resolve(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Defaults merged with `params`; unknown or mistyped parameters are rejected."""
        unknown = set(params) - set(self.defaults)
        if unknown:
            raise StyleError(f"unknown parameter(s) for style {self.name!r}: {sorted(unknown)}")
        resolved = dict(self.defaults)
        for key, value in params.items():
            default = self.defaults[key]
            if isinstance(default, int | float) and not isinstance(default, bool):
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise StyleError(f"{self.name}.{key} must be a number, got {value!r}")
                if value < 0:
                    raise StyleError(f"{self.name}.{key} must not be negative, got {value!r}")
            elif isinstance(default, str) and key.endswith("color"):
                try:
                    if not isinstance(value, str):
                        raise ValueError
                    ImageColor.getrgb(value)
                except ValueError as exc:
                    raise StyleError(f"{self.name}.{key}: invalid colour {value!r}") from exc
            resolved[key] = value
        return resolved

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
        raise StyleError(f"style {cls.name!r} is already registered")
    _REGISTRY[cls.name] = cls()
    return cls


def get_style(name: str) -> Style:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise StyleError(
            f"unknown style {name!r}; available: {', '.join(available_styles())}"
        ) from None


def available_styles() -> list[str]:
    return sorted(_REGISTRY)
