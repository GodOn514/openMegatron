from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any


class JournalMatcher:
    FIELD_SYNONYMS = {
        "ml": ["machine learning", "deep learning", "neural network", "learning"],
        "cv": ["computer vision", "image processing", "visual", "vision"],
        "nlp": ["nlp", "natural language", "text mining", "language model"],
        "robotics": ["robot", "motion planning", "manipulation", "autonomous", "drone", "uav"],
        "control": ["control", "mpc", "model predictive", "feedback"],
        "wireless": ["wireless", "mimo", "ofdm", "cellular", "5g", "6g"],
        "comm": ["communication", "transmission", "channel", "modulation"],
        "security": ["security", "privacy", "cryptography", "attack detection"],
        "network": ["network", "routing", "protocol", "sdn", "iot", "edge computing"],
        "data_mining": ["data mining", "knowledge discovery", "recommendation"],
        "database": ["database", "data management", "query", "big data"],
        "power": ["power", "energy", "smart grid", "renewable"],
        "trans": ["transportation", "traffic", "autonomous vehicle", "v2x"],
        "iv": ["intelligent vehicle", "autonomous driving", "adas", "self-driving"],
        "vehicular": ["vehicular", "v2x", "vanet", "connected vehicle"],
        "multimedia": ["multimedia", "video", "audio", "streaming"],
        "sigproc": ["signal processing", "filtering", "estimation", "detection"],
        "ai": ["artificial intelligence", "ai", "intelligent system"],
        "automation": ["automation", "manufacturing", "scheduling", "cyber-physical"],
        "sustainable": ["sustainable", "green", "energy-efficient"],
        "cloud": ["cloud computing", "edge computing", "distributed"],
        "industrial": ["industrial", "iot", "cyber-physical", "factory"],
        "affective": ["affective computing", "emotion", "sentiment", "hci"],
        "medical": ["medical", "clinical", "biomedical", "healthcare"],
        "complex": ["complex network", "social network", "graph"],
    }

    def __init__(self, base_dir="."):
        data_path = Path(base_dir).parent / "data" / "journals.json"
        with open(data_path, encoding="utf-8") as f:
            self.journals = _json.load(f)
        self._build_index()

    def _build_index(self):
        self.journal_by_id = {j["id"]: j for j in self.journals}
        self.field_journals = {}
        for j in self.journals:
            for fld in j.get("fields", []):
                self.field_journals.setdefault(fld, []).append(j)

    def match(self, title="", abstract="", keywords=None, field="", top_k=5, used_journals=None, include_conferences=True):
        keywords = keywords or []
        used_journals = used_journals or []
        all_text = title + " " + abstract + " " + " ".join(keywords)
        all_text = all_text.lower()
        candidates = []
        seen_ids = set()
        if field and field in self.FIELD_SYNONYMS:
            for j in self.journals:
                if not include_conferences and j.get("type") == "conference":
                    continue
                if field.lower() in [f.lower() for f in j.get("fields", [])]:
                    candidates.append(j)
                    seen_ids.add(j["id"])
        for kw in keywords:
            kw_lower = kw.lower()
            for j in self.journals:
                if j["id"] in seen_ids:
                    continue
                if not include_conferences and j.get("type") == "conference":
                    continue
                j_kws = [k.lower() for k in j.get("keywords", [])]
                if any(kw_lower in k or k in kw_lower for k in j_kws):
                    candidates.append(j)
                    seen_ids.add(j["id"])
        for j in self.journals:
            if j["id"] in seen_ids:
                continue
            if not include_conferences and j.get("type") == "conference":
                continue
            name_lower = j["name"].lower()
            j_kws = [k.lower() for k in j.get("keywords", [])]
            all_terms = [name_lower] + j_kws
            match_count = sum(1 for t in all_terms if t in all_text)
            if match_count > 0:
                candidates.append(j)
                seen_ids.add(j["id"])
            else:
                words = set(re.findall(r"\w+", all_text))
                overlap = sum(1 for t in all_terms if any(w in t or t in w for w in words))
                if overlap >= 2:
                    candidates.append(j)
                    seen_ids.add(j["id"])
        if not candidates:
            candidates = [j for j in self.journals if include_conferences or j.get("type") != "conference"]
        scored = self._score(candidates, all_text, keywords, field)
        used_lower = [u.lower() for u in used_journals]
        scored = [s for s in scored if s["name"].lower() not in used_lower]
        seen = set()
        deduped = []
        for s in scored:
            if s["id"] not in seen:
                seen.add(s["id"])
                deduped.append(s)
        return deduped[:top_k]

    def _score(self, candidates, all_text, keywords, field):
        scored = []
        for j in candidates:
            score = 0.0
            reasons = []
            j_kws = set(k.lower() for k in j.get("keywords", []))
            text_words = set(re.findall(r"\w+", all_text))
            overlap = j_kws & text_words
            if overlap:
                score += len(overlap) * 0.15
                top_items = sorted(overlap)[:5]
                reasons.append("keyword overlap: " + ", ".join(top_items))
            if field and field.lower() in [f.lower() for f in j.get("fields", [])]:
                score += 0.5
                reasons.append("field match")
            if_latest = j.get("if_latest")
            if if_latest and isinstance(if_latest, (int, float)):
                score += min(if_latest / 20, 0.5)
            if j.get("ccf") == "A":
                score += 0.3
                reasons.append("CCF-A")
            review = j.get("review_months", [])
            if review and isinstance(review, list) and len(review) >= 2:
                avg = (review[0] + review[1]) / 2
                if avg <= 6:
                    score += 0.2
                    reasons.append("fast review")
            j_name_lower = j["name"].lower()
            for kw in keywords:
                if kw.lower() in j_name_lower:
                    score += 0.3
                    reasons.append("keyword in name: " + kw)
            result = dict(j)
            result["score"] = min(score, 3.0)
            result["match_reason"] = "; ".join(reasons) if reasons else "composite"
            scored.append(result)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored
