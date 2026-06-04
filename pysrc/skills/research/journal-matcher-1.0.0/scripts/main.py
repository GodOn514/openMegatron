from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    try:
        params = json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {exc}", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)

    title = params.get("title", "")
    abstract = params.get("abstract", "")
    keywords = params.get("keywords", [])
    field = params.get("field", "")
    top_k = min(int(params.get("top_k", 5)), 15)
    used = params.get("used_journals", [])
    include_conferences = params.get("include_conferences", True)
    lang = params.get("lang", "zh")

    if not title and not abstract:
        print(json.dumps({"status": "error", "message": "Missing title or abstract.", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)

    from matcher import JournalMatcher
    matcher = JournalMatcher(base_dir=str(Path(__file__).parent))

    results = matcher.match(
        title=title,
        abstract=abstract,
        keywords=keywords,
        field=field,
        top_k=top_k,
        used_journals=used,
        include_conferences=include_conferences,
    )

    # Enhance with online data
    if params.get("online", True):
        from matcher import enhance_with_online
        results = enhance_with_online(results, top_k)

    if lang == "zh":
        output = format_results_zh(results)
    else:
        output = format_results_en(results)

    print(json.dumps({"status": "success", "completed": True, "result": output}, ensure_ascii=False, indent=2))


def format_results_zh(results: list) -> dict:
    return {
        "recommendations": [{
            "rank": i + 1,
            "name": r["name"],
            "type": "期刊" if r["type"] == "journal" else "会议",
            "match_score": round(r["score"] * 100, 1),
            "impact_factor": r.get("if_latest", "-"),
            "jcr_quartile": r.get("jcr", "-"),
            "cas_quartile": r.get("cas", "-"),
            "ccf_level": r.get("ccf", "-"),
            "review_cycle": f"{r['review_months'][0]}-{r['review_months'][1]} 个月" if r.get("review_months") else "-",
            "acceptance_rate": r.get("acceptance", "-"),
            "match_reason": r.get("match_reason", ""),
            "link": r.get("openalex_id", "") or (f"https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber={r.get('punumber', '')}" if r.get("punumber") else f"https://scholar.google.com/scholar?q={r['name']}"),
        } for i, r in enumerate(results)],
        "total_matched": len(results),
        "note": "数据基于内置期刊画像库，建议投稿前核实官方最新信息。"
    }


def format_results_en(results: list) -> dict:
    return {
        "recommendations": [{
            "rank": i + 1,
            "name": r["name"],
            "type": "Journal" if r["type"] == "journal" else "Conference",
            "match_score": round(r["score"] * 100, 1),
            "impact_factor": r.get("if_latest", "-"),
            "jcr_quartile": r.get("jcr", "-"),
            "cas_quartile": r.get("cas", "-"),
            "ccf_level": r.get("ccf", "-"),
            "review_cycle": f"{r['review_months'][0]}-{r['review_months'][1]} months" if r.get("review_months") else "-",
            "acceptance_rate": r.get("acceptance", "-"),
            "match_reason": r.get("match_reason", ""),
            "link": r.get("openalex_id", "") or (f"https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber={r.get('punumber', '')}" if r.get("punumber") else f"https://scholar.google.com/scholar?q={r['name']}"),
        } for i, r in enumerate(results)],
        "total_matched": len(results),
        "note": "Data based on built-in journal profiles; verify against official sources before submission."
    }


if __name__ == "__main__":
    main()


