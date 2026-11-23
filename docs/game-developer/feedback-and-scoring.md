# Feedback and scoring

## Where feedback comes from

After the reader presses **Check** on a form screen, the feedback panel shows, in order:

1. `feedback` from every option the reader chose (for visible fields), then
2. every screen `feedback` rule whose `when` condition is true (a rule without `when` always shows).

The panel is a polite live region, so screen readers announce it. The reader then presses Continue.

```json
"feedback": [
  { "when": { "field": "comfort", "lte": 2 }, "text": "That's common. Chapter 28 has scripts you can borrow.", "tone": "neutral" },
  { "text": "Whatever you chose, you can change your mind later.", "tone": "neutral" }
]
```

## Tones

| tone | Use for | Looks like |
|---|---|---|
| `neutral` | most feedback | gray edge |
| `positive` | affirming a helpful choice or fact | teal edge |
| `consider` | "another way to see it" | violet edge |
| `caution` | safety information | mustard edge |

Tone is never conveyed by color alone: the words must carry the meaning.

## Writing feedback (editorial rules)

- **Interpersonal situations have no single right answer.** Explain what a choice might lead to, from more
  than one perspective, and what to try. Never "Wrong!" or "Correct!" for a choice between people.
- Aim reality checks at the reader's own choices, without shame. Assume good intent.
- Never present manipulation, pressure, jealousy tactics, persistence after a "no" or getting around
  consent as an option that "works". If a scenario shows one, the feedback names it as harmful.
- Never assign a diagnosis, label, attachment style or personality type ("you are an anxious type").
  Describe experiences instead ("some people find…").
- Don't stereotype any gender. Rotate names, genders, orientations and ages; use fresh names that don't
  collide with the book's examples.
- Match the chapter: use its fixed terms (overload, shutdown, masking, boundary vs request, double empathy
  problem) and don't contradict it.

## Scoring

Scoring is allowed **only** in `knowledge-check` games, only on choice fields marked `"scored": true`,
and only for facts that can be checked against the chapter or its sources (for example "Which of these is
required for consent?" if the chapter states it). Mark the right option(s) `"correct": true`.

- Single-choice and dropdown: the chosen value must be correct.
- Multiple-choice and multi-select cards: the chosen set must equal the set of correct options.
- `showScore` on a completion screen shows "Knowledge questions: 3 of 4 matched the book." There is no
  pass mark, timer, leaderboard or penalty.

Not allowed (the validator rejects these): `correct` without `scored`, scored fields outside
`knowledge-check`, scored fields in `sensitive` games, and required answers in `sensitive` games.

## Reflections

`reflection` activities help readers think about themselves. They are never scored, never conclude what
the reader "is", and written answers are optional. `showSummary` on the completion screen shows the
reader's answers back to them with a Copy button; they are never stored and disappear when the reader
leaves or restarts.

## Sensitive topics

Trauma, abuse, assault, stalking, self-harm and crisis activities must set `"sensitive": true`, include
content warnings, be ungraded and have no required answers. Point readers to the book's support and crisis
chapters (59 and 60) rather than giving crisis advice inside the game. Readers can always skip.

## Completion results (API 1.1)

Completion screens can have `feedback` rules. Every rule whose condition matches is shown when the reader finishes, so results can depend on variables, answers or `{"score": {...}}`. Keep them nuanced: say what the answers suggest and point back to the chapter, never grade a person.
