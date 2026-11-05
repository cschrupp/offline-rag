"""Opt-in functional smoke for the configured local conversation generator."""

from __future__ import annotations

import json
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
            {
                "name": "summary",
                "request": (
                    'Summarize this: "The pump stopped at noon. The operator '
                    'restarted it at 12:15. It then ran for six hours."'
                ),
                "operation": "summarize",
                "target": (
                    "The pump stopped at noon. The operator restarted it at "
                    "12:15. It then ran for six hours."
                ),
            },
            {
                "name": "rewrite",
                "request": 'Rewrite this: "The operator closed the red valve."',
                "operation": "rewrite",
                "target": "The operator closed the red valve.",
            },
            {
                "name": "translation_es",
                "request": 'Translate this into Spanish: "The pump is ready."',
                "operation": "translate",
                "target": "The pump is ready.",
            },
        )
        results: dict[str, str] = {}
        for case in cases:
            request_text = case["request"]
            route = route_conversation_intent(request_text, ())
            assert route.kind == "conversation_transform"
            assert route.operation == case["operation"]
            assert route.instruction is not None
            assert route.target_text is not None
            result = transform_conversation_text(
                runtime,
                operation=route.operation,
                instruction=route.instruction,
                target_text=route.target_text,
            )
            result = result.strip()
            assert result
            results[case["name"]] = result

        summary = results["summary"].lower()
        assert len(summary.split()) < len(cases[0]["target"].split())
        assert "pump" in summary
        assert "six hours" in summary or "6 hours" in summary

        rewrite = results["rewrite"].lower()
        original_rewrite = cases[1]["target"].lower()
        assert rewrite != original_rewrite
        assert "operator" in rewrite
        assert "valve" in rewrite and ("closed" in rewrite or "shut" in rewrite)

        translation = results["translation_es"].lower()
        assert "bomba" in translation
        assert "lista" in translation or "preparada" in translation
        print(
            "BETA_CONV_01_LOCAL_MODEL_RESULT="
            + json.dumps(results, ensure_ascii=False, sort_keys=True)
        )
    finally:
        generator.close()
