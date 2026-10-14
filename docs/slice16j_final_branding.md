# Slice 16J — Final Seneca public branding

**Design freeze:** `S16-J-REOPEN-BRANDING-UX-DESIGN-FREEZE-001` — ACCEPTED / FROZEN  
**Implementation authority:** `S16-J-FINAL-BRANDING-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Canonical technical base:** `09407ae0e5186b262a0b034e752672424e237fa2`  
**Status:** DESIGN FROZEN / IMPLEMENTATION AUTHORIZED (NOT COMPLETE / NOT ACCEPTED)

## Product identity (frozen)

| Field | Value |
|---|---|
| Product | Seneca — Grounded knowledge workspace |
| Author | Carlos A. Schrupp |
| Contact | carlos.schrupp@berkeley.edu |

## Naming boundary (frozen)

**Public product:** Seneca / Seneca — Grounded knowledge workspace  

**Engineering identity remains:** repository `offline-rag`, Python package `offline_rag`,
CLI `offline-rag`, API modules/routes, Docker/image/config identifiers, environment
variables, schemas, persistence identifiers, and technically meaningful test fixture
identities.

This is **not** a global rename.

## Objectives (frozen)

1. First-open Seneca welcome / splash screen (`/welcome`, outside AppShell)
2. Accessible About dialog (existing `ModalDialog`)
3. README + `pyproject.toml` author attribution
4. Removal of remaining rendered “OfflineRAG” branding from the React product

## First-open semantics (frozen)

- Fresh browser session navigating to `/` shows `/welcome` first
- Storage: `sessionStorage` key `seneca-welcome-shown-v1` only
- Once per browser session (not every reload, not permanent localStorage)
- Direct deep links bypass the splash
- Explicit `/welcome` always shows welcome
- Entering Welcome marks the session key so returning to `/` opens Overview

## About content (frozen)

Seneca; Grounded knowledge workspace; Version 0.1.0; author/contact as above;
Local-first · Evidence-grounded · Private by design; © 2026 Carlos A. Schrupp.
Actions: Contact (mailto), Show welcome screen, Source repository, Close.
No License field.

## Out of scope

Bulk watermarking, LICENSE invention, OfflineRAG platform rename, telemetry,
Gold/science/config/deploy changes, 16K, 9G, Slice 17, Slice 16 closeout claim.

## Splash assets (frozen production payload)

Only optimized WebP under `ui/public/brand/seneca/`:

- `seneca-splash-background-960.webp` (960×540)
- `seneca-splash-background-1280.webp` (1280×720)
- `seneca-splash-background-1600.webp` (1600×900)
- `seneca-splash-mobile-4x5.webp` (753×941)
