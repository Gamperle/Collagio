# Collagio

Desktop photo collage creator for Windows and Linux.

> **Status:** early development (Phase 0 – project setup). Nothing usable yet.

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
