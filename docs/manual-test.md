# Manual release test

Automated tests cover the logic, rendering and editor; CI smoke-tests every package.
Before publishing a release, check what only a person can judge, on a clean
**Windows 11** and **Ubuntu 24.04** machine (VMs are fine).

## Install

- [ ] Windows: run `Collagio-X.Y.Z-setup.exe` (per user, no admin prompt). Start menu entry
      and, if chosen, desktop icon exist; the app icon shows in the taskbar.
- [ ] Windows: double-clicking a `.collagio` file opens it in Collagio.
- [ ] Linux AppImage: `chmod +x` and start it; icon and title look right.
- [ ] Linux Flatpak: `flatpak install --user Collagio-X.Y.Z-x86_64.flatpak`, start from the
      application menu.
- [ ] Uninstall (Windows "Apps", `flatpak uninstall`) leaves no Start menu entry or association.

## Use

- [ ] Add a folder with ~30 real photos (incl. portrait photos from a phone with EXIF
      rotation, a HEIC/PNG if available): thumbnails and canvas appear within seconds.
- [ ] Grid: shuffle a few times, swap two photos by dragging, pan and zoom a crop (Alt+drag,
      Ctrl+wheel). Undo/redo every step.
- [ ] Scattered: rotate (Shift snaps) and resize with the handles; bring to front/back.
- [ ] Try every style; polaroid with a caption; per-photo styles on two photos.
- [ ] Backgrounds: texture, blurred photo; add a title with shadow and drag it.
- [ ] Save, close, reopen: everything identical. Move the folder with project and photos:
      still opens.
- [ ] Kill the app with unsaved changes, restart, *File > Recover unsaved work*.
- [ ] Export JPEG and A4 PDF with 3 mm bleed and crop marks; open the PDF in a viewer and
      check size (210 × 297 mm trim), marks, sharpness of photos at 300 DPI.
- [ ] *View > Language > Deutsch*, restart: everything in German.
- [ ] High-DPI screen (150 %/200 % scaling): handles and text are crisp and usable.
