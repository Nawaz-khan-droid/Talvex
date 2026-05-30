// TALVEX Functional Resume Template
// Skills-first format — emphasizes competencies over chronology
// Font: Carlito (metric-compatible with Calibri), fallback to Liberation Sans

#set page(
  paper: "us-letter",
  margin: (top: 0.6in, bottom: 0.6in, left: 0.75in, right: 0.75in),
)

#set text(
  font: ("Carlito", "Liberation Sans", "DejaVu Sans"),
  size: 11pt,
  lang: "en",
)

#set par(leading: 0.65em, justify: true, first-line-indent: 0em)
#set list(marker: "•", indent: 0.35in, body-indent: 0.1in)
#set enum(numbering: "1.", indent: 0.35in, body-indent: 0.1in)

// ---- Color palette ----
#let accent = rgb("#2c3e50")
#let body-color = rgb("#333333")
#let muted = rgb("#666666")

// ---- Reusable heading style ----
#let section-heading(title) = {
  v(12pt)
  text(size: 13pt, weight: "bold", fill: accent, tracking: 0.5pt)[
    #upper(title)
  ]
  v(2pt)
  line(length: 100%, stroke: 0.8pt + accent)
  v(6pt)
}

// ==== HEADER ====
#set align(center)
#text(size: 22pt, weight: "bold", fill: accent, tracking: 1pt)[
  #full_name
]
#v(4pt)
#text(size: 9.5pt, fill: muted)[#contact_line]
#line(length: 100%, stroke: 1.2pt + accent)
#v(10pt)

// ==== PROFESSIONAL SUMMARY ====
#set align(left)
#section-heading("Professional Summary")
#text(size: 11pt, fill: body-color)[
  #professional_summary
]

// ==== RELEVANT SKILLS & THEMATIC ACCOMPLISHMENTS ====
#section-heading("Relevant Skills & Thematic Accomplishments")
#skills_section

// ==== WORK HISTORY (brief) ====
#section-heading("Work History")
#work_experience

// ==== EDUCATION ====
#section-heading("Education")
#education
