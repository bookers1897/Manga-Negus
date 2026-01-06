# Next Steps: Advanced Cloudflare Bypass & Source Fixes

**Date**: 2026-01-05
**Status**: Planning Phase

---

## Completed Fixes ✅

1. **MangaNato V2** - Updated to `mangakakalot.gg` (domain migration)
2. **WeebCentral V2** - Fixed structural bug in `_get()` method
3. **Test Infrastructure** - Fixed attribute errors and imports

**Result**: 4 sources now fully functional (search + chapters + pages)

---

## Immediate Priority: MangaFire Cloudflare 403

### Current Status
```
Testing: MangaFire (mangafire)...
🔍 Searching MangaFire: naruto
⚠️ 403 error, retrying in 5s...
⚠️ 403 error, retrying in 5s...
  ⚠️ search: WARN - no results
```

### Root Cause

MangaFire is detecting `curl_cffi` browser impersonation. Current bypass:
```python
# sources/mangafire.py (using cloudscraper)
session = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)
```

**Problem**: Cloudflare has improved detection in 2025-2026, recognizes:
- TLS fingerprints from cloudscraper
- Missing browser APIs (WebGL, Canvas, etc.)
- Automated request patterns

### Research Findings (2026)

Based on research agent findings, top Cloudflare bypass methods:

#### 1. **Playwright-Stealth** (Recommended)
- **Success Rate**: ~85-90%
- **Speed**: Medium (full browser)
- **Complexity**: Low
```bash
pip install playwright playwright-stealth
playwright install chromium
```

**Pros**:
- Real browser (full JS execution)
- Active stealth plugins
- Good for HTMX/React sites

**Cons**:
- Slower than curl_cffi
- Higher resource usage

#### 2. **Undetected-Chromedriver**
- **Success Rate**: ~80-85%
- **Speed**: Medium
- **Complexity**: Medium
```bash
pip install undetected-chromedriver
```

**Pros**:
- Selenium-compatible
- Auto-updates Chrome version
- Battle-tested

**Cons**:
- Requires Chrome/Chromium installed
- Occasional detection on strict sites

#### 3. **Camoufox** (Newest - 2026)
- **Success Rate**: ~90-95%
- **Speed**: Medium
- **Complexity**: Medium
```bash
pip install camoufox
```

**Pros**:
- Firefox-based (different fingerprint)
- Anti-detect features built-in
- Less common = harder to detect

**Cons**:
- Newer, less tested
- Python-specific

#### 4. **curl_cffi + Better Fingerprinting**
- **Success Rate**: ~70-75%
- **Speed**: Fast
- **Complexity**: High
```bash
# Already installed
```

**Improvements Needed**:
- JA3/JA4 fingerprint randomization
- HTTP/2 fingerprinting
- More realistic headers (Accept-CH, Sec-CH-UA, etc.)

### Recommended Implementation Plan

**Phase 1: Quick Win - Playwright-Stealth**
```python
# sources/mangafire.py - NEW VERSION
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

class MangaFireV2Connector(BaseConnector):
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page()
        stealth_sync(self.page)  # Apply anti-detection

    def search(self, query):
        self.page.goto(f"https://mangafire.to/filter?keyword={query}")
        self.page.wait_for_load_state("networkidle")
        html = self.page.content()
        # Parse with BeautifulSoup as before
```

**Phase 2: Fallback Strategy**
Implement multi-method cascade:
1. Try curl_cffi (fast)
2. If 403 → Try playwright-stealth (reliable)
3. If still blocked → Try undetected-chromedriver
4. If all fail → Mark source unavailable

**Phase 3: Monitoring**
Add success rate tracking:
```python
class BypassMethod:
    name: str
    success_count: int
    fail_count: int
    avg_response_time: float

def choose_best_method(source_id):
    # Pick method with highest success rate for this source
    pass
```

---

## Other High-Priority Fixes

### 1. MangaDex Chapters (0 chapters)

**Issue**: Search works (15 results) but `get_chapters()` returns 0

**Investigation Needed**:
```python
# Test MangaDex API directly
import requests
manga_id = "<id_from_search>"
resp = requests.get(
    f"https://api.mangadex.org/manga/{manga_id}/feed",
    params={"translatedLanguage[]": "en", "limit": 100}
)
print(resp.json())
```

**Possible Causes**:
- API endpoint changed
- Rate limiting (need delay between requests)
- Missing required query parameters

### 2. Empty Results (24 sources)

Sources returning 0 results likely need:
- **Domain migration research** (like manganato.com)
- **HTML selector updates** (sites redesigned)
- **Cloudflare bypass** (like MangaFire)

**Systematic Approach**:
1. For each source, manually visit website
2. Search for "naruto" in browser
3. If results appear → selector update needed
4. If Cloudflare challenge → bypass needed
5. If redirect/404 → domain migration research

