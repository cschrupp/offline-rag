# Known Limitations — Initial Design

This file should evolve with measured project results.

Expected early limitations include:

- table extraction/retrieval may require specialized handling;
- OCR quality can dominate downstream retrieval quality on scanned documents;
- exact numeric answers can fail even when semantically similar passages rank highly;
- hierarchical expansion may add excessive context if parent sections are large;
- local judge models may produce unstable semantic evaluation scores;
- quantized generators may vary in citation-format reliability;
- an offline system still requires an explicit initial model/dependency provisioning step;
- prompt-injection defenses reduce risk but do not constitute a formal security proof;
- benchmark results on one technical corpus do not imply universal ranking superiority.

Public documentation should state measured limitations rather than hiding them.

- the flagship deployment is one OfflineRAG container plus a separately running local generator runtime (Ollama by default), not a literal single-process/single-container LLM stack;
- strict-offline correctness depends on deployment configuration and verification of the external local model runtime as well as the application container.
