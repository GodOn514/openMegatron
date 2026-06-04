import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pysrc"))

from integrations.feishu_bot import FeishuBotAdapter, FeishuConfig  # noqa: E402
from confirmation_state import ConfirmationStateTracker  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [key for key in self.values if key.startswith(prefix)]


class FakeAgent:
    def __init__(self):
        self.ctx = type("Ctx", (), {"redis": FakeRedis()})()
        self.confirmation_state = ConfirmationStateTracker(self.ctx.redis)

    async def _get_active_chat_turn(self, session_id):
        return await self.confirmation_state.get_active_turn(session_id)

    async def _mark_confirmation_denied(self, key, data, reason):
        await self.confirmation_state.mark_denied(key, data, reason)


def receive_event(text="hello", event_id="evt_1"):
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "tenant_key": "tenant_1",
            "token": "verify-token",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }


class FeishuBotAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.adapter = FeishuBotAdapter(FeishuConfig(verification_token="verify-token", reply_enabled=False))

    def test_url_verification_payload(self):
        payload = {"type": "url_verification", "token": "verify-token", "challenge": "abc"}
        self.assertTrue(self.adapter.verify_token(payload))
        self.assertTrue(self.adapter.is_url_verification(payload))

    def test_parse_plain_text_event(self):
        message = self.adapter.parse_event(receive_event("<at id=\"bot\">bot</at> 帮我查论文"))
        self.assertEqual(message["user_id"], "ou_1")
        self.assertEqual(message["chat_id"], "oc_1")
        self.assertEqual(message["text"], "帮我查论文")
        self.assertEqual(self.adapter.session_id_for(message), "feishu_tenant_1_oc_1")

    async def test_duplicate_event_detection_uses_redis_nx(self):
        agent = FakeAgent()
        message = self.adapter.parse_event(receive_event())
        self.assertFalse(await self.adapter.is_duplicate_event(agent, message))
        self.assertTrue(await self.adapter.is_duplicate_event(agent, message))

    async def test_confirmation_command_approves_pending_request(self):
        agent = FakeAgent()
        message = self.adapter.parse_event(receive_event("/approve"))
        session_id = self.adapter.session_id_for(message)
        await agent.confirmation_state.start_turn(session_id)
        pending = await agent.confirmation_state.create_pending_request(session_id, "Run tool?", "")

        result = await self.adapter.apply_confirmation_action(agent, message, ("approve", None))
        stored = await agent.confirmation_state.get_request(pending["key"])

        self.assertEqual(result["status"], "success")
        self.assertEqual(stored["status"], "approved")

    async def test_card_action_approves_pending_request_by_session(self):
        agent = FakeAgent()
        session_id = "feishu_tenant_1_oc_1"
        await agent.confirmation_state.start_turn(session_id)
        pending = await agent.confirmation_state.create_pending_request(session_id, "Run tool?", "")
        request_id = pending["data"]["request_id"]
        payload = {
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger", "token": "verify-token"},
            "event": {
                "action": {
                    "value": {
                        "action": "approve",
                        "session_id": session_id,
                        "request_id": request_id,
                    }
                }
            },
        }

        action = self.adapter.parse_card_action(payload)
        result = await self.adapter.apply_confirmation_action_for_session(
            agent,
            action["session_id"],
            action["action"],
            action["request_id"],
        )
        stored = await agent.confirmation_state.get_request(pending["key"])

        self.assertEqual(result["status"], "success")
        self.assertEqual(stored["status"], "approved")

    def test_confirmation_card_contains_actions_and_fallback_commands(self):
        card = self.adapter.build_confirmation_card("feishu_tenant_chat", "req-1", "Run tool?")
        content = json.dumps(card, ensure_ascii=False)
        self.assertIn("允许", content)
        self.assertIn("拒绝", content)
        self.assertIn("/approve req-1", content)


if __name__ == "__main__":
    unittest.main()
