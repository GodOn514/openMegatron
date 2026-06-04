import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pysrc"))

from conversation_flow import ConversationFlow  # noqa: E402


class ConversationFlowTests(unittest.TestCase):
    def setUp(self):
        self.flow = ConversationFlow()

    def test_research_review_request_is_not_a_followup(self):
        request = "\u5e2e\u6211\u5199\u4e2a2024\u5e74\u4ee5\u540e\u667a\u80fd\u4f53\u8bb0\u5fc6\u7684\u6587\u732e\u7efc\u8ff0"
        focus = self.flow.build_task_focus(request, [])
        self.assertEqual(focus.routing_text, request)
        self.assertIsNone(focus.anchored_user_request)

    def test_tool_followup_anchors_to_immediate_previous_user_request(self):
        previous = "\u628a\u8fd9\u4e2a\u94fe\u63a5\u7684\u89c6\u9891\u4e0b\u8f7d\u5230D\u76d8"
        followup = "\u4f60\u76f4\u63a5\u8c03\u7528\u6211\u7684\u5de5\u5177\u5462"
        focus = self.flow.build_task_focus(followup, [{"role": "user", "content": previous}])
        self.assertEqual(focus.anchored_user_request, previous)
        self.assertIn(previous, focus.routing_text)
        self.assertIn(followup, focus.routing_text)

    def test_link_confirmation_followup_anchors_to_previous_research_request(self):
        previous = "\u5e2e\u6211\u67e5\u4e00\u4e0b2024\u5e74\u7684\u667a\u80fd\u4f53\u8bb0\u5fc6\u7684\u8bba\u6587\u53ef\u4ee5\u5417"
        followup = "\u7ed9\u51fa\u94fe\u63a5\u8ba9\u6211\u786e\u5b9a"
        focus = self.flow.build_task_focus(followup, [{"role": "user", "content": previous}])
        self.assertEqual(focus.anchored_user_request, previous)
        self.assertIn(previous, focus.routing_text)
        self.assertIn(followup, focus.routing_text)
        self.assertIn("source links", focus.prompt_context)

    def test_tool_followup_after_refusal_is_generic_bypass_refusal(self):
        history = [
            {"role": "user", "content": "\u628a\u8fd9\u4e2a\u94fe\u63a5\u7684\u89c6\u9891\u4e0b\u8f7d\u5230D\u76d8"},
            {"role": "assistant", "content": "\u6211\u65e0\u6cd5\u5904\u7406\u8fd9\u4e2a\u8bf7\u6c42\u3002"},
        ]
        followup = "\u4f60\u76f4\u63a5\u8c03\u7528\u6211\u7684\u5de5\u5177\u5462"
        self.assertTrue(self.flow.should_refuse_tool_bypass_after_refusal(followup, history))


if __name__ == "__main__":
    unittest.main()
