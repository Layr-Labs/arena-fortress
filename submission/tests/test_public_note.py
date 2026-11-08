"""Keep the shipped research note compact enough for the documented input contract."""
import json
from pathlib import Path
import unittest


class PublicNoteTests(unittest.TestCase):
    def test_note_size_and_dependency_contract(self):
        root = Path(__file__).resolve().parents[1]
        note = (root / "NOTE.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(note.encode("utf-8")), 5 * 1024)
        # Leave headroom below the documented 40,000-char note limit for CLI metadata.
        self.assertLessEqual(len(note), 30000)
        deps = (root / "dependencies.json").read_bytes()
        self.assertLess(len(deps), 64 * 1024)
        ids = [d["submissionId"] for d in json.loads(deps)]
        self.assertIn("9b597a76-9bf9-4923-a9d4-1c8ee83067a9", ids)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
