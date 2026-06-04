import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

try:
    from fastapi import HTTPException
except Exception:  # pragma: no cover - adapter can still be unit tested without FastAPI
    HTTPException = None

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception:  # pragma: no cover - optional, only needed for encrypted callbacks
    Cipher = None
    algorithms = None
    modes = None
    default_backend = None


APPROVE_WORDS = {"/approve", "approve", "同意", "允许", "确认", "y", "yes"}
DENY_WORDS = {"/deny", "deny", "拒绝", "不同意", "取消", "n", "no"}


@dataclass
class FeishuConfig:
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""
    api_base: str = "https://open.feishu.cn"
    request_timeout_sec: int = 20
    reply_enabled: bool = True
    confirmation_watch_sec: int = 65

    @classmethod
    def from_config(cls, config: dict) -> "FeishuConfig":
        integrations = config.get("integrations", {}) if isinstance(config, dict) else {}
        feishu_cfg = integrations.get("feishu", {}) or config.get("feishu", {}) or {}

        def env_or_cfg(env_name: str, key: str, default: Any = ""):
            value = os.environ.get(env_name)
            if value is not None:
                return value
            return feishu_cfg.get(key, default)

        def to_bool(value: Any, default: bool = True) -> bool:
            if value is None:
                return default
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)

        return cls(
            app_id=str(env_or_cfg("FEISHU_APP_ID", "app_id", "")),
            app_secret=str(env_or_cfg("FEISHU_APP_SECRET", "app_secret", "")),
            verification_token=str(env_or_cfg("FEISHU_VERIFICATION_TOKEN", "verification_token", "")),
            encrypt_key=str(env_or_cfg("FEISHU_ENCRYPT_KEY", "encrypt_key", "")),
            api_base=str(env_or_cfg("FEISHU_API_BASE", "api_base", "https://open.feishu.cn")).rstrip("/"),
            request_timeout_sec=int(env_or_cfg("FEISHU_REQUEST_TIMEOUT_SEC", "request_timeout_sec", 20)),
            reply_enabled=to_bool(env_or_cfg("FEISHU_REPLY_ENABLED", "reply_enabled", True)),
            confirmation_watch_sec=int(env_or_cfg("FEISHU_CONFIRMATION_WATCH_SEC", "confirmation_watch_sec", 65)),
        )


