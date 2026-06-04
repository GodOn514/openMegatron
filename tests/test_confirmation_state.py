import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pysrc"))

from confirmation_state import ConfirmationStateTracker  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [key for key in self.values if key.startswith(prefix)]


class ConfirmationStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_becomes_stale_after_new_turn(self):
        tracker = ConfirmationStateTracker(FakeRedis())
        session_id = "default"
        await tracker.start_turn(session_id)
        pending = await tracker.create_pending_request(session_id, "Run tool?", "")
        data = pending["data"]

        self.assertFalse(await tracker.request_is_stale(session_id, data.get("turn_id")))

        await tracker.start_turn(session_id)
        self.assertTrue(await tracker.request_is_stale(session_id, data.get("turn_id")))

    async def test_cancel_pending_marks_request_denied(self):
        redis = FakeRedis()
        tracker = ConfirmationStateTracker(redis)
        session_id = "default"
        pending = await tracker.create_pending_request(session_id, "Run tool?", "")

        count = await tracker.cancel_pending(session_id, "new_message")
        data = await tracker.get_request(pending["key"])

        self.assertEqual(count, 1)
        self.assertEqual(data["status"], "denied")
        self.assertEqual(data["denial_reason"], "new_message")


if __name__ == "__main__":
    unittest.main()
