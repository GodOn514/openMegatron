import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TaskFocus:
    routing_text: str
    prompt_context: str = ""
    anchored_user_request: Optional[str] = None


class ConversationFlow:
    TOOL_FOLLOWUP_MARKERS = [
        "call my tool", "use my tool", "directly call", "run the tool", "run_skill_script",
        "\u76f4\u63a5\u8c03\u7528", "\u8c03\u7528\u6211\u7684\u5de5\u5177", "\u7528\u6211\u7684\u5de5\u5177",
        "\u8dd1\u5de5\u5177", "\u7528\u5de5\u5177", "\u5de5\u5177\u5462",
    ]
    FOLLOWUP_MARKERS = [
        "\u8fd9\u4e2a", "\u8fd9\u4ef6\u4e8b", "\u521a\u624d", "\u4e0a\u9762", "\u5b83", "\u90a3\u4e2a", "\u5462",
        "\u94fe\u63a5", "\u7ed9\u51fa\u94fe\u63a5", "\u53c2\u8003\u94fe\u63a5", "\u786e\u5b9a", "\u786e\u8ba4", "\u8ba9\u6211\u786e\u5b9a",
        "this", "that", "it", "above", "previous", "earlier", "link", "links", "confirm",
    ]
    REFUSAL_MARKERS = [
        "\u6211\u4e0d\u80fd", "\u4e0d\u80fd", "\u65e0\u6cd5", "\u62d2\u7edd", "\u4e0d\u652f\u6301", "\u9650\u5236",
        "i cannot", "i can't", "cannot", "can't help", "unable to", "not allowed", "blocked", "policy",
    ]

    def normalize(self, text: str) -> str:
        return (text or "").strip().lower()

    def looks_chinese(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

    def previous_user_message(self, history: List[dict]) -> Optional[str]:
        for item in reversed(history or []):
            if item.get("role") == "user":
                content = str(item.get("content") or "").strip()
                if content:
                    return content
        return None

    def previous_assistant_message(self, history: List[dict]) -> Optional[str]:
        for item in reversed(history or []):
            if item.get("role") == "assistant":
                content = str(item.get("content") or "").strip()
                if content:
                    return content
        return None

    def is_tool_followup(self, user_input: str) -> bool:
        lower = self.normalize(user_input)
        return any(marker in lower for marker in self.TOOL_FOLLOWUP_MARKERS)

    def is_link_confirmation_followup(self, user_input: str) -> bool:
        lower = self.normalize(user_input)
        markers = ["\u94fe\u63a5", "\u7ed9\u51fa\u94fe\u63a5", "\u53c2\u8003\u94fe\u63a5", "\u786e\u5b9a", "\u786e\u8ba4", "link", "links", "confirm"]
        return any(marker in lower for marker in markers)

    def is_context_dependent_followup(self, user_input: str) -> bool:
        lower = self.normalize(user_input)
        if not lower or self._has_direct_resource(user_input):
            return False
        if self.is_tool_followup(user_input):
            return True
        return len(user_input.strip()) <= 80 and any(marker in lower for marker in self.FOLLOWUP_MARKERS)

    def should_refuse_tool_bypass_after_refusal(self, user_input: str, history: List[dict]) -> bool:
        if not self.is_tool_followup(user_input):
            return False
        previous_answer = self.previous_assistant_message(history) or ""
        lower_answer = self.normalize(previous_answer)
        return any(marker in lower_answer for marker in self.REFUSAL_MARKERS)

    def tool_bypass_refusal(self, user_input: str) -> str:
        if self.looks_chinese(user_input):
            return "\u5de5\u5177\u8c03\u7528\u4e5f\u5fc5\u987b\u9075\u5b88\u521a\u624d\u7684\u9650\u5236\u6216\u62d2\u7edd\uff0c\u4e0d\u80fd\u7528\u201c\u76f4\u63a5\u8c03\u5de5\u5177\u201d\u6765\u7ed5\u8fc7\u3002\u5982\u679c\u4f60\u662f\u5728\u6d4b\u8bd5\u4e0d\u540c\u8eab\u4efd\u4e0b\u7684\u5de5\u5177\u5206\u914d\uff0c\u8bf7\u660e\u786e\u63d0\u4f9b\u5f53\u524d\u8eab\u4efd\u548c\u8981\u6d4b\u7684\u5de5\u5177\u7b56\u7565\u3002"
        return "Tool calls must follow the same restriction or refusal from the previous turn; they cannot be used as a bypass. For a tool-routing test, provide the current identity and routing policy to test."

    def build_task_focus(self, user_input: str, history: List[dict]) -> TaskFocus:
        previous_user = self.previous_user_message(history)
        if previous_user and self.is_context_dependent_followup(user_input):
            prompt_context = (
                "The current user message is a follow-up to the immediate previous user request. "
                "Keep tool routing and execution anchored to that immediate request. "
                "Do not resume older goals or workflow patterns unless the user explicitly mentions them."
            )
            if self.is_link_confirmation_followup(user_input):
                prompt_context += (
                    " If the user asks for links or confirmation, provide source links for the papers/items just discussed "
                    "in the previous assistant answer; do not switch back to a broader literature-review objective."
                )
            return TaskFocus(
                routing_text=f"{previous_user}\nFollow-up: {user_input}",
                prompt_context=prompt_context,
                anchored_user_request=previous_user,
            )
        return TaskFocus(routing_text=user_input)

    def _has_direct_resource(self, text: str) -> bool:
        return bool(re.search(
            r"https?://|www\.|[a-zA-Z]:[\\/]|/[^ \n\t]+|\b[A-Z]{1,10}[a-zA-Z0-9_-]{6,}\b|\b\d{8,}\b|10\.\d{4,9}/[-._;()/:A-Z0-9]+",
            text or "",
            re.I,
        ))
