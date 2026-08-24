import unittest

from data2doc2data.documents import DocumentCorpus, DocumentSection, ParsedDocument
from data2doc2data.text_ml import analyze_text_corpus, build_word_cloud_svg


def document(name: str, text: str, line: int) -> ParsedDocument:
    return ParsedDocument(
        name=name,
        title=name.removesuffix(".md"),
        format="md",
        sha256=(name.encode("utf-8").hex() + "0" * 64)[:64],
        sections=(DocumentSection(name, text, line, line + 1),),
    )


def two_topic_corpus() -> DocumentCorpus:
    return DocumentCorpus(
        "corpus-topics",
        (
            document("delivery-1.md", "物流延迟，包裹到货太慢，客户投诉配送时效。", 2),
            document("delivery-2.md", "配送延误持续增加，仓库发货和物流履约需要改善。", 5),
            document("delivery-3.md", "到货时间不稳定，快递延迟导致履约投诉。", 8),
            document("price-1.md", "订阅价格上涨，客户认为套餐费用太高。", 11),
            document("price-2.md", "涨价后续费意愿下降，价格和折扣成为主要反馈。", 14),
            document("price-3.md", "套餐定价昂贵，客户要求降低订阅费用。", 17),
        ),
        (),
        0,
    )


class LocalTextMLTests(unittest.TestCase):
    def test_discovers_two_topics_with_representative_citations(self):
        result = analyze_text_corpus(two_topic_corpus(), seed=7, max_topics=2, max_clusters=2)

        self.assertEqual(result.method, "tfidf_nmf_kmeans")
        self.assertEqual(len(result.topics), 2)
        topic_terms = [set(topic.keywords) for topic in result.topics]
        self.assertTrue(any({"物流", "延迟"} & terms for terms in topic_terms))
        self.assertTrue(any({"价格", "订阅", "套餐"} & terms for terms in topic_terms))
        self.assertTrue(all(topic.representatives for topic in result.topics))
        self.assertTrue(all(topic.representatives[0].citation.start_line for topic in result.topics))
        self.assertEqual(len(result.clusters), 2)

    def test_output_is_deterministic_for_a_fixed_seed(self):
        first = analyze_text_corpus(two_topic_corpus(), seed=11, max_topics=2, max_clusters=2)
        second = analyze_text_corpus(two_topic_corpus(), seed=11, max_topics=2, max_clusters=2)

        self.assertEqual(first, second)

    def test_word_cloud_is_deterministic_offline_svg(self):
        first = build_word_cloud_svg({"退款": 10, "延迟": 7, "物流": 4}, width=640, height=320, seed=7)
        second = build_word_cloud_svg({"退款": 10, "延迟": 7, "物流": 4}, width=640, height=320, seed=7)

        self.assertEqual(first, second)
        self.assertIn("<svg", first)
        self.assertIn("退款", first)
        self.assertNotIn("http", first)
        self.assertIn('role="img"', first)

    def test_single_document_uses_a_bounded_fallback(self):
        corpus = DocumentCorpus(
            "corpus-single",
            (document("single.md", "退款投诉增加，退款处理时间过长。", 3),),
            (),
            0,
        )

        result = analyze_text_corpus(corpus, seed=7)

        self.assertEqual(result.method, "tfidf_fallback")
        self.assertEqual(len(result.topics), 1)
        self.assertEqual(len(result.clusters), 1)
        self.assertTrue(result.diagnostics)

    def test_empty_corpus_returns_an_explicit_unavailable_result(self):
        result = analyze_text_corpus(DocumentCorpus("empty", (), (), 0), seed=7)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.topics, ())
        self.assertTrue(result.diagnostics)


if __name__ == "__main__":
    unittest.main()
