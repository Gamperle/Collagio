# Implementation Plan – Collagio

Based on [TASK.md](TASK.md). Created: 2026-10-23.

## 1. Architecture principles

- **Headless core, thin GUI.** All logic (model, layout, styles, rendering,
  export) lives in pure-Python packages with no Qt dependency. The GUI and CLI
  are both clients of the same core. This keeps ~80 % of the code testable
  without a display.
- **Model → Renderer → Output.** The project model is a plain data structure
  (dataclasses), serialised to JSON. The renderer turns a model into a Pillow
  image at any resolution. Preview and export use the same renderer, at
  different scales.
- **Determinism.** Every random choice (layout, rotation, torn edges) comes from
  `random.Random(seed)` derived from project seed + photo id. No global RNG.
  This makes golden-image tests possible.
- **Commands for edits.** Every user edit is a `Command` object
  (`do`/`undo`) on the model, so undo/redo works the same for every edit and
  can be tested without Qt.

```
          ┌──────────┐      ┌──────────┐
          │   GUI    │      │   CLI    │
          │ (PySide6)│      │ (argparse│
          └────┬─────┘      └────┬─────┘
               │  commands        │
          ┌────▼──────────────────▼────┐
          │ core: Project model, Undo  │
          └────┬──────────────┬────────┘
       ┌───────▼──┐     ┌─────▼──────┐
       │  layout  │     │   styles   │
       └───────┬──┘     └─────┬──────┘
          ┌────▼──────────────▼────┐
          │ render + export        │
          │ (Pillow, PDF)          │
          └────────────────────────┘
```

## 2. Tooling

| Purpose | Tool |
|---|---|
| Packaging / deps | `pyproject.toml`, `uv` (or pip + venv) |
| Lint / format | `ruff` (lint + format) |
| Types | `mypy --strict` on `core`, `layout`, `styles`, `render` |
| Tests | `pytest`, `pytest-cov`, `pytest-qt`, `hypothesis`, `pytest-xdist` |
| Image compare | own helper: per-pixel diff with tolerance + SSIM (`scikit-image`) |
| PDF | `reportlab` (write), `pypdf` (read back in tests) |
| CI | GitHub Actions, matrix `ubuntu-latest` + `windows-latest`, Python 3.12/3.13 |
| Pre-commit | ruff, mypy, end-of-file/whitespace hooks |

## 3. Package layout

```
src/collagio/
  core/
    model.py         # Project, Canvas, PhotoItem, StyleRef, Background (dataclasses)
    serialize.py     # JSON load/save + schema version + migration
    commands.py      # Command base, MoveItem, Rotate, Resize, Swap, SetStyle, ...
    undo.py          # UndoStack
    units.py         # mm <-> px <-> pt, DPI, paper presets
    rng.py           # seeded RNG helpers
  imaging/
    loader.py        # open, EXIF orientation, format support, HEIC optional
    cache.py         # thumbnail + preview cache (disk + LRU memory)
    smartcrop.py     # centre / saliency / face-aware crop rect
  layout/
    base.py          # LayoutGenerator protocol
    grid.py          # mixed-size grid (row/col spans)
    scattered.py     # rotated + overlapping placement
  styles/
    base.py          # Style protocol, registry, common params
    plain.py  stamp.py  cutout.py  torn.py  polaroid.py  tape.py  filmstrip.py
    textures/        # paper noise, fibre masks (generated, not stock images)
  render/
    renderer.py      # model -> PIL.Image at given scale
    background.py    # solid, gradient, texture, blurred photo
    text.py          # text/title elements
    export.py        # PNG, JPEG, PDF (bleed, crop marks)
  cli/
    main.py          # `collagio` entry point
  app/
    main_window.py   # menus, toolbars, panels
    canvas_view.py   # QGraphicsView editor, handles
    items.py         # QGraphicsItem per PhotoItem
    panels/          # photo list, layout panel, style panel, canvas panel
    workers.py       # background export / thumbnail jobs (QThreadPool)
    settings.py
  i18n/              # *.ts / *.qm (en, de)
tests/
  unit/  integration/  golden/  gui/  cli/  fixtures/
packaging/
  pyinstaller.spec  windows/installer.iss  linux/AppImageBuilder.yml  linux/flatpak.yml
```

