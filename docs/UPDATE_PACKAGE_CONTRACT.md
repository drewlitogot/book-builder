# Update package contract (`bookbuilder-upgrade`)

An update package is a ZIP that changes **application source only**. It contains exactly:

```
forge-manifest.json
payload/<relative path>     complete final contents of each added or replaced file (nothing else)
```

## forge-manifest.json

```json
{
  "schema_version": 1,
  "project_id": "book-builder",
  "package_id": "short-unique-id",
  "package_type": "bookbuilder-upgrade",
  "base_revision": "<64-hex source revision the change was made against>",
  "target_revision": "<revision after applying, or null if unknown>",
  "title": "What changed",
  "description": "Why, and anything the person should know",
  "assignment_id": "optional: the AI assignment this answers",
  "created": "2026-11-22T15:00:00+0000",
  "operations": [
    {"op": "add",     "path": "tools/new_module.py", "sha256": "<new content hash>"},
    {"op": "replace", "path": "tools/routes.py",     "sha256": "<new>", "original_sha256": "<current file hash>"},
    {"op": "delete",  "path": "tools/old.py",        "original_sha256": "<current file hash>"}
  ]
}
```

- **Paths:** canonical, relative, forward slashes. They must be application source as defined in `tools/bbmanage/paths.py`: `tools/`, `tests/`, `run/`, `assets/typst|filters|csl|css|fonts/`, `site/src|tests` and site config, `docs/` top-level and `docs/book-manager|game-developer|architecture/`, plus top-level app files. Book data (`book/`, `drafts/`, `research/`, `book.yml` …) can never be in a package.
- **Hashes:** SHA-256 in lowercase hex. `original_sha256` comes from the handoff's `source-inventory.json`.
- **Source revision:** SHA-256 over every source file, in sorted path order, of `path \0 sha256 \n`. See `python tools/manage.py revision`.

## What Book Builder checks (option 3, nothing is executed)

1. The archive is safe:
   - no absolute or `..` paths, backslashes, drive letters, symlinks or encrypted entries
   - no duplicate or case-colliding names
   - size and compression-ratio limits
2. The package type, project id and schema version are right. Backups, QA reviews, handoffs and diagnostics are rejected, with a note saying what they are.
3. `base_revision` equals the installation's current revision. **Stale packages are rejected, never "best-effort" applied.**
4. Every add or replace has its payload, and the payload hash matches. Every replace or delete has an `original_sha256` matching the current file. An add must not overwrite an existing file. No undeclared payload, and no files outside `payload/`.
5. Every path is application source.
6. The full plan is shown.
7. Book Builder must not be running.
8. You type `APPLY`.
9. Backups are made, files are staged, and each one is swapped in with an atomic replace. Any error restores the source backup.
10. Syntax checks run on changed `.py`, `.js` and `.json` files, plus a `requirements.txt` sanity check. Run QA (option 4) next. New dependencies need option 1.

Applied packages are copied unchanged to `~/.book-builder/packages/` and logged in `manager-state.json`.

## Building a package

```
python tools/manage.py make-update --base-backup <source backup.zip> --out update.zip --id my-change --title "My change"
python tools/manage.py make-update --base-inventory source-inventory.json --root source --out update.zip --id my-change --title "My change" [--delete path]
```

The second form is for AI handoffs: their `source/` copy can be partial, so files missing from it count as unchanged. Deletions must be listed explicitly with `--delete`.

## Parallel work: not yet

`assignment_id` and `base_revision` let several returned packages be kept side by side. Book Builder applies **one package at a time, in order, each against the exact revision it was built on**. Out-of-order merging is not supported. After one package is applied, others built on the old revision are rejected as stale and must be rebuilt.
