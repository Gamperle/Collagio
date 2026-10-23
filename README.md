# Collagio

Desktop photo collage creator for Windows and Linux.

> **Status:** early development. Phases 1-5 are done: desktop editor, command line and
> print-ready PDF export work; German UI and installers follow.
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

## Desktop editor

```bash
uv sync --extra gui      # or: pip install "collagio[gui]"
uv run collagio-gui      # optionally followed by photos, folders or a .collagio.json file
```

- Add photos with **File > Add photos**, the photo list's button, or by dropping files or
  folders onto the window. The Layout, Style and Canvas tabs change the whole collage;
  each "Apply" is one undo step.
- **Click** selects a photo (**Ctrl+click** adds to the selection), **drag** moves it. In grid
  mode, dropping a photo onto another one **swaps** them.
- **Corner handles** resize (aspect ratio kept), the **round handle** rotates (**Shift** snaps to
  15°).
- **Alt+drag** moves the photo inside its frame, **Ctrl+wheel** zooms it; *Edit > Reset crop*
  goes back to the automatic crop. The **mouse wheel** zooms the view, the **middle button** pans.
- Right-click a photo for stacking order, crop reset and removal. Undo/redo covers every edit.
- The **Text** tab adds titles and captions (size, colour, rotation, font, shadow); drag them on
  the canvas to move them. The **Canvas** tab offers solid, gradient, paper/cork/wood texture
  and blurred-photo backgrounds, and shows the size in mm.
- **File > Export image** renders the full-resolution PNG, JPEG or PDF in the background
  (cancellable); the options ask for quality, bleed and, for PDF, crop marks.
  Unsaved work is autosaved every two minutes; *File > Recover unsaved work* brings it back
  after a crash.

## Command-line usage

```bash
collagio -i ./photos -o collage.png --size A4 --dpi 300 --seed 42
collagio -i a.jpg b.jpg c.jpg -o out.jpg --size fullhd --border 8 --corner-radius 12 \
         --background "#f4f1ea" --save-project my.collagio.json
collagio -i ./photos -o scattered.jpg --mode scattered --rotation 15 --overlap 0.7
collagio -i ./photos -o mixed.jpg --mode scattered --mix stamp,polaroid,tape,torn
collagio -i ./photos -o out.png --style polaroid --style-param "caption=Summer 2026"
collagio -i ./photos -o print.pdf --size A4 --bleed 3 --crop-marks --title "Summer 2026"
collagio -i ./photos -o wall.jpg --background texture:cork --style polaroid --mode scattered
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
- **Scattered mode** (`--mode scattered`): rotated, overlapping photos. `--rotation` (max
  degrees, default 12), `--overlap 0..1` (default 0.5), `--min-visible 0..1` (share of every
  photo that stays uncovered, default 0.5; guaranteed)
- **Shadow:** `--shadow OPACITY` (default 0.45 in scattered mode, off in grid mode),
  `--shadow-blur`
- **Styles:** `--style plain|stamp|cutout|torn|polaroid|tape|filmstrip` for all photos;
  `--style-param KEY=VALUE` for any style parameter (e.g. `caption=Summer`, `value=60c`,
  `variant=corners`, `sides=top,bottom`, `orientation=vertical`); `--mix stamp,polaroid,...`
  gives each photo a random style from the list; `--photo-style 3=torn` sets one photo's style.
  Tiles are shaped for photo + frame, so frames do not crop the photo.
- **Plain style shortcuts:** `--border`, `--corner-radius` in 1/1000 of the canvas short edge,
  `--border-color`
- **Background:** one colour, two comma-separated colours for a gradient, `texture:paper|cork|wood`
  (optionally `,COLOR`), or `photo:PATH` (blurred, `--background-blur`, `--background-dim`)
- **Print:** `.pdf` output; `--bleed MM` extends the background on every side (all formats),
  `--crop-marks` adds crop marks outside the bleed (PDF); the PDF has TrimBox and BleedBox set
- **Title:** `--title TEXT` (`\n` for line breaks), `--title-position top|bottom|center` (top and
  bottom keep the photos clear), `--title-size`, `--title-color`, `--title-font FILE`,
  `--title-shadow`

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
