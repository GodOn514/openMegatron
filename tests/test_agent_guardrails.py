import unittest
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pysrc"))
from pysrc.agent import YuanGeAgent


class FakeToolManager:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        self.tools[tool.name] = tool


class AgentGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.agent = YuanGeAgent.__new__(YuanGeAgent)

    def test_repairs_utf8_as_latin1_mojibake(self):
        mojibake = "人机协同 信息系统".encode("utf-8").decode("latin1")
        repaired = self.agent._repair_mojibake_text(mojibake)
        self.assertIn("人机协同", repaired)
        self.assertIn("信息系统", repaired)

    def test_repairs_gbk_as_latin1_mojibake(self):
        mojibake = "人机协同 信息系统".encode("gbk").decode("latin1")
        repaired = self.agent._repair_mojibake_text(mojibake)
        self.assertIn("人机协同", repaired)
        self.assertIn("信息系统", repaired)

    def test_simple_research_lookup_detects_repaired_text(self):
        mojibake = "人机协同 信息系统 论文 给出链接".encode("gbk").decode("latin1")
        self.assertTrue(self.agent._is_simple_research_lookup(mojibake))

    def test_simple_research_lookup_excludes_review_requests(self):
        self.assertFalse(self.agent._is_simple_research_lookup("人机协同论文综述"))

    def test_trace_detects_successful_wrapped_paper_fetch_output(self):
        arguments = json.dumps({
            "skill_name": "paper_fetch_review",
            "args_string": json.dumps({"query": "human-AI collaboration"}),
        })
        trace = {
            "tool_calls": [
                {
                    "tool": "run_skill_script",
                    "arguments": arguments,
                    "parsed_output": {
                        "status": "success",
                        "output": json.dumps({"status": "success", "valid_count": 1, "papers": [{"title": "x"}]}),
                    },
                }
            ]
        }
        self.assertTrue(self.agent._trace_has_successful_paper_fetch(trace))


class SkillLoaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_loader_accepts_bom_and_crlf_front_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "research" / "bom-skill"
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "main.py").write_text("def main(**kwargs):\n    return {'status': 'success'}\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "\ufeff---\r\n"
                "name: bom_skill\r\n"
                "description: Test skill with BOM and CRLF front matter.\r\n"
                "entry_function: main\r\n"
                "parameters:\r\n"
                "  type: object\r\n"
                "  properties: {}\r\n"
                "---\r\n"
                "\r\n"
                "# Body\r\n",
                encoding="utf-8",
            )

            agent = YuanGeAgent.__new__(YuanGeAgent)
            agent.skills_dir = root
            agent.tool_manager = FakeToolManager()
            await agent._load_skills()

            self.assertIn("bom_skill", agent.loaded_skills)


if __name__ == "__main__":
    unittest.main()
