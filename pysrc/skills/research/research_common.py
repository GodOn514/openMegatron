from __future__ import annotations

import json
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import requests
except Exception:
    requests = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


HEADERS = {"User-Agent": "MegatronResearchAssistant/1.0"}
RESEARCH_DIR = Path(__file__).resolve().parent
CONFIG_DIR = RESEARCH_DIR / "config"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def fail(message: str, *, completed: bool = False) -> None:
    emit({"status": "error", "message": message, "completed": completed})
    raise SystemExit(1)


def parse_params(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON argument: {exc}")
    if not isinstance(value, dict):
        fail("First argument must be a JSON object.")
    return value


def compact_text(text: Any, *, max_chars: int = 12000) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value[:max_chars]


def load_research_config(name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    filename = name if name.endswith(".toml") else f"{name}.toml"
    path = CONFIG_DIR / filename
    if not path.exists():
        return default or {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        return data if isinstance(data, dict) else (default or {})
    except Exception:
        return default or {}
def _clean_issn(value: Any) -> str:
    return re.sub(r"[^0-9Xx]", "", str(value or "")).upper()


def normalize_venue_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _domain_allowed(record: dict[str, Any], domain: str | None) -> bool:
    if not domain:
        return True
    domains = {str(x).lower() for x in _as_list(record.get("domain"))}
    return not domains or str(domain).lower() in domains or "general" in domains


def venue_policy(domain: str | None = None) -> dict[str, Any]:
    data = load_research_config("venues", {})
    records = [v for v in data.get("venues", []) if isinstance(v, dict) and _domain_allowed(v, domain)]
    prefixes = [normalize_venue_name(x) for x in data.get("matching", {}).get("prefixes", [])]
    alias_map: dict[str, dict[str, Any]] = {}
    issn_map: dict[str, dict[str, Any]] = {}
    for record in records:
        names = [record.get("name"), *_as_list(record.get("aliases"))]
        for name in names:
            key = normalize_venue_name(str(name or ""))
            if key:
                alias_map[key] = record
        for issn in _as_list(record.get("issn")):
            clean = _clean_issn(issn)
            if clean:
                issn_map[clean] = record
    return {
        "strict": bool(data.get("strict_top_venue", True)),
        "prefixes": [p for p in prefixes if p],
        "aliases": alias_map,
        "issns": issn_map,
        "records": records,
    }


def match_top_venue(venue: str, issn_clean: str = "", domain: str | None = None) -> dict[str, Any] | None:
    policy = venue_policy(domain)
    issn = _clean_issn(issn_clean)
    if issn and issn in policy["issns"]:
        return policy["issns"][issn]
    normalized = normalize_venue_name(venue)
    if not normalized:
        return None
    aliases: dict[str, dict[str, Any]] = policy["aliases"]
    if normalized in aliases:
        return aliases[normalized]
    padded = f" {normalized} "
    for alias, record in aliases.items():
        record_type = str(record.get("type") or "").lower()
        if record_type == "conference" and len(alias) >= 4 and f" {alias} " in padded:
            return record
    for prefix in policy["prefixes"]:
        if normalized == prefix or normalized.startswith(prefix + " "):
            return {
                "name": venue,
                "type": "journal",
                "tier": "top-prefix",
                "domain": ["general"],
                "source": "prefix-policy",
            }
    return None


def is_top_venue_configured(venue: str, issn_clean: str = "", domain: str | None = None) -> bool:
    return match_top_venue(venue, issn_clean, domain) is not None


def venue_score(venue: str, issn_clean: str = "", domain: str | None = None) -> int:
    matched = match_top_venue(venue, issn_clean, domain)
    if not matched:
        return 0
    tier = str(matched.get("tier", "")).lower()
    if tier in ("top", "ccf-a", "jcr-q1", "cas-c1", "ieee-transactions"):
        return 3
    if tier in ("ccf-b", "jcr-q2", "cas-c2", "top-prefix"):
        return 2
    if tier in ("ccf-c", "jcr-q3", "cas-c3"):
        return 1
    return 0


def venue_policy_summary(domain: str | None = None) -> dict[str, Any]:
    policy = venue_policy(domain)
    flags = []
    if policy["strict"]:
        flags.append("strict")
    venues = list({r.get("name", "?") for r in policy["records"]})
    return {
        "count": len(policy["records"]),
        "strict": policy["strict"],
        "domains": [domain] if domain else None,
        "venues": venues[:20],
    }

def keyword_set(text: str) -> set[str]:
    lowered_text = (text or "").lower()
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", lowered_text)
    zh_map = {
        "检索": ["retrieval", "rag"],
        "增强": ["augmented"],
        "记忆": ["memory"],
        "长期": ["long-term"],
        "规划": ["planning"],
        "推理": ["reasoning"],
        "反馈": ["reflection"],
        "幻觉": ["hallucination"],
        "智能体": ["agent", "agents"],
        "自主": ["autonomous"],
        "决策": ["decision"],
        "强化学习": ["reinforcement", "learning"],
        "医疗": ["medical", "clinical"],
        "生物医学": ["biomedicine"],
        "自适应": ["self-adaptive"],
        "多智能体": ["multi-agent"],
    }
    expanded: list[str] = []
    for zh, mapped in zh_map.items():
        if zh in lowered_text:
            expanded.extend(mapped)
    tokens.extend(expanded)
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "are", "was", "were", "large",
        "language", "model", "models", "paper", "study", "survey", "method", "methods",
        "limitations", "limitation", "available", "explicit", "abstract", "requires", "require",
        "not", "need", "needs", "mostly", "metadata", "signal",
    }
    return {tok for tok in tokens if tok not in stop}


def overlap_score(left: str, right: str) -> float:
    a = keyword_set(left)
    b = keyword_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def infer_method(text: str) -> str:
    lowered = (text or "").lower()
    review_terms = ["systematic review", "meta-analysis", "meta analysis", "evidence synthesis"]
    if any(term in lowered for term in review_terms):
        return "systematic review / meta-analysis"

    def has_marker(marker: str) -> bool:
        if marker in {"rag", "rl"}:
            return re.search(rf"\b{re.escape(marker)}\b", lowered) is not None
        return marker in lowered

    rules = [
        ("retrieval / RAG", ["retrieval", "rag", "knowledge base", "vector", "检索"]),
        ("memory systems", ["memory", "long-term", "episodic", "记忆", "长期"]),
        ("reasoning / planning", ["reasoning", "planning", "system 2", "chain-of-thought", "决策", "规划", "推理"]),
        ("reinforcement learning", ["reinforcement learning", "reward", "policy", "rl", "强化学习"]),
        ("multi-agent systems", ["multi-agent", "agents", "collaborative", "orchestration", "多智能体"]),
        ("self-adaptive systems", ["self-adaptive", "feedback loop", "monitoring", "execution", "自适应"]),
        ("evaluation / reliability", ["hallucination", "evaluation", "benchmark", "certainty", "safety", "幻觉"]),
        ("domain application", ["biomedicine", "clinical", "medical", "robot", "iot", "aiot", "医疗"]),
    ]
    hits = [label for label, needles in rules if any(has_marker(n) for n in needles)]
    return "; ".join(hits[:3]) if hits else "general / conceptual"


def infer_contribution_type(text: str) -> str:
    lowered = (text or "").lower()
    if any(k in lowered for k in ["systematic review", "meta-analysis", "meta analysis", "evidence synthesis"]):
        return "review / meta-analysis / evidence synthesis"
    if any(k in lowered for k in ["benchmark", "dataset", "evaluation", "基准"]):
        return "benchmark / survey / evaluation"
    if any(k in lowered for k in ["framework", "architecture", "system", "agent", "框架", "系统"]):
        return "system / framework"
    if any(k in lowered for k in ["algorithm", "optimization", "training", "算法", "训练"]):
        return "algorithm / training method"
    if any(k in lowered for k in ["application", "case study", "clinical", "应用"]):
        return "application / case study"
    return "conceptual / empirical"


def infer_findings(text: str) -> str:
    text_c = compact_text(text, max_chars=2000)
    sentences = re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", text_c)
    preferred = []
    for sentence in sentences:
        low = sentence.lower()
        if any(k in low for k in ["show", "find", "propose", "improve", "demonstrate", "indicate", "suggest"]):
            preferred.append(sentence.strip())
    return compact_text(" ".join(preferred[:2] or sentences[:2]), max_chars=700)


def infer_limitations(text: str) -> str:
    lowered = (text or "").lower()
    hints = []
    if "hallucination" in lowered or "幻觉" in lowered:
        hints.append("requires hallucination detection and uncertainty control")
    if "privacy" in lowered or "clinical" in lowered or "biomedicine" in lowered or "隐私" in lowered:
        hints.append("privacy, governance, and domain validation are critical")
    if "survey" in lowered or "review" in lowered or "综述" in lowered:
        hints.append("mostly synthesizes literature and needs task-specific empirical validation")
    if "autonomous" in lowered or "decision" in lowered or "自主" in lowered or "决策" in lowered:
        hints.append("deployment risk rises in open-ended decision environments")
    if "memory" in lowered or "记忆" in lowered:
        hints.append("long-term consistency, update policy, and forgetting control need explicit evaluation")
    return "; ".join(hints) if hints else "limitations are not explicit in the available abstract"


def infer_evidence_strength(paper: dict[str, Any]) -> str:
    abstract_len = len(paper.get("abstract") or paper.get("text") or "")
    citations = int(paper.get("citations") or 0)
    if abstract_len >= 500 and citations >= 100:
        return "strong metadata signal"
    if abstract_len >= 300 or citations >= 25:
        return "moderate metadata signal"
    return "weak metadata signal"

def normalize_paper(raw: dict[str, Any], index: int = 0) -> dict[str, Any]:
    raw = raw or {}
    authors_raw = raw.get("authors")
    str_authors = authors_raw if isinstance(authors_raw, str) else (", ".join(authors_raw) if isinstance(authors_raw, list) else "")
    doi = (raw.get("doi") or "").strip()
    url = (raw.get("url") or "").strip()
    citations = raw.get("citations") or raw.get("cited_by_count") or 0

    # Build best available link
    link = ""
    if doi:
        link = f"https://doi.org/{doi}" if doi.startswith("10.") else doi
    if not link and url:
        link = url
    if not link:
        oid = (raw.get("openalex_id") or raw.get("id") or "").strip()
        if oid and "openalex.org" in oid:
            link = oid
    if not link:
        title_q = (raw.get("title") or "")
        if title_q:
            q = urllib.parse.quote(f'{title_q} {str_authors[:80]}')
            link = f"https://scholar.google.com/scholar?q={q}"

    return {
        "id": raw.get("id") or f"ref{index}",
        "title": raw.get("title") or "Untitled",
        "authors": str_authors or "Unknown",
        "year": raw.get("year") or "n.d.",
        "venue": raw.get("venue") or "Unknown venue",
        "doi": doi,
        "url": url,
        "link": link,
        "citations": int(citations) if citations else 0,
        "abstract": raw.get("abstract") or raw.get("text") or "",
        "source_quality": raw.get("source_quality") or "from_openalex" if doi or url else "user_provided",
        "evidence_text": raw.get("evidence_text") or raw.get("key_findings") or raw.get("core_problem") or "",
    }


def normalize_papers(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, dict):
        value = [value]
    return [normalize_paper(item, idx) for idx, item in enumerate(value)]


def papers_from_params(params: dict[str, Any]) -> list[dict[str, Any]]:
    papers = params.get("papers") or params.get("items") or []
    if not papers and params.get("path"):
        path = Path(str(params["path"]))
        if path.exists():
            import json
            try:
                raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, list):
                    papers = raw
                elif isinstance(raw, dict):
                    papers = raw.get("papers") or raw.get("items") or [raw]
            except Exception:
                pass
    return normalize_papers(papers)


def reading_from_paper(paper: dict[str, Any]) -> dict[str, Any]:
    text = paper.get("abstract") or paper.get("text") or ""
    combined = f"{paper.get('title', '')}. {text}"
    return {
        "id": paper.get("id"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "venue": paper.get("venue"),
        "doi": paper.get("doi"),
        "url": paper.get("url"),
        "link": paper.get("link") or paper.get("url") or (f"https://doi.org/{paper.get('doi')}" if paper.get("doi") and str(paper.get("doi")).startswith("10.") else "") or (f"https://scholar.google.com/scholar?q={paper.get('title', '')}" if paper.get("title") else ""),
        "source_quality": paper.get("source_quality") or "unknown",
        "venue_tier": paper.get("venue_tier") or "",
        "method_category": infer_method(combined),
        "contribution_type": infer_contribution_type(combined),
        "core_problem": compact_text(combined, max_chars=450),
        "key_findings": infer_findings(text),
        "limitations": infer_limitations(text),
        "research_gap_hint": infer_limitations(text),
        "evidence_strength": infer_evidence_strength(paper),
        "evidence_text": compact_text(text, max_chars=1200),
    }


def build_evidence_matrix(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for idx, paper in enumerate(papers, start=1):
        reading = reading_from_paper(paper)
        rows.append({
            "ref_id": idx,
            "title": reading["title"],
            "year": reading["year"],
            "venue": reading["venue"],
            "link": reading["link"],
            "source_quality": reading["source_quality"],
            "venue_tier": reading["venue_tier"],
            "method_category": reading["method_category"],
            "contribution_type": reading["contribution_type"],
            "research_question_or_problem": reading["core_problem"],
            "main_evidence_or_findings": reading["key_findings"],
            "limitations": reading["limitations"],
            "research_gap_or_open_question": reading["research_gap_hint"],
            "evidence_strength": reading["evidence_strength"],
            "citation_hint": f"[{idx}]",
            "doi": reading["doi"],
            "url": reading["url"],
        })
    return rows


def analyze_research_gaps(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    methods = Counter(str(row.get("method_category") or "unknown") for row in matrix)
    contributions = Counter(str(row.get("contribution_type") or "unknown") for row in matrix)
    limitations = [str(row.get("limitations") or "") for row in matrix if row.get("limitations")]
    limitation_terms = Counter()
    for item in limitations:
        for token in keyword_set(item):
            limitation_terms[token] += 1
    expected_angles = [
        "retrieval / RAG",
        "memory systems",
        "reasoning / planning",
        "evaluation / reliability",
        "privacy / governance",
        "domain validation",
    ]
    observed_text = " ".join(methods.keys()).lower()
    underexplored = [angle for angle in expected_angles if angle.split(" / ")[0].lower() not in observed_text]
    potential = []

    if any("memory" in m.lower() for m in methods):
        potential.append("围绕长期记忆的更新、遗忘与冲突解决策略设计可复现实验。")
    if any("retrieval" in m.lower() or "rag" in m.lower() for m in methods):
        potential.append("将检索质量与下游生成、决策可靠性联合评测，而不是只看召回或相似度指标。")
    if underexplored:
        potential.append("把覆盖不足的方向转化为消融轴或研究问题：" + "、".join(underexplored[:3]) + "。")
    if not potential:
        potential.append("先用证据矩阵比较方法族、数据集与评测设置，再归纳可证明的创新点。")

    return {
        "paper_count": len(matrix),
        "method_distribution": dict(methods),
        "contribution_distribution": dict(contributions),
        "recurring_limitations": [term for term, _ in limitation_terms.most_common(8)],
        "underexplored_angles": underexplored,
        "potential_innovation_directions": potential,
        "caution": "研究空白分析默认由元数据和摘要推断；若要支撑强结论，需要继续读取 PDF 全文。",
    }


def build_review_protocol(
    query: str,
    *,
    review_type: str = "narrative",
    year_start: int | None = None,
    top_n: int | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    protocols = load_research_config("review_protocols", {})
    selected = protocols.get("protocols", {}).get(review_type) or protocols.get("protocols", {}).get("narrative") or {}
    return {
        "query": query,
        "review_type": review_type,
        "objective": selected.get("objective") or "Synthesize top-tier evidence for the research topic.",
        "inclusion_criteria": [
            "Only accept papers whose venue matches the configured top journal/conference policy.",
            f"Domain policy: {domain or 'all configured domains'}.",
            f"Earliest year: {year_start or 'not restricted'}.",
            f"Target paper count: {top_n or 'not restricted'}.",
        ],
        "screening_steps": selected.get("screening_steps") or [
            "Search candidate papers.",
            "Filter by configured top venues.",
            "Rank by venue policy, source influence, paper citations, and recency.",
            "Build readings, evidence matrix, gap analysis, review, references, and citation checks.",
        ],
        "outputs": selected.get("outputs") or [
            "ranked_papers", "readings", "evidence_matrix", "gap_analysis",
            "review", "references", "citation_verification",
        ],
        "limits": [
            "OpenAlex metadata can lag behind venues and proceedings.",
            "Domestic/foreign status is not inferred from author nationality unless supplied explicitly.",
            "Full-text claims require PDF or indexed full text, not just abstracts.",
        ],
    }

def _first_author(authors: str) -> str:
    parts = authors.replace(" and ", ",").split(",")
    return (parts[0] or "?").strip().replace(" ", "")


def format_reference(paper: dict[str, Any], *, style: str = "gbt7714", index: int = 1) -> str:
    title = compact_text(paper.get("title") or "Untitled", max_chars=240)
    authors = compact_text(paper.get("authors") or "Unknown", max_chars=220)
    year = paper.get("year") or "n.d."
    venue = paper.get("venue") or "Unknown venue"
    doi = (paper.get("doi") or "").strip()
    raw_url = (paper.get("url") or "").strip()

    # Build best available link: doi -> url -> openalex id -> scholar fallback
    link = ""
    if doi:
        link = f"https://doi.org/{doi}" if doi.startswith("10.") else doi
    if not link and raw_url:
        link = raw_url
    if not link:
        openalex_id = (paper.get("openalex_id") or paper.get("id") or "").strip()
        if openalex_id and "openalex.org" in openalex_id:
            link = openalex_id
    if not link:
        title_q = (paper.get("title") or "").strip()
        if title_q:
            q = urllib.parse.quote(f'{title_q} {str(paper.get("authors") or "")[:80]}')
            link = f"https://scholar.google.com/scholar?q={q}"

    style = (style or "gbt7714").lower()
    if style == "ieee":
        tail = f" {link}." if link else ".[No link]"
        return f"[{index}] {authors}, \"{title},\" {venue}, {year}.{tail}"
    if style == "apa":
        tail = f" {link}" if link else " [No link]"
        return f"{authors} ({year}). {title}. {venue}.{tail}"
    if style == "bibtex":
        key = re.sub(r"[^A-Za-z0-9]+", "", f"{_first_author(authors)}{year}") or f"ref{index}"
        return (
            f"@article{{{key},\n"
            f"  title = {{{title}}},\n"
            f"  author = {{{authors}}},\n"
            f"  year = {{{year}}},\n"
            f"  journal = {{{venue}}},\n"
            f"  doi = {{{doi}}},\n"
            f"  url = {{{link}}}\n"
            f"}}"
        )
    tail = f" {link}." if link else ".[No link]"
    return f"[{index}] {authors}. {title}[J/C]. {venue}, {year}.{tail}"


def format_reference_list(papers: list[dict[str, Any]], *, style: str = "gbt7714") -> list[str]:
    return [format_reference(paper, style=style, index=idx) for idx, paper in enumerate(papers, start=1)]

def verify_citations(review: str, papers: list[dict[str, Any]]) -> dict[str, Any]:
    refs = sorted({int(x) for x in re.findall(r"\[(\d+)\]", review or "")})
    issues = []
    checked = []
    for ref in refs:
        if ref < 1 or ref > len(papers):
            issues.append({"ref": ref, "severity": "error", "message": "citation index is out of range"})
            continue
        paper = papers[ref - 1]
        contexts = re.findall(r"[^\u3002\uff01\uff1f.!?]*\[" + str(ref) + r"\][^\u3002\uff01\uff1f.!?]*[\u3002\uff01\uff1f.!?]?", review or "")
        source = " ".join([paper.get("title", ""), paper.get("abstract", ""), paper.get("venue", "")])
        scores = [overlap_score(ctx, source) for ctx in contexts] or [0.0]
        max_score = max(scores)
        verdict = "supported" if max_score >= 0.12 else "weak"
        if verdict == "weak":
            issues.append({
                "ref": ref,
                "severity": "warning",
                "message": "low lexical overlap between cited sentence and paper metadata; inspect manually",
                "score": round(max_score, 3),
            })
        checked.append({"ref": ref, "title": paper.get("title"), "verdict": verdict, "score": round(max_score, 3)})
    uncited = [idx for idx in range(1, len(papers) + 1) if idx not in refs]
    return {
        "citation_count": len(refs),
        "paper_count": len(papers),
        "checked": checked,
        "uncited_refs": uncited,
        "issues": issues,
        "verdict": "pass" if not any(i["severity"] == "error" for i in issues) else "fail",
    }


def extract_pdf_text(path: Path, *, max_chars: int = 12000) -> str:
    if PdfReader is not None:
        try:
            reader = PdfReader(str(path))
            chunks = []
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
                if sum(len(chunk) for chunk in chunks) >= max_chars:
                    break
            text = compact_text("\n".join(chunks), max_chars=max_chars)
            if text:
                return text
        except Exception:
            pass
    data = path.read_bytes().decode("utf-8", errors="ignore")
    data = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff .,;:!?()\[\]\-_/]+", " ", data)
    return compact_text(data, max_chars=max_chars)


def http_get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 25) -> dict[str, Any]:
    if requests is None:
        fail("requests package is required for network actions.")
    response = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def reconstruct_openalex_abstract(inv: Any) -> str:
    if not isinstance(inv, dict):
        return ""
    positions = []
    for word, pos_list in inv.items():
        if isinstance(pos_list, list):
            for pos in pos_list:
                positions.append((pos, word))
    positions.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positions)


def openalex_work_to_paper(item: dict[str, Any]) -> dict[str, Any]:
    source = ((item.get("primary_location") or {}).get("source") or {})
    authors = []
    for authorship in item.get("authorships", []) or []:
        author = authorship.get("author") or {}
        if author.get("display_name"):
            authors.append(author["display_name"])
    abstract = item.get("abstract") or reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
    return normalize_paper({
        "id": item.get("id"),
        "title": item.get("title"),
        "authors": authors,
        "year": item.get("publication_year"),
        "venue": source.get("display_name"),
        "citations": item.get("cited_by_count"),
        "doi": item.get("doi"),
        "url": item.get("doi") or item.get("id"),
        "abstract": abstract,
        "issn": (source.get("issn") or [""])[0] if isinstance(source.get("issn"), list) else source.get("issn"),
    })


def search_openalex(query_text: str, *, limit: int = 20) -> list[dict[str, Any]]:
    data = http_get_json("https://api.openalex.org/works", {"search": query_text, "per-page": min(limit, 200)})
    return [openalex_work_to_paper(item) for item in data.get("results", [])]


def openalex_id_from_paper(paper: dict[str, Any]) -> str | None:
    doi = (paper.get("doi") or paper.get("url") or "").strip()
    if doi:
        if doi.startswith("https://doi.org/"):
            return "https://doi.org/" + doi.split("https://doi.org/", 1)[1]
        if doi.lower().startswith("10."):
            return "https://doi.org/" + doi
    url = paper.get("url") or ""
    if "openalex.org/" in url:
        return url
    return None


def openalex_fetch_work(identifier: str) -> dict[str, Any] | None:
    if not identifier:
        return None
    encoded = urllib.parse.quote(identifier, safe="")
    try:
        return http_get_json(f"https://api.openalex.org/works/{encoded}")
    except Exception:
        return None
