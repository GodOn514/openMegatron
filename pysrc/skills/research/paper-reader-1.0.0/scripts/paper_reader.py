from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_common import compact_text, emit, extract_pdf_text, fail, normalize_paper, normalize_papers, openalex_fetch_work, openalex_work_to_paper, parse_params, reading_from_paper

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    import requests
except Exception:
    requests = None


def read_file(path: Path, max_chars: int) -> dict:
    if not path.exists():
        fail(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown", ".rst", ".bib", ".ris"):
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        papers = normalize_papers(value)
        if papers:
            return {"status": "success", "completed": True, "readings": [reading_from_paper(p) for p in papers]}
        text = json.dumps(value, ensure_ascii=False)
    elif suffix == ".pdf":
        text = extract_pdf_text(path, max_chars=max_chars)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    paper = normalize_paper({"title": path.stem, "text": compact_text(text, max_chars=max_chars)})
    paper["abstract"] = compact_text(text, max_chars=max_chars)
    return {"status": "success", "completed": True, "reading": reading_from_paper(paper)}


def read_url(url: str, max_chars: int) -> dict:
    if "doi.org/" in url or url.lower().startswith("10."):
        identifier = url if url.lower().startswith("http") else "https://doi.org/" + url
        work = openalex_fetch_work(identifier)
        if work:
            return {"status": "success", "completed": True, "reading": reading_from_paper(openalex_work_to_paper(work))}
    if requests is None:
        fail("requests package is required to read URLs.")
    response = requests.get(url, timeout=25, headers={"User-Agent": "MegatronResearchAssistant/1.0"})
    response.raise_for_status()
    html = response.text
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        title = soup.title.get_text(" ", strip=True) if soup.title else url
    else:
        text = re.sub(r"<[^>]+>", " ", html)
        title = url
    paper = normalize_paper({"title": title, "url": url, "abstract": compact_text(text, max_chars=max_chars)})
    return {"status": "success", "completed": True, "reading": reading_from_paper(paper)}


def main() -> int:
    params = parse_params(sys.argv[1] if len(sys.argv) > 1 else "{}")
    action = str(params.get("action", "read")).lower()
    max_chars = int(params.get("max_chars") or 12000)
    if action == "read_many":
        papers = normalize_papers(params.get("papers") or params.get("path") or params.get("items") or [])
        emit({"status": "success", "completed": True, "count": len(papers), "readings": [reading_from_paper(p) for p in papers]})
        return 0
    if params.get("paper"):
        emit({"status": "success", "completed": True, "reading": reading_from_paper(normalize_paper(params["paper"]))})
        return 0
    if params.get("papers"):
        papers = normalize_papers(params["papers"])
        emit({"status": "success", "completed": True, "count": len(papers), "readings": [reading_from_paper(p) for p in papers]})
        return 0
    if params.get("path"):
        emit(read_file(Path(str(params["path"])).expanduser(), max_chars))
        return 0
    if params.get("doi"):
        emit(read_url(str(params["doi"]), max_chars))
        return 0
    if params.get("url"):
        emit(read_url(str(params["url"]), max_chars))
        return 0
    fail("Provide paper, papers, path, doi, or url.")


if __name__ == "__main__":
    raise SystemExit(main())
