## Planned Fixes (executed 2025-01-08)

Context: Redesign is now the default UI. Smoke tests run in `.venv`; PostgreSQL unavailable (fallback to file), Playwright sandbox failure for MangaFire V2, DNS failure for weebcentral.com.

### Changes implemented
1) Frontend source-id propagation (static/js/main.js)
   - Capture `source_id`/`manga_id` returned by `/api/chapters` and update `state.currentManga` so downloads, reader, and library ops use the resolved source instead of the pseudo `jikan`.

2) Playwright guard (sources/__init__.py)
   - Added opt-in env flag `SKIP_PLAYWRIGHT_SOURCES=1` to skip Playwright-backed connectors (currently `mangafire_v2`) in restricted environments.

### Out of scope (for now)
- PostgreSQL provisioning; remains file-based unless creds provided.
- DNS/network for WeebCentral; environment-specific.
- Broader cleanup/renames already done (redesign promoted, legacy archived).
