# Slice 8 — Grounded local generation

Slice 8 turns Slice 7 evidence into a validator-owned grounded answer with
closed-world `ev_…` citations. The generative model runs outside OfflineRAG
(OpenAI-compatible / Ollama-on-host by default).

**Status:** implemented.

## Architecture

```text
offline-rag query
        ↓
Generation READY
        ↓
HybridRerankContextAssembler
        ↓
empty context? → insufficient_evidence / empty_context
        ↓
prompt-grounded-v1
        ↓
OpenAICompatibleGenerator (one attempt, no-retry-v1)
        ↓
grounded-answer-v1 parse/validate
        ↓
citation membership (current-query EvidenceUnit[])
        ↓
GroundedAnswerResult
```

Package: `src/offline_rag/generation/`

Orchestrator: `GroundedAnswerOrchestrator`

Public method: `query` (no retrieval-method selector)

## Configuration

```yaml
generation:
  enabled: true
  provider: openai_compatible
  base_url: http://127.0.0.1:11434/v1
  model: <approved-local-model-id>
  temperature: 0.0
  max_output_tokens: 1200
  timeout_seconds: 120
  approved_endpoints: [...]
  approved_models: [...]
```

Code-owned contracts (hashed into `gencfg_`):

| Contract | ID |
|---|---|
| Adapter | `openai-compatible-generator-v1` |
| Prompt | `prompt-grounded-v1` |
| Output | `grounded-answer-v1` |
| Recovery | `no-retry-v1` |

`gencfg_` hashes: provider, adapter, selected model, temperature, max_output_tokens, prompt/output/recovery contracts.

Not hashed: enabled, raw base_url, allowlists, timeout, upstream retrieval hashes.

Example semantic payload:

```json
{
  "provider": "openai_compatible",
  "adapter_contract": "openai-compatible-generator-v1",
  "model": "llama3.2:3b",
  "temperature": 0.0,
  "max_output_tokens": 1200,
  "prompt_contract": "prompt-grounded-v1",
  "output_contract": "grounded-answer-v1",
  "recovery_contract": "no-retry-v1"
}
```

→ `gencfg_<sha256>`

## Result statuses

| Status | Meaning |
|---|---|
| `answered` | Valid prose + ≥1 current-query `ev_` citations |
| `insufficient_evidence` | `empty_context` or `model_abstain` |
| `generation_failed` | Transport/parse/schema/context-window failure |
| `citation_invalid` | Schema-valid citations outside current evidence |

Unvalidated model prose never becomes public `answer_text`.

## Citation identity

Cite only `evidence_unit_id` (`ev_…`) from the current query’s `EvidenceUnit[]`.
Membership validity ≠ semantic support.

Valid IDs resolve to source chunk/document/section/page/clipping provenance.

## Prompt (`prompt-grounded-v1`)

Per-unit evidence wrappers (exact `EvidenceUnit.text`, assembly order preserved):

```text
### BEGIN EVIDENCE ev_...
<exact text>
### END EVIDENCE ev_...
```

Do not duplicate Slice 7 `assembled_text` into the prompt. Evidence is untrusted data.

## Output (`grounded-answer-v1`)

```json
{"abstain": false, "answer": "...", "citation_ids": ["ev_..."]}
```

or

```json
{"abstain": true, "answer": null, "citation_ids": []}
```

## Readiness

```text
Context READY + generation.enabled + approved endpoint/model
+ offline adapter + non-generative /models probe + model listed
→ Generation READY
```

No GenerationState. Doctor never pulls models or sends completions.

## CLI

```bash
offline-rag query --corpus <name> --query "..." [--json]
offline-rag eval query --dataset <path> --corpus <name>
```

Eval reports operational outcomes only (no answer correctness / faithfulness).

## Boundaries

- No second hard prompt-token budget (Slice 7 evidence budget unchanged)
- No automatic retries / repair / failover
- No retrieval-method selector on `query`
- No LangGraph / tool use / cloud fallback
- No semantic citation entailment / answer-quality metrics
