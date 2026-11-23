# Book Builder

Book Builder is a local app for planning, writing, checking, building and publishing books. You
write with the help of ChatGPT or Claude, and the app keeps the outline, research, drafts, reviews
and approvals organised. It runs only on your computer, in your browser, at http://127.0.0.1:8765.

A small **Sample Book** ships in this folder so every screen has something to show. Create your own
books from the Library; each book lives in its own folder.

## What it does

- **Library:** create, import, export and switch between book projects.
- **Writing:** a content outline, chapter files with statuses (planned, draft, approved), copy-ready
  prompts and ZIP handoffs for ChatGPT and Claude, and reply import with checks.
  Approved chapters are never rewritten by the tools.
- **Research Library:** import PDFs, Word, Excel, PowerPoint and EPUB files and search them locally.
- **Design:** Brand Studio (colours, fonts, logo, cover) and Image Studio (planning, alt text,
  licences, approval).
- **Builds:** PDF (Typst), EPUB, DOCX and HTML through Pandoc, with APA citations from
  `references.bib`.
- **Website:** a reader website (Astro) built from approved chapters only. You can publish it to
  GitHub Pages, or download it as a ZIP with a hosting guide. Publishing always asks first.
- **Interactive activities:** import and review game packages that follow the Game Package API
  (`docs/game-developer`).
- **Send to Kindle:** optional, off until you turn it on.
- **Manager:** install, launch, ZIP updates, backups, QA runs and diagnostics (`tools/manage.py`).

## Requirements

- Python 3.10 or newer
- [Pandoc](https://pandoc.org) and [Typst](https://typst.app) to build books
- Node.js to build the reader website
- Git, optionally, for Save Work and publishing

## Start

| System | Run |
|---|---|
| macOS | double-click `BookBuilder_Manager.command` (the first time: right-click › Open) |
| Windows | double-click `BookBuilder_Manager.cmd` |
| Any | `python tools/manage.py` |

Choose **1 Install**, then **2 Launch**. See [START_HERE.md](START_HERE.md) for the full guide.

App data (the Library, settings, backups and logs) lives in `~/.book-builder`. Set
`BOOK_BUILDER_HOME` to use another folder.

## Tests

```bash
python -m unittest discover -s tests
```

```bash
cd site && npm ci && npx vitest run
```

## Documentation

- [docs/MODULAR_ARCHITECTURE.md](docs/MODULAR_ARCHITECTURE.md): how the code is organised (see `MODULES.json`)
- [docs/TESTING.md](docs/TESTING.md)
- [docs/BACKUP_AND_RECOVERY.md](docs/BACKUP_AND_RECOVERY.md)
- [docs/UPDATE_PACKAGE_CONTRACT.md](docs/UPDATE_PACKAGE_CONTRACT.md)
- [docs/game-developer/](docs/game-developer/): the Game Package API

## Third-party files

- Icons: see `tools/web/ICONS-LICENSE.txt`.
- Citation style: `assets/csl/apa.csl` (Citation Style Language project, CC BY-SA 3.0).
