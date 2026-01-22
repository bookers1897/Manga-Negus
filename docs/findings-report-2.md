# Frontend Security & Architecture Audit Report

**Document ID:** FN-AUDIT-2026-002
**Date:** January 22, 2026
**Target:** MangaNegus Frontend Application (`static/js/`, `static/js/legacy_modules/`)
**Assessment Type:** Deep Dive Static Analysis

---

## 1. Executive Summary

This comprehensive audit of the MangaNegus frontend codebase reveals a system in a critical state of transition. The architecture suffers from significant **technical debt** due to a "split-brain" implementation: a monolithic, 10,072-line "Redesign" co-existing with a fragmented "Legacy" modular system.

While sophisticated performance mechanisms (Web Workers, Request Queues) utilize modern browser capabilities, they are implemented inconsistently. This inconsistency creates a fractured **Attack Surface** where security controls (like rate limiting and input sanitization) applied in one context are bypassed in another. The lack of modular separation violates the **Single Responsibility Principle**, leading to a fragile system where minor changes risk cascading failures in core functions like Search and Reading.

**Overall Risk Rating:** **HIGH**
*The application's availability and maintainability are severely compromised by architectural flaws, though direct exploitability (e.g., XSS/CSRF) is currently mitigated by ad-hoc helper functions.*

---

## 2. Vulnerability Details

### Finding #1: Monolithic "God Object" State Management
*   **Type:** Architectural Flaw / Maintainability
*   **Severity:** **Critical**
*   **Location:** `static/js/main.js` (Global `state` object)
*   **Description:** The application relies on a single, global mutable object (`state`) containing over 100 properties. This object mixes disparate concerns: authentication tokens, UI visibility booleans, data caches, and user preferences.
*   **Impact:**
    *   **State Corruption:** Any function in the 10k-line file can mutate any part of the app state, leading to race conditions and unpredictable UI behavior.
    *   **Regression Risk:** Modifications to unrelated features can inadvertently break core workflows.

### Finding #2: Inconsistent Network Layer & Protection Bypass
*   **Type:** Resilience / Availability
*   **Severity:** **High**
*   **Location:** `static/js/main.js` vs. `static/js/legacy_modules/api.js`
*   **Description:** The application implements two competing network stacks. `main.js` uses a robust `RequestQueue` with rate-limiting. However, legacy modules utilize raw `fetch()` calls.
*   **Impact:**
    *   **Control Bypass:** Actions triggered via legacy paths bypass the `RequestQueue`, exposing the user's IP to upstream rate limits and bans (HTTP 429).

### Finding #3: Poor API Response Inconsistency
*   **Type:** Logic / Integration
*   **Severity:** **Medium**
*   **Location:** Backend-Frontend Interface (Various endpoints)
*   **Description:** The backend returns different data shapes for "Manga" objects across endpoints (e.g., `/api/search/smart` uses a wrapper, `/api/popular` returns a raw array, `/api/library` returns an object keyed by source:id).
*   **Impact:**
    *   **Logic Errors:** The frontend is forced to use complex defensive checks, increasing the likelihood of `TypeError` crashes when processing results.

### Finding #4: Unoptimized Asset Loading & CDN Dependencies
*   **Type:** Performance / Reliability
*   **Severity:** **Medium**
*   **Location:** `templates/index.html`, `static/js/main.js`
*   **Description:** All management logic is bundled in a single 10k-line script, leading to massive download overhead for simple reader-only visits. Additionally, the UI depends on external CDNs (`unpkg.com`) for Lucide and Phosphor icons.
*   **Impact:**
    *   **Load Latency:** High Time-to-Interactive (TTI).
    *   **Fragility:** If the icon CDN is blocked or down, the UI becomes unnavigable (blank icons).

### Finding #5: Non-Responsive Design & Mobile UX Flaws
*   **Type:** User Experience
*   **Severity:** **Low**
*   **Location:** `static/js/reader.js`, `static/css/reader.css`
*   **Description:** The reader uses hardcoded pixel values (e.g., `980px` for fit-width) and lacks gesture support (swipe-to-open sidebar). Touch targets for checkboxes and status pills are below the 44x44px standard.
*   **Impact:**
    *   **Accessibility:** Users on small screens or with motor impairments will find "Download Selected" and navigation significantly more difficult.

### Finding #6: Caching Invalidation & Redundancy
*   **Type:** Reliability
*   **Severity:** **Medium**
*   **Location:** `static/js/main.js` (`memoryCache`), `static/js/storage.js`
*   **Description:** There is no synchronization between the search cache and the library state. Adding an item to the library does not invalidate its search result state. Data is mirrored in memory, localStorage, and IndexedDB without a strict "Source of Truth" protocol.
*   **Impact:**
    *   **Data Desync:** Search results may show outdated "+" buttons for several minutes after an item is saved. Redundant writes to storage can cause performance stuttering.

---

## 3. Remediation Steps

### 3.1. Architecture: Decompose the Monolith
**Goal:** Enforce Separation of Concerns.
**Action:** Refactor `main.js` into distinct ES Modules (`auth.js`, `router.js`, `store.js`, `ui/`).

### 3.2. Network: Enforce Unified Transport
**Goal:** Eliminate "Shadow IT" network calls.
**Action:** Extract the `RequestQueue` and `API` logic into a standalone `network.js` module and force all modules (including legacy) to use this singleton.

### 3.3. API: Standardize Response Models
**Goal:** Consistent Data Consumption.
**Action:** Refactor backend endpoints to return a unified `MangaResponse` schema or implement a frontend "Adapter" layer to normalize all incoming manga data.

### 3.4. Assets: Self-Host & Code Split
**Goal:** Reliable Performance.
**Action:** 
1.  Self-host icon libraries within the `static/` directory.
2.  Implement dynamic imports or separate entry points for the "Management View" and the "Reader View."

### 3.5. UX: Fluid Layouts & Touch Optimization
**Goal:** Mobile First.
**Action:** 
1.  Replace hardcoded pixel widths with relative units (vw/%).
2.  Increase touch target sizes for all interactive elements to 44px minimum.
3.  Add `touchstart`/`touchend` listeners for sidebar gestures.

---

## 4. Appendix: Codebase Metrics

| Metric | Value | Status |
| :--- | :--- | :--- |
| **Main Entry Point Size** | ~10,072 LOC | 🚩 Critical Bloat |
| **State Properties** | >100 | 🚩 High Complexity |
| **External Dependencies** | unpkg.com (Icons) | ⚠️ Reliability Risk |
| **Storage Engines** | RAM, LS, IndexedDB | 🚩 Sync Complexity |

---

## 5. Conclusion

To restore stability to searching, reading, and downloading, the immediate priority must be **Network Layer Consolidation**. By forcing all traffic through a single, intelligent queue, you will immediately resolve the intermittent "fetching" errors caused by rate limiting. Following this, standardizing the API responses and modularizing the code will ensure the application remains manageable as more sources are added.