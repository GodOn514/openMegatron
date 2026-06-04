import json
import re
import uuid
from dataclasses import dataclass
from typing import List


@dataclass
class SyntheticFunctionCall:
    name: str
    arguments: str


@dataclass
class SyntheticToolCall:
    id: str
    function: SyntheticFunctionCall
    textual: bool = True


class TextToolCallParser:
    def contains_tool_markup(self, content: str) -> bool:
        text = content or ""
        return "DSML" in text and "tool_calls" in text

    def parse(self, content: str) -> List[SyntheticToolCall]:
        if not self.contains_tool_markup(content):
            return []
        calls = []
        for tool_name, body in self._iter_invocations(content):
            params = self._parse_parameters(body)
            arguments = self._arguments_for_tool(tool_name, params)
            calls.append(
                SyntheticToolCall(
                    id=f"textcall_{uuid.uuid4().hex}",
                    function=SyntheticFunctionCall(name=tool_name, arguments=arguments),
                )
            )
        return calls

    def _iter_invocations(self, content: str):
        pattern = re.compile(
            r"<[^>]*invoke\s+name=[\"']([^\"']+)[\"'][^>]*>(.*?)</[^>]*invoke>",
            re.I | re.S,
        )
        yield from pattern.findall(content or "")

    def _parse_parameters(self, body: str) -> dict:
        params = {}
        pattern = re.compile(
            r"<[^>]*parameter\s+name=[\"']([^\"']+)[\"'][^>]*>(.*?)</[^>]*parameter>",
            re.I | re.S,
        )
        for name, value in pattern.findall(body or ""):
            params[name] = value.strip()
        return params

    def _arguments_for_tool(self, tool_name: str, params: dict) -> str:
        if tool_name == "run_skill_script":
            return json.dumps(
                {
                    "skill_name": params.get("skill_name", ""),
                    "args_string": params.get("args_string") or params.get("params_json") or "{}",
                },
                ensure_ascii=False,
            )
        return json.dumps(params, ensure_ascii=False)
