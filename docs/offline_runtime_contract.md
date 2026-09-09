# Offline Runtime Contract

## Claim

OfflineRAG's strict-offline profile must be able to execute ingestion, retrieval, reranking, generation, citation validation, and evaluation without using internet/cloud services after provisioning.

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