## 4. Phases

Each phase ends with a usable state, green CI and the coverage gates from
section 6.

### Phase 0 – Project setup (≈2 days) – ✅ done

The Flatpak + PySide6 packaging spike from the risk table is deferred until
PySide6 is added (Phase 4).
- Repo, `pyproject.toml`, `src/` layout, ruff, mypy, pre-commit
- GitHub Actions: lint + type check + tests on Linux and Windows
- Test fixtures: generator script for synthetic test photos (coloured
  gradients with numbers, various aspect ratios, one with EXIF rotation,
  one PNG with alpha, one large 6000×4000)
- `tests/helpers/image_compare.py` (tolerance diff + SSIM, writes diff images on failure)

**Tests:** smoke test that the package imports; image-compare helper tested itself.

### Phase 1 – Core model, import, grid layout, export, CLI (M1, ≈2 weeks) – ✅ done
1. `core/model.py`, `core/units.py`, `core/rng.py`
2. `core/serialize.py` with `schema_version: 1`
3. `imaging/loader.py` (EXIF orientation, JPEG/PNG/WebP/TIFF), `imaging/cache.py`
4. `imaging/smartcrop.py` (centre crop first; saliency later)
5. `layout/grid.py` – algorithm:
   - choose rows/cols for N on canvas aspect ratio
   - assign spans (1×1, 2×1, 1×2, 2×2) seeded, prefer spans matching photo aspect
   - fill with no gaps, verify full coverage
6. `styles/plain.py` + style registry
7. `render/renderer.py`, `render/background.py` (solid, gradient)
8. `render/export.py` – PNG, JPEG
9. `cli/main.py` – `--input`, `--mode grid`, `--size`, `--dpi`, `--seed`, `--output`, `--project`

**Tests**
- *unit*: unit conversion (A4 @300 DPI = 2480×3508), model defaults,
  serialisation round-trip, loader orientation for all 8 EXIF values,
  cache hit/miss/eviction, smartcrop keeps the requested aspect ratio.
- *property-based (hypothesis)* for `grid`: for any N in 2–100, any canvas
  ratio and any seed –
  - exactly N cells, one per photo
  - no two cells overlap
  - all cells inside the canvas (respecting margin) and no empty holes
  - gap between neighbours equals the configured gap (±1 px)
  - same seed → same layout; different seed → different layout (for N ≥ 4)
- *golden*: grid with 3, 7, 20 photos, plain style, fixed seed.
- *cli*: run against fixture folder → file exists, correct size, exit code 0;
  bad input → non-zero exit and readable error.

### Phase 2 – Scattered mode (M2, ≈1 week) – ✅ done
1. `layout/scattered.py` – Poisson-disc-like placement of centres, seeded
   rotation in ±max angle, size variation, overlap target controls spacing;
   ensures every photo is at least X % visible
2. Shadows in renderer (Gaussian blur on alpha, offset)
3. Z-order in model

**Tests**
- *property-based*: all N photos placed; rotation within ±max; centres inside
  canvas; each photo's visible (non-covered) area ≥ configured minimum
  (computed with `shapely` polygons); determinism by seed.
- *unit*: shadow offset/blur parameters change the alpha mask as expected.
- *golden*: scattered with 5 and 25 photos.

### Phase 3 – Styles (M3, ≈2–3 weeks) – ✅ done
Style protocol: `render(img: Image, params: StyleParams, rng: Random, scale: float) -> StyledResult(image RGBA, shadow_mask, content_rect)`.
`scale` keeps edge details the same physical size in preview and export.

Order: postage stamp → cut-out → torn → Polaroid → tape/corners → film strip.

- **Stamp:** border + perforation of semicircles along edges, spacing computed
  so holes fit evenly per side; paper noise texture.
