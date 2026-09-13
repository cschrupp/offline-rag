# Offline Runtime Contract

## Claim

OfflineRAG's strict-offline profile must be able to execute ingestion, chunking, dense indexing/retrieval, lexical BM25 indexing/retrieval, hybrid RRF, hybrid-rerank, context assembly, grounded local generation (via an approved external OpenAI-compatible endpoint), and corresponding evaluation without using internet/cloud services after provisioning.

Context expansion (7), grounded generation/citation membership validation (8), and retrieval-eval harness (9) are implemented. Milestone 4 offline gold authoring: Slice **9A** boundary done ([`slice9a_gold_authoring.md`](slice9a_gold_authoring.md)); next is **9B**. Semantic answer/citation quality evaluation is Milestone 5 / Slice 10.

**Currently enforceable offline after provisioning:** Docling PDF parse, tiktoken chunk budgets, Qwen (or FakeEmbedder) dense index/retrieve/eval, project-owned BM25 lexical index/retrieve/eval, hybrid RRF / hybrid-rerank / hybrid-rerank-context, grounded `query` against an approved local generator, Qdrant Local.

## Allowed runtime communication

- loopback/application-local communication;
- application container -> explicitly approved host/local generation endpoint;
- optional explicitly approved local-network services in non-standalone profiles.

## Forbidden in strict mode

- cloud LLM endpoints;
- cloud embedding/reranking endpoints;
- remote evaluators/judges;
- remote tracing;
- telemetry that transmits corpus/query content;
- runtime model downloads;
- silent fallback from a local provider to a cloud provider.

## Why endpoint validation is not enough

A process listening on localhost can itself proxy to a remote/cloud model. Strict mode therefore validates both:

1. the approved endpoint; and
2. the approved local model identifier/manifest.

The manifest is a trust assertion owned by the deployment operator.

## Verification levels

### Level 1 — configuration audit

Validate endpoints, model identifiers, local asset availability, tracing/telemetry settings, and absence of cloud credentials in the active profile.

### Level 2 — network observation

Run integration tests while monitoring outbound connections and verify that only expected local/host communication occurs.

### Level 3 — disconnected/egress-restricted host

Run the complete benchmark/demo after disabling internet access or applying outbound egress controls. This is the preferred evidence for the public strict-offline claim.

## Evidence to record

Store with the release benchmark:

- OS/container runtime;
- OfflineRAG image digest/version;
- generator runtime/version;
- approved model identifier;
- embedding/reranker model hashes or versions;
- active config hash;
- date;
- verification level;
- result.
