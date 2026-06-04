---
name: evidence_matrix
description: Build a structured evidence matrix and research-gap analysis from papers or paper_reader outputs for literature reviews.
entry_function: main
parameters:
  type: object
  properties:
    action:
      type: string
      description: Use build.
    papers:
      type: array
      description: Paper metadata list.
    readings:
      type: array
      description: Structured readings from paper_reader.
    path:
      type: string
      description: JSON file path containing papers or readings.
    out:
      type: string
      description: Optional JSON output path.
  required:
    - action
keywords: [evidence, matrix, literature review, synthesis, research gap, innovation]
---

# Evidence Matrix

Turns paper notes into review-ready rows and a compact gap-analysis block for topic selection and innovation framing.
