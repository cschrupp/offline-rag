"""Run the accepted lifecycle loopback with the combined scorer wiring.

The loopback owns transport and worker tests. A deterministic FP32 forward
fixture makes held-worker cases reproducible without native BGE timing.
"""

import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import torch

from offline_rag.config.models import RerankerSettings
from offline_rag.rerank.cross_encoder import CrossEncoderReranker

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests/unit/app"))
import test_slice16d_b3_conversation as fixture


class TinyTokenizer:
    def encode(self, text, *, add_special_tokens):
        return list(text.encode())

    def __call__(self, *, text, text_pair, max_length, truncation, padding, **_):
        assert truncation == "only_second"
        rows = [
            [
                1,
                *self.encode(query, add_special_tokens=False),
                2,
                *self.encode(passage, add_special_tokens=False)[
                    : max_length - len(query.encode()) - 3
                ],
                2,
            ]
            for query, passage in zip(text, text_pair, strict=True)
        ]
        if not padding:
            return {"input_ids": rows}
        width = max(map(len, rows))
        ids = torch.tensor([row + [0] * (width - len(row)) for row in rows])
        return {"input_ids": ids}


class FixtureCrossEncoder(CrossEncoderReranker):
    def __init__(self):
        model = RerankerSettings().model
        super().__init__(
            model_path=Path(os.environ["SENECA_STAGE2_LOCAL_BGE"]),
            model_id=model.model_id,
            model_revision=model.revision,
            adapter_contract=model.adapter_contract,
            device="cpu",
            batching_strategy=os.environ["OFFLINE_RAG_RERANKER_BATCHING_STRATEGY"],
        )
        self._loaded = (
            TinyTokenizer(),
            lambda input_ids: SimpleNamespace(
                logits=input_ids.sum(dim=1, keepdim=True).float()
            ),
        )


fixture.FakeReranker = FixtureCrossEncoder
script = (
    ROOT
    / "docs/evidence/workspace-conversation-lifecycle-implementation/owned_loopback.py"
)
namespace = runpy.run_path(str(script))
if len(sys.argv) == 4:
    namespace["serve"](Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]))
else:
    import tempfile

    run = namespace["run"]
    run.__globals__["__file__"] = __file__
    with tempfile.TemporaryDirectory(prefix="seneca-integrated-") as directory:
        run(Path(directory), Path(sys.argv[1]).resolve())
