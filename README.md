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
- **Trash:** deleted books, saved prompts and revision files go to the Trash (Settings › Trash),
  where you can restore them or delete them for good.

## Download the desktop app

Ready-to-run builds for macOS (Apple silicon and Intel), Windows and Linux are on the
[Releases page](https://github.com/drewlitogot/book-builder/releases). They include Python, Pandoc
and Typst, so nothing else needs to be installed, and they open Book Builder in its own window
(Electron). To use your browser instead, choose File › Open in Browser, or change
Settings › Preferences › "Open Book Builder in". Each download has a README with start-up steps.
The builds aren't signed by Apple or Microsoft yet, so the first start shows a security prompt.

### Build it yourself

Double-click the build script for your system. It needs Python 3.10 or newer with pip and an
internet connection the first time:

| System | Build script |
|---|---|
| macOS | `Build_App_macOS.command` (the first time: right-click › Open) |
| Windows | `Build_App_Windows.cmd` |
| Linux | `Build_App_Linux.sh` |

The result is in `dist/packages`. Add `--target all` to build for every system at once, or run
`python tools/package_app.py --help`.

## Run from source

### Requirements

- Python 3.10 or newer
- [Pandoc](https://pandoc.org) and [Typst](https://typst.app) to build books
- Node.js to build the reader website
- Git, optionally, for Save Work and publishing

### Start

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

## License

Book Builder is released under the [MIT License](LICENSE). Bundled third-party files keep their own
licenses: the fonts in `assets/fonts` (SIL Open Font License), the icons (ISC) and the citation style
(CC BY-SA 3.0). Books you make with Book Builder are yours to license however you like.
