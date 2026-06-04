import base64
import hashlib
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class EvolutionError(ValueError):
    pass


BLOCKED_DIRS = {
    ".git",
    ".runtime",
    ".docker-cli",
    ".npm-cache",
    ".npm-home",
    ".pytest_cache",
    "__pycache__",
    "dist",
    "log",
    "logs",
    "node_modules",
    "venv",
}

BLOCKED_FILES = {
    ".env",
    "model.toml",
    "pysrc/model.toml",
}

TEXT_PREVIEW_LIMIT = 12000


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_rel_path(path_value: str) -> str:
    raw = str(path_value or "").strip().replace("\\", "/")
    if not raw:
        raise EvolutionError("Target path cannot be empty.")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw or raw == "..":
        raise EvolutionError(f"Path escapes the workspace: {path_value}")
    return raw.strip("/")


class EvolutionStore:
    """Review ledger for controlled skill/project evolution."""

    def __init__(self, repo_root: Path, state_dir: Optional[Path] = None):
        self.repo_root = Path(repo_root).resolve()
        self.state_dir = Path(state_dir).resolve() if state_dir else self.repo_root / ".runtime" / "evolution"
        self.snapshot_dir = self.state_dir / "snapshots"
        self.ledger_path = self.state_dir / "proposals.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def policy(self) -> dict:
        return {
            "blocked_dirs": sorted(BLOCKED_DIRS),
            "blocked_files": sorted(BLOCKED_FILES),
            "state_dir": str(self.state_dir),
            "snapshot_dir": str(self.snapshot_dir),
            "principle": "Proposals are reviewed before writes; applying creates a restorable snapshot.",
        }

    def list_proposals(self, status: str = "", include_content: bool = True) -> List[dict]:
        proposals = self._load()
        filtered = [
            self._public_proposal(item, include_content=include_content)
            for item in proposals
            if not status or str(item.get("status") or "") == status
        ]
        return sorted(filtered, key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)

    def get_proposal(self, proposal_id: str, include_content: bool = True) -> dict:
        proposal = self._find(proposal_id)
        return self._public_proposal(proposal, include_content=include_content)

    def create_proposal(
        self,
        *,
        title: str,
        summary: str,
        files: List[dict],
        kind: str = "project",
        author: str = "agent",
        notes: Optional[List[str]] = None,
    ) -> dict:
        title = str(title or "").strip()
        summary = str(summary or "").strip()
        if not title:
            raise EvolutionError("Proposal title is required.")
        if not summary:
            raise EvolutionError("Proposal summary is required.")
        if not isinstance(files, list) or not files:
            raise EvolutionError("At least one file change is required.")

        safe_files = [self._normalize_file_change(file_change) for file_change in files]
        content_hash = hashlib.sha256(
            json.dumps({"title": title, "summary": summary, "files": safe_files}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        proposal_id = f"evo_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{content_hash}"
        now = utc_iso()
        proposal = {
            "id": proposal_id,
            "kind": str(kind or "project").strip() or "project",
            "title": title,
            "summary": summary,
            "author": str(author or "agent").strip() or "agent",
            "status": "proposed",
            "created_at": now,
            "updated_at": now,
            "files": safe_files,
            "notes": notes if isinstance(notes, list) else [],
            "events": [{"type": "created", "at": now, "actor": str(author or "agent")}],
        }

        proposals = self._load()
        proposals.append(proposal)
        self._save(proposals)
        return self._public_proposal(proposal)

    def apply_proposal(self, proposal_id: str, reviewer: str = "user") -> dict:
        proposals = self._load()
        proposal = self._find_in(proposals, proposal_id)
        if proposal.get("status") != "proposed":
            raise EvolutionError(f"Only proposed changes can be applied; current status is {proposal.get('status')}.")

        snapshot_root = self.snapshot_dir / str(proposal["id"])
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root)
        snapshot_root.mkdir(parents=True, exist_ok=True)

        snapshots = []
        targets = []
        for file_change in proposal.get("files", []):
            target = self.resolve_target(file_change.get("path"))
            targets.append((file_change, target))
            snapshots.append(self._capture_snapshot(snapshot_root, target, str(file_change.get("path") or "")))

        for file_change, target in targets:
            action = file_change.get("action") or "write"
            if action == "delete":
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(file_change.get("content") or ""), encoding="utf-8", newline="")

        now = utc_iso()
        proposal["status"] = "applied"
        proposal["updated_at"] = now
        proposal["applied_at"] = now
        proposal["reviewer"] = str(reviewer or "user")
        proposal["snapshot_dir"] = str(snapshot_root)
        proposal["snapshots"] = snapshots
        proposal.setdefault("events", []).append({"type": "applied", "at": now, "actor": reviewer})
        self._save(proposals)
        return self._public_proposal(proposal)

    def reject_proposal(self, proposal_id: str, reviewer: str = "user", reason: str = "") -> dict:
        proposals = self._load()
        proposal = self._find_in(proposals, proposal_id)
        if proposal.get("status") not in {"proposed"}:
            raise EvolutionError(f"Only proposed changes can be rejected; current status is {proposal.get('status')}.")
        now = utc_iso()
        proposal["status"] = "rejected"
        proposal["updated_at"] = now
        proposal["reviewer"] = str(reviewer or "user")
        if reason:
            proposal["rejection_reason"] = str(reason)
        proposal.setdefault("events", []).append({"type": "rejected", "at": now, "actor": reviewer, "reason": reason})
        self._save(proposals)
        return self._public_proposal(proposal)

    def rollback_proposal(self, proposal_id: str, reviewer: str = "user") -> dict:
        proposals = self._load()
        proposal = self._find_in(proposals, proposal_id)
        if proposal.get("status") != "applied":
            raise EvolutionError(f"Only applied changes can be rolled back; current status is {proposal.get('status')}.")
        snapshots = proposal.get("snapshots") or []
        if not snapshots:
            raise EvolutionError("No snapshot metadata found for this proposal.")

        for snapshot in snapshots:
            target = self.resolve_target(snapshot.get("path"))
            if snapshot.get("existed"):
                encoded = snapshot.get("content_b64")
                if encoded is None:
                    raise EvolutionError(f"Snapshot content missing for {snapshot.get('path')}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(encoded.encode("ascii")))
            elif target.exists():
                target.unlink()

        now = utc_iso()
        proposal["status"] = "rolled_back"
        proposal["updated_at"] = now
        proposal["rolled_back_at"] = now
        proposal["rollback_reviewer"] = str(reviewer or "user")
        proposal.setdefault("events", []).append({"type": "rolled_back", "at": now, "actor": reviewer})
        self._save(proposals)
        return self._public_proposal(proposal)

    def resolve_target(self, path_value: str) -> Path:
        rel = normalize_rel_path(path_value)
        if rel in BLOCKED_FILES:
            raise EvolutionError(f"Path is blocked because it can contain secrets or local runtime state: {rel}")
        parts = rel.split("/")
        if any(part in BLOCKED_DIRS for part in parts):
            raise EvolutionError(f"Path is blocked because it is generated or unsafe runtime state: {rel}")
        target = (self.repo_root / rel).resolve()
        try:
            target.relative_to(self.repo_root)
        except ValueError:
            raise EvolutionError(f"Path escapes the workspace: {path_value}")
        return target

    def _normalize_file_change(self, file_change: dict) -> dict:
        if not isinstance(file_change, dict):
            raise EvolutionError("File changes must be objects.")
        rel = normalize_rel_path(file_change.get("path"))
        self.resolve_target(rel)
        action = str(file_change.get("action") or "write").strip().lower()
        if action not in {"write", "delete"}:
            raise EvolutionError("File action must be 'write' or 'delete'.")
        normalized = {
            "path": rel,
            "action": action,
            "summary": str(file_change.get("summary") or "").strip(),
        }
        if action == "write":
            content = str(file_change.get("content") or "")
            normalized["content"] = content
            normalized["content_hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            normalized["size"] = len(content.encode("utf-8"))
        return normalized

    def _capture_snapshot(self, snapshot_root: Path, target: Path, rel_path: str) -> dict:
        existed = target.exists()
        content = target.read_bytes() if existed else b""
        record = {
            "path": normalize_rel_path(rel_path),
            "existed": existed,
            "content_b64": base64.b64encode(content).decode("ascii") if existed else None,
            "content_hash": hashlib.sha256(content).hexdigest() if existed else None,
            "captured_at": utc_iso(),
        }
        meta_name = f"{uuid.uuid4().hex}.json"
        (snapshot_root / meta_name).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        record["snapshot_file"] = meta_name
        return record

    def _public_proposal(self, proposal: dict, include_content: bool = True) -> dict:
        public = dict(proposal)
        files = []
        for file_change in public.get("files", []):
            item = dict(file_change)
            if include_content:
                content = item.get("content")
                if isinstance(content, str) and len(content) > TEXT_PREVIEW_LIMIT:
                    item["content"] = content[:TEXT_PREVIEW_LIMIT]
                    item["truncated"] = True
            else:
                item.pop("content", None)
            files.append(item)
        public["files"] = files
        if isinstance(public.get("snapshots"), list):
            public["snapshots"] = [
                {key: value for key, value in dict(snapshot).items() if key != "content_b64"}
                for snapshot in public["snapshots"]
                if isinstance(snapshot, dict)
            ]
        return public

    def _find(self, proposal_id: str) -> dict:
        return self._find_in(self._load(), proposal_id)

    def _find_in(self, proposals: List[dict], proposal_id: str) -> dict:
        proposal_id = str(proposal_id or "").strip()
        for proposal in proposals:
            if proposal.get("id") == proposal_id:
                return proposal
        raise EvolutionError(f"Evolution proposal not found: {proposal_id}")

    def _load(self) -> List[dict]:
        if not self.ledger_path.exists():
            return []
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            backup = self.ledger_path.with_suffix(f".broken.{int(time.time())}.json")
            shutil.copy2(self.ledger_path, backup)
            return []

    def _save(self, proposals: List[dict]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.ledger_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.ledger_path)
