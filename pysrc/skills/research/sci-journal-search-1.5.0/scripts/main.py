from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        params = json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {exc}", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)
    journal = params.get("journal_name") or params.get("query") or params.get("name")
    if not journal:
        print(json.dumps({"status": "error", "message": "Missing journal_name.", "completed": False}, ensure_ascii=False))
        raise SystemExit(1)
    script = Path(__file__).with_name("query.py")
    args = [sys.executable, str(script), str(journal), "--json"]
    if params.get("fast"):
        args.append("--fast")
    if params.get("year"):
        args.extend(["--year", str(params["year"])])
    proc = subprocess.run(args, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=int(params.get("timeout") or 120))
    if proc.returncode != 0:
        print(json.dumps({"status": "error", "message": (proc.stderr or proc.stdout)[:1000], "completed": False}, ensure_ascii=False))
        raise SystemExit(1)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"raw": proc.stdout}
    print(json.dumps({"status": "success", "completed": True, "result": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
