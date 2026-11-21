"""Research-only local BGE forward pilot using synthetic incident-length pairs."""

import hashlib
import json
import os
import platform
import resource
import sys
from pathlib import Path
from time import perf_counter, process_time

import torch
import transformers

from offline_rag.core.ids import RAW_LOGIT_SCORE_CONTRACT
from offline_rag.rerank.cross_encoder import CrossEncoderReranker

LENGTHS = [
    31,
    41,
    368,
    99,
    111,
    241,
    188,
    286,
    104,
    338,
    132,
    278,
    19,
    104,
    175,
    158,
    150,
    200,
    234,
    166,
    406,
    22,
    86,
    20,
    71,
    221,
    238,
    20,
    297,
    178,
]
REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
QUERY = "Which ingredients go into oven chips?"
WORDS = (" oil", " salt", " food", " red", " water", " green")
ADAPTER = "sentence-transformers-cross-encoder-v1"


ATOL = 1e-4
RTOL = 1e-5


def assign_logits(scores, seen, group, logits):
    if (
        len(set(group)) != len(group)
        or seen.intersection(group)
        or any(not 0 <= candidate < len(scores) for candidate in group)
    ):
        raise ValueError("candidate-score association is invalid")
    if (
        logits.shape != (len(group), 1)
        or logits.dtype != torch.float32
        or not torch.isfinite(logits).all()
    ):
        raise ValueError("expected one finite FP32 logit per candidate")
    scores[group] = logits.squeeze(1)
    seen.update(group)


def rank_scores(scores, seen):
    if seen != set(range(len(scores))):
        raise ValueError("candidate scores are missing")
    return sorted(seen, key=lambda i: (-scores[i].item(), i))


def check_parity(baseline, candidate):
    close = torch.allclose(candidate[1], baseline[1], atol=ATOL, rtol=RTOL)
    rank_match = baseline[2] == candidate[2]
    print(
        json.dumps(
            {
                "parity_block": baseline[0]["block"],
                "allclose": close,
                "rank_match": rank_match,
                "atol": ATOL,
                "rtol": RTOL,
                "max_abs_difference": (baseline[1] - candidate[1]).abs().max().item(),
            }
        ),
        flush=True,
    )
    if not close or not rank_match:
        raise ValueError("pilot parity failed")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(model_path):
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    reranker = CrossEncoderReranker(
        model_path=model_path,
        model_id="BAAI/bge-reranker-v2-m3",
        model_revision=REVISION,
        adapter_contract=ADAPTER,
        score_transform=RAW_LOGIT_SCORE_CONTRACT,
        device="cpu",
    )
    tokenizer, model = reranker._load()
    reranker._assert_query_fits(tokenizer, QUERY)
    if any(p.dtype != torch.float32 for p in model.parameters()):
        raise ValueError("expected FP32 model parameters")
    overhead = len(tokenizer(QUERY, text_pair="oil")["input_ids"]) - 1
    passages = [
        WORDS[i % len(WORDS)] * (length - overhead) for i, length in enumerate(LENGTHS)
    ]
    order = sorted(range(30), key=lambda i: (LENGTHS[i], i))
    arms = {
        "consecutive16": [list(range(16)), list(range(16, 30))],
        "sorted8": [order[i : i + 8] for i in range(0, 30, 8)],
    }
    print(
        json.dumps(
            {
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "python": platform.python_version(),
                "machine": platform.machine(),
                "cpu_model": next(
                    line.partition(":")[2].strip()
                    for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")
                ),
                "affinity_count": len(os.sched_getaffinity(0)),
                "threads": [2, 2],
                "revision": REVISION,
                "weights_sha256": sha256(model_path / "model.safetensors"),
                "tokenizer_sha256": sha256(model_path / "tokenizer.json"),
            }
        ),
        flush=True,
    )
    outputs = []
    inputs = {}
    for block, names in enumerate((list(arms), list(arms), list(reversed(arms)))):
        for name in names:
            scores = torch.empty(30, dtype=torch.float32)
            seen = set()
            timings = []
            started = perf_counter()
            for group in arms[name]:
                tokens = tokenizer(
                    text=[QUERY] * len(group),
                    text_pair=[passages[i] for i in group],
                    truncation="only_second",
                    max_length=1024,
                    padding=True,
                    return_tensors="pt",
                )
                for ordinal, candidate in enumerate(group):
                    active = tokens["attention_mask"][ordinal].bool()
                    if active.sum().item() != LENGTHS[candidate]:
                        raise ValueError("candidate token length changed")
                    identity = tokens["input_ids"][ordinal, active].tolist()
                    if inputs.setdefault(candidate, identity) != identity:
                        raise ValueError("candidate encoded inputs changed")
                with torch.inference_mode():
                    wall, cpu = perf_counter(), process_time()
                    logits = model(**tokens).logits
                    timings.append(
                        [
                            list(tokens["input_ids"].shape),
                            perf_counter() - wall,
                            process_time() - cpu,
                        ]
                    )
                assign_logits(scores, seen, group, logits)
            rank = rank_scores(scores, seen)
            record = {
                "block": block,
                "arm": name,
                "warmup": block == 0,
                "batches": timings,
                "scorer_wall_s": perf_counter() - started,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
            outputs.append((record, scores, rank))
            print(json.dumps(record), flush=True)
    for block in (1, 2):
        baseline = next(
            row
            for row in outputs
            if row[0]["block"] == block and row[0]["arm"] == "consecutive16"
        )
        sorted_arm = next(
            row
            for row in outputs
            if row[0]["block"] == block and row[0]["arm"] == "sorted8"
        )
        check_parity(baseline, sorted_arm)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
