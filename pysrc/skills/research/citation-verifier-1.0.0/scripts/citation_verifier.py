from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_common import emit, fail, format_reference_list, normalize_papers, papers_from_params, parse_params, verify_citations


def main() -> int:
    params = parse_params(sys.argv[1] if len(sys.argv) > 1 else "{}")
    if params.get("path"):
        value = json.loads(Path(str(params["path"])).read_text(encoding="utf-8", errors="replace"))
        if isinstance(value, dict):
            params = {**value, **params}
    review = str(params.get("review") or params.get("text") or "")
    papers = papers_from_params(params)
    if not papers and params.get("matrix"):
        papers = normalize_papers(params["matrix"])
    if not review:
        fail("Missing review text.")
    if not papers:
        fail("Missing papers or matrix.")
    result = verify_citations(review, papers)
    payload = {"status": "success", "completed": True, **result}
    if params.get("include_references", True):
        payload["references"] = format_reference_list(papers, style=str(params.get("citation_style") or "gbt7714"))
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
