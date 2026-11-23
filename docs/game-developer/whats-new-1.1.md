# What's new in API 1.1

API 1.1 adds optional features. Every 1.0 package still runs unchanged. To use any of these, set
`"apiVersion": "1.1"` in **both** `game.json` and `activity.json`; the validator names any 1.1 feature
used in a 1.0 package.

| Feature | Where | What it does |
|---|---|---|
| Personalized text | any title, body, feedback, perspective body or takeaway | `{{answer:<fieldId>}}` inserts the reader's answer; `{{var:<name>}}` inserts a variable |
| `ranking` field | form screens | the reader puts 2–8 options in order |
| `shuffle` | single-choice, multiple-choice, cards, ranking | random option order for each play |
| `hint` | any field | a short hint behind a "Need a hint?" toggle |
| `first` condition | ranking fields | `{"field": "priorities", "first": "space"}` is true when that option is ranked first |
| `score` condition | anywhere a condition goes | `{"score": {"gte": 0.8}}`: share (0–1) of scored questions answered as the book suggests |
| Completion `feedback` | completion screens | rules pick the result shown when the reader finishes |
| `takeaways` | completion screens | 1–8 short points, shown as "To take with you" |
| `allowSaveNotes` | completion screens | a "Save my notes" button; needs the `save-notes` capability |
| `icon` | game.json | a square image asset shown on activity cards |

## Personalized text

```json
{ "id": "firm", "type": "form", "title": "Your top choice: {{answer:priorities}}" }
```

- Choice answers read as their option labels; multiple answers are joined with commas; rankings read
  "1. …; 2. …"; checkboxes read Yes or No; written answers read as typed.
- An unanswered placeholder reads "—". Every placeholder must name an existing field or declared variable.
- Written answers are shown only on the reader's own screen and never leave the page.

## Ranking

```json
{ "id": "priorities", "type": "ranking", "label": "Most important first", "shuffle": true,
  "options": [ { "value": "calm", "label": "Feeling calm and safe together" }, ... ] }
```

- The value is the list of option values in the reader's order. It starts in the shown order, so it
  always has an answer; `required` has no effect.
- Each item has Move up and Move down buttons (keyboard and screen-reader friendly; moves are announced).
- Ranking options can't be scored and can't carry `feedback` or `effects`. React to a ranking with screen
  feedback rules or `next` rules using `first`, or `includes`.

## Completion results, takeaways and saved notes

```json
{
  "id": "done", "type": "completion", "title": "Your results",
  "feedback": [
    { "when": { "score": { "gte": 0.8 } }, "text": "Most of your answers matched the chapter.", "tone": "positive" },
    { "when": { "score": { "lt": 0.8 } }, "text": "A few answers differed; the chapter explains why.", "tone": "consider" }
  ],
  "takeaways": ["Ask, don't assume.", "A pause is an answer you can respect."],
  "showSummary": true,
  "allowSaveNotes": true
}
```

- Completion feedback shows every rule whose condition matches, in order.
- **Save my notes** makes a plain-text file in the reader's browser (answers, results and takeaways) and
  downloads it to their device. Nothing is sent anywhere. Add `"save-notes"` to `requiredCapabilities`.
- When `allowSaveNotes` is on, the summary's "Copy my answers" button is replaced by "Save my notes".

## Images and the icon

Games use the unified house look in `image-style.md`: 8 scene images delivered as two 2×2 sheets, plus one
square icon. Declare the scene images in panel order and the icon last, then point `"icon"` at it. The Book
Manager cuts the sheets into images. Sensitive chapters use only the icon.

## Updating a 1.0 game

In the Book Manager's Games view, **Update prompt** on an installed game copies a prompt that gives ChatGPT
the current package, this API and the image style, and asks for version x.(y+1).0 at API 1.1. Import the
reply with **Replace or update** ticked; the game returns to review.
