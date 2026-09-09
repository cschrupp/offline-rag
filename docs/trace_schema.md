# Query Trace Schema

A query trace is the primary debugging artifact for one request.

## Suggested structure

```json
{
  "trace_id": "...",
  "query": {
    "original": "...",
    "normalized": "...",
    "rewrites": []
  },
  "retrieval": {
    "dense": [],
    "sparse": [],
    "fused": [],
    "reranked": []
  },
  "context": {
    "selected_chunk_ids": [],
    "expanded_chunk_ids": [],
    "token_count": 0
  },
  "decision": {
    "evidence_sufficient": true,
    "abstained": false,
    "reason": null
  },
  "generation": {
    "model": "...",
    "prompt_version": "...",
    "answer": "...",
    "citation_ids": []
  },
  "citation_validation": {
    "valid": true,
    "errors": []
  },
  "timing_ms": {
    "dense": 0,
    "sparse": 0,
    "fusion": 0,
    "rerank": 0,
    "context": 0,
    "generation": 0,
    "total": 0
  }
}
```

## Principles

- Trace IDs should not expose sensitive source paths.
- Candidate records should preserve both rank and raw stage score.
- Final context should identify exactly what the model received.
- Rewrite attempts should be explicit rather than overwriting the original query.
- Timing should be stage-local and end-to-end.
