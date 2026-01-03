# MangaNegus v3.0 - Breakthrough Notes

> **Date:** 2025-12-31
> **Issue:** WeebCentral returning empty results despite 200 OK responses
> **Resolution:** It wasn't Cloudflare - the API endpoint changed to HTMX

---

## The Problem

WeebCentral's Python connector was returning **empty results** for all searches. Initial diagnosis pointed to Cloudflare protection:

```
requires_cloudflare = True  # Flag in weebcentral.py
```

We tried multiple bypass methods:
1. **cloudscraper** - Python library for Cloudflare bypass
2. **curl_cffi** - Chrome TLS fingerprint impersonation

Both returned `HTTP 200 OK` but with empty/error content.

---

## The Investigation

### Step 1: Check Response Content

```python
resp = session.get("https://weebcentral.com/search/data?text=naruto")
print(resp.status_code)  # 200
print(resp.text[:500])   # HTML error page!
```

**Finding:** Status was 200, but content was an error page saying "400 Bad Request"

### Step 2: Analyze the Error

```html
<title>400 | Weeb Central</title>
<meta name="description" content="Oops! It looks like there's a bad request...">
```

**Key Insight:** This wasn't Cloudflare blocking us - the site was explicitly returning a 400 error wrapped in a 200 response. The API endpoint had changed!

### Step 3: Inspect the Search Page

```python
soup = BeautifulSoup(resp.text, 'html.parser')
htmx_elements = soup.select('[hx-get]')
```

**Discovery:** WeebCentral now uses **HTMX** for dynamic content loading!

```html
<div id="search-results"
     hx-get="https://weebcentral.com/search/data"
     hx-trigger="submit, change from:[name='display_mode']"
     hx-include="#advanced-search-form, [name='display_mode']">
```

### Step 4: The Fix

HTMX endpoints require special headers:

```python
headers = {
    "HX-Request": "true",
    "HX-Current-URL": "https://weebcentral.com/search"
}

resp = session.get(
    "https://weebcentral.com/search/data",
    params={"text": "naruto", "display_mode": "Full Display"},
    headers=headers,
    impersonate="chrome120"
)
```

**Result:** 8 manga results returned!

---

## Root Cause Analysis

| Symptom | Initial Diagnosis | Actual Cause |
|---------|------------------|--------------|
| Empty results | Cloudflare blocking | API endpoint changed |
| 200 OK status | Bypass not working | Site returns 200 for errors |
| No JSON data | Rate limiting | Now uses HTMX, not REST API |

### Why cloudscraper Failed

cloudscraper is designed to bypass **JavaScript challenges** (captchas, browser verification). WeebCentral's issue wasn't a challenge - it was that the **API contract changed**.

### Why curl_cffi Was Needed

While the main issue was HTMX headers, curl_cffi's Chrome impersonation was still necessary because:
1. WeebCentral does have some Cloudflare protection on certain pages
2. TLS fingerprinting helps avoid bot detection
3. Session cookies are properly maintained

---

## The Solution: WeebCentral Lua Adapter

Created `sources/weebcentral_lua.py` with:

```python
from curl_cffi import requests as curl_requests

class WeebCentralLuaAdapter(BaseConnector):
    def _get(self, url, params=None, htmx=False):
        headers = {}
        if htmx:
            headers["HX-Request"] = "true"
            headers["HX-Current-URL"] = f"{self.base_url}/search"

        resp = self._session.get(
            url,
            params=params,
            headers=headers,
            impersonate="chrome120"
        )
        return resp.text
```

---

## Results

### Before (Old Python Connector)
```
Search "naruto": 0 results
Chapters: 0
Status: Blocked/Empty
```

### After (New Lua Adapter)
```
Search "naruto": 8 results
Naruto chapters: 701
Pages: 17 per chapter
Status: Fully working!
```

---

## Lessons Learned

1. **HTTP 200 doesn't mean success** - Always check response content, not just status codes

2. **Modern sites use HTMX/SPA** - Many manga sites have moved from REST APIs to HTMX/dynamic loading. Need to inspect page source for `hx-*` attributes

3. **Cloudflare isn't always the culprit** - When requests fail, the issue might be:
   - Changed API endpoints
   - Missing required headers
   - Changed authentication
   - Modified request format

4. **Browser DevTools are essential** - The solution was found by inspecting the actual HTML and finding HTMX attributes

---

## Technical Details

### HTMX Headers Required

| Header | Value | Purpose |
|--------|-------|---------|
| `HX-Request` | `true` | Indicates HTMX request |
| `HX-Current-URL` | Page URL | Referrer for HTMX |
| `HX-Trigger` | Event name | Optional trigger info |

### WeebCentral URL Structure

```
Search:    /search/data?text=query&display_mode=Full%20Display
Series:    /series/{ID}/{SLUG}
Chapters:  /series/{ID}/full-chapter-list
Pages:     /chapters/{CHAPTER_ID}/images?reading_style=long_strip
```

### Image CDN

Pages are hosted on: `https://hot.planeptune.us/manga/{SERIES}/{CHAPTER}-{PAGE}.png`

---

## Phase Change: v2.3 → v3.0

This breakthrough marks the transition from MangaNegus v2.3 to v3.0:

| Feature | v2.3 | v3.0 |
|---------|------|------|
| Architecture | Python only | Python + Lua hybrid |
| Cloudflare bypass | None | curl_cffi + HTMX |
| WeebCentral | Broken | 701 chapters |
| MangaDex | 3 chapters | 3 chapters (API limit) |
| Sources | 17 Python | 28 (Python + Lua) |

---

## Files Created/Modified

### New Files
- `sources/lua_runtime.py` - Lua interpreter wrapper
- `sources/lua_adapter.py` - MangaDex Lua adapter
- `sources/weebcentral_lua.py` - WeebCentral with HTMX support
- `DEVELOPMENT_PLAN.md` - v3.0 roadmap
- `BREAKTHROUGH_NOTES.md` - This document

### Modified Files
- `sources/__init__.py` - Added Lua source discovery

---

## Next Steps

1. **MangaFire Lua Adapter** - Apply same HTMX pattern
2. **MangaSee Lua Adapter** - Check if HTMX or REST
3. **Direct URL Detection** - Auto-detect source from pasted URL
4. **ComicInfo.xml** - Add metadata to CBZ downloads

---

**Key Takeaway:** When debugging web scraping issues, always inspect the actual HTML response and look for modern patterns like HTMX, Alpine.js, or React hydration markers before assuming it's a blocking issue.
