# game.json reference

Formal schema: [schemas/game.schema.json](schemas/game.schema.json). Unknown fields are rejected.

| Field | Type | Required | Description |
|---|---|---|---|
| `$schema` | string | no | Optional pointer to the schema, ignored by the runtime. |
| `apiVersion` | `"1.1"` or `"1.0"` | yes | API version the package targets. Use 1.1 for new games. |
| `icon` | path | no (1.1) | A square image asset declared in `assets`, shown on activity cards. See `image-style.md`. |
| `id` | string | yes | Permanent unique id. `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`. Convention: `ch28-two-to-four-words`. Becomes the URL `/activities/<id>/`. Never reuse an id for a different game. |
| `title` | string 3–80 | yes | Shown on the activity card and as the heading. Sentence case. |
| `description` | string 10–400 | yes | One or two sentences: what the reader does and why. Also printed in the book next to the link. |
| `version` | `MAJOR.MINOR.PATCH` | yes | Package version. See [versioning.md](versioning.md). |
| `chapter` | integer 1–60 | yes | The chapter it belongs to. The chapter must exist; it must be approved before the game can be published. |
| `activityType` | enum | yes | `knowledge-check` (facts that can be checked), `scenario` (choices in a situation between people), `reflection` (thinking about yourself), `practice` (rehearsing words or steps), `sorting` (grouping or ordering ideas), `explainer` (guided explanation with little input). |
| `subjects` | array of slugs, max 6 | no | Topic tags for the library filter, e.g. `["texting", "boundaries"]`. Lowercase, hyphens. |
| `learningObjectives` | array of 1–6 strings | yes | What the reader can do afterwards. Start with a verb. |
| `contentWarnings` | array of strings, max 10 | yes | Plain content notes (may be empty `[]`). Required (non-empty) when `sensitive` is true. |
| `sensitive` | boolean | no (default false) | True for trauma, abuse, assault, stalking, self-harm or crisis topics. Sensitive games must be ungraded and every answer optional. |
| `estimatedMinutes` | integer 1–60 | no | Shown on the card. |
| `language` | `"en-US"` | no | The book is US English. |
| `accessibility.summary` | string 10–400 | yes | What the activity involves, so readers can decide before starting (e.g. "Five short choices with feedback and one optional written answer"). |
| `accessibility.keyboard` | `true` | yes | Confirms you used only runtime components (always keyboard-accessible). |
| `accessibility.screenReader` | `true` | yes | Confirms all images have alt text and all meaning is in text. |
| `accessibility.readingLevel` | string | no | e.g. "Grade 6–8". |
| `accessibility.notes` | string | no | Anything else, e.g. "Audio has a full transcript". |
| `requiredCapabilities` | array | yes | Runtime features used: `images`, `audio`, `branching`, `variables`, `perspective-switching`, `reflection-summary`, `scoring`. A runtime that lacks one refuses to start the game (with a clear message) instead of misbehaving. |
| `assets` | array | yes (may be `[]`) | Every file in `assets/`. Each: `path` (lowercase, under `assets/`), `type` (`image`, `audio`, `captions`, `transcript`), `alt` (images), `transcript` (audio), `credit` (optional). |
| `authors` | array of `{name, role?, url?}` | yes | Who made it. `url` must be `https://`. Don't include email addresses. |
| `license` | string | no | Normally `CC BY-NC-ND 4.0`, matching the book. |

## Example

```json
{
  "apiVersion": "1.1",
  "id": "ch23-reading-short-texts",
  "title": "Reading short texts",
  "description": "Look at five short messages, consider what each could mean, and practice asking instead of guessing.",
  "version": "1.0.0",
  "chapter": 23,
  "activityType": "scenario",
  "subjects": ["texting", "communication"],
  "learningObjectives": ["Name more than one meaning for a short message.", "Write a low-pressure check-in question."],
  "contentWarnings": [],
  "sensitive": false,
  "estimatedMinutes": 5,
  "language": "en-US",
  "accessibility": { "summary": "Five choices with feedback and one optional written answer that is never saved.", "keyboard": true, "screenReader": true },
  "requiredCapabilities": ["branching", "reflection-summary"],
  "assets": [],
  "authors": [{ "name": "Example Author", "role": "writer" }],
  "license": "CC BY-NC-ND 4.0"
}
```
