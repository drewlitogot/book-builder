# Branching and state

## next

`next` is either a screen id:

```json
"next": "after"
```

or rules, checked in order; the first match wins, otherwise `default`:

```json
"next": {
  "rules": [
    { "when": { "field": "response", "equals": "guess" }, "goto": "guess-outcome" },
    { "when": { "var": "askedFirst", "gte": 2 }, "goto": "good-habit" }
  ],
  "default": "views"
}
```

Branching games must list `"branching"` in `requiredCapabilities`.

## Conditions

Used in `next` rules, feedback rules (`when`) and `showIf`.

| Form | Meaning |
|---|---|
| `{ "field": "f", "equals": "a" }` | answer equals the value (a one-item array also matches) |
| `{ "field": "f", "notEquals": "a" }` | answer is not that value (true when unanswered) |
| `{ "field": "f", "in": ["a", "b"] }` | answer is one of these |
| `{ "field": "f", "includes": "a" }` | multi-select answer contains the value |
| `{ "field": "f", "gt": 3 }` / `gte` / `lt` / `lte` | numeric comparison (sliders) |
| `{ "field": "f", "answered": true }` | the reader answered (or didn't, with `false`) |
| `{ "var": "v", ... }` | same operators on a variable |
| `{ "visited": "screen-id" }` | the reader has been to that screen |
| `{ "all": [ ... ] }`, `{ "any": [ ... ] }`, `{ "not": { ... } }` | combine conditions |

A field or variable condition takes exactly one operator. Unanswered fields fail every comparison except
`notEquals` and `answered: false`. Conditions may only refer to fields that exist; `showIf` may only refer to
fields above it on the same screen, or to earlier screens.

## Variables and effects

Declare variables with initial values, then change them with effects:

```json
"variables": { "askedFirst": { "initial": 0 }, "ending": { "initial": "none" } }
```
```json
{ "value": "ask", "label": "Ask", "effects": [ { "var": "askedFirst", "add": 1 } ] }
```
```json
{ "id": "calm-ending", "type": "completion", "title": "…", "effects": [ { "var": "ending", "set": "calm" } ] }
```

- Option effects apply when the reader **leaves** the form screen with that option chosen.
- Screen effects apply when the reader **enters** the screen.
- `add` needs a numeric variable; `set` replaces the value.
- Games using variables should list `"variables"` in `requiredCapabilities`.

## Hidden fields

When a field's `showIf` is false, it isn't shown, doesn't block Continue, and any earlier answer to it is
dropped when the screen is submitted.

## Back and Restart

**Back** returns to the previous screen with answers and variables as they were before leaving it, so
effects are never applied twice. **Restart** clears everything and returns to `start`.

## Progress

The progress bar shows steps taken compared with the shortest remaining path to a completion screen, so
it never jumps backwards much when a branch is longer.

## Worked example

See `templates/branching-package/activity.json`: a card choice branches to an extra outcome screen when
the reader guesses, both paths meet at a perspective screen, and a written reflection appears only if the
reader rates their comfort 3 or higher.

## New conditions in API 1.1

- `{"field": "<ranking id>", "first": "<value>"}`: true when that option is ranked first.
- `{"score": {"gte": 0.8}}`: the share (0–1) of scored questions answered as the book suggests; works in `next` rules, `showIf` and feedback.
