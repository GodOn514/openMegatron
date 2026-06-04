---
name: sci_journal_search
description: Query academic journal metadata such as ISSN, publisher, impact factor, JCR/CAS quartile, citation count, and h-index.
category: research
entry_function: main
parameters:
  type: object
  properties:
    journal_name:
      type: string
      description: Target journal name, for example Nature or ACM Computing Surveys.
    fast:
      type: boolean
      description: Use faster online sources when possible.
    year:
      type: integer
      description: Optional JCR year.
  required:
    - journal_name
keywords: [journal, jcr, cas, impact factor, issn, h-index, research]
---

# SCI Journal Search

Research-category skill for checking journal metadata and ranking signals.
