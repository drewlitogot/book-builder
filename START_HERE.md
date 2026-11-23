# Book Builder: start here

Book Builder is the local app that plans, writes (with ChatGPT and Claude), checks, builds and publishes books. It runs only on your computer at http://127.0.0.1:8765 (or the next free port). Each book lives in its own folder; the Library keeps track of them.

## Open the manager

| System | Double-click |
|---|---|
| Windows | `BookBuilder_Manager.cmd` (or run it from Command Prompt or PowerShell) |
| macOS | `BookBuilder_Manager.command` (first time: right-click › Open) |
| Any | `python tools/manage.py` |

```
[1] Install / First Run            [7] Installation Status
[2] Launch Book Builder            [8] Make Book Data Backup
[3] Update Book Builder from ZIP   [9] Restore Book Data Backup
[4] Run Local QA Tests             [10] View Logs / Diagnostics
[5] Make Source Backup             [11] Generate AI Development Handoff
[6] Restore Source Backup          [0] Exit
```

Every option is also a command, for example `python tools/manage.py status` or `BookBuilder_Manager.cmd qa --zip`.

## First time

1. **1 Install:**
   - checks Python (3.10 or newer)
   - creates `.venv` inside this folder
   - installs `requirements.txt` (it asks first, because it downloads)
   - reports whether Pandoc, Typst, Node and Git are installed. It never installs system software.
2. **2 Launch:** starts Book Builder and opens your browser. Logs go to `~/.book-builder/logs`. Press Ctrl+C or Quit in the page to stop.

## Four kinds of ZIP: never mix them up

| ZIP | Made by | Contains | Used for |
|---|---|---|---|
| **Update package** (`forge-manifest.json`) | an AI or developer | changed app source files only | option 3; needs the word APPLY |
| **Source backup** | option 5 | the app's source files | option 6; needs RESTORE |
| **Book data backup** | option 8 | chapters, drafts, research, metadata, assets, Library | option 9; needs RESTORE |
| **QA review / AI handoff / diagnostics** | options 4, 11, 10 | evidence and context | sending to a person or AI; **never installable** |

Book outputs (PDF, EPUB, DOCX, website) are separate again: they're in `dist/` and `site/dist/`.

## Where things live

- App source: this folder (see `MODULES.json`).
- Book data: each book's own folder (`book.yml`, `book/`, `drafts/`, `research/` …).
- App data, backups, logs, QA history: `~/.book-builder` (on Windows `C:\Users\<you>\.book-builder`).

More: [docs/MODULAR_ARCHITECTURE.md](docs/MODULAR_ARCHITECTURE.md), [docs/BACKUP_AND_RECOVERY.md](docs/BACKUP_AND_RECOVERY.md), [docs/UPDATE_PACKAGE_CONTRACT.md](docs/UPDATE_PACKAGE_CONTRACT.md), [docs/AI_DEVELOPMENT_HANDOFF.md](docs/AI_DEVELOPMENT_HANDOFF.md), [docs/TESTING.md](docs/TESTING.md).
