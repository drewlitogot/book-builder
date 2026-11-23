// Cover and title page for the PDF (included via --include-before-body).
// COVER_PATH and the text below are filled in by tools/build.py.

#page(margin: 0pt, header: none, footer: none)[
  #image("COVER_PATH", width: 100%, height: 100%, fit: "cover")
]

#page(header: none, footer: none)[
  #set par(first-line-indent: 0pt, justify: false)
  #set text(hyphenate: false)
  #v(1fr)
  // The book's logo (assets/branding/logo-black.png), alt text: TITLE_LOWER
  #image("LOGO_PATH", width: 88%)
  #v(0.9em)
  #text(font: ui-font, weight: 500, size: 13pt, fill: charcoal)[SUBTITLE]
  #v(2.2fr)
  // CREDITS-START
  #text(font: ui-font, weight: 700, size: 11pt, tracking: 0.04em, fill: ink)[AUTHOR]
  #v(0.35em)
  #text(font: ui-font, size: 9.5pt, fill: charcoal)[CREATED_BY]
  #v(0.15em)
  #text(font: ui-font, size: 9.5pt, fill: charcoal)[CREDIT_LINE]
  // CREDITS-END
]

// ABOUT-START
#page(header: none, footer: none)[
  #set par(first-line-indent: 0pt, justify: false)
  #v(1fr)
  #text(font: ui-font, weight: 700, size: 9.5pt, fill: ink)[About this book and its authors]
  #v(0.5em)
  #text(font: ui-font, size: 8.5pt, fill: charcoal)[ABOUT_AUTHORS]
  #v(1.2em)
  #text(font: ui-font, size: 8.5pt, fill: charcoal)[RIGHTS]
]
// ABOUT-END

#counter(page).update(1)
