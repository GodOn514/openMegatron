import json
import time
import uuid
from typing import Optional


class ConfirmationStateTracker:
    def __init__(self, redis_client, ttl_seconds: int = 600, logger=None):
        self.redis = redis_client
        self.ttl_seconds = max(600, int(ttl_seconds or 600))
        self.logger = logger

    def active_turn_key(self, session_id: str) -> str:
        return f"active_chat_turn:{session_id or 'default'}"

    async def get_active_turn(self, session_id: str) -> Optional[str]:
        try:
            return await self.redis.get(self.active_turn_key(session_id))
        except Exception as e:
            self._debug(f"Active chat turn read skipped: {e}")
            return None

    async def start_turn(self, session_id: str) -> str:
        turn_id = str(uuid.uuid4())
        try:
            await self.redis.set(self.active_turn_key(session_id), turn_id, ex=self.ttl_seconds)
        except Exception as e:
            self._debug(f"Active chat turn write skipped: {e}")
        return turn_id

    async def create_pending_request(
        self,
        session_id: str,
        prompt: str,
        code_preview: str,
        ttl_seconds: int = 120,
    ) -> dict:
        request_id = str(uuid.uuid4())
        key = f"confirm_req:{session_id}:{request_id}"
        data = {
            "schema": "megatron.hitl.v1",
            "kind": "confirmation_request",
            "prompt": (prompt or "").strip(),
            "code_preview": code_preview or "",
            "status": "pending",
            "session_id": session_id,
            "request_id": request_id,
            "turn_id": await self.get_active_turn(session_id),
            "created_at": time.time(),
        }
        await self.redis.set(key, json.dumps(data, ensure_ascii=False), ex=ttl_seconds)
        return {"key": key, "data": data}

    async def get_request(self, key: str) -> Optional[dict]:
        data_str = await self.redis.get(key)
        return json.loads(data_str) if data_str else None

    async def request_is_stale(self, session_id: str, request_turn_id: Optional[str]) -> bool:
        if not request_turn_id:
            return False
        active_turn = await self.get_active_turn(session_id)
        return request_turn_id != active_turn

    async def mark_denied(self, key: str, data: dict, reason: str):
        data["status"] = "denied"
        data["denial_reason"] = reason
        data["cancelled_at"] = time.time()
        try:
            await self.redis.set(key, json.dumps(data, ensure_ascii=False), ex=60)
        except Exception as e:
            self._debug(f"Confirmation denial write skipped: {e}")

    async def cancel_pending(self, session_id: str, reason: str) -> int:
        try:
            keys = await self.redis.keys(f"confirm_req:{session_id or 'default'}:*")
        except Exception as e:
            self._debug(f"Confirmation cancellation scan skipped: {e}")
            return 0
        cancelled = 0
        for key in keys:
            try:
                data = await self.get_request(key)
                if not data or data.get("status") != "pending":
                    continue
                await self.mark_denied(key, data, reason)
                cancelled += 1
            except Exception as e:
                self._debug(f"Confirmation cancellation skipped for {key}: {e}")
        return cancelled

    def _debug(self, message: str):
        if self.logger:
            self.logger.debug(message)
