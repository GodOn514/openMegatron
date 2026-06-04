---
name: citation_verifier
description: Verify numbered review citations against supplied papers or evidence matrix metadata, and format references in common styles.
entry_function: main
parameters:
  type: object
  properties:
    action:
      type: string
      description: Use verify.
    review:
      type: string
      description: Review text containing citations like [1].
    papers:
      type: array
      description: Paper metadata list.
    matrix:
      type: array
      description: Evidence matrix rows.
    path:
      type: string
      description: JSON file containing review and papers or matrix.
    citation_style:
      type: string
      description: gbt7714, ieee, apa, or bibtex. Default gbt7714.
    include_references:
      type: boolean
      description: Whether to include formatted references. Default true.
  required:
    - action
keywords: [citation, verify, references, bibliography, bibtex, review, hallucination]
---

# Citation Verifier

Checks citation indices, weak support signals, and returns formatted references for the same paper list.
