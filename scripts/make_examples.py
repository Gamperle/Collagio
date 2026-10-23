"""Render the example collages and the editor screenshot shown in the README.

    uv run python scripts/make_examples.py              # writes docs/images/*.jpg

The photos are painted procedurally (sky, sun or moon, mountain ridges, water),
so the examples are reproducible and free of licence questions. Each collage is
made with the real command line; the commands are listed in EXAMPLES.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "images"

Color = tuple[int, int, int]


@dataclass(frozen=True)
class Scene:
    name: str
    size: tuple[int, int]
    sky: tuple[Color, Color]  # top, horizon
    ridges: tuple[Color, ...]  # far to near
    sun: Color | None = None
    sun_pos: tuple[float, float] = (0.7, 0.35)  # share of width, height
    horizon: float = 0.62  # share of height
    water: bool = False
    stars: bool = False
    seed: int = 0


SCENES = (
    Scene("sunset-sea", (1500, 1000), ((70, 40, 110), (255, 150, 80)), ((90, 50, 90),),
          sun=(255, 225, 160), sun_pos=(0.5, 0.52), horizon=0.6, water=True, seed=1),
    Scene("alps", (1000, 1500), ((60, 120, 200), (200, 225, 245)),
          ((150, 170, 200), (90, 110, 140), (40, 80, 50)), sun=(255, 250, 220),
          sun_pos=(0.75, 0.15), horizon=0.7, seed=2),
    Scene("night-lake", (1200, 1200), ((5, 10, 35), (35, 50, 100)), ((20, 25, 45),),
          sun=(235, 235, 210), sun_pos=(0.3, 0.25), horizon=0.58, water=True, stars=True,
          seed=3),
    Scene("desert", (1600, 900), ((120, 170, 230), (250, 215, 170)),
          ((210, 150, 100), (190, 120, 70)), sun=(255, 245, 210), sun_pos=(0.2, 0.2),
          horizon=0.62, seed=4),
    Scene("misty-forest", (1000, 1250), ((170, 185, 180), (225, 230, 220)),
          ((140, 160, 150), (90, 120, 100), (40, 70, 50)), horizon=0.55, seed=5),
    Scene("lagoon", (1500, 1000), ((40, 150, 210), (170, 225, 240)), ((60, 120, 80),),
          sun=(255, 255, 235), sun_pos=(0.8, 0.18), horizon=0.5, water=True, seed=6),
    Scene("dusk-hills", (1000, 1500), ((40, 30, 80), (240, 120, 120)),
          ((120, 60, 100), (70, 35, 70), (30, 20, 40)), sun=(255, 200, 150),
          sun_pos=(0.4, 0.55), horizon=0.62, seed=7),
    Scene("glacier", (1200, 1200), ((110, 160, 210), (230, 240, 250)),
          ((220, 230, 240), (160, 185, 210)), horizon=0.6, water=True, seed=8),
    Scene("autumn", (1500, 1000), ((120, 160, 210), (240, 220, 190)),
          ((200, 120, 60), (160, 70, 30), (90, 40, 20)), sun=(255, 245, 215),
          sun_pos=(0.85, 0.2), horizon=0.6, seed=9),
    Scene("aurora", (1600, 900), ((10, 40, 50), (40, 160, 120)), ((15, 30, 35),),
          horizon=0.7, stars=True, seed=10),
    Scene("canyon", (1000, 1250), ((90, 150, 220), (245, 200, 160)),
          ((200, 110, 70), (160, 70, 40), (110, 45, 30)), sun=(255, 250, 225),
          sun_pos=(0.3, 0.12), horizon=0.5, seed=11),
    Scene("fjord", (1500, 1000), ((90, 120, 160), (200, 210, 220)),
          ((110, 125, 140), (60, 75, 85)), horizon=0.55, water=True, seed=12),
)  # fmt: skip


def _ridge(width: int, rng: np.random.Generator, roughness: float) -> np.ndarray:
    """A smooth random mountain profile, values around 0 (fraction of height)."""
    profile = np.zeros(width)
    for octave in range(1, 7):
        points = 2**octave + 1
        knots = rng.normal(0, roughness / octave**1.3, points)
        profile += np.interp(np.linspace(0, points - 1, width), np.arange(points), knots)
    return profile


def paint(scene: Scene) -> Image.Image:
    width, height = scene.size
    rng = np.random.default_rng(scene.seed)
    ys = np.linspace(0, 1, height)[:, None, None]
    top, bottom = (np.array(c, float) for c in scene.sky)
    sky = top + (bottom - top) * np.clip(ys / scene.horizon, 0, 1) ** 1.4
    image = np.broadcast_to(sky, (height, width, 3)).copy()

    yy, xx = np.mgrid[0:height, 0:width]
    if scene.stars:
        count = width * height // 900
        sy, sx = rng.integers(0, int(height * scene.horizon), count), rng.integers(0, width, count)
        image[sy, sx] = 255 * rng.uniform(0.5, 1.0, (count, 1))
    if scene.name == "aurora":
        band = np.exp(-(((yy / height - 0.3 - 0.12 * np.sin(xx / width * 6)) / 0.08) ** 2))
        image += band[..., None] * np.array([40, 200, 120]) * 0.8
    if scene.sun is not None:
        cx, cy = scene.sun_pos[0] * width, scene.sun_pos[1] * height
        dist = np.hypot(xx - cx, yy - cy) / min(width, height)
        glow = np.exp(-((dist / 0.18) ** 2))[..., None]
        disc = np.clip((0.06 - dist) / 0.005, 0, 1)[..., None]
        sun = np.array(scene.sun, float)
        image = image * (1 - 0.6 * glow) + sun * 0.6 * glow
        image = image * (1 - disc) + sun * disc

    horizon_px = scene.horizon * height
    ground_bottom = height if not scene.water else horizon_px
    for index, color in enumerate(scene.ridges):
        depth = (index + 1) / len(scene.ridges)
        base = horizon_px - (0.25 - 0.18 * depth) * height * (0 if scene.water else 1)
        profile = base + _ridge(width, rng, 0.07 + 0.05 * (1 - depth)) * height
        if scene.water:
            profile = np.minimum(profile, horizon_px)
        mask = (yy >= profile[None, :]) & (yy < ground_bottom)
        shade = np.clip(1 - (yy - base) / height * 0.8, 0.5, 1)[..., None]
        image = np.where(mask[..., None], np.array(color, float) * shade, image)

    if scene.water:
        h = int(horizon_px)
        reflected = image[max(0, 2 * h - height) : h][::-1]
        below = height - h
        reflected = reflected[:below]
        if reflected.shape[0] < below:
            pad = np.repeat(reflected[-1:], below - reflected.shape[0], axis=0)
            reflected = np.concatenate([reflected, pad])
        ripple = np.sin(np.arange(below)[:, None] * 0.9 + rng.uniform(0, 6, (1, width)) * 0.3)
        water = reflected * 0.7 + np.array(scene.sky[0], float) * 0.15
        image[h:] = water * (0.92 + 0.08 * ripple[..., None])

    vignette = 1 - 0.35 * (((xx / width - 0.5) ** 2 + (yy / height - 0.5) ** 2) * 2)
    image = image * vignette[..., None] + rng.normal(0, 3, image.shape)
    picture = Image.fromarray(np.clip(image, 0, 255).astype(np.uint8))
    return picture.filter(ImageFilter.GaussianBlur(0.6))


@dataclass(frozen=True)
class Example:
    name: str
    args: str  # collagio options after "-i PHOTOS -o OUTPUT"
    photos: tuple[str, ...] = ()  # default: all


EXAMPLES = (
    Example("grid", "--size 1800x1200 --gap 0.012 --margin 0.025 --background '#f4f1ea' "
            "--corner-radius 10 --seed 7"),
    Example("scattered-polaroid", "--size 1800x1200 --mode scattered --style polaroid "
            "--background texture:cork --rotation 14 --shadow 0.45 --seed 3",
            ("sunset-sea", "alps", "night-lake", "desert", "misty-forest", "lagoon", "autumn")),
    Example("mixed-styles", "--size 1800x1200 --mode scattered "
            "--mix stamp,polaroid,tape,torn,cutout --background texture:paper "
            "--rotation 10 --shadow 0.35 --seed 11"),
    Example("filmstrip", "--size 1800x1200 --style filmstrip --background '#2a2826,#4a4540' "
            "--gap 0.015 --seed 5",
            ("sunset-sea", "alps", "night-lake", "desert", "glacier", "aurora", "canyon")),
    Example("stamps-title", "--size 1200x1500 --style stamp --background texture:wood "
            "--title 'Mountains & Lakes' --title-position top --title-color '#fdf8ee' "
            "--title-shadow --shadow 0.4 --seed 2",
            ("alps", "night-lake", "misty-forest", "glacier", "dusk-hills", "fjord")),
    Example("photo-background", "--size 1800x1200 --mode scattered --style tape "
            "--background photo:PHOTOS/sunset-sea.jpg --background-dim 0.3 "
            "--title 'Summer 2026' --title-color white --title-shadow --rotation 8 "
            "--shadow 0.5 --seed 4",
            ("lagoon", "autumn", "desert", "canyon", "dusk-hills")),
)  # fmt: skip


def screenshot(project: Path, target: Path, temp: Path) -> None:
    """The editor with `project` open and one photo selected, rendered off screen."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["COLLAGIO_LANG"] = "en"
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from collagio.app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(temp / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings, cache_dir=temp / "cache")
    window.resize(1400, 860)
    window.show()
    window.open_file(project)
    window.canvas.select([window.document.project.photos[1].id])
    for _ in range(3):  # previews are rendered in the background
        window.renderer.wait()
        app.processEvents()
    window.grab().save(str(target), quality=85)
    window.document.undo_stack.set_clean()  # nothing to save on close
    window.close()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        photos = Path(temp) / "photos"
        photos.mkdir()
        for scene in SCENES:
            paint(scene).save(photos / f"{scene.name}.jpg", quality=90)
        for example in EXAMPLES:
            chosen = example.photos or tuple(s.name for s in SCENES)
            inputs = [str(photos / f"{name}.jpg") for name in chosen]
            target = OUT_DIR / f"{example.name}.jpg"
            args = shlex.split(example.args.replace("PHOTOS", str(photos)))
            command = [sys.executable, "-m", "collagio.cli.main", "-i", *inputs, "-o", str(target)]
            if example.name == "scattered-polaroid":
                args += ["--save-project", str(Path(temp) / "editor.collagio")]
            subprocess.run([*command, *args, "--quality", "82"], check=True)
            print(target.relative_to(ROOT))
        screenshot(Path(temp) / "editor.collagio", OUT_DIR / "editor.jpg", Path(temp))
        print((OUT_DIR / "editor.jpg").relative_to(ROOT))


if __name__ == "__main__":
    main()