import requests as _requests
import urllib.parse

def _online_enhance(journal_name: str, issn: str = "") -> dict:
    """Query OpenAlex for real-time journal metrics."""
    try:
        if issn:
            url = f"https://api.openalex.org/sources?filter=issn:{issn}"
        else:
            url = f"https://api.openalex.org/sources?search={urllib.parse.quote(journal_name)}&per_page=5"
        resp = _requests.get(url, headers={"User-Agent": "JournalMatcher/1.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return {}
        # Find best match
        name_lower = journal_name.lower()
        best = None
        for src in results:
            display = src.get("display_name", "")
            alt = [t.lower() for t in src.get("alternate_titles", [])]
            if name_lower in display.lower() or any(name_lower in t for t in alt):
                best = src
                break
        if not best:
            best = results[0]
        summary = best.get("summary_stats") or {}
        if_live = summary.get("2yr_mean_citedness", 0)
        return {
            "if_latest": round(if_live, 3) if if_live else None,
            "cited_by_count": best.get("cited_by_count", 0),
            "h_index": best.get("h_index", 0),
            "openalex_id": best.get("id", ""),
            "online_source": "OpenAlex",
        }
    except Exception:
        return {}

def enhance_with_online(results: list, top_k: int) -> list:
    """Enhance match results with real-time OpenAlex data."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        fut_to_idx = {}
        for i, r in enumerate(results):
            issn = ""
            name = r["name"]
            fut = pool.submit(_online_enhance, name, issn)
            fut_to_idx[fut] = i
        for fut in concurrent.futures.as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            try:
                live = fut.result()
                if live and live.get("if_latest"):
                    results[idx]["if_latest"] = live["if_latest"]
                    results[idx]["cited_by_count"] = live.get("cited_by_count", results[idx].get("cited_by_count", 0))
                    results[idx]["h_index"] = live.get("h_index", results[idx].get("h_index", 0))
                    results[idx]["online_enhanced"] = True
            except Exception:
                pass
    return results[:top_k]
