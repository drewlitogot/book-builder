# Component reference

## Screen types

### info
Text (and optionally an image) with a Continue button. Use for setup, explanations and transitions.
```json
{ "id": "setup", "type": "info", "title": "The situation", "body": "Two people are on a second date…", "next": "choose" }
```

### form
One or more fields. A multi-step form is simply several `form` screens in a row; the progress bar shows
how far along the reader is. If the screen or any chosen option has feedback, the button reads **Check**,
then **Continue** once feedback is shown.
```json
{ "id": "choose", "type": "form", "title": "What would you say?", "fields": [ ... ], "next": "after" }
```

### perspective
The same moment seen by different people, as keyboard-accessible tabs (arrow keys, Home, End). Use it for
the book's central idea: everyone sees something real; nobody sees all of it.
```json
{ "id": "views", "type": "perspective", "title": "Two views of the same evening",
  "perspectives": [
    { "id": "wren", "label": "Wren", "body": "Wren noticed the noise and wanted to leave early." },
    { "id": "kai", "label": "Kai", "body": "Kai thought the evening was going well." }
  ],
  "requireAllPerspectives": true, "next": "reflect" }
```

### feedback
A screen that responds to earlier choices, usually reached by a branch rule. Same fields as `info`.

### completion
The end. Shows its body, optional score (`showScore`), optional summary of answers (`showSummary`) with a
Copy button, and Restart. Completion screens have no `next`. You may have several (different endings).

## Form fields

Common properties: `id` (unique across the whole activity), `type`, `label`, `help`, `required`,
`showIf` (a condition, see [branching-and-state.md](branching-and-state.md)).

Fields are optional by default and labelled "(optional)". Only make a field `required` when the activity
can't continue without it. Written answers should never be required.

| type | Reader sees | Value | Extra properties |
|---|---|---|---|
| `single-choice` | radio buttons | option value (string) | `options` (2–12), `scored` |
| `multiple-choice` | checkboxes | array of option values | `options`, `minSelected`, `maxSelected`, `scored` |
| `checkbox` | one checkbox | `true` / `false` | (`required` means "must tick") |
| `dropdown` | a select menu | option value | `options`, `scored` |
| `slider` | a range slider with labels | number | `min`, `max` (required), `step`, `initial`, `minLabel`, `maxLabel` |
| `text` | one-line text box | string | `maxLength` (≤ 2000), `placeholder` |
| `textarea` | multi-line text box | string | `maxLength`, `placeholder` |
| `cards` | selectable cards with descriptions | value, or array if `multiple` | `options`, `multiple`, `minSelected`, `maxSelected`, `scored` |

### Options

| Property | Description |
|---|---|
| `value` | Id used in conditions, `^[a-z0-9][a-z0-9_-]{0,47}$`, unique within the field. |
| `label` | What the reader sees (≤ 200). |
| `description` | Second line, shown on cards and options (≤ 400). |
| `feedback` | Shown after Check if this option was chosen (text format). |
| `tone` | `neutral` (default), `positive`, `consider`, `caution`. See [feedback-and-scoring.md](feedback-and-scoring.md). |
| `correct` | Only on `scored` fields in `knowledge-check` games. |
| `effects` | Variable changes applied when the reader leaves the screen with this option chosen. |

### Examples

```json
{ "id": "comfort", "type": "slider", "label": "How comfortable would that feel?", "min": 1, "max": 5, "step": 1,
  "initial": 3, "minLabel": "Not at all", "maxLabel": "Very" }
```
```json
{ "id": "approach", "type": "cards", "label": "Pick the approach closest to yours",
  "options": [
    { "value": "ask", "label": "Ask", "description": "“Would you like to keep talking, or call it a night?”" },
    { "value": "wait", "label": "Wait", "description": "See whether they bring it up." }
  ] }
```
```json
{ "id": "why", "type": "textarea", "label": "What would you want them to know? (optional)", "maxLength": 400,
  "showIf": { "field": "approach", "equals": "ask" } }
```

## Built in for every game (you don't configure these)

- An introduction card with title, description, minutes, content warnings, the accessibility summary and
  **Start activity** / **Skip activity**.
- A progress bar, **Back**, and **Leave activity** on every screen.
- Validation messages for required and min/max fields, announced to screen readers.
- A contained error message if the package can't run; the chapter stays readable.

## New in API 1.1

- `ranking` field: the reader orders 2–8 options with Move up / Move down buttons. Value: option values in order.
- `shuffle` (choice, cards, ranking) and `hint` (any field).
- Completion screens: `feedback` rules, `takeaways`, `allowSaveNotes` (Save my notes).
- Personalized text: `{{answer:fieldId}}` and `{{var:name}}`.

Details and examples: `whats-new-1.1.md`.
