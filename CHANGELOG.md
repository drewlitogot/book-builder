# Changelog

## 2.1.0-beta.1 (2026-11-22)

- Desktop app for macOS, Windows and Linux: Book Builder opens in its own window (Electron), with
  Python, Pandoc and Typst included. File › Open in Browser, and a Preferences setting to always use
  the browser. Click-to-run build scripts (`Build_App_*`) and `tools/package_app.py`.
- Delete with a Trash: delete books from the Library, saved prompts (AI Studio › Saved Prompts) and
  draft, notes and check files (Chapters › Revisions). Everything goes to Settings › Trash first,
  where it can be restored or deleted for good. Approved chapters are never deleted.

## 2.1.0 (2026-11-22)

First public release of Book Builder as its own project, with a generic Sample Book.

- Multi-book Library: create, import, export and switch books
- Writing workflow with AI prompt packs and handoffs; approvals protect finished chapters
- Research Library with local search (PDF, DOCX, XLSX, PPTX, EPUB)
- Brand Studio and Image Studio
- PDF, EPUB, DOCX and HTML builds; reader website with GitHub Pages publishing and website ZIPs
- Game Package API importer and review
- Guided Mode tours
- Local manager: install, launch, ZIP updates, backups, QA and diagnostics
