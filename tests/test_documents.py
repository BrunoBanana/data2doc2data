from pathlib import Path
import tempfile
import unittest

from data2doc2data.documents import build_document_corpus, parse_document


class DocumentCorpusTests(unittest.TestCase):
    def test_markdown_sections_keep_lines_hash_and_verbatim_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strategy.md"
            path.write_text("# 增长策略\n\n收入目标提升 10%。\n\n## 风险\n\n成本可能上升。\n", encoding="utf-8")

            document = parse_document(path)

        self.assertEqual(document.title, "增长策略")
        self.assertEqual([section.heading for section in document.sections], ["增长策略", "风险"])
        self.assertEqual(document.sections[0].start_line, 1)
        self.assertIn("收入目标提升 10%", document.sections[0].text)
        self.assertRegex(document.sha256, r"^[0-9a-f]{64}$")

    def test_corpus_deduplicates_content_and_records_partial_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.md"
            duplicate = root / "duplicate.txt"
            bad = root / "bad.md"
            first.write_text("同一份策略。", encoding="utf-8")
            duplicate.write_text("同一份策略。", encoding="utf-8")
            bad.write_bytes(b"\xff")

            corpus = build_document_corpus((first, duplicate, bad), "corpus-1")

        self.assertEqual(len(corpus.documents), 1)
        self.assertEqual(corpus.duplicate_count, 1)
        self.assertEqual(len(corpus.failures), 1)
        self.assertEqual(corpus.failures[0].name, "bad.md")


if __name__ == "__main__":
    unittest.main()
