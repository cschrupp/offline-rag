# Project Structure

The project is organized around explicit domain boundaries. Framework-specific
integrations stay behind project-owned interfaces so parsing, storage, and
inference adapters can be replaced without rewriting the application core.
Future orchestration adapters such as LangGraph remain deferred / not
authorized in the accepted product disposition.

## Current repository map

Derived from the checked-out tree (not a hypothetical long-term sketch).

```text
offline-rag/
├── README.md
├── ROADMAP.md
├── DEPLOYMENT.md
├── DEVELOPMENT_GUIDE.md
├── PROJECT_STRUCTURE.md
├── ARCHITECTURE_DECISIONS.md
├── EVALUATION_HARNESS.md
├── SECURITY_MODEL.md
├── PORTFOLIO_DEMO.md              # publication artifact; update gated
├── project_description.md
├── detailed_implementation_slices.md
├── STARTER_PACKAGE_CONTENTS.md    # historical bootstrap snapshot
├── pyproject.toml
├── .env.example
├── config/
│   ├── base.yaml
│   ├── deployment/
│   │   ├── standalone_ollama.yaml
│   │   └── external_openai_compatible.yaml
│   └── experiments/               # ablation / measurement overlays
├── deploy/
│   ├── Dockerfile
│   └── docker-compose.example.yml
├── docs/                          # accepted slice evidence, amendments, plans
├── eval/                          # gold and evaluation datasets
├── models/                        # provisioned local weights (content gitignored)
├── scripts/
│   ├── provision_docling.py
│   ├── provision_tiktoken.py
│   ├── provision_embedding.py
│   └── …
├── src/offline_rag/
│   ├── cli.py
│   ├── settings.py
│   ├── api/                       # FastAPI surface + server entry
│   ├── app/                       # product use-cases (workspaces, ingest, query, …)
│   │   ├── workspace/
│   │   ├── conversation/
│   │   └── …
│   ├── ingestion/
│   ├── chunking/
│   ├── dense/
│   ├── lexical/
│   ├── hybrid/
│   ├── rerank/
│   ├── context/
│   ├── generation/
│   ├── sufficiency/
│   ├── recovery/                  # bounded contracts; product recovery disabled
│   ├── evaluation/                # retrieval / generation / security / performance
│   ├── gold_authoring/
│   ├── guardrails/
│   ├── domain/
│   ├── core/
│   ├── config/
│   └── observability/
├── ui/                            # Seneca React application
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/
│       ├── components/
│       ├── features/
│       ├── pages/
│       └── test/
└── tests/                         # pytest suite
```

Runtime data under `data/` (workspaces, traces, indexes, locks) is local state
and is not the source of truth for structure documentation.

## Deferred / future areas (not current inventory)

These remain deferred or unauthorized; they are not present as active product
paths:

- LangGraph product orchestration adapter
- NeMo Guardrails integration
- Distributed / server-mode Qdrant topology
- Publication-grade portfolio packaging (`PORTFOLIO_DEMO.md` update; Slice 18)
- Slice 17 regression-CI packaging gate

For status and authorization boundaries, see `ROADMAP.md` and
`docs/milestone7_performance_ui.md`.
