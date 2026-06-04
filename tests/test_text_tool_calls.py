import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pysrc"))

from text_tool_calls import TextToolCallParser  # noqa: E402


class TextToolCallParserTests(unittest.TestCase):
    def test_recovers_run_skill_script_dsml(self):
        content = """
<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="run_skill_script">
<｜｜DSML｜｜parameter name="skill_name" string="true">paper_fetch_review</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="args_string" string="true">{"action":"fetch","query":"Mem0","year_start":2024}</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
"""
        calls = TextToolCallParser().parse(content)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].function.name, "run_skill_script")
        args = json.loads(calls[0].function.arguments)
        self.assertEqual(args["skill_name"], "paper_fetch_review")
        self.assertEqual(json.loads(args["args_string"])["query"], "Mem0")

    def test_ignores_plain_text(self):
        self.assertEqual(TextToolCallParser().parse("normal answer"), [])


if __name__ == "__main__":
    unittest.main()
