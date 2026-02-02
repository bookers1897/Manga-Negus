# Reader + Worker Fixes (2026-02-02)

Date: 2026-02-02
Owner: Codex
Scope:
- Reader UI/behavior: `/reader`
- Frontend worker resilience
- Cleanup of dead inline reader

## What was fixed

### 1) Reader flow split + dead inline reader
- **Issue**: The app redirected to `/reader`, but an inline reader still lived in `templates/index.html` with matching CSS/JS. That caused dead code, drift, and inconsistent UI behavior.
- **Fix**: Removed the inline reader markup, CSS, and JS flow so the reader exists only at `/reader`.
- **Files touched**:
  - `templates/index.html`
  - `static/css/styles.css`
  - `static/js/main.js`

### 2) Reader defaults (manga vs webtoon)
- **Issue**: Default reader settings were not tailored to content type (manga vs webtoon).
- **Fix**:
  - `openReader` now passes `manga_type` + `manga_tags` to `/reader`.
  - `reader.js` infers content profile:
    - Manga: **RTL**, **fit-height**
    - Webtoon/manhwa/manhua: **webtoon mode**, **LTR**, **fit-width**
- **Files touched**:
  - `static/js/main.js`
  - `static/js/reader.js`

### 3) Mobile tap-to-show controls + settings visibility
- **Issue**: On mobile, the settings button could be hidden or clash with topbar; controls stayed visible and consumed screen space.
- **Fix**:
  - Added mobile control auto-hide with tap-to-show (top and center zones).
  - Settings toggle always visible when controls are shown; hides with the topbar otherwise.
  - Settings view keeps controls visible while open.
- **Files touched**:
  - `static/js/reader.js`
  - `static/css/reader.css`

### 4) Reader topbar clipping on mobile
- **Issue**: The topbar title and chapter info could be clipped on small screens.
- **Fix**:
  - Mobile topbar uses safe-area padding.
  - Chapter title clamps to two lines.
  - Topbar height recalculated after title text is injected (post-render layout pass).
- **Files touched**:
  - `static/css/reader.css`
  - `static/js/reader.js`

### 5) Faster perceived image load (prefetch + cache)
- **Issue**: Reader pages could take a long time to load with no cached reuse.
- **Fix**:
  - IndexedDB cache used when available; fallback to proxy URL if cache miss.
  - Prefetch distance now adaptive via user setting.
  - Blob URLs revoked after use to prevent memory leaks.
- **Files touched**:
  - `static/js/reader.js`

### 6) Web Worker failure fallback
- **Issue**: `new Worker('/static/js/worker.js')` was unconditional; if blocked or unsupported the app could hard-fail.
- **Fix**:
  - Worker creation now guarded with feature detection + try/catch.
  - `onerror` terminates worker and falls back to synchronous filtering.
  - Added sync filter functions to preserve functionality when worker is unavailable.
- **Files touched**:
  - `static/js/main.js`

## How it was fixed (implementation summary)
- Consolidated reader to `/reader` and removed inline reader UI/assets.
- Added content-aware defaults in reader init (`manga_type`, `manga_tags`).
- Implemented mobile control hide/show logic + safe-area topbar styling.
- Improved image loading by preferring cached blobs before proxy fallback.
- Added safe worker initialization and sync fallback for filtering.

## Notes / Follow-ups
- Reader enhancement sliders (brightness/contrast/sharpen/crop) are still stored in localStorage but are not yet applied on the `/reader` page. If desired, that can be wired next.
- The filter worker uses a simplified collection logic; the main thread uses local collection tags. If consistent filtering by collections is required in worker mode, worker logic should be aligned with main thread storage keys.

