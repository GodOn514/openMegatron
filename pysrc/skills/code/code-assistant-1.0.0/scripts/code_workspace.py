from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "venvs",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    "target",
    "vendor",
    "logs",
}

TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cc",
    ".cfg",
    ".cmd",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lock",
    ".lua",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

KEY_FILES = {
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "pyproject.toml",
    "requirements.txt",
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "gradlew",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.mjs",
}

SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|credential|base[_-]?url|openai[_-]?api[_-]?key)"
    r"(\s*[:=]\s*)([\"']?)([^\"'\s,;]+)([\"']?)"
)
SECRET_VALUE_RE = re.compile(r"(?i)\b(sk-[a-z0-9_\-]{12,}|[a-z0-9_\-]{32,}\.[a-z0-9_\-]{16,}\.[a-z0-9_\-]{16,})\b")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def fail(message: str, **extra: Any) -> None:
    emit({"status": "error", "completed": False, "message": message, **extra})
    raise SystemExit(1)


def parse_params(raw: str) -> dict[str, Any]:
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read()
    raw = (raw or "{}").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception as exc:
        fail(f"Invalid JSON parameters: {exc}")
    if not isinstance(value, dict):
        fail("Parameters must be a JSON object.")
    return value


def redact(text: str) -> str:
    text = SECRET_KEY_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(5)}", text)
    return SECRET_VALUE_RE.sub("[REDACTED]", text)


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    if b"\0" in sample:
        return False
    return True


def safe_root(raw_root: Any) -> Path:
    root = Path(str(raw_root or os.getcwd())).expanduser().resolve()
    if not root.exists():
        fail(f"Root does not exist: {root}")
    if not root.is_dir():
        fail(f"Root is not a directory: {root}")
    return root


def resolve_inside(root: Path, raw_path: Any) -> Path:
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        fail(f"Path is outside root: {raw_path}")
    return resolved


def iter_files(root: Path, targets: list[Any] | None = None, max_files: int = 4000) -> list[Path]:
    start_paths: list[Path]
    if targets:
        start_paths = [resolve_inside(root, item) for item in targets]
    else:
        start_paths = [root]
    files: list[Path] = []
    for start in start_paths:
        if start.is_file():
            files.append(start)
            continue
        if not start.exists():
            continue
        for current, dirs, names in os.walk(start):
            dirs[:] = [
                d for d in dirs
                if d not in EXCLUDED_DIRS and not d.startswith(".cache") and not d.startswith("env_")
            ]
            current_path = Path(current)
            for name in names:
                path = current_path / name
                try:
                    if path.is_file():
                        files.append(path)
                except OSError:
                    continue
                if len(files) >= max_files:
                    return files
    return files


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def read_text(path: Path, max_chars: int = 12000) -> str:
    if path.stat().st_size > 2_000_000:
        return "[SKIPPED: file is larger than 2 MB]"
    if not is_text_file(path):
        return "[SKIPPED: binary file]"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[TRUNCATED]"
    return redact(text)


def detect_stack(files: list[Path]) -> list[str]:
    names = {path.name for path in files}
    suffixes = {path.suffix.lower() for path in files}
    stack: list[str] = []
    if "package.json" in names:
        stack.append("node")
    if suffixes & {".ts", ".tsx"}:
        stack.append("typescript")
    if suffixes & {".js", ".jsx", ".mjs"}:
        stack.append("javascript")
    if "pyproject.toml" in names or "requirements.txt" in names or ".py" in suffixes:
        stack.append("python")
    if "Cargo.toml" in names or ".rs" in suffixes:
        stack.append("rust")
    if "go.mod" in names or ".go" in suffixes:
        stack.append("go")
    if "pom.xml" in names or "build.gradle" in names or ".java" in suffixes:
        stack.append("jvm")
    if "Dockerfile" in names or "docker-compose.yml" in names or "docker-compose.yaml" in names:
        stack.append("docker")
    return list(dict.fromkeys(stack))


def package_scripts(root: Path) -> dict[str, str]:
    path = root / "package.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}
    return {str(k): str(v) for k, v in scripts.items()}


