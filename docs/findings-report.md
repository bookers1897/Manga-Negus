# Findings Report

## Summary
Overview: The search bar is wired to render results only in the Discover grid and relies on a view switch to make results visible. The reader depends on resolved source and query parameters, plus CSRF-protected API calls and a valid manga_id for navigation. The service worker caches frontend JS with a fixed version, which can preserve older behavior across clients.

Key Metrics:
- Total findings: 7
- Severity distribution: High 2, Medium 4, Low 1
- Primary locations: `static/js/main.js`, `static/js/reader.js`, `static/sw.js`

## Details
### F-01 Search results render only to Discover grid
- Severity: High
- Count: 1
- Location: `static/js/main.js:2722`, `static/js/main.js:2759`, `static/js/main.js:2004`
- Evidence: `searchManga` and `detectUrl` always render into `els.discoverGrid` and `els.discoverEmpty`. Results are only visible when the Discover view is active; other views have no search results container.
- Impact: Search appears to do nothing outside Discover unless the view switch occurs; users can perceive the search as broken on Library/Details.

### F-02 Search refresh only re-runs on Discover
- Severity: Medium
- Count: 1
- Location: `static/js/main.js:2678`
- Evidence: `reloadActiveView` only calls `performSearch` when `state.activeView === 'discover'` and `state.searchQuery` is set.
- Impact: Refreshing or changing filters while on other views does not re-run search, leaving stale or missing results and reinforcing the Discover-only behavior.

### F-03 Service worker cache can pin old search behavior
- Severity: Medium
- Count: 1
- Location: `static/sw.js:1`, `static/sw.js:6`, `static/sw.js:35`
- Evidence: The service worker caches `/static/js/main.js` and `/static/js/reader.js` with cache-first and a fixed VERSION (`v6`).
- Impact: Clients can keep older JS even after server updates, which can preserve the pre-fix behavior where search does not switch views or render correctly outside Discover.

### F-04 Reader requires resolved source and chapter_id
- Severity: High
- Count: 1
- Location: `static/js/main.js:6988`, `static/js/main.js:7016`, `static/js/reader.js:291`, `static/js/reader.js:1182`
- Evidence: `openReader` aborts if `state.currentManga.source` is missing or still `jikan`. The reader page then refuses to load without `chapter_id` and `source` query params.
- Impact: Reader fails to open when source resolution does not complete, especially for items originating from Jikan or when source resolution is delayed.

### F-05 Reader API calls depend on CSRF token
- Severity: Medium
- Count: 1
- Location: `static/js/reader.js:408`, `static/js/reader.js:433`, `static/js/reader.js:440`
- Evidence: `getChapterPages` and `getAllChapters` call `ensureCsrfToken` and send a CSRF header. Any failure in `/api/csrf-token` or token mismatch causes reader fetches to fail.
- Impact: Pages can fail to load with an error message even when `chapter_id` and `source` are present, leading to a blank reader view.

### F-06 Reader chapter navigation depends on manga_id
- Severity: Medium
- Count: 1
- Location: `static/js/reader.js:452`, `static/js/reader.js:951`, `static/js/main.js:7035`
- Evidence: `getAllChapters` returns null when `manga_id` is missing, so `ensureChapterList` fails and next/prev navigation is disabled.
- Impact: Chapter navigation and prefetching break if the reader URL lacks a resolved `manga_id` for the selected source.

### F-07 Prefetcher uses direct cross-origin fetch with Referer header
- Severity: Low
- Count: 1
- Location: `static/js/reader.js:164`
- Evidence: `Prefetcher.prefetchImage` uses `fetch(url)` with a manually set `Referer` header. Browsers typically block setting `Referer` directly and many sources block cross-origin image fetches.
- Impact: Prefetch silently fails, reducing performance and making reader feel slower on subsequent pages.

## Recommendations
### R-01 For F-01 (Discover-only rendering)
1. Route all search results through a dedicated search results view or shared results container that is visible regardless of the current view.
2. If Discover is the intended display, explicitly switch to Discover before rendering and ensure `activeView` reflects the current screen state.

### R-02 For F-02 (Search refresh scope)
1. Update `reloadActiveView` so it re-runs search whenever `state.searchQuery` is present, independent of the active view.
2. Alternatively, separate global search from view-specific refresh logic to avoid overwriting search results with view loaders.

### R-03 For F-03 (Service worker caching)
1. Bump the service worker `VERSION` when frontend JS changes to force cache invalidation.
2. Consider a network-first strategy for `/static/js/*.js` or add cache-busting query strings during deployment.

### R-04 For F-04 (Reader source resolution)
1. Resolve `source` and `manga_id` before allowing `openReader` to navigate; if unresolved, block with a clear error and retry option.
2. Add a fallback that redirects back to Details with a visible resolution error when `chapter_id` or `source` is missing.

### R-05 For F-05 (CSRF dependency)
1. Make `/api/csrf-token` failure explicit in the UI (toast or banner) so users know why pages fail to load.
2. Validate CSRF handling on reader endpoints and ensure tokens are refreshed on session expiry.

### R-06 For F-06 (manga_id dependency)
1. Ensure `openReader` always includes a resolved `manga_id` for the selected source before navigation.
2. If `manga_id` is unavailable, disable next/prev controls with a user-facing message rather than silently failing.

### R-07 For F-07 (Prefetch reliability)
1. Prefetch via `/api/proxy/image` instead of direct cross-origin URLs to avoid CORS and Referer restrictions.
2. If direct fetch is required, use the `referrer` fetch option rather than setting the `Referer` header manually.
