---
name: review_pipeline
description: "Run the research assistant workflow: configured top-venue search, paper reading, evidence matrix, research gap analysis, optional review generation, reference formatting, and citation verification."
entry_function: main
parameters:
  type: object
  properties:
    action:
      type: string
      description: Use run.
    query:
      type: string
      description: Research topic query.
    year_start:
      type: integer
      description: Earliest paper year.
    limit:
      type: integer
      description: Candidate search limit. Default 100.
    top_n:
      type: integer
      description: Number of papers to keep. Default 8.
    generate_review:
      type: boolean
      description: Whether to call the configured LLM for a Chinese review.
    review_type:
      type: string
      description: narrative or systematic. Controls the protocol metadata.
    citation_style:
      type: string
      description: gbt7714, ieee, apa, or bibtex. Default gbt7714.
    domain:
      type: string
      description: Optional venue-policy domain such as ai, nlp, cv, data, hci, cs, is, management, medicine. Use management for 信管/信息管理/信息系统/MIS topics; use hci for human-AI collaboration or human-computer interaction when the user did not ask for a management/IS lens.
    fill_abstracts:
      type: boolean
      description: Whether to enrich missing abstracts for final candidates. Default true.
    out:
      type: string
      description: Optional JSON output path.
  required:
    - action
    - query
keywords: [review pipeline, literature review, systematic review, evidence matrix, citation verification, research gap, innovation]
---

# Review Pipeline

Chains installed research skills into a single tested workflow. The output includes the active top-venue policy, protocol, readings, evidence matrix, gap analysis, review draft, formatted references, and citation verification.
