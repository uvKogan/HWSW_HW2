// Names + IDs page. Compile with:
//   typst compile --input matan-id=<ID> --input yuval-id=<ID> ids.typ ids.pdf
// Real IDs are injected at compile time (see make_submission.sh sourcing the
// gitignored report/ids.local); without them the page shows "<ID>".
#let matan-id = sys.inputs.at("matan-id", default: "<ID>")
#let yuval-id = sys.inputs.at("yuval-id", default: "<ID>")

#set page(margin: 2cm)
#align(center + horizon)[
  #text(size: 16pt, weight: "bold")[HW2 — Traditional vs Function-as-a-Service] \
  #v(0.3em)
  #text(size: 12pt)[Olympic Games Management System] \
  #v(2em)
  #text(size: 13pt)[
    Matan Cohen — ID: #matan-id \
    #v(0.4em)
    Yuval Kogan — ID: #yuval-id
  ]
]
