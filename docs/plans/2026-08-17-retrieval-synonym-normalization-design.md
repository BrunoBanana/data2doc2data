# Retrieval Synonym Normalization Design

**Date:** 2026-08-17

## Goal

Widen Chinese business-document recall without giving up determinism or the zero-dependency constraint. A user asking "客户流失" must find a document that says "用户流失"; an English query "revenue" must find "收入".

## Decision

- Add a static, auditable `SYNONYM_GROUPS` table to `retrieval.py`. Each group's first term is the canonical form; every other term normalizes to it before BM25 scoring.
- `build_synonym_map(groups)` flattens the groups into a `term -> canonical` lookup; `DEFAULT_SYNONYMS` is that map for the built-in groups.
- `_terms(value, synonyms)` applies the map to every extracted token (English words and Chinese bigrams/trigrams).
- `search_chunks(..., synonyms=DEFAULT_SYNONYMS)` passes the map through; callers may pass `None` to disable normalization.

## Why this stays deterministic and private

- The table is module-level static data, not a learned or loaded model; identical inputs always produce identical rankings.
- Normalization happens only at scoring time. Stored chunk text, line ranges, and hashes remain verbatim, so provenance and traceability are unchanged.
- No new runtime dependency: the mapping is a plain dict over standard-library string handling.

## Built-in groups

Business vocabulary that commonly varies across Chinese and English sources: 客户/用户, 收入/营收/销售额, 流失/流失率/churn, 留存/留存率/retention, 激活/激活率/activation, 转化/转化率/conversion, 利润/盈利, 成本/费用.

## Non-goals

- Direction words (上升/下降) are intentionally not normalized here; hypothesis parsing owns direction semantics and would conflict with a bag-of-words normalization.
- This is not semantic search; out-of-vocabulary paraphrases still require future work (an optional embedding extra, if the project ever opts into dependencies).

## Acceptance

- `search_chunks("客户流失", [chunk "用户流失…"])` returns the chunk.
- `search_chunks("revenue", [chunk "收入…"])` returns the chunk.
- `search_chunks("客户", chunks, synonyms=None)` returns nothing for a "用户"-only corpus.
- Chunk text is never rewritten.