- **Cut-out:** polygon outline with small random offsets per segment (seeded),
  white border, slightly rotated cut line.
- **Torn:** fractal (midpoint displacement) edge per side + fibre layer
  (lighter, noisy band outside the edge); configurable sides and roughness.
- **Polaroid:** fixed proportions, caption with bundled open font.
- **Tape/corners:** semi-transparent tape quads with jagged ends, or corner triangles.
- **Film strip:** dark frame with sprocket holes; single photo per frame.
- Per-photo style override in model + global default.

**Tests**
- *unit per style*:
  - output is RGBA, size = input + border according to params
  - content area contains the photo unchanged (sample pixels)
  - stamp: number of holes per side as computed; holes are fully transparent
  - torn/cut-out: edge differs from straight line by > 0 and ≤ roughness
  - scale invariance: render at scale 1 and 4, downsample → SSIM ≥ 0.95
  - determinism: same seed → identical bytes
- *registry*: every registered style has defaults, a German/English label,
  and renders a 1×1 and a 6000×4000 image without error (parametrised test
  over all styles – new styles are automatically covered).
- *golden*: one image per style × mode (7 × 2 = 14), plus a mixed per-photo-style collage.

### Phase 4 – GUI editor (M4, ≈3 weeks) – ✅ done
1. Main window: photo list (thumbnails), mode/style/canvas panels, preview canvas
2. `canvas_view.py`: `QGraphicsScene` showing preview-scale renders; selection,
   move, resize/rotate handles, pan/zoom-in-frame (grid mode)
3. All edits via `core/commands.py` → `UndoStack` (bridged to `QUndoStack` or own)
4. Drag & drop import; drag-to-swap in grid (uses the existing `SwapPhotos` command)
5. Save/Open project, recent files, autosave
6. Background workers for thumbnails and export, with progress and cancel

**Tests**
- *unit (no Qt)*: each command `do → undo` restores the model exactly
  (compare serialised JSON); `do → undo → redo` equals `do`; undo stack limits
  and merge of consecutive moves.
- *hypothesis stateful test*: random sequence of commands, then undo all →
  model equals initial model.
- *gui (pytest-qt, offscreen)*:
  - app starts, imports fixture folder, preview shows N items
  - drag item → model position changed; Ctrl+Z → restored
  - change style in panel → model updated, item re-rendered
  - save → reopen → identical model
  - export dialog runs worker and produces file (with `qtbot.waitSignal`)
- Run with `QT_QPA_PLATFORM=offscreen` on Linux CI; Windows runs natively.

### Phase 5 – Print & PDF (M5, ≈1 week) – ✅ done
- Canvas in mm with DPI; paper presets; orientation
- PDF export via reportlab: page size = canvas + 2 × bleed, image placed at
  full res, optional crop marks outside trim box; set TrimBox/BleedBox
- Texture backgrounds, blurred-photo background, text elements

**Tests**
- *unit*: bleed geometry (A4 + 3 mm bleed = 216 × 303 mm), crop mark positions.
- *integration*: read PDF back with `pypdf` – page count 1, MediaBox/TrimBox/
  BleedBox values correct, embedded image has expected pixel size for DPI.
- *golden*: rasterised PDF (via `pypdfium2`) compared to PNG export of the same
  project.

### Phase 6 – Localisation, packaging, release (M6, ≈1–2 weeks) – ✅ done (release pending)
- All UI strings via `self.tr()`; `pyside6-lupdate` → `de.ts`; translate; `.qm` built in CI
- PyInstaller one-folder build; Inno Setup installer for Windows
- AppImage (appimage-builder) and Flatpak manifest (KDE runtime with PySide6)
- App icon, `.desktop` file, file association for `.collagio`
- Release workflow: tag → build artefacts → GitHub Release

**Tests**
- *i18n*: test that every `tr()` source string has a German translation
  (parse `.ts`, fail on `type="unfinished"`); app starts with `LANG=de_DE`.
- *packaging smoke test in CI*: start the built binary with `--version` and
  run the CLI on fixtures (Linux AppImage + Windows exe).
