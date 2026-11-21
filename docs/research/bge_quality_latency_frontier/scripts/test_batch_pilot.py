"""Check parity failure behavior without loading a checkpoint."""

import pytest
import torch
from batch_pilot import assign_logits, check_parity, rank_scores


def test_assignment_restores_original_candidate_order():
    scores = torch.empty(3)
    seen = set()
    assign_logits(scores, seen, [2, 0], torch.tensor([[0.5], [1.0]]))
    with pytest.raises(ValueError, match="missing"):
        rank_scores(scores, seen)
    with pytest.raises(ValueError, match="association"):
        assign_logits(scores, seen, [2], torch.tensor([[0.5]]))
    assign_logits(scores, seen, [1], torch.tensor([[1.0]]))
    assert scores.tolist() == [1.0, 1.0, 0.5]
    assert rank_scores(scores, seen) == [0, 1, 2]


@pytest.mark.parametrize(
    ("group", "logits", "message"),
    [
        ([0, 0], [[0.0], [0.0]], "association"),
        ([3], [[0.0]], "association"),
        ([0, 1], [[0.0]], "FP32"),
        ([0], [[float("nan")]], "FP32"),
    ],
)
def test_invalid_assignment_fails_closed(group, logits, message):
    with pytest.raises(ValueError, match=message):
        assign_logits(torch.empty(3), set(), group, torch.tensor(logits))


@pytest.mark.parametrize(
    ("scores", "order"),
    [([0.1, 0.0], [0, 1]), ([0.0, 0.00001], [1, 0])],
)
def test_numeric_or_rank_mismatch_fails(scores, order):
    baseline = ({"block": 1}, torch.tensor([0.0, 0.0]), [0, 1])
    with pytest.raises(ValueError, match="parity failed"):
        check_parity(baseline, ({"block": 1}, torch.tensor(scores), order))


def test_parity_passes_with_tolerated_change_and_stable_rank():
    baseline = ({"block": 1}, torch.tensor([1.0, 0.0]), [0, 1])
    check_parity(baseline, ({"block": 1}, torch.tensor([1.00001, 0.0]), [0, 1]))
