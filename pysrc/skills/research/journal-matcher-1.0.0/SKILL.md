---
name: journal_matcher
description: Match paper metadata (title, abstract, keywords, field) to recommended target journals and conferences, with impact factor, JCR/CAS quartile, review cycle, and acceptance rate.
category: research
entry_function: main
parameters:
  type: object
  properties:
    title:
      type: string
      description: Paper title.
    abstract:
      type: string
      description: Paper abstract.
    keywords:
      type: array
      description: Paper keywords.
      items:
        type: string
    field:
      type: string
      description: Research field to narrow matching scope.
    top_k:
      type: integer
      description: Number of top recommendations (default 5, max 15).
    used_journals:
      type: array
      description: Already-published-in journal names to filter out.
      items:
        type: string
    include_conferences:
      type: boolean
      description: Whether to include top conferences (default true).
    online:
      type: boolean
      description: Query OpenAlex for real-time impact factor and citation data (default true).
    lang:
      type: string
      description: Output language, zh or en (default zh).
  required:
    - title
    - abstract
keywords: [journal, conference, match, recommend, impact factor, quartile, submission, research]
---

# Journal Matcher

Recommends suitable target journals and conferences for a paper based on its title, abstract, keywords, and research field. Returns ranked results with impact factors, quartiles, typical review timelines, and acceptance rates.

