import unittest

from data2doc2data.semantic_text import LocalSentenceTransformerAdapter, semantic_cluster
from tests.test_text_ml import two_topic_corpus


class FakeLocalEmbeddingAdapter:
    model_version = "fake-local-1"

    def encode(self, texts: list[str]) -> list[list[float]]:
        delivery = [[1.0, 0.0], [0.9, 0.1], [0.95, 0.05]]
        pricing = [[0.0, 1.0], [0.1, 0.9], [0.05, 0.95]]
        return (delivery + pricing)[: len(texts)]


class UnavailableAdapter:
    model_version = "missing"

    def encode(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("local model is unavailable")


class SemanticTextTests(unittest.TestCase):
    def test_uses_injected_local_embeddings_without_network(self):
        result = semantic_cluster(two_topic_corpus(), adapter=FakeLocalEmbeddingAdapter(), seed=7)

        self.assertEqual(result.method, "local_embeddings")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.clusters), 2)
        self.assertEqual(result.model_versions["semantic"], "fake-local-1")
        for cluster in result.clusters:
            terms = set(cluster.keywords)
            if any(name.startswith("delivery") for name in cluster.documents):
                self.assertTrue({"物流", "延迟", "配送"} & terms)
            if any(name.startswith("price") for name in cluster.documents):
                self.assertTrue({"价格", "订阅", "套餐"} & terms)

    def test_falls_back_to_tfidf_when_local_model_is_unavailable(self):
        result = semantic_cluster(two_topic_corpus(), adapter=UnavailableAdapter(), seed=7)

        self.assertEqual(result.method, "tfidf_fallback")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.diagnostics[0]["code"], "embedding_model_unavailable")
        self.assertTrue(result.topics)

    def test_sentence_transformer_adapter_requires_an_existing_local_directory(self):
        with self.assertRaises(ValueError):
            LocalSentenceTransformerAdapter("/definitely/not/a/local/model")

    def test_rejects_invalid_embedding_shape_and_falls_back(self):
        class InvalidAdapter:
            def encode(self, texts: list[str]) -> list[list[float]]:
                return [[1.0]]

        result = semantic_cluster(two_topic_corpus(), adapter=InvalidAdapter(), seed=7)

        self.assertEqual(result.method, "tfidf_fallback")
        self.assertEqual(result.diagnostics[0]["code"], "embedding_model_unavailable")


if __name__ == "__main__":
    unittest.main()