class FeishuBotAdapter:
    name = "feishu"

    def __init__(self, config: FeishuConfig, logger=None):
        self.config = config
        self.logger = logger
        self._tenant_access_token: Optional[str] = None
        self._tenant_access_token_expire_at = 0.0

    async def handle_callback(self, request, agent, background_tasks):
        raw_body = await request.body()
        if not self.verify_signature(request.headers, raw_body):
            return self.forbidden("invalid signature")
        payload = self.decode_payload(raw_body)
        if not self.verify_token(payload):
            return self.forbidden("invalid token")
        if self.is_url_verification(payload):
            return {"challenge": payload.get("challenge", "")}

        card_action = self.parse_card_action(payload)
        if card_action:
            result = await self.apply_confirmation_action_for_session(
                agent,
                card_action["session_id"],
                card_action["action"],
                card_action.get("request_id"),
            )
            return {
                "status": result.get("status"),
                "toast": {
                    "type": "success" if result.get("status") == "success" else "warning",
                    "content": result.get("message", "确认请求已处理。"),
                },
            }

        message = self.parse_event(payload)
        if not message:
            return {"status": "ignored"}

        if await self.is_duplicate_event(agent, message):
            return {"status": "duplicate_ignored"}

        confirm_action = self.parse_confirmation_action(message.get("text", ""))
        if confirm_action:
            result = await self.apply_confirmation_action(agent, message, confirm_action)
            if result.get("status") == "success":
                await self.deliver(message, result.get("message", "已处理确认请求。"))
            return result

        background_tasks.add_task(self.process_and_reply, agent, message)
        return {"status": "processing"}

    @staticmethod
    def forbidden(message: str):
        if HTTPException is not None:
            raise HTTPException(status_code=403, detail=message)
        return {"status": "error", "message": message}

    def decode_payload(self, raw_body: bytes) -> dict:
        payload = json.loads(raw_body.decode("utf-8"))
        encrypted = payload.get("encrypt")
        if not encrypted:
            return payload
        if not self.config.encrypt_key:
            raise ValueError("Encrypted Feishu callback requires FEISHU_ENCRYPT_KEY")
        return json.loads(self.decrypt_event_payload(encrypted))

    def decrypt_event_payload(self, encrypted_text: str) -> str:
        if Cipher is None:
            raise RuntimeError("cryptography is required to decrypt Feishu callback payloads")
        key = hashlib.sha256(self.config.encrypt_key.encode("utf-8")).digest()
        encrypted = base64.b64decode(encrypted_text)
        iv, cipher_text = encrypted[:16], encrypted[16:]
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend()).decryptor()
        padded = decryptor.update(cipher_text) + decryptor.finalize()
        pad_len = padded[-1]
        if pad_len < 1 or pad_len > 16:
            raise ValueError("Invalid Feishu encrypted payload padding")
        return padded[:-pad_len].decode("utf-8")

    def verify_signature(self, headers, raw_body: bytes) -> bool:
        signature = headers.get("X-Lark-Signature") or headers.get("x-lark-signature")
        if not signature:
            return True
        if not self.config.encrypt_key:
            return False
        timestamp = headers.get("X-Lark-Request-Timestamp") or headers.get("x-lark-request-timestamp") or ""
        nonce = headers.get("X-Lark-Request-Nonce") or headers.get("x-lark-request-nonce") or ""
        content = f"{timestamp}{nonce}{self.config.encrypt_key}".encode("utf-8") + raw_body
        expected = hashlib.sha256(content).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_token(self, payload: dict) -> bool:
        expected = self.config.verification_token
        if not expected:
            return True
        actual = payload.get("token") or payload.get("header", {}).get("token")
        return hmac.compare_digest(str(actual or ""), expected)

    @staticmethod
    def is_url_verification(payload: dict) -> bool:
        return payload.get("type") == "url_verification" and "challenge" in payload

    def parse_event(self, payload: dict) -> Optional[dict]:
        header = payload.get("header") or {}
        event = payload.get("event") or {}
        event_type = header.get("event_type") or payload.get("type")
        if event_type != "im.message.receive_v1":
            return None

        message = event.get("message") or {}
        if message.get("message_type") != "text":
            return None

        content = self.parse_message_content(message.get("content"))
        text = self.clean_message_text(content.get("text", ""))
        if not text:
            return None

        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        tenant_key = header.get("tenant_key") or ""
        user_id = sender_id.get("user_id") or sender_id.get("open_id") or sender_id.get("union_id") or "unknown"
        chat_id = message.get("chat_id") or user_id
        return {
            "event_id": header.get("event_id") or event.get("event_id"),
            "tenant_key": tenant_key,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message.get("message_id"),
            "chat_type": message.get("chat_type"),
            "text": text,
            "raw": payload,
        }

    @staticmethod
    def parse_card_action(payload: dict) -> Optional[dict]:
        header = payload.get("header") or {}
        event = payload.get("event") or {}
        event_type = header.get("event_type") or payload.get("type")
        if event_type not in {"card.action.trigger", "interactive_card.action_trigger"}:
            return None
        action = event.get("action") or payload.get("action") or {}
        value = action.get("value") or {}
        action_name = value.get("action")
        session_id = value.get("session_id")
        if action_name not in {"approve", "deny"} or not session_id:
            return None
        return {
            "action": action_name,
            "request_id": value.get("request_id"),
            "session_id": session_id,
        }

    @staticmethod
    def parse_message_content(content: Any) -> dict:
        if isinstance(content, dict):
            return content
        if not content:
            return {}
        try:
            return json.loads(content)
        except Exception:
            return {"text": str(content)}

    @staticmethod
    def clean_message_text(text: str) -> str:
        cleaned = re.sub(r"<at[^>]*>.*?</at>", "", text or "", flags=re.I | re.S)
        cleaned = re.sub(r"@_user_\d+", "", cleaned)
        return cleaned.strip()

    def session_id_for(self, message: dict) -> str:
        tenant = str(message.get("tenant_key") or "tenant")
        chat = str(message.get("chat_id") or message.get("user_id") or "default")
        safe_tenant = re.sub(r"[^a-zA-Z0-9_.:-]", "_", tenant)
        safe_chat = re.sub(r"[^a-zA-Z0-9_.:-]", "_", chat)
        return f"feishu_{safe_tenant}_{safe_chat}"

    async def is_duplicate_event(self, agent, message: dict) -> bool:
        event_id = message.get("event_id")
        if not event_id:
            return False
        try:
            key = f"feishu_event_seen:{event_id}"
            inserted = await agent.ctx.redis.set(key, "1", ex=300, nx=True)
            return inserted is False
        except Exception:
            return False

    def parse_confirmation_action(self, text: str) -> Optional[tuple[str, Optional[str]]]:
        normalized = (text or "").strip()
        if not normalized:
            return None
        parts = normalized.split()
        command = parts[0].lower()
        request_id = parts[1] if len(parts) > 1 else None
        if command in APPROVE_WORDS:
            return ("approve", request_id)
        if command in DENY_WORDS:
            return ("deny", request_id)
        return None

    async def apply_confirmation_action(self, agent, message: dict, action_info: tuple[str, Optional[str]]) -> dict:
        action, request_id = action_info
        session_id = self.session_id_for(message)
        return await self.apply_confirmation_action_for_session(agent, session_id, action, request_id)

    async def apply_confirmation_action_for_session(self, agent, session_id: str, action: str, request_id: Optional[str] = None) -> dict:
        pending = await self.find_pending_confirmation(agent, session_id, request_id)
        if not pending:
            return {"status": "not_found", "message": "没有找到待处理的确认请求。"}
        key, data = pending
        active_turn = await agent._get_active_chat_turn(session_id)
        request_turn = data.get("turn_id")
        if action == "approve" and request_turn and request_turn != active_turn:
            await agent._mark_confirmation_denied(key, data, "stale_confirmation_request")
            return {"status": "stale", "message": "确认请求已过期，请重新发起任务。"}
        data["status"] = "approved" if action == "approve" else "denied"
        await agent.ctx.redis.set(key, json.dumps(data, ensure_ascii=False), ex=60)
        return {
            "status": "success",
            "message": "已允许执行。" if action == "approve" else "已拒绝执行。",
            "request_id": data.get("request_id"),
        }

    async def find_pending_confirmation(self, agent, session_id: str, request_id: Optional[str] = None):
        try:
            keys = await agent.ctx.redis.keys(f"confirm_req:{session_id}:*")
        except Exception:
            return None
        for key in keys:
            data = await agent.confirmation_state.get_request(key)
            if not data or data.get("status") != "pending":
                continue
            if request_id and data.get("request_id") != request_id:
                continue
            return key, data
        return None

    async def process_and_reply(self, agent, message: dict):
        session_id = self.session_id_for(message)
        chat_task = asyncio.create_task(agent.chat(session_id, message.get("text", ""), domain="auto"))
        watcher_task = asyncio.create_task(self.watch_confirmations(agent, message, session_id, chat_task))
        try:
            answer = await chat_task
            await self.deliver(message, answer)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Feishu adapter chat failed: {e}", exc_info=True)
            await self.deliver(message, f"处理失败：{e}")
        finally:
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass

    async def watch_confirmations(self, agent, message: dict, session_id: str, chat_task: asyncio.Task):
        notified = set()
        deadline = time.time() + max(5, self.config.confirmation_watch_sec)
        while not chat_task.done() and time.time() < deadline:
            pending = await self.find_pending_confirmation(agent, session_id)
            if pending:
                _, data = pending
                request_id = data.get("request_id")
                if request_id and request_id not in notified:
                    notified.add(request_id)
                    prompt = data.get("prompt", "")
                    await self.deliver_confirmation(
                        message,
                        session_id=session_id,
                        request_id=request_id,
                        prompt=prompt,
                    )
            await asyncio.sleep(0.8)

    async def deliver(self, message: dict, answer: str):
        await self.deliver_message(message, "text", {"text": answer or ""})

    async def deliver_confirmation(self, message: dict, session_id: str, request_id: str, prompt: str):
        card = self.build_confirmation_card(session_id, request_id, prompt)
        if not self.config.reply_enabled or not self.config.app_id or not self.config.app_secret:
            fallback = (
                "需要你确认后才能继续执行。\n"
                f"请求 ID：{request_id}\n"
                f"{prompt}\n\n"
                f"回复 `/approve {request_id}` 允许，或 `/deny {request_id}` 拒绝。"
            )
            if self.logger:
                self.logger.info(f"[Feishu dry-run confirmation to {message.get('chat_id')}]: {fallback}")
            return
        await self.deliver_message(message, "interactive", card)

    @staticmethod
    def build_confirmation_card(session_id: str, request_id: str, prompt: str) -> dict:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "orange",
                "title": {"tag": "plain_text", "content": "需要确认后继续执行"},
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**请求 ID**：{request_id}\n\n{prompt}",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "允许"},
                            "type": "primary",
                            "value": {"action": "approve", "session_id": session_id, "request_id": request_id},
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "拒绝"},
                            "type": "danger",
                            "value": {"action": "deny", "session_id": session_id, "request_id": request_id},
                        },
                    ],
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"也可以回复 /approve {request_id} 或 /deny {request_id}",
                        }
                    ],
                },
            ],
        }

    async def deliver_message(self, message: dict, msg_type: str, content: Any):
        if not self.config.reply_enabled or not self.config.app_id or not self.config.app_secret:
            if self.logger:
                self.logger.info(f"[Feishu dry-run reply to {message.get('chat_id')}]: {content}")
            return
        if not message.get("message_id"):
            if self.logger:
                self.logger.warning("Feishu reply skipped: missing message_id")
            return
        if msg_type == "text":
            for chunk in self.split_text(content.get("text", "")):
                await self.reply_to_message(message["message_id"], "text", {"text": chunk})
            return
        await self.reply_to_message(message["message_id"], msg_type, content)

    @staticmethod
    def split_text(text: str, limit: int = 3500):
        text = text or ""
        if len(text) <= limit:
            return [text]
        chunks = []
        current = []
        current_len = 0
        for line in text.splitlines(True):
            if current_len + len(line) > limit and current:
                chunks.append("".join(current))
                current = []
                current_len = 0
            if len(line) > limit:
                for start in range(0, len(line), limit):
                    chunks.append(line[start:start + limit])
                continue
            current.append(line)
            current_len += len(line)
        if current:
            chunks.append("".join(current))
        return chunks

    async def tenant_access_token(self) -> str:
        if self._tenant_access_token and time.time() < self._tenant_access_token_expire_at - 60:
            return self._tenant_access_token
        url = f"{self.config.api_base}/open-apis/auth/v3/tenant_access_token/internal"
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json={"app_id": self.config.app_id, "app_secret": self.config.app_secret}) as resp:
                data = await resp.json(content_type=None)
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu tenant_access_token failed: {data}")
        self._tenant_access_token = data["tenant_access_token"]
        self._tenant_access_token_expire_at = time.time() + int(data.get("expire", 7200))
        return self._tenant_access_token

    async def reply_to_message(self, message_id: str, msg_type: str, content: dict):
        token = await self.tenant_access_token()
        url = f"{self.config.api_base}/open-apis/im/v1/messages/{message_id}/reply"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"msg_type": msg_type, "content": json.dumps(content, ensure_ascii=False)}
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=body) as resp:
                data = await resp.json(content_type=None)
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu reply failed: {data}")