- Manual test checklist (`docs/manual-test.md`) for installers on clean
  Windows 11 and Ubuntu 24.04 VMs.

## 5. Test strategy summary

| Level | What | Tooling | Runs |
|---|---|---|---|
| Unit | model, units, serialize, loader, cache, commands, each style | pytest | every push |
| Property-based | layout invariants, undo/redo sequences | hypothesis | every push (more examples nightly) |
| Golden image | full collages per mode × style, PDF raster | own compare helper + SSIM | every push |
| Integration | renderer + export + PDF read-back, CLI end-to-end | pytest, pypdf, subprocess | every push |
| GUI | main flows in the editor | pytest-qt, offscreen | every push |
| Performance | 100 × 24 MP import + preview render time; export A3@300 DPI time and peak memory | pytest-benchmark, tracemalloc | nightly |
| Packaging smoke | built exe/AppImage start + CLI run | CI job | release tags |
| Manual | installers, look & feel of styles | checklist | before release |

**Golden images**
- Stored in `tests/golden/expected/*.png` at small size (e.g. 800 px) to keep repo small.
- Compared with tolerance (max channel diff ≤ 2, SSIM ≥ 0.99) to absorb
  Pillow/platform differences between Linux and Windows.
- `pytest --update-golden` regenerates them; diffs are written to
  `tests/golden/_diff/` and uploaded as CI artefacts on failure.

**Performance budgets** (nightly, fail if exceeded by > 20 %)
- Import 100 × 24 MP photos with thumbnail generation: < 30 s cold, < 2 s warm cache
- Preview re-render after one edit: < 100 ms
- Export A3 @ 300 DPI (4961 × 7016) with 50 photos: < 15 s, peak RAM < 2 GB

## 6. Coverage targets

Measured with `pytest-cov` (branch coverage), enforced in CI via `--cov-fail-under`
per package (separate `coverage` report per path).

| Package | Line + branch coverage gate |
|---|---|
| `core` | ≥ 95 % |
| `layout` | ≥ 95 % |
| `styles` | ≥ 90 % |
| `render` (incl. export) | ≥ 90 % |
| `imaging` | ≥ 85 % |
| `cli` | ≥ 85 % |
| `app` (GUI) | ≥ 60 % (main flows covered; widgets layout code excluded) |
| **Overall** | **≥ 85 %** |

Rules:
- New code in a PR may not lower coverage (diff-coverage ≥ 90 % via `diff-cover`).
- Every bug fix comes with a regression test.
- `# pragma: no cover` only for platform-specific branches tested elsewhere,
  with a comment explaining why.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Memory with 100 large photos | Never keep full-res in memory during editing; load full-res per photo only during export, streaming into the canvas |
| Golden images differ between Windows/Linux | Tolerant comparison; same Pillow version pinned; bundled fonts only |
| Flatpak + PySide6 packaging friction | Use KDE runtime's PySide6 or pip-install in build; prototype early in Phase 0 as a spike |
| Grid algorithm produces ugly layouts for some N | Score layouts (aspect fit, size variety) and pick best of K seeded candidates; visual review set of N = 2..30 |
| Style edges look "computer-generated" | Layered noise + fibre textures; tune with reference images; parameters exposed |

## 8. Timeline (one developer, rough)

| Phase | Duration | Cumulative |
|---|---|---|
| 0 Setup | 2 days | 0.5 wk |
| 1 Core + grid + CLI | 2 wk | 2.5 wk |
| 2 Scattered | 1 wk | 3.5 wk |
| 3 Styles | 2–3 wk | 6.5 wk |
| 4 GUI editor | 3 wk | 9.5 wk |
| 5 Print/PDF | 1 wk | 10.5 wk |
| 6 i18n + packaging | 1–2 wk | ~12 wk |

## 9. Definition of done (per phase)

- Features of the phase work via CLI (and GUI from Phase 4)
- CI green on Linux and Windows
- Coverage gates met
- Golden images reviewed and committed
- `CHANGELOG.md` updated
