"""Paired / alternating baseline-treatment scheduling for Slice 14B."""

from __future__ import annotations

from collections.abc import Sequence


def paired_alternating_schedule(
    subjects: Sequence[str],
    variants: Sequence[str],
) -> list[tuple[str, str]]:
    """Return ``(subject, variant)`` pairs in paired/alternating order.

    For subjects ``[Q1, Q2]`` and variants ``[baseline, treatment]`` this yields::

        (Q1, baseline), (Q1, treatment), (Q2, baseline), (Q2, treatment), …

    rather than all-baseline then all-treatment.
    """
    if not subjects:
        raise ValueError("subjects must be non-empty")
    if not variants:
        raise ValueError("variants must be non-empty")
    if len(subjects) != len(set(subjects)):
        raise ValueError("duplicate subjects are forbidden")
    if len(variants) != len(set(variants)):
        raise ValueError("duplicate variants are forbidden")
    return [(subject, variant) for subject in subjects for variant in variants]