def suggest_commands(root: Path, files: list[Path]) -> list[str]:
    commands: list[str] = []
    scripts = package_scripts(root)
    for name in ["test", "lint", "typecheck", "build", "check"]:
        if name in scripts:
            commands.append(f"npm run {name}")
    names = {path.name for path in files}
    rels = {rel(root, path) for path in files}
    if "pnpm-lock.yaml" in names:
        commands = [cmd.replace("npm run", "pnpm") for cmd in commands]
    elif "yarn.lock" in names:
        commands = [cmd.replace("npm run", "yarn") for cmd in commands]
    if "pytest.ini" in names or "pyproject.toml" in names or any(item.startswith("tests/") for item in rels):
        commands.append("python -m pytest")
    if "Cargo.toml" in names:
        commands.extend(["cargo test", "cargo clippy"])
    if "go.mod" in names:
        commands.extend(["go test ./..."])
    if "Makefile" in names:
        commands.append("make test")
    return list(dict.fromkeys(commands))


def inspect_workspace(params: dict[str, Any]) -> None:
    root = safe_root(params.get("root"))
    max_files = int(params.get("max_files") or 4000)
    files = iter_files(root, max_files=max_files)
    rel_files = [rel(root, path) for path in files]
    key_files = [item for item in rel_files if Path(item).name in KEY_FILES]
    top_dirs: dict[str, int] = {}
    for item in rel_files:
        first = item.split("/", 1)[0]
        top_dirs[first] = top_dirs.get(first, 0) + 1
    source_files = [
        item for item in rel_files
        if Path(item).suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs", ".vue"}
    ][:80]
    emit({
        "status": "success",
        "completed": True,
        "root": str(root),
        "file_count_scanned": len(files),
        "detected_stack": detect_stack(files),
        "key_files": key_files[:80],
        "top_dirs": dict(sorted(top_dirs.items(), key=lambda item: item[1], reverse=True)[:20]),
        "package_scripts": package_scripts(root),
        "likely_verification_commands": suggest_commands(root, files),
        "sample_source_files": source_files,
    })


def normalize_paths(params: dict[str, Any]) -> list[Any] | None:
    paths = params.get("paths")
    if paths is None and params.get("path") is not None:
        paths = [params.get("path")]
    if paths is None:
        return None
    if not isinstance(paths, list):
        fail("paths must be an array when provided.")
    return paths


def search_workspace(params: dict[str, Any]) -> None:
    pattern = str(params.get("pattern") or "")
    if not pattern:
        fail("Missing pattern for search.")
    root = safe_root(params.get("root"))
    max_results = int(params.get("max_results") or 80)
    targets = normalize_paths(params)
    files = iter_files(root, targets=targets)
    use_regex = bool(params.get("regex"))
    needle = pattern if use_regex else pattern.lower()
    compiled = None
    if use_regex:
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            fail(f"Invalid regex: {exc}")
    results: list[dict[str, Any]] = []
    for path in files:
        if len(results) >= max_results:
            break
        try:
            if path.stat().st_size > 2_000_000 or not is_text_file(path):
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, 1):
            matched = bool(compiled.search(line)) if compiled else needle in line.lower()
            if matched:
                results.append({
                    "path": rel(root, path),
                    "line": line_no,
                    "text": redact(line.strip())[:500],
                })
                if len(results) >= max_results:
                    break
    emit({"status": "success", "completed": True, "pattern": pattern, "count": len(results), "results": results})


def read_files(params: dict[str, Any]) -> None:
    root = safe_root(params.get("root"))
    paths = normalize_paths(params)
    if not paths:
        fail("Missing path or paths for read.")
    max_chars = int(params.get("max_chars") or 12000)
    files = []
    for item in paths:
        path = resolve_inside(root, item)
        if not path.exists():
            files.append({"path": str(item), "error": "not found"})
            continue
        if path.is_dir():
            files.append({"path": rel(root, path), "error": "is a directory"})
            continue
        files.append({"path": rel(root, path), "content": read_text(path, max_chars=max_chars)})
    emit({"status": "success", "completed": True, "count": len(files), "files": files})


def test_plan(params: dict[str, Any]) -> None:
    root = safe_root(params.get("root"))
    files = iter_files(root)
    emit({
        "status": "success",
        "completed": True,
        "detected_stack": detect_stack(files),
        "likely_verification_commands": suggest_commands(root, files),
        "note": "Run the smallest command that covers the edited surface first; expand when shared behavior changed.",
    })


def main() -> int:
    params = parse_params(sys.argv[1] if len(sys.argv) > 1 else "")
    action = str(params.get("action") or "").strip().lower()
    if action == "inspect":
        inspect_workspace(params)
    elif action == "search":
        search_workspace(params)
    elif action == "read":
        read_files(params)
    elif action == "test_plan":
        test_plan(params)
    else:
        fail("action must be one of inspect, search, read, test_plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
