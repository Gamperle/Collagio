# Contributing to Collagio

Thanks for helping! Bug reports, fixes, features and translations are all welcome.
Look for issues labelled `good first issue` or `help wanted` if you want a place to start.

## Development setup

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Gamperle/Collagio.git
cd Collagio
uv sync                     # core, GUI and development dependencies
uv run pre-commit install   # ruff, ruff format and mypy before every commit
uv run collagio-gui         # start the editor
uv run collagio --help      # command line
```

On Linux the Qt tests need a few system libraries
(`libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`). The tests always run
Qt with `QT_QPA_PLATFORM=offscreen`, so no windows open.

## Workflow: feature branches

`main` is always releasable. Every change – bug fix, feature, documentation – is made
on its own short-lived branch and merged back into `main`; nobody commits to `main`
directly.

1. **Start from an issue.** Open one first for anything bigger than a typo, so the
   approach can be discussed before you write code.
2. **Create a branch** from an up-to-date `main`:

   ```bash
   git switch main
   git pull
   git switch -c fix/9-merge-crop-zoom-undo
   ```

   Name it `<type>/<issue number>-<short-description>`, with the type being
   `fix` (bug), `feature` (enhancement), `docs`, `refactor`, `test`, `build` or `ci`.
   Leave the number out when there is no issue.
3. **Commit in small, logical steps.** Write the subject line in the imperative
   ("Merge consecutive crop zooms into one undo step"), at most ~70 characters, and
   explain *why* in the body when it isn't obvious. Reference the issue in the last
   commit or the pull request with `Fixes #9` (bugs) or `Closes #12` (features) so it
   is closed on merge.
4. **Every fix comes with a test** that fails without it; every feature with tests
   for its behaviour. User-visible changes get a line in [CHANGELOG.md](CHANGELOG.md)
   under *Unreleased*.
5. **Check locally** before pushing (the same checks CI runs):

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy
   uv run pytest -n auto
   ```

6. **Keep the branch current.** If `main` moved on, rebase onto it
   (`git fetch && git rebase origin/main`) rather than merging `main` into your branch.
7. **Open a pull request** against `main`. Describe what changed and how you tested
   it; add screenshots for visible editor changes. CI must be green (lint, mypy and
   tests on Linux and Windows with Python 3.12 and 3.13, plus the coverage gates).
8. **Merge** with a merge commit (`git merge --no-ff`) once the review is done, so each
   branch stays visible as one unit in the history, then delete the branch.

## Tests

```bash
uv run pytest -n auto                    # everything (unit, golden, CLI, GUI)
uv run pytest tests/unit                 # one area
uv run pytest -n auto --cov              # with coverage
uv run python scripts/coverage_gates.py  # per-package minimums (after --cov)
```

- `tests/unit` – core, layout, styles, rendering; `tests/cli` – the command line;
  `tests/gui` – the editor with pytest-qt; `tests/golden` – rendered images compared
  with references in `tests/golden/expected`.
- Test photos are generated (`tests/fixtures/generate.py`); don't commit real photos.
- **Golden images:** when a rendering change is intended, regenerate the references
  with `uv run pytest tests/golden --update-golden`, look at every changed PNG and
  commit them together with the change. Failing comparisons write diff images to
  `tests/golden/_diff/` (CI uploads them as an artifact).
- Core packages need 95 % coverage, styles and rendering 90 %, the GUI 60 %
  (see `scripts/coverage_gates.py`).

## Code style

- ruff (lint and format, line length 100) and `mypy --strict` must pass.
- The core (`collagio.core`, `layout`, `styles`, `render`, `imaging`) must not import Qt;
  the editor in `collagio.app` only translates user actions into `Document` calls.
- Every edit of a project goes through an undoable command.
- Errors shown to users derive from `CollagioError` and are raised with a literal English
  template and keyword arguments, e.g.
  `ImageLoadError("photo not found: {path}", path=path)`, never with an f-string: the
  editor translates the template. List new templates in `src/collagio/app/strings.py`
  (a test checks this).

## Translations

The interface is English with a German translation; more languages are very welcome
(French, Italian, Spanish, …).

Texts in the editor are marked with `self.tr(...)`, `QCoreApplication.translate(...)`
or, for texts that come from the core (undo labels, style parameters, textures), listed
in `src/collagio/app/strings.py`. After changing interface texts:

```bash
uv run python scripts/translations.py update    # refresh the .ts files from the code
uv run pyside6-linguist src/collagio/i18n/collagio_de.ts   # translate the new texts
uv run python scripts/translations.py release   # compile .ts to .qm
```

Commit both the `.ts` and the `.qm` file. `tests/gui/test_i18n.py` fails if a text is
untranslated or unfinished, if placeholders (`{}`) or `&` shortcuts don't match, or if
the files are out of date.

**Adding a language** (e.g. French):

1. Create the file: `uv run pyside6-lupdate src/collagio/app/*.py -ts src/collagio/i18n/collagio_fr.ts -no-obsolete -locations none`.
2. Add the language to `LANGUAGES` in `src/collagio/app/i18n.py`
   (`"fr": "Français"`, in its own language).
3. Translate every text in Qt Linguist, mark them as finished, then run
   `scripts/translations.py release`.
4. Run `uv run pytest tests/gui/test_i18n.py` and try the editor with
   `COLLAGIO_LANG=fr uv run collagio-gui`.

## Reporting bugs

Please include the Collagio version (*Help > About*), the operating system, what you
did, what you expected and what happened. A project file (`.collagio`) or a command
line that shows the problem helps a lot.

## Licence

Collagio is licensed under the GPL-3.0-or-later. By contributing you agree that your
contribution is published under the same licence.
