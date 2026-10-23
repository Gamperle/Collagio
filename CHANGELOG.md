# Changelog

## Unreleased

- Contributing guide (`CONTRIBUTING.md`) with the feature-branch workflow
- Fixed: a continuous Ctrl+wheel zoom of a crop is now one undo step instead of one per notch (#9)
- Fixed: photo list icons are refreshed when a photo is changed on disk (#5)
- Fixed: the thumbnail disk cache is kept under 500 MB (least recently used previews are removed at start-up); *View > Clear thumbnail cache* empties it (#6)
- Fixed: opening a project with many missing photos shows one summary message instead of one per photo; missing photos are shown as placeholders (#4)

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
