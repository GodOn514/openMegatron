from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_common import (  # noqa: E402
    analyze_research_gaps,
    build_evidence_matrix,
    build_review_protocol,
    emit,
    fail,
    format_reference_list,
    normalize_papers,
    parse_params,
    reading_from_paper,
    verify_citations,
)


def top_paper_script() -> Path:
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "top_paper_search-1.0.0" / "scripts" / "top_paper_search.py"


def run_top_paper(params: dict) -> dict:
    script = top_paper_script()
    if not script.exists():
        fail("top_paper_search skill is missing.")
    payload = {
        "action": "review" if params.get("generate_review", True) else "fetch",
        "query": params["query"],
        "year_start": params.get("year_start"),
        "limit": int(params.get("limit") or 100),
        "top_n": int(params.get("top_n") or 8),
        "generate_review": bool(params.get("generate_review", True)),
        "domain": params.get("domain"),
        "fill_abstracts": bool(params.get("fill_abstracts", True)),
        "abstract_limit": int(params.get("abstract_limit") or 8),
    }
    proc = subprocess.run(
        [sys.executable, str(script), json.dumps(payload, ensure_ascii=False)],
        cwd=str(script.parents[1]),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=int(params.get("timeout") or 240),
    )
    if proc.returncode != 0:
        fail((proc.stderr or proc.stdout or "top_paper_search failed")[:1200])
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        fail(f"Could not parse top_paper_search output: {exc}")


def fallback_review(query: str, matrix: list[dict], gap_analysis: dict) -> str:
    lines = [
        f"# {query} 文献综述草稿",
        "",
        "## 一、研究现状概览",
    ]
    if not matrix:
        lines.append("未检索到符合顶刊顶会白名单的候选文献，不能生成可靠综述。")
        return "\n".join(lines)
    for row in matrix:
        lines.append(
            f"- {row['citation_hint']} {row['title']}（{row.get('year') or 'n.d.'}，"
            f"{row.get('venue') or 'unknown'}）主要涉及 {row.get('method_category')}，"
            f"贡献类型为 {row.get('contribution_type')}。"
        )
    lines.extend([
        "",
        "## 二、方法脉络",
        "现有证据可先按方法类别、贡献类型和评测设置拆分，再比较各方向在可靠性、可扩展性和领域适配上的差异。",
        "",
        "## 三、研究空白与创新方向",
    ])
    for item in gap_analysis.get("potential_innovation_directions", []):
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## 四、证据边界",
        "本草稿基于题名、摘要、venue 和引用数等元数据生成；涉及实验细节、数据集、指标和定量结论时，需要继续读取 PDF 全文。",
    ])
    return "\n".join(lines)


def main() -> int:
    params = parse_params(sys.argv[1] if len(sys.argv) > 1 else "{}")
    if str(params.get("action") or "run").lower() != "run":
        fail("review_pipeline only supports action=run.")
    if not params.get("query"):
        fail("Missing query.")

    search_result = run_top_paper(params)
    effective_domain = search_result.get("effective_domain", params.get("domain"))
    papers = normalize_papers(search_result.get("papers", []))
    readings = [reading_from_paper(paper) for paper in papers]
    matrix = build_evidence_matrix(papers)
    gap_analysis = analyze_research_gaps(matrix)
    review = search_result.get("review") or fallback_review(str(params["query"]), matrix, gap_analysis)
    verification = verify_citations(review, papers) if papers else {"verdict": "no_papers", "issues": []}
    references = format_reference_list(papers, style=str(params.get("citation_style") or "gbt7714"))
    protocol = build_review_protocol(
        str(params["query"]),
        review_type=str(params.get("review_type") or "narrative"),
        year_start=params.get("year_start"),
        top_n=params.get("top_n"),
        domain=effective_domain,
    )
    payload = {
        "status": "success",
        "completed": True,
        "query": params["query"],
        "protocol": protocol,
        "search": {
            "filter_mode": search_result.get("filter_mode"),
            "venue_policy": search_result.get("venue_policy"),
            "requested_domain": search_result.get("requested_domain", params.get("domain")),
            "effective_domain": effective_domain,
            "effective_query": search_result.get("effective_query"),
            "total_fetched": search_result.get("total_fetched"),
            "valid_count": search_result.get("valid_count"),
        },
        "papers": papers,
        "readings": readings,
        "evidence_matrix": matrix,
        "gap_analysis": gap_analysis,
        "review": review,
        "references": references,
        "citation_verification": verification,
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
