# Lifecycle and events

The runtime owns the lifecycle; packages contain no code. This page documents what happens, so you can
design for it and so the host page can listen.

## Lifecycle

1. **init**: the runtime reads `game.json` and `activity.json` and checks the API version, capabilities,
   start screen and every `next` target. If anything is wrong it emits `error` and shows a contained
   "This activity couldn't load" message. The chapter stays readable.
2. **ready**: the introduction card is shown (title, description, minutes, content warnings,
   accessibility summary, Start / Skip).
3. **start**: the reader presses Start. Variables are set to their initial values and the `start` screen
   is entered.
4. **input**: the reader changes a field or opens a perspective tab.
5. **submit / feedback**: on a form, Check validates answers, drops hidden fields, and shows feedback if any.
6. **screenchange / progress**: Continue applies option effects, follows `next`, enters the new screen
   (applying its effects) and moves keyboard focus to its heading.
7. **complete**: a completion screen is entered.
8. **restart**, **back**, **exit** (Leave activity) and **skip** (Skip on the introduction card) can happen
   at any time.

## Events

Every event is an object:

```json
{ "type": "screenchange", "gameId": "ch23-reading-short-texts", "gameVersion": "1.0.0", "apiVersion": "1.0",
  "screenId": "q2", "timestamp": 1795300000000, "detail": { "from": "q1", "to": "q2", "screenType": "form" } }
```

| type | detail |
|---|---|
| `init` | `{ apiVersion }` |
| `ready` | `{ screens }` (number of screens) |
| `start` | `{}` |
| `input` | `{ fieldId, fieldType, answered, value? }`; `value` is **omitted for text and textarea** so nothing typed leaves the game. Perspective tabs: `{ perspectiveId }` |
| `submit` | `{ fields }`: ids of visible fields submitted |
| `feedback` | `{ count, tones }` |
| `screenchange` | `{ from, to, screenType }` |
| `progress` | `{ step, remaining, fraction }` (fraction 0–1) |
| `complete` | `{ score: { correct, total } or null, path: [screen ids] }` |
| `back` | `{ from, to }` |
| `restart` | `{}` |
| `exit` / `skip` | `{ from, completed }` |
| `error` | `{ code, messages, recoverable }`; codes: `invalid-package`, `missing-screen`, `render-error` |

On the website, events are dispatched as a bubbling DOM `CustomEvent` named `bookbuilder:game` (the
event object is `event.detail`). The site uses only `complete`, and only to remember that an activity was
finished if the reader turned on "Remember progress". There is no analytics and nothing is sent anywhere.

The Book Manager's preview page lists every event as it happens, which is the easiest way to check a
package's branching.

## Error-handling requirements for packages

- Every `next` target and every referenced field, variable, screen and asset must exist (the validator
  checks this).
- Every reachable screen must have a path to a completion screen.
- Don't depend on an answer that may be hidden or skipped: give rules a sensible `default`.
- If a runtime doesn't support a capability you list, it refuses to start the game rather than running it
  partially. Only list capabilities you use.
