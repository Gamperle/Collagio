# Collagio

Desktop photo collage creator for Windows and Linux.

> **Status:** early development. Phase 1 is done: grid collages from the command line.
> The desktop GUI follows in Phase 4.

## Planned features

- Collages from 2–100 photos
- **Layouts:** grid with mixed cell sizes; scattered photos with rotation and overlap
- **Styles (per photo):** plain, postage stamp, scissor cut-out, torn paper,
  Polaroid, tape / photo corners, film strip
- Automatic layout generation plus manual editing (move, rotate, resize, swap, crop) with undo/redo
- Export to PNG, JPEG and print-ready PDF (mm/DPI sizes, bleed, crop marks)
- Command-line / batch mode
- English and German interface
- Installers: Windows `.exe`, Linux AppImage and Flatpak

See [TASK.md](TASK.md) for the specification and
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap and test strategy.

## Command-line usage

```bash
collagio -i ./photos -o collage.png --size A4 --dpi 300 --seed 42
collagio -i a.jpg b.jpg c.jpg -o out.jpg --size fullhd --border 8 --corner-radius 12 \
         --background "#f4f1ea" --save-project my.collagio.json
collagio --project my.collagio.json -o out.png      # re-render a saved project
collagio --help                                     # all options
```

- **Sizes:** paper presets (`A5`, `A4`, `A3`, `10x15`, `13x18`, `20x30`), pixel presets
  (`fullhd`, `4k`, `instagram-square`, `instagram-portrait`), `1920x1080` or `210x297mm`;
  `--orientation portrait|landscape`
- **Layout:** `--gap` and `--margin` as a fraction of the canvas short edge,
  `--size-variation 0..1`, `--seed` for a reproducible layout (a random seed is printed)
- **Photo placement:** `--order shape` (default: photos go into cells of matching shape,
  least cropping), `random` (shuffled by the seed) or `input` (given order from the top-left);
  `--swap 1,4` exchanges two photos afterwards (by number in input order or by id such as
  `p004`, repeatable, also works with `--project`)
- **Style:** `--border`, `--corner-radius` in 1/1000 of the canvas short edge, `--border-color`
- **Background:** one colour, or two comma-separated colours for a gradient

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # create .venv with Python 3.13 and dev tools
uv run pytest                    # run tests
uv run pytest --cov              # with coverage (gate: 85 %)
uv run pytest -m "not slow"      # skip slow tests
uv run pytest --update-golden    # regenerate golden reference images
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit install        # run lint/type checks on every commit
```

Generate the synthetic test photos to look at them:

```bash
uv run python tests/fixtures/generate.py /tmp/collagio-photos --large
```

## Licence

Collagio is free software, licensed under the
[GNU General Public License v3.0 or later](LICENSE).
