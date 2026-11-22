"""Compare both production scorer strategies on synthetic local workloads."""

import argparse
import json
import os
import resource
from time import perf_counter, process_time

import torch

from offline_rag.config.models import RerankerSettings
from offline_rag.rerank.cross_encoder import CrossEncoderReranker
from offline_rag.rerank.protocol import RerankerPair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    cfg = RerankerSettings()
    scorer = CrossEncoderReranker(
        model_path=args.model_path,
        model_id=cfg.model.model_id,
        model_revision=cfg.model.revision,
        adapter_contract=cfg.model.adapter_contract,
        device=args.device,
    )
    tokenizer, model = scorer._load()
    if any(param.dtype != torch.float32 for param in model.parameters()):
        raise RuntimeError("Expected the approved FP32 model")
    print(
        json.dumps(
            {
                "torch": str(torch.__version__),
                "device": args.device,
                "affinity": len(os.sched_getaffinity(0)),
                "threads": [2, 2],
                "revision": cfg.model.revision,
            }
        ),
        flush=True,
    )

    def synchronize():
        if args.device == "cuda":
            torch.cuda.synchronize()

    for workload, lengths in (
        ("short_homogeneous", [40] * 10),
        ("mixed", [160, 12, 55, 24, 90, 35] * 5),
    ):
        words = ["copper", "map", "salt", "desk", "book", "tree"]
        pairs = [
            RerankerPair(
                str(ordinal),
                "Why does copper conduct electricity?",
                (words[ordinal % len(words)] + " ") * length + str(ordinal),
            )
            for ordinal, length in enumerate(lengths)
        ]
        for strategy in ("consecutive", "length_sorted_8"):
            scorer.batching_strategy = strategy
            scorer._loaded = (tokenizer, model)
            scorer.score_pairs(pairs)
        baseline = None
        for strategy in (
            "consecutive",
            "length_sorted_8",
            "length_sorted_8",
            "consecutive",
        ):
            timings = []
            prepass = []

            class TimedTokenizer:
                def __getattr__(self, name):
                    return getattr(tokenizer, name)

                def __call__(self, observed=prepass, **kwargs):
                    start = perf_counter()
                    result = tokenizer(**kwargs)
                    if not kwargs["padding"]:
                        observed.append(perf_counter() - start)
                    return result

            scorer._loaded = (TimedTokenizer(), model)
            scorer.batching_strategy = strategy
            original_forward = model.forward

            def timed_forward(forward=original_forward, observed=timings, **kwargs):
                synchronize()
                start = perf_counter()
                result = forward(**kwargs)
                synchronize()
                observed.append(
                    [list(kwargs["input_ids"].shape), perf_counter() - start]
                )
                return result

            model.forward = timed_forward
            try:
                synchronize()
                start, cpu = perf_counter(), process_time()
                scores = scorer.score_pairs(pairs)
                synchronize()
                result = {
                    "workload": workload,
                    "strategy": strategy,
                    "wall_s": perf_counter() - start,
                    "cpu_s": process_time() - cpu,
                    "prepass_s": sum(prepass),
                    "batches": timings,
                    "process_peak_rss_kib": resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss,
                }
            finally:
                model.forward = original_forward
            if baseline is None:
                baseline = scores
            torch.testing.assert_close(
                torch.tensor(scores), torch.tensor(baseline), rtol=1e-5, atol=1e-4
            )

            def rank(values, candidates=pairs):
                return sorted(
                    range(len(candidates)),
                    key=lambda i: (-values[i], candidates[i].chunk_id),
                )

            if rank(scores) != rank(baseline):
                raise RuntimeError("Rank parity failed")
            result["max_abs_logit_delta"] = max(
                abs(score - reference)
                for score, reference in zip(scores, baseline, strict=True)
            )
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
