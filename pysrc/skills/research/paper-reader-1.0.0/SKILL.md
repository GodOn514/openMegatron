---
name: paper_reader
description: Read paper metadata, abstracts, local text/markdown/json/PDF files, web pages, DOI/OpenAlex records, and produce structured research notes for evidence matrices and gap analysis.
entry_function: main
parameters:
  type: object
  properties:
    action:
      type: string
      description: One of read, read_many.
    paper:
      type: object
      description: Paper metadata object with title, abstract, doi, url, venue, year.
    papers:
      type: array
      description: List of paper metadata objects.
    path:
      type: string
      description: Local text, markdown, json, or PDF path. PDF extraction uses pypdf when available and falls back to best-effort text recovery.
    url:
      type: string
      description: Web page, DOI URL, or OpenAlex URL.
    doi:
      type: string
      description: DOI to resolve through OpenAlex.
    max_chars:
      type: integer
      description: Maximum text characters to keep.
  required:
    - action
keywords: [paper, read, pdf, full text, abstract, doi, research notes]
---

# Paper Reader

Produces compact structured notes for later evidence matrices, including method category, contribution type, limitations, gap hints, and evidence strength.
