"""Loopback-only Stage 2 entry point using Seneca's provider factory seam."""

import json
import os
import re
from dataclasses import replace

import torch
import uvicorn

from offline_rag.api.app import create_app
from offline_rag.app.runtime import default_resource_factories
from offline_rag.generation.fake import FakeGenerator


def respond(request):
    prompt = "\n".join(message.content for message in request.messages)
    handles = re.findall(r"\[EVIDENCE (E[1-9][0-9]*)\]", prompt)
    if not handles:
        raise ValueError("Stage 2 fixture requires a structured evidence handle")
    return json.dumps(
        {
            "abstain": False,
            "blocks": [
                {"text": "Stage 2 fixture answer.", "evidence_handles": handles[:1]}
            ],
            "abstention_reason": None,
        }
    )


def create_fixture_app():
    factories = replace(
        default_resource_factories(),
        generator_client=lambda _: FakeGenerator(response_fn=respond),
    )
    return create_app(factories=factories)


if __name__ == "__main__":
    if torch.version.cuda is not None or len(os.sched_getaffinity(0)) != 4:
        raise RuntimeError(
            "Stage 2 requires CPU-only Torch and four affinity-visible CPUs"
        )
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    uvicorn.run(create_fixture_app(), host="127.0.0.1", port=8080)
