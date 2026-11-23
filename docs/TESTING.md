# Testing

| Suite | Command | Notes |
|---|---|---|
| Everything | `python tools/manage.py qa` (option 4) | Runs both suites with an isolated, temporary `BOOK_BUILDER_HOME`. Results are kept per source revision in `~/.book-builder/qa/`. A revision that already passed isn't re-run unless you pass `--force`. `--zip` exports a QA review ZIP. |
| Python | `python -m unittest discover -s tests` | Build, chapters, games, Book Builder, git scenarios, management system, module registry |
| Website | `cd site && npx vitest run` | Game engine. Reported as *unavailable* (never "passed") if `site/node_modules` is missing. |

## What the management tests cover

These are in `tests/test_bbmanage.py` and `tests/test_modules.py`. They run on a throwaway copy of the app in a folder whose name contains spaces.

- Source revision is deterministic, changes with code, and doesn't change with chapters.
- Source and data sets never overlap.
- Source backup and restore:
  - removes files added later
  - leaves chapters untouched
  - refuses damaged archives and data backups
- Book-data backup and restore leave the source untouched. Private sources need opt-in.
- Update packages:
  - a valid package applies exactly (add, replace, delete), with backups kept
  - stale, wrong-project and wrong-type packages are rejected
  - modified, missing and undeclared payloads are rejected
  - paths outside the source, `..` traversal and symlinks are rejected
  - an original-hash mismatch is rejected
  - a simulated mid-apply failure rolls back
  - backups and QA reviews can't be installed as updates
- The AI handoff excludes manuscripts and round-trips into a valid one-file package.
- CLI: `status`, `revision`, and stale-update refusal through `manage.py`.
- Windows launcher: CRLF line endings, quoted paths (structure only).
- Every source file has exactly one module owner. Feature routes register without importing `webapp`.

## Not tested here

- **Windows:** `BookBuilder_Manager.cmd` and the Windows clipboard and open helpers have not been run on Windows. Only the launcher file's structure is checked automatically.
- **Real package downloads:** `install` with real pip downloads, and launch with a real browser, were checked by hand on macOS only.
