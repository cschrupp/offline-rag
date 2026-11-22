"""Local CrossEncoderReranker with raw logits and passage-only truncation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from threading import Lock

from offline_rag.config.models import AppSettings, RerankerBatchingStrategy
from offline_rag.core.ids import (
    RAW_LOGIT_SCORE_CONTRACT,
    SEQ_TRUNC_1024_PASSAGE_RIGHT,
)
from offline_rag.rerank.protocol import RerankerPair
from offline_rag.rerank.provision import (
    require_reranker_artifacts,
    resolve_reranker_model_dir,
)


class CrossEncoderRerankerError(RuntimeError):
    pass


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch
    except ImportError as exc:
        raise CrossEncoderRerankerError(
            "torch is required for CrossEncoderReranker"
        ) from exc
    return "cuda" if torch.cuda.is_available() else "cpu"


class CrossEncoderReranker:
    """Load a provisioned local sequence-classification reranker (raw logits)."""

    def __init__(
        self,
        *,
        model_path: Path,
        model_id: str,
        model_revision: str,
        adapter_contract: str,
        max_length: int = 1024,
        sequence_contract: str = SEQ_TRUNC_1024_PASSAGE_RIGHT,
        score_transform: str = RAW_LOGIT_SCORE_CONTRACT,
        device: str = "auto",
        batch_size: int = 16,
        batching_strategy: RerankerBatchingStrategy = "consecutive",
        local_files_only: bool = True,
        trust_remote_code: bool = False,
    ) -> None:
        if not local_files_only:
            raise CrossEncoderRerankerError("local_files_only must be true")
        if trust_remote_code:
            raise CrossEncoderRerankerError("trust_remote_code must be false")
        if sequence_contract == SEQ_TRUNC_1024_PASSAGE_RIGHT and max_length != 1024:
            raise CrossEncoderRerankerError(
                f"{SEQ_TRUNC_1024_PASSAGE_RIGHT} requires max_length=1024 (got {max_length})"
            )
        if score_transform != RAW_LOGIT_SCORE_CONTRACT:
            raise CrossEncoderRerankerError(
                f"unsupported score_transform: {score_transform} "
                f"(expected {RAW_LOGIT_SCORE_CONTRACT})"
            )
        if batch_size < 1:
            raise CrossEncoderRerankerError("batch_size must be >= 1")

        if batching_strategy not in ("consecutive", "length_sorted_8"):
            raise CrossEncoderRerankerError("unsupported reranker batching strategy")

        self.model_path = Path(model_path).expanduser().resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.adapter_contract = adapter_contract
        self.max_length = int(max_length)
        self.sequence_contract = sequence_contract
        self.score_transform = score_transform
        self.device = _resolve_device(device)
        self.batch_size = int(batch_size)
        self.batching_strategy = batching_strategy
        self.local_files_only = True
        self.trust_remote_code = False
        self._load_lock = Lock()
        self._tokenizer_lock = Lock()
        self._loaded: tuple[object, object] | None = None

        require_reranker_artifacts(
            self.model_path,
            expected_model_id=model_id,
            expected_revision=model_revision,
            expected_adapter_contract=adapter_contract,
        )

    @classmethod
    def from_settings(cls, settings: AppSettings) -> CrossEncoderReranker:
        rrk = settings.reranker
        model_dir = resolve_reranker_model_dir(
            reranker_artifacts_root=settings.paths.reranker_artifacts,
            model_path=rrk.model.model_path,
        )
        return cls(
            model_path=model_dir,
            model_id=rrk.model.model_id,
            model_revision=rrk.model.revision,
            adapter_contract=rrk.model.adapter_contract,
            max_length=rrk.max_length,
            sequence_contract=rrk.sequence_contract,
            score_transform=rrk.score_transform,
            device=rrk.device,
            batch_size=rrk.batch_size,
            batching_strategy=rrk.batching_strategy,
            local_files_only=rrk.model.local_files_only,
            trust_remote_code=rrk.model.trust_remote_code,
        )

    def _load(self) -> tuple[object, object]:
        loaded = self._loaded
        if loaded is not None:
            return loaded

        with self._load_lock:
            if self._loaded is None:
                # Publish the pair only after initialization succeeds. A failed
                # attempt leaves the next caller free to retry.
                self._loaded = self._initialize()
            return self._loaded

    def _initialize(self) -> tuple[object, object]:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            str(self.model_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            str(self.model_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        self._require_materialized(model)
        model.eval()
        model.to(self.device)
        self._require_materialized(model)
        return tokenizer, model

    @staticmethod
    def _require_materialized(model) -> None:
        if any(tensor.is_meta for tensor in model.parameters()) or any(
            tensor.is_meta for tensor in model.buffers()
        ):
            raise CrossEncoderRerankerError(
                "reranker checkpoint contains unmaterialized meta parameters or buffers"
            )

    def _assert_query_fits(self, tokenizer: object, query_text: str) -> None:
        """Fail if query + pair specials cannot fit within max_length."""
        encode = getattr(tokenizer, "encode", None)
        if encode is None:
            raise CrossEncoderRerankerError("tokenizer missing encode()")
        query_ids = encode(query_text, add_special_tokens=False)
        specials = 3
        num_special = getattr(tokenizer, "num_special_tokens_to_add", None)
        if callable(num_special):
            specials = int(num_special(pair=True))
        if len(query_ids) + specials > self.max_length:
            raise CrossEncoderRerankerError(
                "query alone cannot fit within max_length under "
                f"{self.sequence_contract}: "
                f"query_tokens={len(query_ids)} specials={specials} "
                f"max_length={self.max_length}"
            )

    def score_pairs(self, pairs: Sequence[RerankerPair]) -> list[float]:
        if not pairs:
            return []

        for pair in pairs:
            if not isinstance(pair, RerankerPair) or any(
                not isinstance(text, str) or not text.strip()
                for text in (pair.chunk_id, pair.query_text, pair.passage_text)
            ):
                raise CrossEncoderRerankerError("invalid reranker pair")

        import torch

        tokenizer, model = self._load()
        with self._tokenizer_lock:
            seen_queries: set[str] = set()
            for pair in pairs:
                if pair.query_text not in seen_queries:
                    self._assert_query_fits(tokenizer, pair.query_text)
                    seen_queries.add(pair.query_text)

        order = list(range(len(pairs)))
        batch_size = self.batch_size
        if self.batching_strategy == "length_sorted_8":
            with self._tokenizer_lock:
                unpadded = tokenizer(
                    text=[pair.query_text for pair in pairs],
                    text_pair=[pair.passage_text for pair in pairs],
                    truncation="only_second",
                    max_length=self.max_length,
                    padding=False,
                    return_attention_mask=False,
                )["input_ids"]
            if len(unpadded) != len(pairs) or any(
                not 0 < len(ids) <= self.max_length for ids in unpadded
            ):
                raise CrossEncoderRerankerError("invalid reranker length prepass")
            order.sort(key=lambda ordinal: (len(unpadded[ordinal]), ordinal))
            batch_size = 8

        # Index by caller ordinal to preserve candidate identity across batches.
        scores: dict[int, float] = {}
        for start in range(0, len(order), batch_size):
            ordinals = order[start : start + batch_size]
            with self._tokenizer_lock:
                encoded = tokenizer(
                    text=[pairs[i].query_text for i in ordinals],
                    text_pair=[pairs[i].passage_text for i in ordinals],
                    truncation="only_second",
                    max_length=self.max_length,
                    padding=True,
                    return_tensors="pt",
                )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.inference_mode():
                logits = model(**encoded).logits
                if logits.shape != (len(ordinals), 1):
                    raise CrossEncoderRerankerError(
                        "expected single raw logit per pair "
                        f"(got logits shape {tuple(logits.shape)})"
                    )
                values = logits.view(-1).detach().cpu().tolist()

            for ordinal, value in zip(ordinals, values, strict=True):
                score = float(value)
                if not math.isfinite(score):
                    raise CrossEncoderRerankerError(
                        f"non-finite reranker logit: {score!r}"
                    )
                if ordinal in scores:
                    raise CrossEncoderRerankerError("duplicate reranker score ordinal")
                scores[ordinal] = score

        if scores.keys() != set(range(len(pairs))):
            raise CrossEncoderRerankerError("missing or invalid reranker score ordinal")
        return [scores[ordinal] for ordinal in range(len(pairs))]
