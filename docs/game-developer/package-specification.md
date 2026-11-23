# Package specification

A game package is a ZIP archive.

```
ch28-saying-it-out-loud.zip
├── game.json          required: the manifest (manifest-reference.md)
├── activity.json      required: screens and logic (activity-schema-reference.md)
├── README.md          recommended: what it is, who made it, what changed
├── LICENSE            optional (LICENSE, LICENSE.md or LICENSE.txt)
└── assets/            optional: images, audio, captions, transcripts
    └── ...
```

## Allowed files

| Location | Allowed |
|---|---|
| top level | `game.json`, `activity.json`, `README.md`, `LICENSE`, `LICENSE.md`, `LICENSE.txt` |
| `assets/` (subfolders allowed) | `.png .jpg .jpeg .webp .gif` images, `.mp3 .m4a .ogg` audio, `.vtt` captions, `.txt` transcripts |

Anything else is rejected, including **JavaScript, HTML, SVG, CSS, fonts, executables and nested ZIPs**.
Games are data; the website's runtime does all rendering.

The ZIP may contain the files directly or inside one wrapping folder. macOS `__MACOSX/` entries and
`.DS_Store` files are ignored.

## Names and paths

- File and folder names: letters, digits, `.`, `_`, `-`; must start with a letter or digit. Asset paths in
  `game.json` must be lowercase (`assets/couch-scene.png`).
- No absolute paths, `..`, backslashes, drive letters, symbolic links, special files or encrypted entries.
- Names must differ by more than letter case.
- At most 6 folder levels.

## Limits

| Limit | Value |
|---|---|
| ZIP size | 20 MB |
| Total uncompressed size | 50 MB |
| One file | 5 MB |
| `game.json` / `activity.json` | 1 MB each |
| Entries | 300 |
| Compression ratio | files over 1 MB must not compress more than 100:1 |
| Screens | 80 |
| Fields per screen | 12 |
| Options per field | 12 (at least 2) |

## Assets

- Every file in `assets/` must be listed in `game.json` `assets`, and every listed asset must exist.
- The file's bytes must match its extension (a renamed file is rejected).
- Images need `alt` text (`""` only for purely decorative images). The Book Manager resizes images wider
  than 1600 px and re-compresses large files when you import, and converts a file to the format its
  declared name says (`.png`, `.jpg`, `.webp`). Prefer WebP or JPEG for photos, PNG for diagrams.
- Image style and content rules (brand palette, no text in images, nothing sexual, violent or
  stereotyped, no images in sensitive chapters) are in `ai-game-creation-prompt.md`, section "Images".
- **Chat delivery:** when files come as a pasted chat reply, images are added separately: after you paste
  the reply, the Book Manager lists each declared image and asks you to choose the downloaded file.
- Audio needs a transcript asset (`"transcript": "assets/....txt"`), and the `audio` capability. Captions
  (`.vtt`) are recommended.
- Photographs should follow the brand: nearly grayscale with one or two muted accent colors.
- Only include assets you have the right to share under the package license.

## Encoding

JSON files are UTF-8 without a byte-order mark. Use straight or curly quotes consistently; the book uses
curly quotes (’ “ ”) in reader-facing text.
