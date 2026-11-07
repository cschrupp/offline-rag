# BETA-CONV-01A PILOT-01 — Authority and Pre-Run Case Record

**Record state:** cases and run envelope frozen before inference; no model
inference has been sent as of this record.

**Starting code commit:** `023724c2b63ec5efd9e9e95cec7a14da8a1f8cbe`  
**Branch:** `implementation/beta-conv-01a-llm-task-planning`  
**Authority:** Human authorization in the PILOT-01 work order in conversation.

## Scope

Development-only feasibility comparison using the canonical
`POST /v1/workspaces/{workspace_id}/conversation/turn` endpoint, Seneca's
existing application factory, runtime, retrieval/transform executors, traces,
and evaluation evidence adapter. Use one local model instance and no more than
one request at a time.

The pilot is limited to the 24 development cases below: one attempt per case in
legacy mode and one in planner mode, maximum 48 HTTP attempts. Preserve the
existing 120-second provider-call bound, 300-second request watchdog, and
90-minute wall-clock limit. No retries. No held-out data, external inference,
planner activation, production changes, or promotion.

The pilot is exploratory engineering evidence, not formal accuracy,
statistical, safety, or production qualification. Human judgments will be
identified as provisional; no independent labels are claimed.

## Case selection

Source: `eval_prep_01/requests_development_candidate.jsonl`  
Selection seed: `beta-conv-01a-pilot-01-dev-v1`  
Dataset SHA-256: `d6c5982b38de197c32a15edd48a4621f9aec40059a17458c0f8d1551d7864b9a`  
Selection rule: per listed stratum, choose the Spanish example with the lowest
SHA-256 of `seed + NUL + case_id`, then fill the remaining quota from English
examples ranked by the same digest. This yields nine Spanish cases, one in each
stratum. The request hashes below are the dataset's canonical request hashes
and were independently recomputed before execution.

| Case ID | Stratum | Language | Request SHA-256 |
| --- | --- | --- | --- |
| `case-ff13b148e6b39449` | ambiguous_reference | en | `ff13b148e6b39449aaee827865f03b6f71d2a7accb03a5116ec295eda365079d` |
| `case-27f6ef8a466b3dc5` | ambiguous_reference | en | `27f6ef8a466b3dc53446176664092fb3f850e782b2a41253d5bca72b80d991a0` |
| `case-d63d0d3cf1ea493d` | ambiguous_reference | es | `d63d0d3cf1ea493d6ed5be6e033d2c63fe8265da196a431a90639e383cd80d0d` |
| `case-027ffb88734d7367` | contextual_grounded | es | `027ffb88734d736759140e74e8701cfd5dbf55b8fc5e58156a9d38e3f9eef209` |
| `case-5197b33787a167aa` | contextual_grounded | en | `5197b33787a167aac71bc3441241f32ee3140527e66037b9c23a8f596d13cced` |
| `case-6e364554084060ea` | contextual_grounded | en | `6e364554084060eaf4b6a609d4466e838a8b77cb9713b9e4276226753e59e439` |
| `case-f4fc707cda2239cf` | conversation_summary | en | `f4fc707cda2239cf18932b601ac6437b8d528f10a4a880a21eada03d44f65d26` |
| `case-bd3a5a88ef908aa4` | conversation_summary | es | `bd3a5a88ef908aa4a367e8b0e9f731e3ad53e1a9957a57b4518cfca287b7715a` |
| `case-563ce513cdd20fbd` | current_transform | es | `563ce513cdd20fbdcffdeeaac4db946de2b09bb61174cf0516f4bbae5d78ec97` |
| `case-ee5a82aeccaaa952` | current_transform | en | `ee5a82aeccaaa9527965b29d072ac44187c0936344815ec27c9b6ca43e367594` |
| `case-fc4195d9af2892bc` | current_transform | en | `fc4195d9af2892bc7b412e06113226bc359b2f5b15e1112670ae214b3766c9db` |
| `case-ea6a81968abebe0a` | factual_source | en | `ea6a81968abebe0adcf5f3ff15a5b0e36694421d230d38a5189044ab640d1170` |
| `case-f708ae4f3e6df91a` | factual_source | en | `f708ae4f3e6df91a3166fd38d21248af70d1e68dd89707e1c018c4c6e5dd1d1e` |
| `case-3243831e196d7f5c` | factual_source | es | `3243831e196d7f5c2f13f5b48c9fa2425c8929f372a10aa7a06c7917c4ab5f38` |
| `case-3730d576efe2d5bd` | factual_source | en | `3730d576efe2d5bddfa4236f54d9a4f46fdb83e6fd50bc9c7ec78270a4cbf50a` |
| `case-f42aa32f3bdadba2` | mixed_source_transform | en | `f42aa32f3bdadba2457b6c98cd4109abcfa91b870b4468637fe8578edc075f42` |
| `case-73d16bded13c9228` | mixed_source_transform | es | `73d16bded13c92282b32f8604d3b5129af92246201d28da81bd4483be5d65cc2` |
| `case-056e99dbee7160b4` | prior_transform | en | `056e99dbee7160b44c91a5c24e13012ad875ca960bedd3fc2e62d848fcc2cd17` |
| `case-bb7d8f06c76e0635` | prior_transform | en | `bb7d8f06c76e063586f78abfece695f2e2e9c68e077f4a6ad709c8e8ada10128` |
| `case-58f694818d5ca68f` | prior_transform | es | `58f694818d5ca68f4794795cb71921d3132ceee1167e6bad2751a940f09203c8` |
| `case-e99cd0d66f6f52da` | prompt_injection | en | `e99cd0d66f6f52dab9f945922a7d981868789f4b2f46551467fddfe51e7ce705` |
| `case-b71fd0c608f73e46` | prompt_injection | es | `b71fd0c608f73e4685dba60dc162d8052d700d7f3435365c40842b8563e6b7f4` |
| `case-6da3804fc5ff3f71` | unsupported_options | en | `6da3804fc5ff3f711f42f790c3522b45ba131652d0ad4bda49cdab2cca53f2d5` |
| `case-d84bc23420265503` | unsupported_options | es | `d84bc234202655037d28decb8e66c86cd57803d9357db0cadf7d436d76cd0c2b` |

