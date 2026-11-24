"""Execution-only settings used by deterministic Stage 2 provider fixtures."""

from __future__ import annotations


def configure_fixture_generation(settings):
    """Use an approved loopback placeholder for the in-process fake provider."""
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": "http://127.0.0.1:9/v1",
            "model": "stage2-synthetic-provider",
            "approved_endpoints": ["http://127.0.0.1:9/v1"],
            "approved_models": ["stage2-synthetic-provider"],
            "api_key": None,
        }
    )
    return settings.model_copy(update={"generation": generation})
