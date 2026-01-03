# Gemini Code Review & Analysis for MangaNegus

**Date:** 2026-01-02
**Project:** MangaNegus
**Analysis by:** Gemini
**Status:** 🚀 v3.0.0-alpha Deployed

## 🚨 Tier 1: Critical & Functionality-Breaking Issues

### 1. `NameError` in `/api/detect_url` - ✅ **FIXED**
*   **Status:** Resolved in `manganegus_app/routes/manga_api.py`.
*   **Fix:** Added `manager = get_source_manager()` to ensure the variable is defined before use.

### 2. Defunct `comick` Source Priority - ✅ **FIXED**
*   **Status:** Resolved in `sources/__init__.py`.
*   **Fix:** Removed `comick` and promoted the new **V2 (curl_cffi)** sources to top priority.

### 3. Duplicate `templates/templates/index.html` - ✅ **FIXED**
*   **Status:** Resolved.
*   **Fix:** Deleted the redundant nested directory.

---

## ⚠️ Tier 2: Major Bugs & Bad Practices

### 1. Circular Imports in Scraper Connectors - ✅ **FIXED**
*   **Status:** Resolved across all source files.
*   **Fix:** Replaced `from app import log` with the central `source_log` callback system.

### 2. Ineffective Cloudflare Bypass - ✅ **FIXED**
*   **Status:** Resolved for major sources (**WeebCentral, MangaSee, MangaNato**).
*   **Fix:** Implemented **V2 Connectors** using `curl_cffi` for TLS fingerprint impersonation.

### 3. Open Image Proxy - ✅ **FIXED**
*   **Status:** Resolved in `manganegus_app/routes/main_api.py`.
*   **Fix:** Strictly enforced the `allowed_domains` list and returned 403 for unauthorized requests.

### 4. Downloader Uses Separate `requests.Session` - ✅ **FIXED**
*   **Status:** Resolved in `manganegus_app/extensions.py`.
*   **Fix:** Updated the `Downloader` to use `source.get_download_session()`, allowing it to inherit the Cloudflare-bypassing sessions from V2 connectors.

### 5. Inefficient Fallback Logic - ✅ **FIXED**
*   **Status:** Resolved in `sources/__init__.py`.
*   **Fix:** Search now treats empty lists `[]` as a successful "no results" state instead of a failure, preventing unnecessary queries to every single source.

---

## 🛠️ Tier 3: Code Quality & Maintainability

### 1. Monolithic Frontend - ✅ **FIXED**
*   **Status:** Resolved.
*   **Fix:** Frontend has been modularized into `static/js/` (api.js, chapters.js, ui.js, etc.).

### 2. Confusing Naming of `weebcentral_lua.py` - ✅ **FIXED**
*   **Status:** Resolved.
*   **Fix:** Renamed to `weebcentral_v2.py` and updated class to `WeebCentralV2Connector`.

### 3. Metadata Support (ComicInfo.xml) - ✨ **NEW**
*   **Status:** Implemented in `Downloader`.
*   **Fix:** CBZ downloads now include standardized `ComicInfo.xml` metadata for compatibility with external library managers.

---

## 📚 Tier 4: Documentation & Consistency

### 1. Inconsistent Versioning - ✅ **FIXED**
*   **Status:** Resolved. Standardized on **v3.0.0-alpha** across all files.

### 2. Outdated `README.md` - ✅ **FIXED**
*   **Status:** Resolved. Completely rewritten to reflect the new architecture and V2 sources.
