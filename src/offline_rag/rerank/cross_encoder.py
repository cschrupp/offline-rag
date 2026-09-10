"""Local CrossEncoderReranker with raw logits and passage-only truncation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from offline_rag.config.models import AppSettings
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
        raise CrossEncoderRerankerError("torch is required for CrossEncoderReranker") from exc
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

        self.model_path = Path(model_path).expanduser().resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.adapter_contract = adapter_contract
        self.max_length = int(max_length)
        self.sequence_contract = sequence_contract
        self.score_transform = score_transform
        self.device = _resolve_device(device)
        self.batch_size = int(batch_size)
        self.local_files_only = True
        self.trust_remote_code = False
        self._tokenizer = None
        self._model = None

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
            local_files_only=rrk.model.local_files_only,
            trust_remote_code=rrk.model.trust_remote_code,
        )

    def _load(self) -> tuple[object, object]:
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model

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
        model.eval()
        model.to(self.device)
        self._tokenizer = tokenizer
        self._model = model
        return tokenizer, model

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

        import torch

        tokenizer, model = self._load()
        seen_queries: set[str] = set()
        for pair in pairs:
            if pair.query_text not in seen_queries:
                self._assert_query_fits(tokenizer, pair.query_text)
                seen_queries.add(pair.query_text)

        scores: list[float] = []
        for start in range(0, len(pairs), self.batch_size):
            batch = pairs[start : start + self.batch_size]
            queries = [pair.query_text for pair in batch]
            passages = [pair.passage_text for pair in batch]
            encoded = tokenizer(
                text=queries,
                text_pair=passages,
                truncation="only_second",
                max_length=self.max_length,
                padding=True,
                return_tensors="pt",
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.inference_mode():
                logits = model(**encoded).logits
                if logits.ndim != 2 or logits.shape[-1] != 1:
                    raise CrossEncoderRerankerError(
                        "expected single raw logit per pair "
                        f"(got logits shape {tuple(logits.shape)})"
                    )
                values = logits.view(-1).detach().cpu().tolist()

            for value in values:
                score = float(value)
                if not math.isfinite(score):
                    raise CrossEncoderRerankerError(
                        f"non-finite reranker logit: {score!r}"
                    )
                scores.append(score)

        if len(scores) != len(pairs):
            raise CrossEncoderRerankerError(
                f"score count mismatch: got {len(scores)} for {len(pairs)} pairs"
            )
        return scores
