"""Optional local semantic embeddings with deterministic lexical fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .documents import DocumentCorpus
from .text_ml import (
    TextCitation,
    TextCluster,
    TextMLResult,
    TextRepresentative,
    analyze_text_corpus,
)


class LocalEmbeddingAdapter(Protocol):
    model_version: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class LocalSentenceTransformerAdapter:
    """Load an explicitly configured local model without downloading assets."""

    def __init__(self, model_path: str | Path) -> None:
        path = Path(model_path).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("semantic model path must be an existing local directory")
        self.model_path = path
        self.model_version = path.name

    def encode(self, texts: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        model = SentenceTransformer(str(self.model_path), local_files_only=True)
        vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return np.asarray(vectors, dtype=float).tolist()


def semantic_cluster(
    corpus: DocumentCorpus,
    *,
    adapter: LocalEmbeddingAdapter,
    seed: int = 7,
    max_clusters: int = 6,
) -> TextMLResult:
    lexical = analyze_text_corpus(corpus, seed=seed, max_clusters=max_clusters)
    passages = [
        (section.text, TextCitation(document.name, document.sha256, section.start_line, section.end_line))
        for document in corpus.documents
        for section in document.sections
        if section.text.strip()
    ][:1_000]
    try:
        vectors = np.asarray(adapter.encode([text for text, _ in passages]), dtype=float)
        if vectors.ndim != 2 or vectors.shape[0] != len(passages) or vectors.shape[1] < 2:
            raise ValueError("embedding adapter returned an invalid shape")
        if not np.isfinite(vectors).all():
            raise ValueError("embedding adapter returned non-finite values")
        if len(passages) < 2:
            raise ValueError("semantic clustering requires at least two passages")
        model = _select_semantic_model(vectors, seed, max_clusters)
        distances = model.transform(vectors)
        clusters = []
        for cluster_index in sorted(set(int(label) for label in model.labels_)):
            members = [index for index, label in enumerate(model.labels_) if int(label) == cluster_index]
            representative_index = min(
                members,
                key=lambda index: (float(distances[index, cluster_index]), index),
            )
            text, citation = passages[representative_index]
            topic = lexical.topics[cluster_index % len(lexical.topics)] if lexical.topics else None
            keywords = topic.keywords if topic else ()
            label = topic.label if topic else f"语义聚类 {cluster_index + 1}"
            clusters.append(
                TextCluster(
                    f"semantic-cluster-{cluster_index + 1}",
                    label,
                    keywords,
                    tuple(sorted({passages[index][1].document for index in members})),
                    TextRepresentative(
                        text[:500],
                        1 / (1 + float(distances[representative_index, cluster_index])),
                        citation,
                    ),
                )
            )
        versions = dict(lexical.model_versions)
        versions["semantic"] = str(getattr(adapter, "model_version", type(adapter).__name__))
        return TextMLResult(
            lexical.corpus_id,
            "completed",
            "local_embeddings",
            lexical.topics,
            tuple(clusters),
            lexical.outliers,
            lexical.keyword_weights,
            versions,
            lexical.diagnostics,
            seed,
        )
    except Exception as exc:
        diagnostic = {
            "code": "embedding_model_unavailable",
            "message": f"本地语义模型不可用，已回退 TF-IDF：{type(exc).__name__}",
        }
        return TextMLResult(
            lexical.corpus_id,
            lexical.status,
            "tfidf_fallback",
            lexical.topics,
            lexical.clusters,
            lexical.outliers,
            lexical.keyword_weights,
            lexical.model_versions,
            (diagnostic, *lexical.diagnostics),
            seed,
        )


def _select_semantic_model(vectors: np.ndarray, seed: int, max_clusters: int) -> KMeans:
    upper = min(max_clusters, len(vectors) - 1)
    candidates = []
    for count in range(2, upper + 1):
        model = KMeans(n_clusters=count, random_state=seed, n_init=20).fit(vectors)
        if len(set(int(label) for label in model.labels_)) < 2:
            continue
        score = float(silhouette_score(vectors, model.labels_))
        candidates.append((score, -count, model))
    if not candidates:
        return KMeans(n_clusters=1, random_state=seed, n_init=1).fit(vectors)
    return max(candidates, key=lambda item: item[:2])[2]
