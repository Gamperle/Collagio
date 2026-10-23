# Task: Collagio – Desktop Collage Creator

Status: **Specified – ready for implementation planning**
Created: 2026-10-23

## 1. Goal

Build a cross-platform desktop application (Windows and Linux) that creates photo
collages from a user-selected set of 2–100 photos. The user picks photos,
chooses a layout mode and visual styles, auto-generates a layout, refines it
manually, and exports a finished image or print-ready PDF.

## 2. Tech stack & platforms

- **Language/UI:** Python 3.12+ with PySide6 (Qt 6)
- **Imaging:** Pillow (+ NumPy / OpenCV where useful for masks, edge effects, smart crop)
- **Canvas/editing:** Qt `QGraphicsScene` / `QGraphicsView` for the interactive editor
- **Platforms:** Windows 10/11 x64, Linux x64 (Ubuntu/Debian, Fedora, Arch)
- **Distribution:**
  - Windows: `.exe` installer (PyInstaller + Inno Setup or NSIS)
  - Linux: AppImage and Flatpak
- One shared codebase; renderer is shared between the GUI and the CLI

## 3. Core workflow

1. **Import photos** – file picker, drag & drop, or a whole folder
   - Formats: JPEG, PNG, WebP, TIFF (HEIC optional via `pillow-heif`)
   - Respect EXIF orientation
   - 2–100 photos per collage; thumbnail/preview cache for fast editing
2. **Choose layout mode** (section 4)
3. **Choose style** (section 5) – globally, or **per photo**
4. **Auto-generate** layout, with "shuffle/regenerate" (seeded)
5. **Edit manually** – drag, resize, rotate, swap, crop/pan inside frame,
   z-order, change style per photo; full **undo/redo**
6. **Export** (section 6)
7. **Save / load project** (JSON project file referencing originals + all
   parameters + seed)

## 4. Layout modes

### 4.1 Grid layout with different image sizes
- Mosaic grid where cells span multiple rows/columns (e.g. one large hero
  photo + several small ones)
- Automatic layout generation for N photos, taking photo aspect ratios into account
- Adjustable gap, outer margin, corner radius
- Smart cropping (keep image centre / faces visible), manual pan/zoom per cell
- Photo placement order: by shape (least cropping, default), random (seeded) or input order
- Swap photos by drag & drop (CLI: `--swap A,B`); manually merge/split cells

### 4.2 Rotated and overlapping images ("scattered" mode)
- Photos placed with random rotation (configurable max angle, e.g. ±15°)
  and partial overlap
- Configurable density / overlap amount and size variation
- Free manual positioning, rotation and scaling via handles
- Z-order: bring to front / send to back
- Drop shadows for depth

## 5. Styles

Styles are per-photo treatments, combinable with both layout modes. A global
default style can be set; individual photos can override it.

| Style | Description |
|---|---|
| **Plain** | Photo as-is, optional border |
| **Postage stamp** | Perforated scalloped edge, white stamp border, optional value/text, subtle paper texture |
| **Cut-out (scissor cut)** | Slightly irregular, hand-cut edge, white paper border, shadow. Purely graphical – no background removal |
| **Ripped / torn paper** | Torn, fibrous paper edges on each photo (configurable sides and roughness) |
| **Polaroid** | White frame with thicker bottom edge, optional caption text |
| **Tape / pinned corners** | Semi-transparent tape strips or photo corners holding the photo |
| **Film strip** | Photo(s) in a film strip frame with sprocket holes |

Common style parameters: border width/colour, shadow strength/offset, edge
roughness, random seed (reproducible edges). Styles are implemented as a plugin-
like interface (`Style.render(image, params, seed) -> RGBA image + shadow`), so new
styles can be added easily.

## 6. Canvas & output

- **Canvas size:** pixel presets (Instagram square/portrait, Full HD/4K wallpaper),
  print presets in mm (A4, A3, 10×15, 13×18, 20×30, portrait/landscape), custom px or mm
- **DPI** setting for print (default 300)
- **Background:** solid colour, gradient, texture (paper, cork, wood), blurred photo
- Optional text/title elements
- **Export formats:**
  - PNG, JPEG (quality setting)
  - **PDF** with optional **bleed** margin (e.g. 3 mm) and crop marks for print shops
- Preview renders at low resolution; final export renders at full resolution
  in a background thread with progress bar

## 7. CLI / batch mode

Same renderer, no GUI. Example:

```
collagio --input ./photos --mode grid --style polaroid \
             --size A4 --dpi 300 --seed 42 --output collage.pdf
collagio --project my.collagio.json --output out.png
```

- Input: folder, file list, or saved project
- All layout/style/canvas options available as flags

## 8. Localisation

- UI languages: **English** and **German** (Qt translation files `.ts/.qm`)
- Language follows system locale, overridable in settings

## 9. Non-functional requirements

- Smooth editing with 100 photos of 24 MP (thumbnail cache, lazy full-res loading)
- Non-destructive: originals are never modified
- Deterministic rendering: same project + seed = same output
- Undo/redo for all edit operations
- Unit tests for layout algorithms and style renderers; golden-image tests for
  rendering; CI builds for Windows and Linux

## 10. Proposed project structure

```
collagio/
  app/          # PySide6 GUI (main window, editor view, panels)
  core/         # project model, undo stack, serialization
  layout/       # grid + scattered layout generators
  styles/       # style plugins (stamp, cutout, torn, polaroid, tape, film)
  render/       # renderer (preview + full-res), export (PNG/JPEG/PDF)
  cli/          # command-line entry point
  i18n/         # translations (en, de)
  assets/       # textures, fonts, icons
tests/
packaging/      # PyInstaller spec, Inno Setup script, AppImage/Flatpak manifests
```

## 11. Milestones

1. **M1 – Core:** project model, image import, grid layout, plain style, PNG/JPEG export, CLI
2. **M2 – Scattered mode:** rotation/overlap, shadows, z-order
3. **M3 – Styles:** postage stamp, cut-out, torn paper, then Polaroid, tape, film strip; per-photo styles
4. **M4 – Editor:** manual drag/resize/rotate/crop, swap, undo/redo, save/load project
5. **M5 – Print:** mm/DPI canvas, PDF export with bleed and crop marks
6. **M6 – Polish & ship:** German translation, installers (exe, AppImage, Flatpak), CI

## 12. Acceptance criteria

- [ ] Installable and runnable on Windows 11 (exe installer) and Ubuntu 24.04 (AppImage + Flatpak)
- [ ] Import 2–100 photos; editor stays responsive with 100 × 24 MP photos
- [ ] Grid collage with mixed cell sizes generated automatically and editable
- [ ] Scattered collage with rotation and overlap generated automatically and editable
- [ ] All 7 styles render correctly in both modes; styles can be set per photo
- [ ] Export PNG, JPEG, and PDF (with bleed) at chosen size/DPI
- [ ] CLI produces the same output as the GUI for the same project + seed
- [ ] Project save/reopen yields an identical result
- [ ] UI available in English and German

## 13. Project decisions

- **Name:** **Collagio** (package/CLI name `collagio`, project file `*.collagio.json`).
  Needs an app icon (SVG + PNG/ICO sizes).
- **Licence:** open source – **GPL-3.0-or-later** (compatible with PySide6's LGPL)
- **Output:** PNG, JPEG and PDF (with bleed) all in scope

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the implementation plan
and test strategy.
