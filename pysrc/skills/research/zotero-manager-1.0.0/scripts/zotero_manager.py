#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("ZOTERO_LOCAL_BASE_URL", "http://127.0.0.1:23119")
LOCAL_USER = "/api/users/0"
LOCAL_API_PREF = "extensions.zotero.httpServer.localAPI.enabled"
API_HEADERS = {"Zotero-API-Version": "3"}
PAGE_LIMIT = 100


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def fail(message: str, *, completed: bool = False) -> None:
    emit({"status": "error", "message": message, "completed": completed})
    raise SystemExit(1)


def zotero_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = []
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.extend([Path(appdata) / "Zotero" / "Zotero", Path(appdata) / "Zotero"])
    elif platform.system() == "Darwin":
        roots.append(home / "Library" / "Application Support" / "Zotero")
    else:
        roots.extend([home / ".zotero" / "zotero", home / ".var" / "app" / "org.zotero.Zotero" / "data" / "zotero"])
    return list(dict.fromkeys(roots))


def profiles_ini_path() -> Path | None:
    for root in zotero_roots():
        candidate = root / "profiles.ini"
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def profile_dir() -> Path | None:
    ini = profiles_ini_path()
    if ini is None:
        return None
    parser = configparser.RawConfigParser()
    parser.read(ini, encoding="utf-8")
    candidates: list[tuple[int, Path]] = []
    for section in parser.sections():
        if not section.lower().startswith("profile") or not parser.has_option(section, "Path"):
            continue
        raw = parser.get(section, "Path")
        path = ini.parent / raw if parser.get(section, "IsRelative", fallback="1") == "1" else Path(raw)
        score = 10 if parser.get(section, "Default", fallback="0") == "1" else 0
        try:
            score += 5 if (path / "prefs.js").exists() else 0
        except OSError:
            pass
        candidates.append((score, path))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    profiles_root = ini.parent / "Profiles"
    try:
        profiles = sorted(profiles_root.glob("*.default*")) if profiles_root.exists() else []
    except OSError:
        profiles = []
    return profiles[0] if profiles else None


def prefs_file() -> Path | None:
    profile = profile_dir()
    if profile is None:
        return None
    prefs = profile / "prefs.js"
    try:
        return prefs if prefs.exists() else None
    except OSError:
        return None


def pref_pattern() -> re.Pattern[str]:
    return re.compile(r'user_pref\("' + re.escape(LOCAL_API_PREF) + r'",\s*(true|false)\s*\);')


def read_local_api_pref() -> bool | None:
    prefs = prefs_file()
    if prefs is None:
        return None
    match = pref_pattern().search(prefs.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) == "true" if match else None


def set_local_api_pref(enabled: bool) -> str:
    prefs = prefs_file()
    if prefs is None:
        fail("Could not find Zotero prefs.js. Start Zotero once, then retry.")
    backup = prefs.with_suffix(prefs.suffix + f".backup-{int(time.time())}")
    shutil.copy2(prefs, backup)
    text = prefs.read_text(encoding="utf-8", errors="replace")
    line = f'user_pref("{LOCAL_API_PREF}", {str(enabled).lower()});'
    pattern = pref_pattern()
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    prefs.write_text(text, encoding="utf-8")
    return str(backup)


def is_zotero_running() -> bool:
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq zotero.exe"],
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return "zotero.exe" in out.lower()
        subprocess.check_output(["pgrep", "-f", "[Zz]otero"], stderr=subprocess.DEVNULL, text=True)
        return True
    except Exception:
        return False


