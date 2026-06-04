---
name: zotero_manager
description: Manage Zotero Desktop through the local API. Use for status checks, enabling the local API, searching items, listing inventory/collections/tags, and exporting BibTeX.
entry_function: main
parameters:
  type: object
  properties:
    action:
      type: string
      description: One of status, enable, search, inventory, collections, tags, export_bibtex.
    query:
      type: string
      description: Search text for action=search.
    limit:
      type: integer
      description: Maximum rows to return. Default 20.
    item_key:
      type: string
      description: Zotero item key for BibTeX export.
    out:
      type: string
      description: Optional output .bib path for action=export_bibtex.
    restart:
      type: boolean
      description: Restart Zotero after enabling local API.
  required:
    - action
keywords: [zotero, citation, bibtex, reference, literature, local api]
---

# Zotero Manager

Small-context skill. Call `run_skill_script` with one JSON object.

Examples:

```json
{"action":"status"}
{"action":"search","query":"retrieval augmented generation","limit":10}
{"action":"export_bibtex","item_key":"ABCD1234","out":"references.bib"}
```

Requires Zotero Desktop local API at `http://127.0.0.1:23119`.