---

## Long-Term Improvements

### 1. Adaptive Bypass System

```python
# bypass_manager.py
class AdaptiveBypassManager:
    """
    Automatically chooses best bypass method per source.
    Falls back to more powerful methods if needed.
    """

    methods = [
        ("curl_cffi", speed=10, reliability=6),
        ("cloudscraper", speed=8, reliability=5),
        ("playwright", speed=4, reliability=9),
        ("undetected_chrome", speed=4, reliability=8)
    ]

    def get_html(self, source_id, url):
        # Try methods in order of success rate for this source
        # Learn from failures, adapt over time
        pass
```

### 2. Browser Fingerprint Randomization

```python
# Better curl_cffi usage
from curl_cffi.requests import Session
import random

def get_random_fingerprint():
    browsers = ["chrome120", "chrome119", "edge101", "safari17"]
    return random.choice(browsers)

session = Session()
response = session.get(
    url,
    impersonate=get_random_fingerprint(),
    headers={
        "Sec-CH-UA": random_ua_header(),
        "Sec-CH-UA-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
        # More randomization...
    }
)
```

### 3. Rate Limit Intelligence

```python
# Smart rate limiting based on actual 429 responses
class SmartRateLimiter:
    def __init__(self, source_id):
        self.base_delay = 1.0
        self.backoff_multiplier = 2.0
        self.max_delay = 30.0

    def on_429(self):
        # Exponential backoff
        self.base_delay = min(
            self.base_delay * self.backoff_multiplier,
            self.max_delay
        )

    def on_success(self):
        # Slowly reduce delay if successful
        self.base_delay = max(0.5, self.base_delay * 0.9)
```

---

## Testing Strategy

### Before Implementing Changes

1. **Baseline Test**
   ```bash
   python test_sources_health.py > before.txt
   ```

2. **Implement Fix**
   - Start with least invasive (selector updates)
   - Then bypass improvements
   - Finally structural changes

3. **Verify Fix**
   ```bash
   python test_sources_health.py > after.txt
   diff before.txt after.txt
   ```

4. **Regression Check**
   - Ensure previously working sources still work
   - Check for new errors introduced

---

## Resources

### Cloudflare Bypass Libraries (2026)

- **playwright-stealth**: https://github.com/AtuboDad/playwright_stealth
- **undetected-chromedriver**: https://github.com/ultrafunkamsterdam/undetected-chromedriver
- **camoufox**: https://camoufox.com/ (anti-detect browser)
- **curl_cffi**: https://github.com/yifeikong/curl_cffi
- **nodriver**: https://github.com/ultrafunkamsterdam/nodriver (Selenium successor)

### Domain Migration Tracking

- **Tachiyomi Extensions**: https://github.com/keiyoushi/extensions-source
  (Active community tracking manga site changes)

- **MALSync**: https://github.com/MALSync/MALSync
  (Tracks domain changes for manga/anime sites)

### Browser Fingerprinting

- **BrowserLeaks**: https://browserleaks.com/
  (Test your scraper's fingerprint)

- **CreepJS**: https://abrahamjuliot.github.io/creepjs/
  (Check bot detection signals)

---

## Success Metrics

### Current Status (After Initial Fixes)
- **Working Sources**: 8/33 (24%)
- **Fully Functional**: 4/33 (12%)

### Target After Cloudflare Fixes
- **Working Sources**: 20+/33 (60%+)
- **Fully Functional**: 15+/33 (45%+)

### Key Performance Indicators
1. **Search Success Rate**: % of sources returning results
2. **Average Response Time**: < 5s for search
3. **Cloudflare Block Rate**: < 10%
4. **False Positives**: 0 (working sites marked as broken)

---

## Timeline Estimate

### Week 1: Critical Fixes
- [ ] MangaFire playwright-stealth implementation
- [ ] MangaDex chapter investigation
- [ ] 5 highest-traffic sources domain research

### Week 2: Systematic Cleanup
- [ ] Test all 33 sources manually
- [ ] Update selectors for redesigned sites
- [ ] Implement fallback bypass system

### Week 3: Optimization
- [ ] Fingerprint randomization
- [ ] Smart rate limiting
- [ ] Performance profiling

---

## Commands for Implementation

```bash
# Install new dependencies
pip install playwright playwright-stealth undetected-chromedriver
playwright install chromium

# Test single source with debug
python -c "from sources.mangafire import *; test_source('naruto')"

# Run full health check
python test_sources_health.py

# Check specific source
python test_all_sources.py --source mangafire --verbose

# Domain migration research
python test_domain_migration.py --source manganato
```

---

**Status**: Ready for Implementation
**Priority**: High (MangaFire blocking 1/3 of users)
**Risk**: Low (changes isolated to individual source files)
