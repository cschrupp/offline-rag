# Preflight error-precedence amendment

**Decision date: 2026-11-22, America/La_Paz.** The independent review
accepts bounded preflight admission as the authoritative protection
boundary for the workspace conversation turn. This decision replaces
only the conflicting precedence in the original design
`76fdf1984ad8b8a0c08893d74d75405f2f8d8625`. The reviewed lifecycle
implementation is `17816f4568ba85cf00229f0aaa97b26318e22f62`.
The observed compatibility conflict and proposed amendment are recorded
at `f2e02a235608330b850c3fb2943af4673718ceaa`. The independent review
disposition is retained in [the authorization](AMENDMENT_AUTHORIZATION.md).
The original design and evidence retain their historical meaning.

## Normative contract

1. Validate HTTP request shape, prior-turn sequence and question before admission.
2. Check runtime readiness.
3. Attempt admission to the bounded, drain-aware preflight registry.
4. If the guard is exhausted, return HTTP 503 `service_overloaded` with
   reason `query_preflight_capacity_exhausted`.
5. For an admitted preflight, preserve workspace, source-scope and
   snapshot-backing validation semantics.
6. Only after successful preparation may the shared execution gate
   return `query_capacity_exhausted`.
7. Preserve immutable snapshot binding and owned-worker lifecycle.
8. Allocate no scientific execution trace for rejection before execution.

When the preflight guard is full, its overload takes precedence over
workspace, source and snapshot validation errors. Request validation
and runtime readiness still take precedence over admission. This applies
only to `POST /v1/workspaces/{workspace_id}/conversation/turn`.

The amendment authorizes no merge, deployment, Stage 2 execution, VM
campaign or batching default change.
