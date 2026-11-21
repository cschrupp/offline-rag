"""Replay frozen retrieval order and summarize existing performance evidence."""

import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

from offline_rag.evaluation.gold import load_gold_dataset
from offline_rag.evaluation.metrics import score_ranking

DEPTHS = (5, 10, 15, 20, 30)
ARMS = ("RRF", *(f"BGE-{k}" for k in DEPTHS))
METRICS = (
    "ndcg5",
    "ndcg10",
    "recall5",
    "recall10",
    "precision5",
    "precision10",
    "hit5",
    "hit10",
    "mrr",
)


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(fused, pool, ranked):
    """Restrict the recorded complete total order to each original RRF prefix."""
    if (
        fused != pool
        or len(fused) != 30
        or len(ranked) != 30
        or len(set(fused)) != 30
        or set(ranked) != set(fused)
    ):
        raise ValueError("incomplete or inconsistent source orders")
    return {
        "RRF": fused,
        **{f"BGE-{k}": [x for x in ranked if x in set(fused[:k])] for k in DEPTHS},
    }


def metrics(case, ranking):
    score = score_ranking(
        case,
        ranking,
        requested_depth=len(ranking),
        hit_rate_30_applicable=len(ranking) >= 30,
    )
    return {
        "ndcg5": score.ndcg[5],
        "ndcg10": score.ndcg[10],
        "recall5": score.recall[5],
        "recall10": score.recall[10],
        "precision5": score.precision[5],
        "precision10": score.precision[10],
        "hit5": score.hit_rate[5],
        "hit10": score.hit_rate[10],
        "mrr": score.mrr,
    }


def summarize(rows):
    result = {}
    for arm in ARMS:
        by_metric = {}
        for metric in METRICS:
            values = [row["arms"][arm][metric] for row in rows]
            paired = [
                value - row["arms"]["BGE-30"][metric]
                for row, value in zip(rows, values, strict=True)
            ]
            rng = random.Random(59)
            samples = sorted(
                statistics.mean(rng.choices(paired, k=len(paired)))
                for _ in range(10_000)
            )
            by_metric[metric] = {
                "mean": statistics.mean(values),
                "delta_vs_30": statistics.mean(paired),
                "bootstrap_95": [samples[249], samples[9749]],
            }
        result[arm] = by_metric
    return result


def padding(lengths, groups):
    slots = sum(len(group) * max(group) for group in groups)
    active = sum(lengths)
    return {
        "widths": [max(group) for group in groups],
        "slots": slots,
        "padding": slots - active,
        "padding_fraction": (slots - active) / slots,
        "attention_proxy": sum(len(group) * max(group) ** 2 for group in groups),
    }


def main(root, gold_path, measurements, output):
    gold = load_gold_dataset(gold_path)
    left_path, right_path = (
        next((root / "eval/results/9h_p").glob(f"{key}_*full22.json")) for key in "EF"
    )
    cohort_path = next(
        (root / "eval/fixtures/sufficiency").glob(f"{gold.dataset_id}_*")
    )
    perf_path = next(
        root.glob("eval/results/performance_14/*/perfrun_deb*/aggregate.json")
    )
    left, right, perf = map(read, (left_path, right_path, perf_path))
    cohorts = read(cohort_path)
    assert cohorts["gold_dataset_id"] == gold.dataset_id
    membership = {row["case_id"]: row["label_cohort"] for row in cohorts["cases"]}
    for artifact in (left, right):
        for key, expected in (
            ("gold_dataset_id", gold.dataset_id),
            ("chunk_set_id", gold.meta.chunk_set_id),
            ("corpus_id", gold.meta.corpus_id),
        ):
            assert artifact[key] == expected
    for key in ("dense_index_id", "lexical_index_id", "fusion_config_hash"):
        assert left["semantic_provenance"][key] == right["semantic_provenance"][key]
    indexes = [
        {row["case_id"]: row for row in artifact["cases"]} for artifact in (left, right)
    ]
    assert (
        set(indexes[0])
        == set(indexes[1])
        == set(membership)
        == {case.id for case in gold.cases}
    )
    rows = []
    for number, case in enumerate(sorted(gold.cases, key=lambda value: value.id), 1):
        fused, reranked = (index[case.id] for index in indexes)
        assert (
            fused["error"] is None
            and reranked["error"] is None
            and case.quality_eligible
        )
        rankings = replay(
            fused["retrieved_chunk_ids"],
            reranked["diagnostics"]["input_pool_chunk_ids"],
            reranked["retrieved_chunk_ids"],
        )
        positives = {judgment.chunk_id for judgment in case.judgments}
        assert all(
            set(row["relevant_chunk_ids"]) == positives and row["query"] == case.query
            for row in (fused, reranked)
        )
        assert all(
            row["positive_judgment_count"] == len(positives)
            for row in (fused, reranked)
        )
        rows.append(
            {
                "ordinal": number,
                "category": case.category,
                "cohort": membership[case.id],
                "positive_labels": len(positives),
                "arms": {arm: metrics(case, rank) for arm, rank in rankings.items()},
                "positive_retention": {
                    arm: len(set(rank) & positives) for arm, rank in rankings.items()
                },
                "top5_overlap_bge30": {
                    arm: len(set(rank[:5]) & set(rankings["BGE-30"][:5]))
                    for arm, rank in rankings.items()
                },
            }
        )
    arms = []
    profile = None
    lengths = None
    for line in measurements.read_text().splitlines():
        if line.startswith("Profile "):
            profile = line.split()[1]
        if not line.startswith("{"):
            continue
        item = json.loads(line)
        if "bge_phase" in item and profile == "2/2" and item["bge_phase"] == "warm":
            observed = item["profile"]["batches"]
            lengths = [length for batch in observed for length in batch["lengths"]]
        if "assembler_total_ms" in item:
            arms.append(dict(item, profile=profile))
    assert lengths and len(lengths) == 30 and len(arms) == 6
    ordered = sorted(lengths)
    projections = {"consecutive16": padding(lengths, [lengths[:16], lengths[16:]])}
    for size in (16, 8, 4, 2):
        projections[f"sorted{size}"] = padding(
            lengths, [ordered[i : i + size] for i in range(0, 30, size)]
        )
    output.write_text(
        json.dumps(
            {
                "provenance": {
                    "gold": gold.dataset_id,
                    "chunk_set": gold.meta.chunk_set_id,
                    "corpus": gold.meta.corpus_id,
                    "rrf": left["run_id"],
                    "bge30": right["run_id"],
                    "14c": perf["run_id"],
                    "input_hashes": {
                        path.name: digest(path)
                        for path in (
                            left_path,
                            right_path,
                            cohort_path,
                            perf_path,
                            gold.path / "meta.json",
                            gold.path / "cases.jsonl",
                            measurements,
                        )
                    },
                },
                "cases": rows,
                "cohorts": {
                    name: summarize(
                        [row for row in rows if name == "all" or row["cohort"] == name]
                    )
                    for name in ("human_reviewed", "assistant_only", "all")
                },
                "14c_quality": perf["quality_by_variant"],
                "14c_latency": perf["by_variant"],
                "vm_observations": arms,
                "incident_lengths": lengths,
                "padding_projections": projections,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
