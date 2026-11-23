# Book Builder game creation prompt (Game Package API 1.1)

You are designing and building one interactive learning activity for a chapter of a nonfiction book
made with Book Builder. The book's title, audience and rules are given with the chapter below.

You have been given:

1. **The approved chapter** (below, or attached). It is the only content source. Teach what it teaches.
2. **The Game API documentation**, as one file (`book-builder-game-api-1.1.md`) or the
   `game-developer/` folder, including the JSON Schemas. Follow it exactly. Read its component
   reference, branching and state, and feedback and scoring sections before designing. If you were
   given no documentation file, the "API essentials" at the end of this prompt are enough to build a
   valid package: follow them exactly.

You do not need, and won't get, the website's source code. The website's runtime renders everything from
your two JSON files.

## Your deliverable

Three text files, plus **three images** (two image sheets and an icon; see "Images" below):

- `game.json`: the manifest
- `activity.json`: the screens and logic
- `README.md`: title, chapter, what the activity does, who made it, version notes

**Default (works in any chat): put each file in its own fenced code block, with the file name on the
line just before it**, exactly like this, and nothing else between them:

    **game.json**
    ```json
    { ... the whole file ... }
    ```

    **activity.json**
    ```json
    { ... the whole file ... }
    ```

    **README.md**
    ```markdown
    ... the whole file ...
    ```

The editor copies your whole reply, and the Book Manager reads the files out of these blocks. Never
abbreviate a file ("..." or "same as above"); always give each file in full.

If you can create downloadable files, you may also offer `<id>.zip` with the same files at its top
level. The code blocks are still required.

Never include JavaScript, HTML, SVG, CSS or any code.

**`game.json` must contain every required field**: `apiVersion`, `id`, `title`, `description`,
`version`, `chapter`, `activityType`, `learningObjectives`, `contentWarnings`, `accessibility` (with
`summary`, `"keyboard": true`, `"screenReader": true`), `requiredCapabilities`, `assets` and
`authors`. Copy the structure of the example in "API essentials" below and change the values.

## Images (required: 9 images in 3 files)

Every game has **8 scene images on 2 sheets** (each sheet one high-resolution image cut into a 2×2 grid)
and **1 square icon**, all in the book's single house look. The section "Image style for Book Builder
games" below is the complete, binding guide: follow its style block, sheet layout, icon rules and naming
exactly. Sensitive chapters get only the icon.

Plan the 8 scenes while you design the flow, so each image shows a moment from a specific screen, and the
same characters look the same in every panel.

## Steps

1. **Read the chapter.** List its 2–4 most practical ideas, the fixed terms it uses, and any safety
   points. Choose the activity that best helps a reader *practice* them, not just recall them.
