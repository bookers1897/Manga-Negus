# MangaNegus - Future Work & Bug Fixes

## Priority: High

### 1. Reader Image Loading Issues (Mobile)
**Status:** Needs Investigation
**Problem:** Images fail to load on many mangas, especially on mobile
**Root Cause (suspected):**
- No retry mechanism for failed images
- No fallback proxy or CDN
- Prefetch errors only log to console.debug
**Files:**
- `/opt/manganegus/static/js/reader.js` (lines 586-643)
- `/opt/manganegus/manganegus_app/routes/main_api.py` (image proxy)
**Solution:**
- Add retry logic with exponential backoff
- Add visual retry button on failed images
- Consider fallback image sources

### 2. Code Refactoring (Major)
**Status:** Planned
**Problem:** Codebase has grown organically, needs cleanup
**Areas:**
- `main.js` is 5000+ lines, split into modules
- Source connectors have duplicated patterns
- CSS could use better organization
**Approach:**
- ES6 modules for JavaScript
- Abstract base patterns for sources
- CSS custom properties consolidation

## Priority: Medium

### 3. Offline Mode Improvements
**Status:** Partial
**Current:** Basic localStorage caching
**Needed:**
- Service worker for true offline
- IndexedDB for larger cache
- Sync queue for actions taken offline

### 4. Search Performance
**Status:** Working but slow
**Problem:** SmartSearch queries all sources in parallel
**Optimization:**
- Early termination when enough results found
- Source prioritization based on success rate
- Query result caching per-source

### 5. Chapter Progress Sync
**Status:** Local only
**Problem:** Reading progress doesn't sync across devices
**Solution:**
- Optional account system
- Or: Import/export progress JSON

## Priority: Low

### 6. PWA Enhancements
- Add to homescreen prompt
- Background sync
- Push notifications for new chapters

### 7. Accessibility
- Screen reader improvements
- Keyboard navigation in reader
- High contrast mode

### 8. Performance Monitoring
- Add timing metrics
- Error tracking (Sentry-like)
- Usage analytics (privacy-respecting)

## Completed

- [x] Source priority sync (Jan 2026)
- [x] SmartSearch as default (Jan 2026)
- [x] Enhanced fallback logging (Jan 2026)
- [x] Source test endpoints (Jan 2026)
- [x] MangaDex-first discovery (Jan 2026)
- [x] UI grid improvements (Jan 2026)
