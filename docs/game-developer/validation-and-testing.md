# Validation and testing

## Commands (book repository)

```bash
python tools/games.py validate path/to/game.zip      # check only; prints errors and warnings
python tools/games.py import path/to/game.zip        # validate and install for review
python tools/games.py import path/to/game.zip --replace   # update an installed game (higher version)
python tools/games.py list                           # installed games and status
python tools/games.py approve ch23-reading-short-texts
python tools/games.py export ch23-reading-short-texts
```

In the Book Manager: **Games** view → *Validate only…* or *Import Game ZIP…*, then *Preview*.

## What is checked

**Errors** (the package is rejected):

- unsafe or disallowed ZIP contents (see [privacy-and-security.md](privacy-and-security.md));
- missing or invalid JSON, unsupported `apiVersion`, schema violations (with the path of each problem);
- chapter doesn't exist;
- duplicate screen or field ids; unknown `start` or `next` targets; conditions that refer to unknown
  fields, variables or screens; `showIf` that depends on a later field; field conditions without exactly one
  operator;
- effects on undeclared variables, or `add` on a non-number;
- assets present but undeclared, declared but missing, wrong type, contents not matching the extension,
  images without alt text, audio without a transcript;
- no reachable completion screen, or a reachable screen with no path to one;
- scoring outside `knowledge-check`, `correct` without `scored`, scored fields without a correct option;
- sensitive games that are scored, have no content warning, or require answers;
- HTML or scripts in text, non-https links.

**Warnings** (installed, but the editor should check them before approving):

- the chapter isn't approved yet (the game can't be published until it is);
- unreachable screens; capabilities used but not listed;
- sliders without end labels; required written answers;
- text that mentions abuse, assault, trauma or crisis in a game not marked sensitive;
- editorial review flags: phrases associated with manipulation (e.g. "wear them down", "negging") or with
  labelling the reader ("you are …", "your type is"). These are prompts for a human, not
  automatic rejections: a game may name a tactic in order to warn against it.

## Error messages

Messages name the file and the location, e.g.
`activity.json screens/3/fields/0: 'options' is a required property` or
`screen choose: next goes to unknown screen 'aftr'`. Fix each one and validate again.

## Manual test checklist

1. Play every branch to every completion screen (the preview's event log shows the path).
2. Press Back from every screen; answers should come back as they were.
3. Restart from the completion screen.
4. Try Continue with required fields empty; check the messages.
5. Skip from the introduction card; Leave from the middle.
6. Keyboard only, then a screen reader (see [accessibility.md](accessibility.md)).
7. Phone width, dark mode, largest text size.
8. Read all feedback against the chapter and the editorial rules in
   [feedback-and-scoring.md](feedback-and-scoring.md).

## For runtime developers

The runtime is tested with synthetic fixtures (`tests/fixtures/games/`) covering every component,
branch rules, conditional fields, feedback, lifecycle events, completion, restart and error handling:
`cd site && npm test`, and `python -m unittest discover tests` for the importer.
