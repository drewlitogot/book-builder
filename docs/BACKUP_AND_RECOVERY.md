# Backup and recovery

Backups are stored in `~/.book-builder/backups/{source,data}/`, outside the app folder. Each backup is a ZIP with `manifest.json`, which records the SHA-256 of every file, plus `files/…`.

| | Source backup (5 / 6) | Book data backup (8 / 9) |
|---|---|---|
| Contains | every application source file (`paths.source_files`) and its revision | `book.yml`, `book/`, `drafts/`, `reviews/`, `research/`, `prompts/`, `briefs/`, `sources/`, `sources-inbox/`, `games/`, `agents/`, `assets/branding/`, `references.bib`, `website.yml`, `workspace.yml`, and the Library and settings (`appdata/`) |
| Never contains | books, `.venv`, `node_modules`, `dist/`, logs, `.env` and keys | app source, builds, `.venv`; `sources-private/` only with `--private` (copyrighted copies) |
| Restore checks | archive safety, kind, every checksum, only source paths | archive safety, kind, every checksum, only data paths |
| Restore needs | Book Builder stopped, the word `RESTORE` | the word `RESTORE` |
| Before restoring | a `pre-restore` source backup | a `pre-restore` data backup |
| Restore effect | source becomes exactly the snapshot; source files added later are removed | the backup's files are written back and verified; files added later are listed, not deleted |

- Restoring source never changes a chapter. Restoring data never changes app code.
- Book data is plain files, so there is no database schema to make an old source incompatible.
- An app update (option 3) makes both backups first. If anything fails mid-update, the source backup is restored automatically.

## Recovery recipes

- **An update broke the app:** option 6, choose the `pre-update` source backup.
- **A chapter or research was lost:** option 9, choose a data backup (or use git history: Build › Save Work).
- **The app won't start:** option 10 shows recent errors. Option 1 repairs `.venv`.
- **Moving to another computer:** copy the folder (or clone the repository), run option 1, then option 9 with a data backup.