The last row's digest must match the canonical dataset hash exactly; any
discrepancy is a preflight failure and must be corrected before inference.

## Model and host preflight

- Seneca effective configuration: `strict_offline=true`; provider
  `openai_compatible`; configured and approved endpoint
  `http://192.168.2.140:8888/v1`; configured and approved model
  `qwen3.6-35b-a3b`; temperature `0`; output limit `1200`; provider timeout
  overridden to the existing contract's `120` seconds for this pilot.
- The endpoint is a private-LAN address. Authenticated `GET /v1/models` returned
  `qwen3.6-35b-a3b`; the HTTP `Server` and model `owned_by` identify
  `llama.cpp`. The API does not expose the loaded model revision/checksum,
  server OS, CPU, RAM, or GPU telemetry. No credential is recorded here.
- Client host: PortableWork WSL2, Linux kernel `6.18.33.2-microsoft-standard-WSL2`,
  x86_64, 16 logical CPUs, 32,722,576 KiB RAM. NVML reports GPU access blocked
  in WSL. The evaluation permits CPU execution, but the model server's hardware
  remains unknown.
- `validate_generation_static_config()` passed for the effective settings.
  The endpoint was verified only by authenticated model listing; this record
  does not claim remote host hardware telemetry or a model checksum.
- No model completion/inference request has been sent yet.

## Source fixtures and evidence

Use the three committed synthetic source fixtures from
`eval_prep_01/synthetic_sources.json` in an isolated temporary data directory.
Bind their aliases to the created workspace's exact active source IDs using
`SourceAliasMap`; preserve snapshot and citation checks from the canonical
evidence adapter. Do not use Seneca's regular workspace data directory.

Run legacy first, then planner. Before each arm, start one canonical app
configured for that router mode. Run 24 sequential requests, close the app,
then start the other mode over the same isolated pilot data. This serialized
order is not counterbalanced and does not control for temporal drift. Capture
normalized adapter observations plus a separate human-readable response
projection containing only the synthetic requests,
prior context, answer text and citation aliases. Do not export credentials,
raw source IDs, or internal trace payloads.

