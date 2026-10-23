# Changelog

## Unreleased

- Fixed: the film strip's sprocket holes are drawn smoothly and evenly at any size, and
  rotated photos (scattered layout) have anti-aliased edges in every style

## 0.1.1 – 2026-10-23

Bug fixes, mostly in the editor.

**Fixed**

- Changing the style for all photos keeps manual moves, rotations, swaps and crops; only an
  automatic layout is laid out again (#1)
- *Apply layout* and *Shuffle* ask before replacing photos moved, rotated, swapped or
  cropped by hand, with "Don't ask again" (#2)
- Several editor windows no longer overwrite each other's autosave; *Recover unsaved work*
  lets you choose between sessions, and copies older than 30 days are removed (#3)
- Opening a project with many missing photos shows one summary message instead of one per
  photo; missing photos are shown as placeholders (#4)
- Photo list icons are refreshed when a photo is changed on disk (#5)
- The thumbnail disk cache is kept under 500 MB; *View > Clear thumbnail cache* empties
  it (#6)
- Error messages from the core are shown in the interface language (#7)
- The film strip's automatic orientation follows the photo, so square and nearly square
  photos are no longer cropped (#8)
- A continuous Ctrl+wheel zoom of a crop is one undo step instead of one per notch (#9)
- German: a gradient background is called "Farbverlauf"
- `packaging/linux/build-appimage.sh` works without arguments and without FUSE

**Documentation**

- README with a feature overview, example gallery and editor screenshot
- Contributing guide (`CONTRIBUTING.md`) with the feature-branch workflow

## 0.1.0 – 2026-10-23

First release.

- Collages from 2–100 photos: grid with mixed cell sizes (placement by shape, random or
  photo order) and scattered layout with rotation, overlap and guaranteed visibility
- Seven photo styles, also per photo: plain, postage stamp, scissor cut-out, torn paper,
  Polaroid, tape / photo corners, film strip; drop shadows
- Backgrounds: colour, gradient, paper/cork/wood textures, blurred photo; titles and captions
- Desktop editor: move, swap, resize, rotate and crop photos with undo/redo, live preview,
  autosave and recovery, English and German
- Export to PNG, JPEG and print-ready PDF with bleed and crop marks
- Command line (`collagio`) for scripted and batch use
- Windows installer and portable zip, Linux AppImage, Flatpak and portable archive
