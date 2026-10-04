"""Abandoned unpublished candidate recovery (D15) — never auto-publish."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from offline_rag.config.models import AppSettings


def candidates_dir(corpora_root: Path, corpus_name: str) -> Path:
    return corpora_root / corpus_name / "candidates"


def abandoned_dir(corpora_root: Path, corpus_name: str) -> Path:
    return corpora_root / corpus_name / "abandoned"


def recover_abandoned_candidates(settings: AppSettings) -> list[Path]:
    """Quarantine unpublished candidate remnants under corpus-local abandoned/.

    Never advances the product published pointer. Safe when no candidates exist.
    """
    corpora_root = settings.paths.corpora
    moved: list[Path] = []
    if not corpora_root.exists() or not corpora_root.is_dir():
        return moved

    for corpus_dir in sorted(corpora_root.iterdir()):
        if not corpus_dir.is_dir() or corpus_dir.name.startswith("."):
            continue
        cand_root = corpus_dir / "candidates"
        if not cand_root.exists() or not cand_root.is_dir():
            continue
        children = [p for p in cand_root.iterdir() if not p.name.startswith(".")]
        if not children:
            continue
        dest_root = abandoned_dir(corpora_root, corpus_dir.name)
        dest_root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        for child in children:
            target = dest_root / f"{stamp}-{child.name}"
            # Avoid collisions if recovery runs twice in the same second.
            n = 0
            while target.exists():
                n += 1
                target = dest_root / f"{stamp}-{child.name}.{n}"
            shutil.move(str(child), str(target))
            moved.append(target)
    return moved
