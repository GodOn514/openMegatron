from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_common import analyze_research_gaps, build_evidence_matrix, emit, fail, normalize_paper, papers_from_params, parse_params


def papers_from_readings(readings):
    papers = []
    for idx, item in enumerate(readings or []):
        if isinstance(item, dict):
            papers.append(normalize_paper({
                "id": item.get("id") or str(idx + 1),
                "title": item.get("title"),
                "year": item.get("year"),
                "venue": item.get("venue"),
                "doi": item.get("doi"),
                "url": item.get("url"),
                "abstract": item.get("evidence_text") or item.get("key_findings") or item.get("core_problem"),
            }, idx))
    return papers


def main() -> int:
    params = parse_params(sys.argv[1] if len(sys.argv) > 1 else "{}")
    papers = papers_from_params(params)
    if not papers and params.get("readings"):
        papers = papers_from_readings(params.get("readings"))
    if not papers and params.get("path"):
        value = json.loads(Path(str(params["path"])).read_text(encoding="utf-8", errors="replace"))
        papers = papers_from_readings(value.get("readings")) if isinstance(value, dict) else []
        if not papers:
            params["papers"] = value
            papers = papers_from_params(params)
    if not papers:
        fail("No papers/readings found for evidence matrix.")
    matrix = build_evidence_matrix(papers)
    payload = {
        "status": "success",
        "completed": True,
        "count": len(matrix),
        "matrix": matrix,
        "gap_analysis": analyze_research_gaps(matrix),
    }
    if params.get("out"):
        out = Path(str(params["out"])).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["out"] = str(out)
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
