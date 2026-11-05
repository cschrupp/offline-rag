"""Opt-in functional smoke for the configured local conversation generator."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from offline_rag.app.conversation.intent import route_conversation_intent
from offline_rag.app.conversation.transform import transform_conversation_text
from offline_rag.app.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint_network_policy,
)
from offline_rag.config import load_dotenv, load_settings
from offline_rag.generation.openai_compatible import OpenAICompatibleGenerator


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("SENECA_RUN_LOCAL_MODEL_TEST") != "1",
    reason="set SENECA_RUN_LOCAL_MODEL_TEST=1 to call the configured loopback model",
)
def test_local_model_performs_summary_rewrite_and_translation() -> None:
    load_dotenv()
    settings = load_settings()
    if not settings.project.strict_offline:
        pytest.skip("functional smoke requires strict-offline generation")
    try:
        validate_endpoint_network_policy(
            settings.generation.base_url,
            strict_offline=True,
        )
    except EndpointPolicyError:
        pytest.skip("configured generation endpoint is not strict-offline/private")
    if not settings.generation.enabled:
        pytest.skip("generation is disabled in the active configuration")

    generator = OpenAICompatibleGenerator(settings)
    runtime = SimpleNamespace(
        settings=settings,
        resources=SimpleNamespace(generator_client=generator),
    )
    try:
        cases = (
            (
                'Summarize this: "The pump stopped. The operator restarted it."',
                "summarize",
            ),
            ('Rewrite this: "The valve was shut by the operator."', "rewrite"),
            ('Translate this into Spanish: "The pump is ready."', "translate"),
        )
        for request_text, expected_operation in cases:
            route = route_conversation_intent(request_text, ())
            assert route.kind == "conversation_transform"
            assert route.operation == expected_operation
            assert route.instruction is not None
            assert route.target_text is not None
            result = transform_conversation_text(
                runtime,
                operation=route.operation,
                instruction=route.instruction,
                target_text=route.target_text,
            )
            assert result.strip()
    finally:
        generator.close()
