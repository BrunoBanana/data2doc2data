from pathlib import Path
import tempfile
import unittest

from data2doc2data.retrieval import index_documents, search_chunks


class RetrievalTests(unittest.TestCase):
    def test_chinese_bigram_ranking_preserves_word_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supporting_path = root / "supporting.md"
            reversed_path = root / "reversed.md"
            supporting_path.write_text("激活上升，同时留存下降。", encoding="utf-8")
            reversed_path.write_text("激活下降，同时留存上升。", encoding="utf-8")

            ranked = search_chunks(
                "激活上升 留存下降",
                index_documents([reversed_path, supporting_path]),
            )

            self.assertEqual(ranked[0].path, supporting_path.resolve())

    def test_chunk_records_line_range_and_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            document_path = Path(directory) / "decision.md"
            document_path.write_text("First line\nsecond line\n\nAnother paragraph\n", encoding="utf-8")

            chunks = index_documents([document_path])

            self.assertEqual(chunks[0].start_line, 1)
            self.assertEqual(chunks[0].end_line, 2)
            self.assertEqual(chunks[1].start_line, 4)
            self.assertRegex(chunks[0].sha256, r"^[0-9a-f]{64}$")

    def test_search_excludes_completely_unrelated_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            document_path = Path(directory) / "decision.md"
            document_path.write_text("Quarterly hiring plan.", encoding="utf-8")

            ranked = search_chunks("激活上升 留存下降", index_documents([document_path]))

            self.assertEqual(ranked, [])

    def test_cache_is_private_and_invalidates_changed_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = root / "decision.md"
            cache_path = root / "config" / "document-index.json"
            document_path.write_text("Retention falls.", encoding="utf-8")
            first = index_documents([document_path], cache_path=cache_path)

            document_path.write_text("Retention rises.", encoding="utf-8")
            second = index_documents([document_path], cache_path=cache_path)

            self.assertEqual(cache_path.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(first[0].sha256, second[0].sha256)
            self.assertIn("rises", second[0].text)


if __name__ == "__main__":
    unittest.main()
