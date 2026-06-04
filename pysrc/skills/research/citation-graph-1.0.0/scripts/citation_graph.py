from __future__ import annotations
import json as _json
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_common import (
    emit, fail, openalex_fetch_work, openalex_id_from_paper,
    openalex_work_to_paper, papers_from_params, parse_params,
    search_openalex, keyword_set, normalize_paper,
)


def graph_from_papers(papers, include_references=False, depth=1, max_nodes=50):
    nodes = []
    edges = []
    seen_ids = set()
    queue = [(p, 0) for p in papers]

    while queue and len(nodes) < max_nodes:
        paper, d = queue.pop(0)
        node_id = paper.get("id") or str(hash(str(paper.get("title", ""))))
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        _doi = (paper.get("doi") or "").strip()
        _link = ""
        if _doi:
            _link = f"https://doi.org/{_doi}" if _doi.startswith("10.") else _doi
        if not _link:
            _id = (paper.get("id") or "").strip()
            if _id and "openalex.org" in _id:
                _link = _id
        if not _link:
            _title_q = (paper.get("title") or "")
            if _title_q:
                import urllib.parse
                _q = urllib.parse.quote(f"{_title_q} {str(paper.get("authors") or "")[:80]}")
                _link = f"https://scholar.google.com/scholar?q={_q}"
        nodes.append({
            "id": node_id,
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "venue": paper.get("venue", ""),
            "citations": paper.get("citations") or 0,
            "doi": paper.get("doi"),
            "link": _link,
            "depth": d,
            "authors": paper.get("authors", ""),
            "type": paper.get("type", "journal"),
            "external": d > 0,
            "concepts": paper.get("concepts", []),
            "keywords": list(keyword_set(paper.get("title", "") + " " + (paper.get("abstract") or ""))),
        })

        if include_references and d < depth:
            identifier = openalex_id_from_paper(paper)
            work = openalex_fetch_work(identifier) if identifier else None
            if work:
                for ref_id in (work.get("referenced_works") or [])[:15]:
                    ref_short = ref_id.rsplit("/", 1)[-1]
                    edges.append({"source": node_id, "target": ref_short, "type": "references"})
                    if ref_short not in seen_ids and len(seen_ids) < max_nodes:
                        ref_work = openalex_fetch_work(ref_id)
                        if ref_work:
                            queue.append((openalex_work_to_paper(ref_work), d + 1))
                        else:
                            nodes.append({"id": ref_short, "title": ref_short, "external": True, "depth": d + 1, "link": f"https://openalex.org/W/{ref_short}" if ref_short.startswith("W") else ""})
                            seen_ids.add(ref_short)

    return _build_output(nodes, edges, len(papers))


def _build_output(nodes, edges, input_count):
    ranked = sorted(
        [n for n in nodes if not n.get("external")],
        key=lambda n: (int(n.get("citations") or 0), str(n.get("year") or "")),
        reverse=True,
    )

    by_year = defaultdict(list)
    for n in nodes:
        y = n.get("year")
        if y:
            by_year[int(y)].append(n)

    timeline = [
        {"year": y, "count": len(items), "papers": [n["title"] for n in items[:5]]}
        for y, items in sorted(by_year.items())
    ]

    venue_counter = Counter()
    for n in nodes:
        v = n.get("venue", "")
        if v:
            venue_counter[v] += 1

    keyword_groups = defaultdict(list)
    for n in nodes:
        for kw in n.get("keywords", [])[:3]:
            keyword_groups[kw].append(n["title"])

    clusters = [
        {"topic": kw, "size": len(items), "papers": items[:5]}
        for kw, items in sorted(keyword_groups.items(), key=lambda x: -len(x[1]))
        if len(items) >= 2
    ][:10]

    mermaid_lines = ["graph LR"]
    for e in edges[:30]:
        s = e["source"][:20]
        t = e["target"][:20]
        mermaid_lines.append("    " + s + "-->" + t)

    return {
        "nodes": nodes,
        "edges": edges,
        "representative_papers": ranked[:15],
        "timeline": timeline,
        "top_venues": venue_counter.most_common(10),
        "clusters": clusters,
        "mermaid": "\n".join(mermaid_lines),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "input_paper_count": input_count,
            "depth_reached": max((n.get("depth", 0) for n in nodes), default=0),
            "unique_venues": len(venue_counter),
            "year_span": (
                f"{min(int(y) for y in by_year.keys())}-{max(int(y) for y in by_year.keys())}"
                if by_year else "N/A"
            ),
        },
    }


def main() -> int:
    params = parse_params(sys.argv[1] if len(sys.argv) > 1 else "{}")
    action = str(params.get("action") or "build").lower()
    include_references = bool(params.get("include_references", False))
    depth = int(params.get("depth", 1))
    max_nodes = int(params.get("max_nodes", 50))

    if action == "query":
        if not params.get("query"):
            fail("Missing query for action=query.")
        papers = search_openalex(str(params["query"]), limit=int(params.get("limit", 20)))
    elif action == "expand":
        paper = params.get("paper")
        if not paper:
            fail("Missing paper for action=expand.")
        papers = [normalize_paper(paper, 0)]
        include_references = True
        depth = max(depth, 2)
    elif action == "analyze":
        if not params.get("query"):
            fail("Missing query for action=analyze.")
        papers = search_openalex(str(params["query"]), limit=int(params.get("limit", 30)))
        include_references = True
        depth = 1
    else:
        papers = papers_from_params(params)
        if not papers and params.get("query"):
            papers = search_openalex(str(params["query"]), limit=int(params.get("limit", 20)))

    if not papers:
        fail("No papers found for citation graph.")

    graph = graph_from_papers(papers, include_references=include_references, depth=depth, max_nodes=max_nodes)

    emit({"status": "success", "completed": True, "query": params.get("query"), **graph})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
