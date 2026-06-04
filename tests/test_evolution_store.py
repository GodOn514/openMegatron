import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pysrc"))

from evolution import EvolutionError, EvolutionStore  # noqa: E402


class EvolutionStoreTests(unittest.TestCase):
    def test_rejects_paths_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStore(Path(tmp))
            with self.assertRaises(EvolutionError):
                store.create_proposal(
                    title="bad",
                    summary="attempt escape",
                    files=[{"path": "../outside.txt", "content": "x"}],
                )

    def test_rejects_generated_and_secret_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionStore(Path(tmp))
            for blocked_path in ("node_modules/pkg/file.js", "pysrc/model.toml", ".runtime/state.json"):
                with self.subTest(blocked_path=blocked_path):
                    with self.assertRaises(EvolutionError):
                        store.create_proposal(
                            title="bad",
                            summary="blocked path",
                            files=[{"path": blocked_path, "content": "x"}],
                        )

    def test_apply_and_rollback_restores_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "docs" / "note.md"
            target.parent.mkdir(parents=True)
            target.write_text("before", encoding="utf-8")

            store = EvolutionStore(root)
            proposal = store.create_proposal(
                title="Update note",
                summary="Replace note content",
                files=[{"path": "docs/note.md", "content": "after", "summary": "new note"}],
            )

            applied = store.apply_proposal(proposal["id"], reviewer="tester")
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(target.read_text(encoding="utf-8"), "after")

            rolled_back = store.rollback_proposal(proposal["id"], reviewer="tester")
            self.assertEqual(rolled_back["status"], "rolled_back")
            self.assertEqual(target.read_text(encoding="utf-8"), "before")

    def test_rollback_removes_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "docs" / "new.md"
            store = EvolutionStore(root)
            proposal = store.create_proposal(
                title="Create note",
                summary="Create a new note",
                files=[{"path": "docs/new.md", "content": "new"}],
            )

            store.apply_proposal(proposal["id"], reviewer="tester")
            self.assertTrue(target.exists())
            store.rollback_proposal(proposal["id"], reviewer="tester")
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
