# activity.json reference

Formal schema: [schemas/activity.schema.json](schemas/activity.schema.json). Unknown fields are rejected.

```json
{
  "apiVersion": "1.1",
  "start": "intro",
  "variables": { "askedFirst": { "initial": 0, "description": "Times the reader chose to ask" } },
  "screens": [ ... ]
}
```

| Field | Required | Description |
|---|---|---|
| `apiVersion` | yes | `"1.1"` (or `"1.0"`) |
| `start` | yes | Id of the first screen. |
| `variables` | no | Up to 20 named values (number, string or boolean) changed by effects and read by conditions. Names: `^[a-z][a-zA-Z0-9_]{0,39}$`. See [branching-and-state.md](branching-and-state.md). |
| `screens` | yes | 1–80 screens. Order in the file doesn't matter; `start` and `next` decide the path. |

## Screen

| Field | Applies to | Description |
|---|---|---|
| `id` | all | Unique id, `^[a-z0-9][a-z0-9_-]{0,47}$`. |
| `type` | all | `info`, `form`, `perspective`, `feedback` or `completion`. See [component-reference.md](component-reference.md). |
| `title` | all | Heading, 1–120 characters. Screen readers move to it on every screen change. |
| `body` | all | Text (format below), up to 4000 characters. |
| `image` | all | `{ "asset": "assets/x.png", "alt": "..." }`; the asset must be a declared image. |
| `fields` | `form` only (required) | 1–12 form fields. |
| `perspectives` | `perspective` only (required) | 2–6 views shown as tabs. |
| `requireAllPerspectives` | `perspective` | Reader must open every tab before continuing. |
| `feedback` | all | Feedback rules shown after the reader presses **Check** on a form. |
| `effects` | all | Variable changes applied when the screen is entered. |
| `showSummary` | `completion` | Show the reader's answers back to them (kept in memory only). |
| `showScore` | `completion` | Show the knowledge-check score (only meaningful with scored fields). |
| `continueLabel` | all but `completion` | Button text instead of "Continue" (max 40). |
| `next` | all but `completion` (required) | Screen id, or rules. Completion screens must not have `next`. |

Every path must reach a `completion` screen; the validator rejects dead ends and loops with no exit.

## Text format

`body`, option `feedback`, feedback rule `text` and perspective `body` accept a small Markdown subset:

- Paragraphs separated by a blank line (`\n\n` in JSON).
- Lists: lines starting with `- `.
- `**bold**`, `*italic*`.
- Links: `[text](https://...)`, https only. They open in a new tab.

HTML, images in text, headings, tables and code are not supported; HTML and `javascript:` are rejected.
Labels, titles, option labels and descriptions are plain text.
