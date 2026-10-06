# OfflineRAG UI (Slice 16C)

React / TypeScript / Vite client for workspace and source management.

## Development

```bash
cd ui
npm ci
npm run dev
```

Vite proxies `/v1` and `/health` to `http://127.0.0.1:8080` in development only.
Production builds use same-origin relative URLs and do not require the proxy.

## Quality gates

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

## Production delivery

The compiled `dist/` is served by the OfflineRAG FastAPI process from
`OFFLINE_RAG_UI_DIR` (default `/app/ui` in the container). Do not commit `dist/`.