def restart_zotero(wait: bool = True) -> bool:
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/IM", "zotero.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            time.sleep(1)
            subprocess.Popen(["zotero.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif platform.system() == "Darwin":
            subprocess.run(["osascript", "-e", 'tell application "Zotero" to quit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            time.sleep(1)
            subprocess.run(["open", "-a", "Zotero"], check=False)
        else:
            subprocess.run(["pkill", "-f", "zotero"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            time.sleep(1)
            subprocess.Popen(["zotero"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    if not wait:
        return True
    for _ in range(30):
        if request("/api/", timeout=1).get("ok"):
            return True
        time.sleep(0.5)
    return False


def zotero_data_dir() -> Path | None:
    prefs = prefs_file()
    if prefs is None:
        return None
    text = prefs.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'user_pref\("extensions\.zotero\.dataDir",\s*"((?:\\.|[^"])*)"\s*\);', text)
    if match:
        raw = match.group(1).replace("\\\\", "\\").replace('\\"', '"')
        return Path(raw)
    return Path.home() / "Zotero"


def zotero_db_path() -> Path | None:
    data_dir = zotero_data_dir()
    if data_dir is None:
        return None
    db = data_dir / "zotero.sqlite"
    return db if db.exists() else None


def url_for(path: str) -> str:
    return BASE_URL.rstrip("/") + path


def request(path: str, *, method: str = "GET", data: Any = None, headers: dict[str, str] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    req_headers = dict(headers or {})
    if path.startswith("/api"):
        req_headers.update({k: v for k, v in API_HEADERS.items() if k not in req_headers})
    body: bytes | None = None
    if data is not None:
        body = json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else str(data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    try:
        req = urllib.request.Request(url_for(path), data=body, method=method, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return {"ok": 200 <= resp.status < 300, "status": resp.status, "headers": dict(resp.headers.items()), "text": text}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "headers": dict(exc.headers.items()), "text": text, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "status": None, "headers": {}, "text": "", "error": str(exc)}


def parse_response(resp: dict[str, Any]) -> Any:
    content_type = str(resp.get("headers", {}).get("Content-Type", ""))
    if "json" not in content_type.lower():
        return resp.get("text", "")
    try:
        return json.loads(resp.get("text") or "null")
    except json.JSONDecodeError:
        return resp.get("text", "")


def api_get(path: str) -> tuple[Any, dict[str, Any]]:
    api_path = path if path.startswith("/api") else "/api" + path
    resp = request(api_path)
    if not resp["ok"]:
        detail = resp.get("error") or resp.get("text", "")[:300] or "no response"
        fail(f"GET {api_path} failed: status={resp.get('status')} detail={detail}")
    return parse_response(resp), resp


def query(params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value is not None}
    return urllib.parse.urlencode(clean)


def total_results(resp: dict[str, Any]) -> int | None:
    raw = resp.get("headers", {}).get("Total-Results")
    return int(raw) if raw and str(raw).isdigit() else None


def creators_from_item(data: dict[str, Any]) -> list[str]:
    names = []
    for creator in data.get("creators", []) or []:
        name = creator.get("name") or " ".join(x for x in [creator.get("firstName"), creator.get("lastName")] if x)
        if name:
            names.append(name)
    return names


def year_from_date(raw: str | None) -> str | None:
    match = re.search(r"(\d{4})", raw or "")
    return match.group(1) if match else None


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data", item)
    return {
        "key": item.get("key") or data.get("key"),
        "itemType": data.get("itemType"),
        "title": data.get("title"),
        "creators": creators_from_item(data),
        "year": year_from_date(data.get("date")),
    }


def count_bibtex_entries(text: str) -> int:
    return len(re.findall(r"@\w+\s*\{", text))


def fetch_items(path: str, *, limit: int) -> list[dict[str, Any]]:
    start = 0
    rows: list[dict[str, Any]] = []
    while len(rows) < limit:
        sep = "&" if "?" in path else "?"
        data, resp = api_get(f"{path}{sep}{query({'limit': min(PAGE_LIMIT, limit - len(rows)), 'start': start})}")
        if not isinstance(data, list):
            break
        rows.extend(data)
        total = total_results(resp)
        start += PAGE_LIMIT
        if not data or (total is not None and start >= total):
            break
    return rows[:limit]


def status_payload() -> dict[str, Any]:
    root = request("/api/", timeout=2)
    return {
        "status": "success",
        "completed": True,
        "zotero_running": is_zotero_running(),
        "api_running": bool(root["ok"]),
        "api_status": root.get("status"),
        "local_api_enabled_pref": read_local_api_pref(),
        "profile_dir_found": profile_dir() is not None,
        "prefs_found": prefs_file() is not None,
        "data_dir": str(zotero_data_dir()) if zotero_data_dir() else None,
        "db_found": zotero_db_path() is not None,
        "base_url": BASE_URL,
    }


def do_enable(params: dict[str, Any]) -> dict[str, Any]:
    backup = set_local_api_pref(True)
    restarted = restart_zotero(wait=True) if params.get("restart") else False
    return {"status": "success", "completed": True, "backup": backup, "restarted": restarted, "current": status_payload()}


def do_search(params: dict[str, Any]) -> dict[str, Any]:
    q = str(params.get("query") or "").strip()
    if not q:
        fail("Missing query for action=search.")
    limit = int(params.get("limit") or 20)
    path = f"{LOCAL_USER}/items/top?{query({'q': q, 'sort': 'dateModified', 'direction': 'desc'})}"
    rows = [summarize_item(item) for item in fetch_items(path, limit=limit)]
    return {"status": "success", "completed": True, "query": q, "count": len(rows), "items": rows}


def do_inventory(params: dict[str, Any]) -> dict[str, Any]:
    limit = int(params.get("limit") or 20)
    rows = [summarize_item(item) for item in fetch_items(f"{LOCAL_USER}/items/top?{query({'sort': 'dateModified', 'direction': 'desc'})}", limit=limit)]
    return {"status": "success", "completed": True, "count": len(rows), "items": rows}


def do_collections(params: dict[str, Any]) -> dict[str, Any]:
    limit = int(params.get("limit") or 50)
    rows = fetch_items(f"{LOCAL_USER}/collections?{query({'sort': 'title', 'direction': 'asc'})}", limit=limit)
    collections = []
    for row in rows:
        data = row.get("data", row)
        collections.append({"key": row.get("key") or data.get("key"), "name": data.get("name"), "parentCollection": data.get("parentCollection")})
    return {"status": "success", "completed": True, "count": len(collections), "collections": collections}


def do_tags(params: dict[str, Any]) -> dict[str, Any]:
    limit = int(params.get("limit") or 50)
    rows = fetch_items(f"{LOCAL_USER}/tags?{query({'sort': 'title', 'direction': 'asc'})}", limit=limit)
    tags = [{"tag": row.get("tag"), "numItems": (row.get("meta") or {}).get("numItems")} for row in rows]
    return {"status": "success", "completed": True, "count": len(tags), "tags": tags}


def export_bibtex(params: dict[str, Any]) -> dict[str, Any]:
    item_key = params.get("item_key")
    include_children = bool(params.get("include_children"))
    if item_key:
        path = f"{LOCAL_USER}/items?{query({'itemKey': item_key, 'format': 'bibtex', 'limit': PAGE_LIMIT})}"
        resp = request("/api" + path)
        if not resp["ok"]:
            fail(f"BibTeX export failed: status={resp.get('status')} detail={resp.get('error') or resp.get('text', '')[:300]}")
        text = resp["text"]
    else:
        endpoint = "items" if include_children else "items/top"
        start = 0
        chunks: list[str] = []
        while True:
            path = f"{LOCAL_USER}/{endpoint}?{query({'format': 'bibtex', 'sort': 'title', 'direction': 'asc', 'limit': PAGE_LIMIT, 'start': start})}"
            resp = request("/api" + path)
            if not resp["ok"]:
                fail(f"BibTeX export failed: status={resp.get('status')} detail={resp.get('error') or resp.get('text', '')[:300]}")
            if resp["text"].strip():
                chunks.append(resp["text"].strip())
            total = total_results(resp)
            start += PAGE_LIMIT
            if total is not None and start >= total:
                break
            if total is None and count_bibtex_entries(resp["text"]) < PAGE_LIMIT:
                break
        text = "\n\n".join(chunks)
        if text:
            text += "\n"
    out = params.get("out")
    if out:
        path = Path(str(out)).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {"status": "success", "completed": True, "path": str(path), "bibtex_entries": count_bibtex_entries(text), "bytes": len(text.encode("utf-8"))}
    return {"status": "success", "completed": True, "bibtex_entries": count_bibtex_entries(text), "bibtex": text}


def parse_jsonish(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        fail("First argument must be a JSON object.")
    if not isinstance(value, dict):
        fail("First argument must be a JSON object.")
    return value


def run_params(params: dict[str, Any]) -> dict[str, Any]:
    action = str(params.get("action") or "status").strip().lower().replace("-", "_")
    if action == "status":
        return status_payload()
    if action == "enable":
        return do_enable(params)
    if action == "search":
        return do_search(params)
    if action == "inventory":
        return do_inventory(params)
    if action == "collections":
        return do_collections(params)
    if action == "tags":
        return do_tags(params)
    if action in ("export_bibtex", "export"):
        return export_bibtex(params)
    fail(f"Unknown action: {action}")
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0].lstrip().startswith("{"):
        emit(run_params(parse_jsonish(argv[0])))
        return 0
    parser = argparse.ArgumentParser(description="Zotero Desktop local API manager")
    parser.add_argument("action", nargs="?", default="status")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--item-key")
    parser.add_argument("--out")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args(argv)
    emit(run_params(vars(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
