# Book Builder Game Package API 1.1

New in 1.1: personalized text, ranking, shuffle, hints, score conditions, completion results,
takeaways, saved notes and a game icon. See `whats-new-1.1.md`. Every game's images follow
`image-style.md`.

Interactive activities for books made with Book Builder
are delivered as small, self-contained ZIP packages. A package contains **data, not code**: two JSON
files describe what the reader sees, what they can answer, how answers change the next screen, and what
feedback they get. The website's built-in runtime draws everything, so every activity is accessible,
private and consistent with the book.

You do not need the website's source code to make a game. These documents are the whole contract.

| Document | What it covers |
|---|---|
| [quickstart.md](quickstart.md) | Make, check and hand in a first package in ten minutes |
| [package-specification.md](package-specification.md) | ZIP layout, allowed files, size limits, naming |
| [manifest-reference.md](manifest-reference.md) | Every field of `game.json` |
| [activity-schema-reference.md](activity-schema-reference.md) | `activity.json`: screens, variables, text format |
| [component-reference.md](component-reference.md) | Every screen type and form field, with examples |
| [branching-and-state.md](branching-and-state.md) | `next` rules, conditions, variables, effects, Back |
| [lifecycle-and-events.md](lifecycle-and-events.md) | Runtime lifecycle, events and their payloads |
| [feedback-and-scoring.md](feedback-and-scoring.md) | Feedback panels, tones, when scoring is allowed |
| [accessibility.md](accessibility.md) | WCAG 2.2 AA rules for content authors |
| [privacy-and-security.md](privacy-and-security.md) | What is stored, what is forbidden, how ZIPs are checked |
| [validation-and-testing.md](validation-and-testing.md) | Validation commands, error messages, test checklist |
| [versioning.md](versioning.md) | API versions, package versions, updates |
| [ai-game-creation-prompt.md](ai-game-creation-prompt.md) | Reusable prompt for an AI that builds a game from a chapter |
| [schemas/](schemas/) | Formal JSON Schemas (draft 2020-12) |
| [templates/](templates/) | Starter packages: minimal and branching |

## The rules in one paragraph

Games teach what the chapter teaches and nothing else. Never teach manipulation, pressure, harassment or
ways around a "no". Right/wrong scoring is only for facts that can be checked; situations between people
get nuanced feedback instead. Reflections never assign a diagnosis, label or personality type. Games about
trauma, abuse, assault or crisis are ungraded, optional and marked `"sensitive": true` with content
warnings. Readers can always skip. Nothing a reader types is ever stored or sent.

## How a package becomes part of the website

1. You build `my-game.zip` following this API.
2. The book's editor imports it into the local Book Manager (Games view). It is validated and installed with status **review**.
3. The editor previews it, then approves it. Nothing is approved automatically.
4. The editor publishes the website. The activity appears at the end of its chapter and in the Activities library.
