# Addendum — Persist the Seneca Research Study in GitHub

Continue the current research task without restarting or interrupting ongoing experiments.

The user has authorized preserving this investigation as a permanent, version-controlled research workstream in `cschrupp/offline-rag`.

## Repository destination

Use:

`docs/research/bge_quality_latency_frontier/`

Create and maintain:

- `REPORT.md` — complete, professionally written research report, with scientific storytelling, methodology, results, figures, references and limitations.
- `RESEARCH_PLAN.md` — preregistered hypotheses, experimental design, metrics and acceptance criteria.
- `REPRODUCIBILITY.md` — exact commands, software versions, hardware identities and reproduction procedures.
- `figures/` — professionally designed figures with accurate captions and units.
- `data/` — machine-readable, appropriately scoped derived measurements.
- `scripts/` — deterministic research analysis and visualization code.
- `evidence/` — experiment authorization, full Codex prompts and responses, results and independent-review findings.

Where existing project evidence conventions require another location for raw artifacts, preserve those conventions and link to them from the report.

## Version control requirements

1. Continue using the current dedicated research branch. Do not create an unnecessary replacement branch.
2. Preserve frozen Slice 9 and Slice 14 evidence unchanged.
3. Commit the research plan, report, analysis scripts, figures and evidence.
4. Store each meaningful execution response alongside its exact corresponding authorization prompt, using only genuinely available transcript content.
5. Do not commit passwords, SSH keys, credentials, private document contents, temporary VM copies, ONNX model weights, or large generated caches.
6. Ensure figures can be reproduced from the retained evidence.
7. Run applicable tests and check repository status before committing.
8. Use descriptive commits and push the research branch to `origin`.
9. Do not force-push, merge into `main`, deploy anything or promote any experimental retrieval configuration.
10. If the research remains incomplete, mark the report explicitly as `INTERIM RESEARCH REPORT` and identify pending measurements.

At completion, provide:

- GitHub branch URL.
- Final commit SHA.
- Direct link to `REPORT.md`.
- Links to figures and reproducibility instructions.
- Experiments completed and still pending.
- Test results and independent-review readiness.

The goal is a research artifact that another engineer can read, inspect, reproduce and review independently.

**Do not wait for all experiments to succeed before documenting negative results.** Those are part of the scientific contribution.
