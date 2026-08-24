"""Offline, deterministic text topics, clustering, and word-cloud artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import html
import logging
import math
import random
import re
from types import MappingProxyType
from typing import Mapping

import jieba
import numpy as np
import sklearn
from sklearn.cluster import KMeans
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from .documents import DocumentCorpus


jieba.setLogLevel(logging.ERROR)

_STOPWORDS = frozenset(
    {
        "一个",
        "一些",
        "主要",
        "以及",
        "仍然",
        "成为",
        "需要",
        "可能",
        "客户",
        "持续",
        "导致",
        "进行",
        "问题",
        "反馈",
        "增加",
        "下降",
        "上涨",
        "改善",
        "要求",
        "认为",
        "时间",
        "the",
        "and",
        "for",
        "with",
    }
)


@dataclass(frozen=True)
class TextCitation:
    document: str
    sha256: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class TextRepresentative:
    text: str
    score: float
    citation: TextCitation


@dataclass(frozen=True)
class TextTopic:
    topic_id: str
    label: str
    keywords: tuple[str, ...]
    weight: float
    representatives: tuple[TextRepresentative, ...]


@dataclass(frozen=True)
class TextCluster:
    cluster_id: str
    label: str
    keywords: tuple[str, ...]
    documents: tuple[str, ...]
    representative: TextRepresentative


@dataclass(frozen=True)
class TextMLResult:
    corpus_id: str
    status: str
    method: str
    topics: tuple[TextTopic, ...]
    clusters: tuple[TextCluster, ...]
    outliers: tuple[str, ...]
    keyword_weights: Mapping[str, float]
    model_versions: Mapping[str, str]
    diagnostics: tuple[Mapping[str, object], ...] = ()
    seed: int = 0
    document_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "keyword_weights", MappingProxyType(dict(self.keyword_weights)))
        object.__setattr__(self, "model_versions", MappingProxyType(dict(self.model_versions)))
        object.__setattr__(
            self,
            "diagnostics",
            tuple(MappingProxyType(dict(item)) for item in self.diagnostics),
        )


@dataclass(frozen=True)
class _Passage:
    text: str
    citation: TextCitation


def analyze_text_corpus(
    corpus: DocumentCorpus,
    *,
    seed: int = 7,
    max_topics: int = 6,
    max_clusters: int = 6,
) -> TextMLResult:
    if max_topics < 1 or max_topics > 12 or max_clusters < 1 or max_clusters > 12:
        raise ValueError("topic and cluster limits must be between one and twelve")
    passages = _passages(corpus)
    versions = {"numpy": np.__version__, "scikit_learn": sklearn.__version__, "jieba": jieba.__version__}
    if not passages:
        return TextMLResult(
            corpus.corpus_id,
            "unavailable",
            "unavailable",
            (),
            (),
            (),
            {},
            versions,
            ({"code": "empty_corpus", "message": "文本语料为空。"},),
            seed,
            len(corpus.documents),
        )

    vectorizer = TfidfVectorizer(
        tokenizer=_tokens,
        token_pattern=None,
        lowercase=False,
        max_features=2_000,
        sublinear_tf=True,
    )
    try:
        matrix = vectorizer.fit_transform([passage.text for passage in passages])
    except ValueError:
        return TextMLResult(
            corpus.corpus_id,
            "unavailable",
            "unavailable",
            (),
            (),
            (),
            {},
            versions,
            ({"code": "empty_vocabulary", "message": "文本没有可分析的有效词项。"},),
            seed,
            len(corpus.documents),
        )
    terms = np.asarray(vectorizer.get_feature_names_out())
    totals = np.asarray(matrix.sum(axis=0)).ravel()
    keyword_weights = {
        str(terms[index]): float(totals[index])
        for index in np.argsort(totals)[::-1][:100]
        if totals[index] > 0
    }

    if len(passages) < 3 or matrix.shape[1] < 2:
        representative = _representative(passages[0], 1.0)
        keywords = tuple(keyword_weights)[:10]
        label = keywords[0] if keywords else passages[0].citation.document
        return TextMLResult(
            corpus.corpus_id,
            "completed",
            "tfidf_fallback",
            (TextTopic("topic-1", label, keywords, 1.0, (representative,)),),
            (TextCluster("cluster-1", label, keywords, (passages[0].citation.document,), representative),),
            (),
            keyword_weights,
            versions,
            ({"code": "small_corpus_fallback", "message": "语料过小，使用单主题 TF-IDF 回退。"},),
            seed,
            len(corpus.documents),
        )

    cluster_count, labels, centroids, distances = _cluster(matrix, seed, max_clusters)
    topic_count = min(max_topics, cluster_count, matrix.shape[0], matrix.shape[1])
    topic_weights, components = _topics(matrix, topic_count, seed)
    topics = _build_topics(passages, terms, topic_weights, components)
    clusters = _build_clusters(passages, terms, labels, centroids, distances)
    outliers = _outliers(passages, distances)
    return TextMLResult(
        corpus.corpus_id,
        "completed",
        "tfidf_nmf_kmeans",
        topics,
        clusters,
        outliers,
        keyword_weights,
        versions,
        (),
        seed,
        len(corpus.documents),
    )


def build_word_cloud_svg(
    weights: Mapping[str, float],
    *,
    width: int = 960,
    height: int = 480,
    seed: int = 7,
) -> str:
    if not 240 <= width <= 4_096 or not 160 <= height <= 2_048:
        raise ValueError("word-cloud canvas is outside supported bounds")
    items = [
        (str(term).strip(), float(weight))
        for term, weight in weights.items()
        if str(term).strip() and math.isfinite(float(weight)) and float(weight) > 0
    ]
    items.sort(key=lambda item: (-item[1], item[0]))
    items = items[:50]
    rng = random.Random(seed)
    palette = ("#00a955", "#151511", "#b87621", "#286c55", "#7b4b9d", "#a84634")
    maximum = max((weight for _, weight in items), default=1.0)
    columns = max(2, min(6, math.ceil(math.sqrt(max(1, len(items)) * width / height))))
    rows = max(1, math.ceil(max(1, len(items)) / columns))
    cell_width, cell_height = width / columns, height / rows
    elements = []
    for index, (term, weight) in enumerate(items):
        column, row = index % columns, index // columns
        font_size = 14 + 38 * math.sqrt(weight / maximum)
        x = (column + 0.5) * cell_width + rng.uniform(-0.08, 0.08) * cell_width
        y = (row + 0.55) * cell_height + rng.uniform(-0.08, 0.08) * cell_height
        color = palette[index % len(palette)]
        elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
            f'font-size="{font_size:.1f}" font-weight="700" fill="{color}">{html.escape(term)}</text>'
        )
    description = "、".join(html.escape(term) for term, _ in items[:10]) or "无可用关键词"
    return (
        f'<svg width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="关键词词云：{description}">'
        f'<rect width="100%" height="100%" fill="#fffdf7"/>{"".join(elements)}</svg>'
    )


def _passages(corpus: DocumentCorpus) -> list[_Passage]:
    values = []
    for document in corpus.documents:
        for section in document.sections:
            text = re.sub(r"(?m)^#{1,6}\s+", "", section.text).strip()
            if text:
                values.append(
                    _Passage(
                        text[:4_000],
                        TextCitation(document.name, document.sha256, section.start_line, section.end_line),
                    )
                )
    return values[:1_000]


def _tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]+", " ", text.lower())
    return [
        token
        for token in (item.strip() for item in jieba.lcut(cleaned, cut_all=False))
        if len(token) > 1 and token not in _STOPWORDS and not token.isdigit()
    ]


def _cluster(matrix, seed: int, max_clusters: int):
    upper = min(max_clusters, matrix.shape[0] - 1)
    best = None
    for count in range(2, upper + 1):
        model = KMeans(n_clusters=count, random_state=seed, n_init=20)
        labels = model.fit_predict(matrix)
        if len(set(int(label) for label in labels)) < 2:
            continue
        score = silhouette_score(matrix, labels, metric="cosine")
        candidate = (float(score), -count, labels, model.cluster_centers_, model.transform(matrix))
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        model = KMeans(n_clusters=1, random_state=seed, n_init=1).fit(matrix)
        return 1, model.labels_, model.cluster_centers_, model.transform(matrix)
    return -best[1], best[2], best[3], best[4]


def _topics(matrix, count: int, seed: int):
    model = NMF(n_components=count, init="nndsvda", random_state=seed, max_iter=600)
    return model.fit_transform(matrix), model.components_


def _build_topics(passages, terms, weights, components) -> tuple[TextTopic, ...]:
    topics = []
    for index, component in enumerate(components):
        keyword_indices = np.argsort(component)[::-1][:10]
        keywords = tuple(str(terms[item]) for item in keyword_indices if component[item] > 0)
        representative_indices = np.argsort(weights[:, index])[::-1][:3]
        representatives = tuple(
            _representative(passages[item], float(weights[item, index]))
            for item in representative_indices
            if weights[item, index] > 0
        )
        topics.append(
            TextTopic(
                f"topic-{index + 1}",
                keywords[0] if keywords else f"主题 {index + 1}",
                keywords,
                float(weights[:, index].sum()),
                representatives,
            )
        )
    return tuple(sorted(topics, key=lambda topic: (-topic.weight, topic.topic_id)))


def _build_clusters(passages, terms, labels, centroids, distances) -> tuple[TextCluster, ...]:
    clusters = []
    for cluster_index in sorted(set(int(label) for label in labels)):
        member_indices = [index for index, label in enumerate(labels) if int(label) == cluster_index]
        representative_index = min(member_indices, key=lambda index: (float(distances[index, cluster_index]), index))
        keyword_indices = np.argsort(centroids[cluster_index])[::-1][:10]
        keywords = tuple(str(terms[index]) for index in keyword_indices if centroids[cluster_index, index] > 0)
        clusters.append(
            TextCluster(
                f"cluster-{cluster_index + 1}",
                keywords[0] if keywords else f"聚类 {cluster_index + 1}",
                keywords,
                tuple(sorted({passages[index].citation.document for index in member_indices})),
                _representative(passages[representative_index], 1 - float(distances[representative_index, cluster_index])),
            )
        )
    return tuple(clusters)


def _outliers(passages, distances) -> tuple[str, ...]:
    nearest = np.min(distances, axis=1)
    if len(nearest) < 3 or float(np.std(nearest)) == 0:
        return ()
    threshold = float(np.mean(nearest) + 2 * np.std(nearest))
    return tuple(
        passages[index].citation.document
        for index in np.argsort(nearest)[::-1]
        if nearest[index] > threshold
    )[:20]


def _representative(passage: _Passage, score: float) -> TextRepresentative:
    return TextRepresentative(passage.text[:500], score, passage.citation)
