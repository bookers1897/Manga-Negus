# Findings Report 1

## Summary
Overview: The search UI is global, but search results are rendered only into the Discover grid and depend on a view switch to become visible. Several code paths bypass that switch, so searches or resets can execute while the Discover view is hidden. The reader is a separate page that relies on resolved source and query parameters, plus CSRF-protected API calls and a resolved manga_id for navigation. A cache-first service worker can keep older frontend bundles and preserve prior behavior even after code changes.

Key Metrics:
- Total findings: 9
- Severity distribution: High 2, Medium 6, Low 1
- Primary locations: `static/js/main.js`, `static/js/reader.js`, `static/sw.js`

## Details
### F-01 Search results render only in Discover container
- Count: 1
- Severity: High
- Location: `static/js/main.js:2722`, `static/js/main.js:2759`, `static/js/main.js:2004`
- Evidence: `searchManga` and `detectUrl` always render into `els.discoverGrid` and `els.discoverEmpty`. `setView` hides `els.discoverView` when the active view is Library or Details.
- Impact: Searches appear to return no results outside Discover because the target container is hidden. There is no parallel results container for Library/Details.

### F-02 Some search paths do not switch to Discover
- Count: 1
- Severity: Medium
- Location: `static/js/main.js:9439`, `static/js/main.js:9444`, `static/js/main.js:2678`
- Evidence: The clear-search handler reloads Discover data but does not call `setView('discover')`. `reloadActiveView` only triggers `performSearch` when the active view is Discover.
- Impact: From Library/Details, clearing or refreshing can update the Discover grid off-screen, reinforcing the perception that search is broken outside Discover.

### F-03 Search visibility depends on current client bundle
- Count: 1
- Severity: Medium
- Location: `static/sw.js:1`, `static/sw.js:6`, `static/sw.js:35`
- Evidence: The service worker caches `/static/js/main.js` and `/static/js/reader.js` using a fixed `VERSION` and cache-first strategy.
- Impact: Clients can keep older JS where search does not switch views or does so inconsistently. This matches the observed behavior if a fix was added server-side but the client is still using cached bundles.

### F-04 Default search uses Jikan when no source is selected
- Count: 1
- Severity: Medium
- Location: `static/js/main.js:2731`
- Evidence: `searchManga` logs and behaves as a Jikan search when `state.filters.source` is empty.
- Impact: Results can lack a resolvable source_id/manga_id pair. This increases the chance that chapters cannot be fetched later, even when search appears to succeed.

### F-05 Reader launch fails when source remains unresolved
- Count: 1
- Severity: High
- Location: `static/js/main.js:6988`, `static/js/main.js:7016`, `static/js/main.js:7020`
- Evidence: `openReader` aborts if `state.currentManga.source` is missing or still `jikan`, even after calling `ensureReaderChapters`.
- Impact: Reader never opens for titles whose sources fail to resolve, which blocks reading and downloading.

### F-06 Reader hard-fails without chapter_id and source params
- Count: 1
- Severity: Medium
- Location: `static/js/reader.js:291`, `static/js/reader.js:1182`
- Evidence: `parseParams` reads `chapter_id` and `source` from the URL, and `init` immediately errors if either is missing.
- Impact: Any navigation that drops those query parameters results in a blank reader view with an error message.

### F-07 Reader API calls depend on CSRF token
- Count: 1
- Severity: Medium
- Location: `static/js/reader.js:408`, `static/js/reader.js:433`, `static/js/reader.js:440`
- Evidence: `getChapterPages` and `getAllChapters` require `ensureCsrfToken`, and `apiRequest` throws on non-OK responses.
- Impact: A failed CSRF fetch or expired session blocks chapter page loading and appears as a reader failure.

### F-08 Reader navigation requires manga_id
- Count: 1
- Severity: Medium
- Location: `static/js/reader.js:452`, `static/js/reader.js:951`, `static/js/main.js:7038`
- Evidence: `getAllChapters` returns null if `manga_id` is missing. `ensureChapterList` relies on `getAllChapters` to enable next/prev navigation.
- Impact: Next/prev chapter navigation and prefetch can fail silently when the reader URL lacks a resolved manga_id.

### F-09 Prefetcher uses direct cross-origin fetch
- Count: 1
- Severity: Low
- Location: `static/js/reader.js:164`, `static/js/reader.js:173`
- Evidence: `Prefetcher.prefetchImage` uses `fetch(url)` and attempts to set the `Referer` header directly.
- Impact: Browsers typically block custom Referer headers and cross-origin image fetches, so prefetch often fails and reader performance degrades.

## Recommendations
### R-01 For F-01 (Discover-only rendering)
1. Add a dedicated global search results panel that is visible regardless of the active view, or explicitly treat search as a navigation to Discover.
2. If search is meant to stay in the current view, create per-view result containers and route `renderMangaGrid` to the active one.

### R-02 For F-02 (Non-switching search paths)
1. Update clear-search and refresh paths to call `setView('discover')` when they change Discover content.
2. Alternatively, prevent non-Discover paths from mutating Discover content when Discover is hidden.

### R-03 For F-03 (Service worker caching)
1. Bump `VERSION` on frontend changes to force static cache invalidation.
2. Consider a network-first policy for `/static/js/*.js` or add cache-busting build hashes.

### R-04 For F-04 (Jikan default search)
1. Surface the active source in the UI and prompt users to pick a source if they want readable chapters.
2. Optionally auto-select a preferred source when no source is set to avoid non-resolvable search results.

### R-05 For F-05 (Reader source resolution)
1. Block reader navigation until a non-Jikan source_id and manga_id are resolved.
2. Provide a retry action on failure that re-runs source resolution and chapter fetch.

### R-06 For F-06 (Missing params)
1. Validate and preserve reader query parameters when navigating or refreshing.
2. Redirect users back to Details with a clear error if required params are missing.

### R-07 For F-07 (CSRF dependency)
1. Surface CSRF errors explicitly so failures are distinguishable from missing chapters.
2. Refresh tokens on session expiry and retry once before surfacing the error.

### R-08 For F-08 (manga_id dependency)
1. Guarantee `manga_id` is included in the reader URL by resolving the source before navigation.
2. Disable next/prev controls and explain why when `manga_id` is unavailable.

### R-09 For F-09 (Prefetch reliability)
1. Prefetch through `/api/proxy/image` to avoid CORS and Referer constraints.
2. If direct fetch is required, use the `referrer` fetch option instead of setting the `Referer` header.
