"""OfflineRAG-owned BM25 Okapi scorer (bm25-okapi-v1)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, MutableMapping

from offline_rag.core.ids import BM25_OKAPI_CONTRACT


def idf(*, n: int, df: int) -> float:
    """Positive-smoothed RSJ IDF: ``ln(1 + (N - df + 0.5) / (df + 0.5))``."""
    if n < 0:
        raise ValueError("n must be >= 0")
    if df < 0:
        raise ValueError("df must be >= 0")
    return math.log(1.0 + (n - df + 0.5) / (df + 0.5))


def score_term_contribution(
    *,
    tf: float,
    doc_length: float,
    avgdl: float,
    idf_value: float,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    """Return one term's BM25 contribution for a document."""
    if tf <= 0.0:
        return 0.0
    if avgdl <= 0.0:
        raise ValueError("avgdl must be > 0")
    if doc_length < 0.0:
        raise ValueError("doc_length must be >= 0")
    denominator = tf + k1 * (1.0 - b + b * (doc_length / avgdl))
    if denominator == 0.0:
        return 0.0
    return idf_value * (tf * (k1 + 1.0)) / denominator


def score_document(
    *,
    term_tfs: Mapping[str, float],
    query_terms: Iterable[str],
    doc_length: float,
    avgdl: float,
    n: int,
    dfs: Mapping[str, int],
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    """Score one document for unique query terms under bm25-okapi-v1."""
    total = 0.0
    seen: set[str] = set()
    for term in query_terms:
        if term in seen:
            continue
        seen.add(term)
        tf = float(term_tfs.get(term, 0.0))
        if tf <= 0.0:
            continue
        df = int(dfs.get(term, 0))
        if df <= 0:
            continue
        total += score_term_contribution(
            tf=tf,
            doc_length=doc_length,
            avgdl=avgdl,
            idf_value=idf(n=n, df=df),
            k1=k1,
            b=b,
        )
    return total


def accumulate_scores(
    *,
    query_terms: Iterable[str],
    postings_by_term: Mapping[str, Mapping[str, float] | Iterable[tuple[str, float]]],
    doc_lengths: Mapping[str, float],
    avgdl: float,
    n: int,
    dfs: Mapping[str, int],
    k1: float = 1.2,
    b: float = 0.75,
) -> dict[str, float]:
    """Accumulate BM25 scores for documents matching any unique query term."""
    scores: MutableMapping[str, float] = {}
    seen: set[str] = set()
    for term in query_terms:
        if term in seen:
            continue
        seen.add(term)
        df = int(dfs.get(term, 0))
        if df <= 0:
            continue
        raw = postings_by_term.get(term)
        if raw is None:
            continue
        if isinstance(raw, Mapping):
            postings = raw.items()
        else:
            postings = raw
        idf_value = idf(n=n, df=df)
        for chunk_id, tf in postings:
            tf_value = float(tf)
            if tf_value <= 0.0:
                continue
            doc_length = float(doc_lengths[chunk_id])
            contrib = score_term_contribution(
                tf=tf_value,
                doc_length=doc_length,
                avgdl=avgdl,
                idf_value=idf_value,
                k1=k1,
                b=b,
            )
            scores[chunk_id] = scores.get(chunk_id, 0.0) + contrib
    return dict(scores)


class BM25OkapiV1Scorer:
    """Project-owned Okapi BM25 scorer with locked baseline parameters."""

    contract_version = BM25_OKAPI_CONTRACT
    k1: float = 1.2
    b: float = 0.75
    idf_contract = "rsj-positive-smoothed-v1"
    query_tf_contract = "unique-terms-v1"

    def __init__(self, *, k1: float = 1.2, b: float = 0.75) -> None:
        if k1 < 0.0 or b < 0.0:
            raise ValueError("BM25 parameters must be >= 0")
        self.k1 = float(k1)
        self.b = float(b)

    def idf(self, *, n: int, df: int) -> float:
        return idf(n=n, df=df)

    def score_document(
        self,
        *,
        term_tfs: Mapping[str, float],
        query_terms: Iterable[str],
        doc_length: float,
        avgdl: float,
        n: int,
        dfs: Mapping[str, int],
    ) -> float:
        return score_document(
            term_tfs=term_tfs,
            query_terms=query_terms,
            doc_length=doc_length,
            avgdl=avgdl,
            n=n,
            dfs=dfs,
            k1=self.k1,
            b=self.b,
        )

    def accumulate(
        self,
        *,
        query_terms: Iterable[str],
        postings_by_term: Mapping[str, Mapping[str, float] | Iterable[tuple[str, float]]],
        doc_lengths: Mapping[str, float],
        avgdl: float,
        n: int,
        dfs: Mapping[str, int],
    ) -> dict[str, float]:
        return accumulate_scores(
            query_terms=query_terms,
            postings_by_term=postings_by_term,
            doc_lengths=doc_lengths,
            avgdl=avgdl,
            n=n,
            dfs=dfs,
            k1=self.k1,
            b=self.b,
        )
