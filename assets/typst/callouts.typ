// Typst additions for the PDF (included via --include-in-header).
// Fonts and colors: set them per book in Book Builder › Design › Brand Kit.

// ---------------------------------------------------------------- brand palette
#let ink = rgb("#171717")
#let paper = rgb("#F7F6F2")
#let charcoal = rgb("#3D3D3D")
#let soft-gray = rgb("#D9D9D9")
#let mustard = rgb("#E3AC19")
#let teal = rgb("#0B858B")
#let violet = rgb("#926A98")

#let display-font = "Playfair Display"         // title and headings (Black 900)
#let body-font = "Source Serif 4"              // printed body text
#let ui-font = "Source Sans 3"                 // subtitles, captions, callouts, running heads

#set document(title: book-title)
#set text(font: body-font, fill: ink)
#show heading: set text(font: display-font, weight: 900, fill: ink, hyphenate: false)
#show heading: set par(justify: false)
#show heading.where(level: 1): set text(size: 22pt)
#show heading.where(level: 2): set text(size: 14pt)
#show heading.where(level: 3): set text(size: 11.5pt)
#show link: set text(fill: ink)
// Tables: narrow columns, so no justification or hyphenation, and left-aligned.
#show table: set par(justify: false)
#show table: set text(hyphenate: false, size: 0.92em)
#set table(stroke: (x, y) => if y == 0 { (bottom: 0.7pt + ink) } else { (bottom: 0.4pt + soft-gray) }, inset: (x: 5pt, y: 5pt))

// Each chapter (level-1 heading) starts on a new page, with a short mustard
// rule under the title: the brand's one accent mark.
// Part headings are marked with supplement [Part] and handled by part-title.
#show heading.where(level: 1): it => {
  if it.supplement == [Part] { it } else {
    pagebreak(weak: true)
    v(1.5em)
    it
    v(-0.2em)
    line(length: 2.4em, stroke: 2.5pt + mustard)
    v(0.6em)
  }
}

// PDF bookmarks list every heading (parts, chapters, sections) when enabled, even when the
// printed contents is simple. `pdf-bookmarks` and `toc-links` come from tools/build.py.
#set heading(bookmarked: pdf-bookmarks)

// Printed contents: part names as small caps-style labels, chapter titles indented under them,
// section headings (detailed contents only) indented again; light dot leaders.
#set outline.entry(fill: box(width: 1fr, repeat(gap: 0.45em)[#text(fill: soft-gray)[.]]))
#show outline.entry: it => {
  let target = it.element
  let is-part = target.func() == heading and target.supplement == [Part]
  let linked(body) = if toc-links { link(target.location(), body) } else { body }
  if is-part {
    v(1.1em, weak: true)
    block(sticky: true, below: 0.5em, linked(text(font: ui-font, weight: 700, size: 0.78em, tracking: 0.08em, fill: charcoal, upper(target.body))))
  } else {
    let entry = if toc-links { it } else {
      block(grid(columns: (1fr, auto), column-gutter: 0.6em, [#target.body #box(width: 1fr, repeat(gap: 0.45em)[#text(fill: soft-gray)[.]])], it.page()))
    }
    pad(left: if it.level == 1 { 0.9em } else { 2.2em }, entry)
  }
}
#show outline.entry.where(level: 1): set block(above: 0.55em)

// Part title page (used by assets/filters/callouts.lua for headings with class .part).
#let part-title(title) = {
  pagebreak(weak: true)
  align(center + horizon)[
    #show heading: set text(size: 26pt, weight: 900)
    #heading(level: 1, supplement: [Part], numbering: none, title)
    #v(0.6em)
    #line(length: 3em, stroke: 3pt + mustard)
  ]
  pagebreak()
}

// Callout boxes for perspective, neurotype and partner notes (used by
// assets/filters/callouts.lua). Accent colors are decorative only: the label
// text stays ink-black so it keeps full contrast.
#let callout(kind: "perspective", label: "", body) = {
  let accent = if kind == "perspective" { violet } else if kind == "partner" { mustard } else { teal }
  block(
    width: 100%,
    inset: (x: 12pt, y: 10pt),
    radius: 3pt,
    fill: accent.lighten(88%),
    stroke: (left: 3pt + accent),
    breakable: true,
  )[
    // Callouts are short asides: block-spaced and flush, matching book.css.
    #set par(first-line-indent: 0pt, spacing: 1em)
    #set text(font: ui-font, size: 0.92em)
    #text(weight: 600)[#label]
    #v(2pt)
    #body
  ]
}

// ---------------------------------------------------------------- book typography
// Paragraphs are indented rather than separated by blank lines, which is what
// distinguishes a typeset book from a report. The first paragraph after a
// heading stays flush, as it should.
#set par(first-line-indent: (amount: 1.2em, all: false), spacing: 0.65em)

// The reference list: Pandoc's template sets zero spacing between entries,
// which made each entry's last line collide with the next. Give each entry its
// own space and a hanging indent, with no first-line indent.
#show <refs>: it => {
  set par(first-line-indent: 0pt, hanging-indent: 1.5em, spacing: 0.75em, justify: false)
  set block(above: 0.8em, below: 0.8em)
  it
}

// Running heads: book title on the left-hand page, current chapter on the
// right. Suppressed on page 1 and on any page where a chapter opens, following
// normal book practice.
#set page(header: context {
  let n = counter(page).at(here()).first()
  if n <= 1 { return }
  let opens-here = query(heading.where(level: 1))
    .filter(h => h.location().page() == here().page())
  if opens-here.len() > 0 { return }
  let before = query(heading.where(level: 1).before(here()))
  set text(font: ui-font, size: 8pt, fill: charcoal)
  if calc.even(n) {
    align(left, lower(book-title))
  } else if before.len() > 0 {
    align(right, before.last().body)
  }
})
