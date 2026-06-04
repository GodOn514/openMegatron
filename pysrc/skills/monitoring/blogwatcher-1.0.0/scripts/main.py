from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SKILLS_DIR / "research"))

try:
    from research_common import emit, load_research_config
except Exception:  # pragma: no cover - keep wrapper usable without research package
    emit = None
    load_research_config = None


def parse_params() -> dict:
    try:
        value = json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {exc}", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)


def research_sources(params: dict) -> None:
    if load_research_config is None:
        payload = {"status": "error", "message": "research config loader is unavailable", "completed": False}
    else:
        config = load_research_config("watch_sources", {})
        domain = str(params.get("domain") or "").lower()
        top_only = bool(params.get("top_venue_only", True))
        sources = []
        for source in config.get("sources", []):
            if not isinstance(source, dict):
                continue
            domains = [str(item).lower() for item in source.get("domain", [])]
            if domain and domain not in domains:
                continue
            if top_only and not source.get("top_venue"):
                continue
            sources.append(source)
        payload = {"status": "success", "completed": True, "count": len(sources), "sources": sources}
    if emit:
        emit(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def run_blogwatcher(args: list[str], timeout: int) -> dict:
    proc = subprocess.run(args, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
    return {
        "status": "success" if proc.returncode == 0 else "error",
        "completed": proc.returncode == 0,
        "command": args,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }


def seed_research(params: dict) -> None:
    if not shutil.which("blogwatcher"):
        print(json.dumps({"status": "error", "message": "blogwatcher CLI is not installed.", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)
    if load_research_config is None:
        print(json.dumps({"status": "error", "message": "research config loader is unavailable", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)
    config = load_research_config("watch_sources", {})
    top_only = bool(params.get("top_venue_only", True))
    dry_run = bool(params.get("dry_run", False))
    timeout = int(params.get("timeout") or 60)
    actions = []
    for source in config.get("sources", []):
        if not isinstance(source, dict):
            continue
        if top_only and not source.get("top_venue"):
            continue
        name = str(source.get("name") or source.get("venue") or "").strip()
        url = str(source.get("url") or "").strip()
        if not name or not url:
            continue
        args = ["blogwatcher", "add", name, url]
        actions.append({"name": name, "url": url, "dry_run": dry_run, "result": None if dry_run else run_blogwatcher(args, timeout)})
    payload = {"status": "success", "completed": True, "count": len(actions), "actions": actions}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    params = parse_params()
    action = str(params.get("action") or "blogs")
    if action == "research_sources":
        research_sources(params)
        return
    if action == "seed_research":
        seed_research(params)
        return
    if not shutil.which("blogwatcher"):
        print(json.dumps({"status": "error", "message": "blogwatcher CLI is not installed.", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)
    args = ["blogwatcher", action]
    for key in ("name", "url", "id"):
        if params.get(key):
            args.append(str(params[key]))
    payload = run_blogwatcher(args, int(params.get("timeout") or 60))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["completed"] else 1)


if __name__ == "__main__":
    main()