2. **Pick the activity type:** `scenario` (choices in a situation, with consequences seen from more than one
   side), `practice` (rehearsing words or steps), `sorting` (grouping ideas), `reflection` (thinking about
   one's own needs), `explainer`, or `knowledge-check` (only for facts the chapter states).
3. **Design the flow on paper first:** 5–12 screens, 3–8 minutes. Start with an `info` screen that sets the
   scene, end with a `completion` screen that links the activity back to the chapter. Use branching where a
   choice should genuinely lead somewhere different, and a `perspective` screen where two people see the
   same moment differently (the book's central image: people standing in different places around the same
   sculpture, each seeing something real).
4. **Write the content** following the rules below.
5. **Write the JSON** with `"apiVersion": "1.1"` in both files. Give it an `id` of the form
   `chNN-two-to-four-words`, `version` `1.0.0`, the correct `chapter` number, the `icon`, and list every
   capability you use in `requiredCapabilities`. Use the API 1.1 features where they help: personalized
   text (`{{answer:fieldId}}`), `ranking`, `hint`, completion `takeaways` and `allowSaveNotes`.
6. **Make the images:** Sheet 1, Sheet 2 and the Icon, following the image style guide.
7. **Validate yourself** before answering: check both files against the schemas; check every `next`,
   `goto`, condition field, variable and asset exists; check every reachable screen can reach a completion
   screen; check field ids are unique across the activity; check `showIf` only uses fields above it. Then go
   through the checklist at the end of this prompt.
8. **Send the files and images** as described under "Your deliverable", then give a short summary: the flow (screen ids and branches), how it meets each
   learning objective, and anything the editor should look at.

## Content rules (non-negotiable)

- **Consent and safety first.** Never teach or reward manipulation, pressure, guilt, jealousy tactics,
  "negging", persistence after a no, or any way around consent. If a scenario includes a harmful behavior,
  it is shown so readers can recognize it, and the feedback says so plainly.
- **No gender stereotyping.** Show helpful and unhelpful patterns in people of every gender. Rotate genders,
  orientations and ages. Use fresh first names that aren't in the book's list of
  example names (if you have `continuity.md`, check "Example names already used"); never Priya, Marcus, Alex,
  Daniel, Sam, Jordan, Morgan, Elena, Mateo, Luis, Jules, Maya or Taylor. One name = one person.
- **Nuanced feedback for situations between people.** No "Correct!"/"Wrong!" for interpersonal choices.
  Explain what a choice might lead to, how it may land for the other person, and what to try. Tones:
  `neutral`, `positive`, `consider`, `caution`.
- **Scoring only for checkable facts**, only in `knowledge-check` games, with `"scored": true` and
  `"correct": true` on the right option(s). No timers, points races or penalties.
- **No labels or diagnoses.** Never tell readers what they "are" (a diagnosis or a type).
  Describe experiences: "Some people find…". Labels are optional in this book.
- **Sensitive topics** (trauma, abuse, assault, stalking, self-harm, crisis): set `"sensitive": true`, add
  content warnings, no scoring, no required answers, and point to the book's support (chapter 59) and crisis
  resources (chapter 60) instead of giving crisis advice.
- **Privacy.** Don't ask for names, contact details, locations, health details or experiences of abuse.
  Written answers are always optional; say they aren't saved.
- **Match the chapter.** Use its terms exactly: *overload* (not overwhelm or flooding), *shutdown*,
  *masking*, *boundary* (a limit on what you will do or accept) vs *request* (asks something of someone
  else, who can say no), *double empathy problem*. Don't add facts, statistics or advice the chapter
  doesn't contain. US focus.
- **Voice.** Neutral, warm handbook voice. Plain language (about grade 6–8), short sentences, one idea per
  screen, at most about five fields per form screen. US spelling. No shaming, no jokes at anyone's expense.

## Accessibility rules

- All meaning is in text; never color, images or sound alone.
- Images need alt text, are declared in `assets`, and never carry meaning the text lacks; audio
  needs a transcript asset; no autoplay, no time limits.
- Labels say exactly what to do. Sliders have `minLabel` and `maxLabel`.
- `accessibility.summary` tells readers what to expect before they start.

## Final checklist (answer each in your summary)

- [ ] `apiVersion` is `"1.1"` in both files; JSON is valid UTF-8.
- [ ] `id` matches `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$` and starts with `chNN-`.
- [ ] `chapter` is correct; objectives come from the chapter.
- [ ] Every path reaches a completion screen; no dead ends.
- [ ] Every referenced screen, field, variable and asset exists; ids are unique.
- [ ] Capabilities listed for everything used (branching, variables, perspective-switching,
      reflection-summary, scoring, images, audio, save-notes).
- [ ] No scoring outside knowledge checks; no right/wrong for interpersonal choices.
- [ ] No manipulation taught; no labels assigned; no gender stereotypes; fresh names.
- [ ] Sensitive topics marked, warned, ungraded and optional.
- [ ] `game.json` has every required field: learningObjectives, authors, and accessibility with
      summary, keyboard: true and screenReader: true.
- [ ] Each file is given in full in its own labeled code block; no code or HTML anywhere.
- [ ] Images: Sheet 1, Sheet 2 (2×2 grids, highest resolution, no borders or text) and the Icon, in
      the house style, each labeled above it; 8 scene images declared in panel order plus the icon, all
      with alt text; `"icon"` set; every scene image used once; `"images"` in requiredCapabilities.
      Sensitive chapters: icon only.
