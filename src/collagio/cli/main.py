"""Command-line entry point (`collagio`).

Examples:
    collagio -i ./photos -o collage.png --size A4 --dpi 300 --seed 42
    collagio -i a.jpg b.jpg c.jpg -o out.jpg --size fullhd --border 8 \\
             --save-project my.collagio.json
    collagio --project my.collagio.json -o out.png --swap 1,4
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Sequence
from pathlib import Path

from collagio import __version__
from collagio.core.commands import SwapPhotos
from collagio.core.model import (
    Background,
    BackgroundKind,
    Canvas,
    LayoutMode,
    LayoutSettings,
    PlacementOrder,
    Project,
    StyleRef,
)
from collagio.core.serialize import load_project, save_project
from collagio.core.units import PAPER_SIZES_MM, PIXEL_PRESETS, Orientation, parse_size
from collagio.errors import CollagioError
from collagio.imaging.loader import find_images, is_supported
from collagio.layout.apply import build_project
from collagio.render.background import parse_color
from collagio.render.export import export_image, format_for_path
from collagio.styles import available_styles, get_style


def _fraction(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 0.5:
        raise argparse.ArgumentTypeError(f"must be between 0 and 0.5, got {value}")
    return number


def _unit_interval(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError(f"must be between 0 and 1, got {value}")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be positive, got {value}")
    return number


def _swap_pair(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2 or not all(parts):
        raise argparse.ArgumentTypeError(f"expected two photos separated by a comma, got {value!r}")
    return parts[0], parts[1]


def build_parser() -> argparse.ArgumentParser:
    presets = ", ".join([*PAPER_SIZES_MM, *PIXEL_PRESETS])
    parser = argparse.ArgumentParser(
        prog="collagio",
        description="Create photo collages from a set of photos.",
        epilog="Size-like style options are in 1/1000 of the canvas short edge.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    source = parser.add_argument_group("input")
    source.add_argument(
        "-i",
        "--input",
        nargs="+",
        action="extend",
        default=[],
        metavar="PATH",
        help="photo files and/or folders (folders are not searched recursively)",
    )
    source.add_argument(
        "-p", "--project", type=Path, help="render an existing project file instead"
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "-o", "--output", type=Path, required=True, help="output image (.png, .jpg)"
    )
    output.add_argument("--quality", type=int, default=92, help="JPEG quality 1-100 (default 92)")
    output.add_argument(
        "--save-project", type=Path, metavar="FILE", help="also save the project file"
    )

    canvas = parser.add_argument_group("canvas")
    canvas.add_argument(
        "--size",
        default="A4",
        help=f"WIDTHxHEIGHT (px), WIDTHxHEIGHTmm or a preset: {presets} (default A4)",
    )
    canvas.add_argument(
        "--orientation", choices=[o.value for o in Orientation], help="force orientation"
    )
    canvas.add_argument("--dpi", type=_positive_int, default=300, help="default 300")
    canvas.add_argument(
        "--background",
        default="#ffffff",
        metavar="COLOR[,COLOR]",
        help="background colour, or two colours for a vertical gradient",
    )

    layout = parser.add_argument_group("layout")
    layout.add_argument(
        "--mode", choices=[m.value for m in LayoutMode], default=LayoutMode.GRID.value
    )
    layout.add_argument("--seed", type=int, help="random seed (default: random, printed)")
    layout.add_argument(
        "--gap", type=_fraction, default=0.01, help="fraction of the short edge (default 0.01)"
    )
    layout.add_argument(
        "--margin",
        type=_fraction,
        default=0.02,
        help="fraction of the short edge (default 0.02)",
    )
    layout.add_argument(
        "--size-variation",
        type=_unit_interval,
        default=0.5,
        help="0 = equal sizes, 1 = strong variation (default 0.5)",
    )
    layout.add_argument(
        "--order",
        choices=[o.value for o in PlacementOrder],
        help="which photo goes into which cell: shape = least cropping (default), "
        "random = shuffled by the seed, input = given order from the top-left",
    )
    layout.add_argument(
        "--swap",
        action="append",
        default=[],
        type=_swap_pair,
        metavar="A,B",
        help="swap the positions of two photos after the layout, by number in input order "
        "(1, 2, ...) or by id from the project file (p001, ...); repeatable",
    )

    style = parser.add_argument_group("style")
    style.add_argument("--style", choices=available_styles(), default="plain")
    style.add_argument("--border", type=float, help="border width")
    style.add_argument("--border-color", help="border colour")
    style.add_argument("--corner-radius", type=float, help="corner radius")
    return parser


def _collect_photos(inputs: Sequence[str]) -> list[Path]:
    photos: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            photos.extend(find_images(path))
        elif not path.exists():
            raise CollagioError(f"input not found: {path}")
        elif not is_supported(path):
            raise CollagioError(f"unsupported file type: {path}")
        else:
            photos.append(path)
    return photos


def _background(spec: str) -> Background:
    colors = [c.strip() for c in spec.split(",")]
    if len(colors) > 2:
        raise CollagioError("--background takes one colour or two comma-separated colours")
    for color in colors:
        parse_color(color)
    if len(colors) == 1:
        return Background(kind=BackgroundKind.SOLID, color=colors[0])
    return Background(kind=BackgroundKind.GRADIENT, color=colors[0], color2=colors[1])


def _style(args: argparse.Namespace) -> StyleRef:
    options = {
        "border_width": args.border,
        "border_color": args.border_color,
        "corner_radius": args.corner_radius,
    }
    params = {key: value for key, value in options.items() if value is not None}
    style = StyleRef(name=args.style, params=params)
    get_style(style.name).resolve(style.params)  # validate early
    return style


def _new_project(args: argparse.Namespace) -> Project:
    photos = _collect_photos(args.input)
    orientation = Orientation(args.orientation) if args.orientation else None
    width, height = parse_size(args.size, args.dpi, orientation)
    return build_project(
        photos,
        Canvas(width=width, height=height, dpi=args.dpi, background=_background(args.background)),
        LayoutSettings(
            mode=LayoutMode(args.mode),
            gap=args.gap,
            margin=args.margin,
            size_variation=args.size_variation,
            order=PlacementOrder(args.order or PlacementOrder.SHAPE),
        ),
        _style(args),
        seed=args.seed,
    )


def _photo_id(project: Project, token: str) -> str:
    """A photo id from a 1-based number in input order, or the id itself."""
    if token.isdigit():
        number = int(token)
        if not 1 <= number <= len(project.photos):
            raise CollagioError(f"photo number {number} is out of range 1..{len(project.photos)}")
        return project.photos[number - 1].id
    return token


def run(args: argparse.Namespace) -> int:
    format_for_path(args.output)  # fail before the (slow) rendering
    if args.project is not None:
        project = load_project(args.project)
    else:
        if args.seed is None:
            args.seed = random.SystemRandom().randrange(1_000_000)
        project = _new_project(args)
    for first, second in args.swap:
        SwapPhotos(_photo_id(project, first), _photo_id(project, second)).apply(project)
    export_image(project, args.output, quality=args.quality)
    if args.save_project is not None:
        save_project(project, args.save_project)
    print(
        f"Wrote {args.output} ({project.canvas.width}x{project.canvas.height} px, "
        f"{len(project.photos)} photos, seed {project.seed})"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.project is not None and args.input:
        parser.error("use either --input or --project, not both")
    if args.project is None and not args.input:
        parser.error("no photos given; use --input or --project")
    if args.project is not None and args.order is not None:
        parser.error("--order only applies when creating a collage from --input")
    try:
        return run(args)
    except (CollagioError, OSError) as exc:
        print(f"collagio: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
