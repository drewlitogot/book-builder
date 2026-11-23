# Book Builder: modular architecture

## Assessment (2026-11-22)

- **Stack:**
  - Python 3.10+ standard library HTTP server (`tools/webapp.py`)
  - a single-page browser UI (`tools/web/index.html`, `tools/web/builder.js`, Lucide icon sprite)
  - Pandoc + Typst for book builds
  - Astro (Node) for the public website
  - Python packages: PyYAML, jsonschema, segno, Pillow
- **No database:**
  - Books are plain files: `book.yml`, Markdown chapters, YAML/JSON registries.
  - App data is JSON in `BOOK_BUILDER_HOME` (default `~/.book-builder`).
  - So "database snapshot" means a hashed file copy, and there are no migrations.
- **Startup commands:**
  - `tools/manage.py launch` (or `run/Book Manager.command`)
  - `python tools/webapp.py [--port N] [--no-open]`
  - CLIs: `tools/chapter.py`, `tools/build.py`, `tools/website.py`, `tools/games.py`
- **Source vs data:**
  - Each book lives in its own folder (`BOOK_PROJECT`); `tools/bbmanage/paths.py` defines exactly which files are app source and which are book data, and every management operation is limited to one set.
- **Oversized files:**
  - `games.py` (1,250 lines), `webapp.py` (≈790), `website.py` (≈735), `chapter.py` (≈660)
  - `tools/web/index.html` (UI)
  - These are split by responsibility where coupling hurt (see below). The rest stays intact so working features aren't destabilised.
- **Tests:**
  - Python `unittest` in `tests/` (about 125 tests)
  - Vitest in `site/tests/`
  - Run both with `tools/manage.py qa`.
- **Backups before this work:** git history only. Now there are source and data backups, update packages with rollback, and QA history (see BACKUP_AND_RECOVERY.md).

## Composition

`tools/routes.py` is the composition layer. Feature modules register HTTP handlers with `@routes.get` and `@routes.post`, and `routes.FEATURES` lists which modules the server loads.

- Feature modules never import `webapp` (it runs as `__main__`).
- The few helpers they need arrive through `routes.ctx`, which keeps imports one-directional.
- Extracted so far:
  - `api_library.py` (Library, projects, settings, dashboards, fonts, brand)
  - `api_git.py` (Save Work)
  - `bookmeta.py` (book.yml metadata)
  - `platformio.py` (clipboard and opening files on macOS, Windows and Linux)
- The remaining routes in `webapp.dispatch` (chapters, prompts, workspace, games, website) work unchanged. They can move into their own feature modules one at a time, with the same pattern.

## Modules

`MODULES.json` is the machine-readable registry. It records each module's files, public interfaces, dependencies, tests, data ownership and guidance for AI work. `tests/test_modules.py` checks that every source file has exactly one owner, and that feature modules don't import `webapp`.

| Module | Owns | Depends on |
|---|---|---|
| core | webapp, routes, jobs, platformio | — |
| library | registry, bookmeta, api_library, insights | core, content |
| content | chapter, menu, special, addboxes | — |
| ai-writing | promptpack, packs, workspace, bundle | content |
| design | fonts, bib, assets/typst, filters, csl, css, fonts | core |
| publication | build, website, gitstatus, api_git, site/ | content, design |
| interactive | games, web/runtime, docs/game-developer | content |
| web-ui | web/index.html, builder.js, icons | everything it shows |
| app-management | manage.py, bbmanage/, launchers, run/ | — (standard library only) |
| docs | README, START_HERE, CHANGELOG, docs | — |

## Rules for module work

1. Change only your module's files (MODULES.json). If you need another module's behaviour, use its public interface. If that isn't enough, say so in your package description rather than editing it.
2. New HTTP endpoints go in a feature module listed in `routes.FEATURES`, not in `webapp.dispatch`.
3. App UI colors are locked (the current palette, see `docs/upgrade-audit/baseline.md`). Book brands style book outputs only.
4. Each module's tests live in the files listed for it; add tests with every change.
5. Return work as an update package (UPDATE_PACKAGE_CONTRACT.md) built on the exact source revision you were given.
