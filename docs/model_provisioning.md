# Model Provisioning

Model provisioning is intentionally separate from normal OfflineRAG runtime.

## 1. Generator

The generative model is managed by an external local inference runtime. Ollama is the default deployment target.

OfflineRAG stores only:

- the configured endpoint;
- the configured model identifier;
- an approved local-model manifest/list;
- generation parameters used for reproducibility.

It does not store generator weights in the application image or `/models`.

## 2. Embedding model

Embedding weights belong under a provisioned local path/cache, for example:

```text
/models/embeddings/<model>/
```

Record model name, revision/hash where practical, dimensionality, tokenizer/version, and any normalization settings in experiment metadata.

## 3. Reranker

Reranker weights belong under:

```text
/models/reranker/<model>/
```

Record model/version, max sequence length, batching configuration, device, and precision.

## 4. Runtime loading

Strict-offline runtime must fail clearly when a required retrieval model is missing. It must not silently download it.

## 5. Manifest

Use `models/manifest.example.yaml` as the future schema seed. The manifest should identify approved retrieval assets and approved generator identifiers separately.
