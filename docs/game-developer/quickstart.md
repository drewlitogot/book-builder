# Quickstart

## 1. Start from a template

Copy `templates/minimal-package/` (one question) or `templates/branching-package/` (a scenario with
branching, perspectives and a reflection). Each has `game.json`, `activity.json` and `README.md`.

## 2. Fill in game.json

- `id`: lowercase words joined by hyphens, starting with the chapter, e.g. `ch28-saying-it-out-loud`.
  The id is permanent and becomes part of the URL.
- `chapter`: the chapter number (1–60).
- `activityType`: `knowledge-check`, `scenario`, `reflection`, `practice`, `sorting` or `explainer`.
- `requiredCapabilities`: list every feature you use (`branching`, `variables`, `perspective-switching`,
  `reflection-summary`, `scoring`, `images`, `audio`).

See [manifest-reference.md](manifest-reference.md) for every field.

## 3. Write the screens in activity.json

```json
{
  "apiVersion": "1.1",
  "start": "intro",
  "screens": [
    { "id": "intro", "type": "info", "title": "A text that could mean two things", "body": "Kai texts: \"sure\".", "next": "q1" },
    { "id": "q1", "type": "form", "title": "What might \"sure\" mean?",
      "fields": [{ "id": "meaning", "type": "multiple-choice", "label": "Choose all that could be true",
        "options": [
          { "value": "yes", "label": "Yes, happily" },
          { "value": "flat", "label": "Yes, but not keen" },
          { "value": "busy", "label": "Busy, replying fast" }
        ] }],
      "feedback": [{ "text": "All three are possible. When it matters, asking is quicker than guessing.", "tone": "neutral" }],
      "next": "done" },
    { "id": "done", "type": "completion", "title": "Done", "body": "Short messages carry less tone than speech." }
  ]
}
```

## 4. Zip it

Zip the **contents** of the folder (a single wrapping folder is also accepted):

```bash
cd my-game && zip -r ../ch21-what-sure-means.zip game.json activity.json README.md assets
```

## 5. Validate

If you have the book repository:

```bash
python tools/games.py validate ch21-what-sure-means.zip
```

Without it, validate both JSON files against `schemas/game.schema.json` and
`schemas/activity.schema.json` with any JSON Schema (draft 2020-12) validator, then work through the
checklist in [validation-and-testing.md](validation-and-testing.md). The builder runs extra checks
(references, reachability, editorial rules) that a schema can't express.

## 6. Hand it in

Send the ZIP to the book's editor. They import it in the Book Manager, preview it and decide whether to
approve it.
