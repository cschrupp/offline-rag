# OfflineRAG Expert Review (GitHub Pages side-path)

Static, loopback-independent questionnaire for external experts.

This branch is **app shell only**. Do **not** commit real corpus text or `bundle.json`.

It does **not** replace Slice 9E `offline-rag gold review` and does **not** mutate the authoritative Silver run. Opening this site does **not** freeze the 9F lineage. Freeze remains the first durable human mutation on the live Silver run (or a later explicit import you authorize).

## Map to GitHub Pages

1. Push this branch: `pages/9f-expert-review`
2. GitHub → Settings → Pages → Source: deploy from branch `pages/9f-expert-review` / root `/`
3. Prefer a **private** repository / private Pages for any real review content
4. Share the Pages URL with the expert

## Generate a private bundle (on your workstation)

From `main` with the OfflineRAG package available:

```bash
python scripts/export_pages_review_bundle.py \
  --run data/corpora/ics_modules/gold_authoring/runs/<authoring_run_id>.json \
  --config config/base.yaml \
  --output /tmp/bundle.json
```

Send `/tmp/bundle.json` to the expert out-of-band (secure share). Do not commit it.

## Expert workflow

1. Open the Pages site
2. **Load bundle** → select `bundle.json`
3. Review cases (grades 0/1/2, optional query/category/tags, accept / approve edited / reject / reopen)
4. Progress is stored in browser `localStorage` keyed by `authoring_run_id`
5. **Download result JSON** → `offline-rag-pages-review-result-v1`

## Result schema

```text
offline-rag-pages-review-result-v1
  authoring_run_id, chunk_set_id, corpus_name, exported_at
  cases[]:
    draft_case_id
    status: pending|accepted|edited|rejected
    query_override
    category_override: { is_overridden, value }
    tags_override
    grade_basis_query
    judgments[]: { chunk_id, relevance }
```

## Import later

There is **no** importer on `main` in this side-path. Keep the downloaded result until you authorize a separate merge into the Silver run. Until then, the authoritative loopback review path remains unchanged.

## Local smoke test

```bash
cd /path/to/this/branch/checkout
python -m http.server 8080
# open http://127.0.0.1:8080/
# load sample/empty-bundle.json
```

## Files

| File | Role |
|---|---|
| `index.html` / `app.js` / `app.css` | Static review UI |
| `sample/empty-bundle.json` | Schema example only (no private text) |
| `.gitignore` | Ignores `bundle.json` / `result*.json` |
| `.nojekyll` | GitHub Pages: serve files as-is |
