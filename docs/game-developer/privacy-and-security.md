# Privacy and security

## Privacy

- **Nothing a reader types is stored or sent.** Text and textarea answers stay in memory and are left out
  of every event. They disappear when the reader leaves, restarts or reloads.
- Choice answers are kept only in memory too. The only thing the website may store, and only if the reader
  turns on "Remember progress", is that an activity id was completed. Readers can clear it at any time.
- There are no accounts, analytics, cookies, trackers or network requests from games. Links to other
  sites open in a new tab and only when the reader chooses.
- Don't ask for personal identifying information (names, contact details, locations, dates of birth),
  health or diagnosis details, or details of abuse. Reflection prompts should be answerable in general
  terms, and every written answer is optional.

## What packages may not contain

- Executable code of any kind: JavaScript, HTML, SVG (it can contain scripts), CSS, WebAssembly, binaries,
  macros, nested archives.
- HTML or `javascript:` in any text field, or non-https links.
- Remote resources: every asset is inside the package.
- Assets you don't have the right to share.

## How the builder checks a ZIP

Archives are read in memory and checked before anything touches the disk:

- size limits (ZIP, total, per file, entry count) and compression-ratio limits against archive bombs;
- no absolute paths, `..`, backslashes, drive letters, symlinks, device files or encrypted entries;
- names restricted to safe characters, case-insensitive duplicates rejected, depth limited;
- only allowed file types, and file contents checked against their extension;
- JSON parsed strictly as UTF-8; both files validated against the JSON Schemas, then semantic and
  editorial checks.

Installation is atomic: files are written to a staging folder with no-overwrite file creation, the
staged folder replaces the installed one in a single rename, and the registry is updated last. Any failure
removes the staging folder and restores the previous version. Installed files are hashed; if they change
after approval, the game is excluded from publishing until it's re-imported and re-approved.

Only validated `game.json`, `activity.json` and declared assets are copied to the public website. README,
LICENSE and the registry stay private.
