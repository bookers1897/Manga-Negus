# CLAUDE.md

AI assistant guide for MangaNegus v3.0.1 - Multi-source manga downloader with hybrid Python + Lua architecture.

## Project Overview

**MangaNegus v3.0.1** - Flask-based manga downloader, library manager, and reader for iOS Code App.

**Target:** iOS Code App (mobile Safari)
**Author:** [@bookers1897](https://github.com/bookers1897)
**Stack:** Python 3.8+ (Flask 3.0) + Vanilla JavaScript + Lua (lupa runtime)

**Key Features:**
- 31+ manga sources (Python + Lua adapters)
- HTMX + Cloudflare bypass (curl_cffi, cloudscraper)
- Token bucket rate limiting
- Automatic source fallback
- Glassmorphism iOS UI
- CBZ downloads with background workers

---

## Architecture

### Technology Stack

- **Backend:** Flask 3.0, BeautifulSoup4, lupa, curl_cffi
- **Frontend:** Vanilla JS, Tailwind CSS CDN, Phosphor Icons
- **Data:** JSON file (`library.json`)
- **APIs:** MangaDex API v5, WeebCentral HTMX endpoints

### Design Patterns

1. **HakuNeko-Inspired Connectors:** `search() → get_chapters() → get_pages()` pipeline
2. **Hybrid Lua/Python:** Run FMD's 590+ Lua modules for massive source coverage
3. **Token Bucket Rate Limiting:** Per-source rate limiting prevents bans
4. **Automatic Fallback:** Priority-based source routing on failure
5. **HTMX Bypass:** Special headers for modern dynamic sites
6. **Callback Pattern:** Eliminates circular imports via `source_log()`

### Project Structure

```
Manga-Negus/
├── run.py                  # Flask entry point
├── library.json            # User library database
├── manganegus_app/         # Flask application package
│   ├── __init__.py         # App factory (create_app)
│   ├── extensions.py       # Library, Downloader singletons
│   ├── log.py              # Thread-safe logging
│   ├── csrf.py             # CSRF protection
│   └── routes/             # Flask blueprints
│       ├── main_api.py     # Index, CSRF, image proxy
│       ├── sources_api.py  # Source health, list
│       ├── manga_api.py    # Search, detect_url, popular
│       ├── library_api.py  # Library CRUD, status, progress
│       └── downloads_api.py # Download, serve CBZ
├── templates/
│   └── index.html          # SPA (HTML structure)
├── static/
│   ├── css/styles.css      # Glassmorphism theme
│   ├── js/                 # Modularized ES6 (v3.0+)
│   │   ├── main.js         # App coordinator (138 lines)
│   │   ├── api.js          # CSRF-protected API singleton (173 lines)
│   │   ├── state.js        # Reactive state container (218 lines)
│   │   ├── utils.js        # XSS prevention utilities (88 lines)
│   │   ├── sources.js      # Source management (103 lines)
│   │   ├── search.js       # Search, trending, URL detection (215 lines)
│   │   ├── library.js      # Library CRUD operations (129 lines)
│   │   ├── chapters.js     # Chapter loading, downloads (332 lines)
│   │   ├── reader.js       # Fullscreen manga reader (98 lines)
│   │   └── ui.js           # View management, logging (59 lines)
│   └── downloads/          # CBZ files (auto-created)
├── sources/
│   ├── __init__.py         # SourceManager (auto-discovery, fallback)
│   ├── base.py             # BaseConnector (rate limiting, logging)
│   ├── webdriver.py        # Selenium helpers
│   ├── lua_runtime.py      # Lua interpreter wrapper
│   ├── lua_adapter.py      # Base Lua adapter
│   ├── weebcentral_lua.py  # HTMX + curl_cffi (1170 chapters!)
│   ├── mangadex.py         # Official API
│   ├── annasarchive.py     # Shadow library
│   ├── libgen.py           # LibGen API
│   ├── comicx.py           # ComicX aggregator
│   └── [19+ other sources]
└── BREAKTHROUGH_NOTES.md   # HTMX discovery documentation
```

---

## Core Files

### Backend (manganegus_app/)

**Entry Point:** `run.py` → `create_app()` factory pattern

**Key Components:**
- **extensions.py**: Library and Downloader singleton instances
- **routes/*.py**: Flask blueprints organize API endpoints
- **log.py**: Thread-safe message queue for real-time console
- **csrf.py**: CSRF protection for POST requests

**Flask Blueprints:**
| Blueprint | Prefix | Routes |
|-----------|--------|--------|
| main_bp | / | Index, CSRF token, image proxy |
| sources_bp | /api | Source health, list sources |
| manga_bp | /api | Search, detect_url, popular |
| library_bp | /api | Library CRUD, status, progress |
| downloads_bp | /api | Download, serve CBZ |

**Critical API Endpoints:**
```python
GET  /api/csrf-token         # CSRF token for POST requests
GET  /api/library            # User's library
POST /api/save               # Add to library (source required)
POST /api/search             # Search manga
POST /api/detect_url         # Detect source from URL (19 patterns)
POST /api/chapters           # Get chapters (paginated, 100/page)
POST /api/chapter_pages      # Stream reader pages
POST /api/download           # Background download (threading)
GET  /downloads/<file>       # Serve CBZ files
GET  /api/sources/health     # Source availability (31 sources)
```

### Frontend (static/js/) - ES6 Modules

**Architecture:** Modular ES6 with event-driven communication (v3.0+)

**Module Breakdown:**
- **main.js** (138 lines): App coordinator, initializes modules, binds events
- **api.js** (173 lines): Singleton for CSRF-protected backend communication
- **state.js** (218 lines): Reactive state container with subscriber pattern
- **utils.js** (88 lines): XSS prevention utilities (escapeHtml, sanitizeUrl)
- **sources.js** (103 lines): Source selection, health display
- **search.js** (215 lines): Search, trending, URL detection
- **library.js** (129 lines): Library grid, filters, CRUD operations
- **chapters.js** (332 lines): Chapter loading, selection, pagination, downloads
- **reader.js** (98 lines): Fullscreen manga reader with lazy loading
- **ui.js** (59 lines): View management, console logging, theme toggle

**Cross-Module Communication:**
```javascript
// Event-driven pattern (loose coupling)
window.dispatchEvent(new CustomEvent('openManga', {
    detail: { id, source, title }
}));

// main.js coordinates responses
window.addEventListener('openManga', e => {
    chapters.showMangaDetails(e.detail.id, e.detail.source, e.detail.title);
});
```

**XSS Prevention:**
All modules use safe DOM methods:
```javascript
// Safe approach: createElement + textContent
const el = document.createElement('div');
el.textContent = untrustedData;  // Auto-escaped
parent.appendChild(el);

// Unsafe method BLOCKED by security hooks
```

### templates/index.html - SPA Template

**Structure:** HTML markup only (JavaScript extracted to modules)

**Views:** `view-search`, `view-library`, `view-details`

**Module Loading:**
```html
<script type="module" src="/static/js/main.js"></script>
```

**Key Functions:**
- `showMangaDetails(id, source, title)` - Load manga
- `loadChapters()` - Paginated fetch
- `downloadRange/Selection()` - CBZ downloads
- `openReader(index)` - Fullscreen reader

### static/css/styles.css

**Theme Variables:**
```css
--bg-primary: rgba(28, 28, 30, 0.72)     /* Dark glass */
--accent-color: #ff453a                   /* Red accent */
--text-primary: #ffffff
```

**Key Classes:** `.glass-panel`, `.glass-btn`, `.manga-card`, `.chapter-item`, `.reader-container`

### library.json - Data Store

```json
{
  "manga_id_uuid": {
    "title": "Title",
    "source": "mangadex",
    "status": "reading|plan_to_read|completed",
    "cover": "https://...",
    "last_chapter": "123.5"
  }
}
```

---

## Development Workflows

### Setup & Run

```bash
# Virtual environment (recommended for Arch/externally-managed Python)
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server
python run.py  # http://127.0.0.1:5000
# or: python -m flask run
```

### Testing Sources

```bash
# Test WeebCentral Lua
python -c "from sources.weebcentral_lua import WeebCentralLuaAdapter; print(WeebCentralLuaAdapter().search('naruto', 1))"

# List all sources
python -c "from sources import get_source_manager; print(get_source_manager().list_sources())"
```

### Adding a New Python Connector

```python
# sources/newsource.py
from .base import BaseConnector, MangaResult, ChapterResult, PageResult, source_log

class NewSourceConnector(BaseConnector):
    id = "newsource"
    name = "New Source"
    base_url = "https://newsource.com"
    icon = "🆕"

    # URL detection
    url_patterns = [r'https?://newsource\.com/manga/([a-z0-9-]+)']

    rate_limit = 1.5
    rate_limit_burst = 3

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        html = self._request_html(f"{self.base_url}/search?q={query}")
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('.manga-item'):
            try:
                results.append(MangaResult(
                    id=item['data-id'],
                    title=item.select_one('.title').text,
                    source=self.id,
                    cover_url=item.select_one('img')['src']
                ))
            except Exception as e:
                source_log(f"[{self.id}] Parse error: {e}")
        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        # Implement chapter fetching
        pass

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        # Implement page fetching
        pass
```

**Auto-discovery:** No registration needed - SourceManager auto-discovers all BaseConnector subclasses.

### Adding a Lua Adapter (HTMX/Cloudflare Sites)

```python
from curl_cffi import requests as curl_requests
from .base import BaseConnector, MangaResult, ChapterResult, PageResult

class NewSiteLuaAdapter(BaseConnector):
    id = "lua-newsite"
    name = "New Site"
    base_url = "https://newsite.com"

    def __init__(self):
        super().__init__()
        self._session = curl_requests.Session()

    def _get(self, url: str, params=None, htmx: bool = False):
        headers = {}
        if htmx:
            headers["HX-Request"] = "true"
            headers["HX-Current-URL"] = f"{self.base_url}/search"

        return self._session.get(
            url, params=params, headers=headers,
            impersonate="chrome120",
            timeout=self.request_timeout
        ).text
```

**Pattern:** Use `htmx=True` for HTMX endpoints, `impersonate="chrome120"` for Cloudflare bypass.

---

## Code Conventions

### Python
- Comprehensive docstrings
- Use `except Exception as e:` with logging (never bare `except:`)
- Thread-safe logging via `source_log()`
- Rate limit handling (HTTP 429)

### JavaScript
- camelCase functions/variables
- Async/await pattern
- Check API responses before use
- Use `textContent` for untrusted data (XSS prevention)

### CSS
- BEM-inspired naming
- CSS variables for theming
- Mobile-first responsive design

---

## MangaDex API Integration

**Base URL:** `https://api.mangadex.org`

**Endpoints:**
```
GET /manga?title={query}&limit=15&includes[]=cover_art
GET /chapter?manga={id}&translatedLanguage[]=en&limit=100&offset={offset}
GET /at-home/server/{chapter_id}
```

**Cover URLs:** `https://uploads.mangadex.org/covers/{manga_id}/{filename}.256.jpg`

**Rate Limiting:** 2 req/s, handle HTTP 429, use persistent session

---

## v3.0 Breakthrough: HTMX + Lua

### WeebCentral Discovery (Dec 2025)

**Problem:** HTTP 200 OK but empty results (suspected Cloudflare)
**Root Cause:** Site migrated from REST to **HTMX** endpoints
**Solution:** HTMX headers + Chrome impersonation

```python
headers = {
    "HX-Request": "true",
    "HX-Current-URL": "https://weebcentral.com/search"
}
resp = curl_requests.get(url, headers=headers, impersonate="chrome120")
```

**Results:** 0 chapters → **701 chapters** for Naruto

### Critical Debugging Patterns

1. HTTP 200 ≠ success - check response content
2. Inspect HTML for `hx-*` attributes
3. Check DevTools Network tab for actual headers
4. Cloudflare isn't always the culprit

### Lua Runtime Architecture

**Components:**
1. **lua_runtime.py** - Wraps lupa, implements FMD API (`HTTP.GET()`, `CreateTXQuery()`)
2. **lua_adapter.py** - Bridges Lua modules to BaseConnector
3. **weebcentral_lua.py** - Production adapter (1170 chapters for One Piece)

---

## Multi-Source System

### SourceManager Auto-Discovery

```python
# Scans sources/ directory
for module_name in pkgutil.iter_modules([sources_dir]):
    module = importlib.import_module(f'.{module_name}', 'sources')
    for attr in dir(module):
        if issubclass(attr, BaseConnector) and attr.__name__ not in skip_classes:
            self._sources[attr().id] = attr()
```

**Skip Classes:** `{'LuaSourceAdapter'}` (requires constructor args)

### Priority-Based Fallback

```python
priority_order = [
    "lua-weebcentral",  # 1170 chapters (HTMX breakthrough)
    "mangadex",         # Official API
    "manganato",        # .gg domain
    "mangafire",        # Cloudflare bypass
    "libgen",           # LibGen API (NEW)
    "annas-archive",    # Shadow library (NEW)
    "comicx"            # NEW aggregator
]

for source_id in priority_order:
    results = source.search(query)
    if results is not None:  # None = failure, [] = no results (valid)
        return results
```

### Token Bucket Rate Limiting

```python
def _wait_for_rate_limit(self):
    # Refill tokens based on elapsed time
    elapsed = time.time() - self._last_request
    self._tokens = min(self.rate_limit_burst, self._tokens + elapsed * self.rate_limit)

    # Wait if no tokens
    if self._tokens < 1.0:
        time.sleep((1.0 - self._tokens) / self.rate_limit)
```

**Per-Source Config:**
| Source | Rate | Burst | Timeout | Cloudflare |
|--------|------|-------|---------|------------|
| MangaDex | 2.0 | 5 | 20s | No |
| WeebCentral | 1.5 | 3 | 20s | curl_cffi |
| MangaFire | 2.0 | 4 | 30s | cloudscraper |

### Cloudflare Bypass Strategies

1. **cloudscraper** - Basic JS challenges
2. **curl_cffi** - TLS fingerprinting + HTMX headers
3. **Selenium** - JS-heavy sites (last resort)

---

## Critical Bug Fixes (Dec 31, 2025)

### Tier 1: Critical (Application Crashes)

#### 1. NameError in `/api/detect_url` ✅
**Fix:** Import `get_source_manager()` function instead of undefined `source_manager` variable.

#### 2. Defunct ComicK in Priority Order ✅
**Impact:** 20-30s timeout on every search
**Fix:** Removed from priority order (site shutdown Sept 2025)
**Result:** Search times: ~60s → 2-3s

#### 3. Duplicate Templates Directory ✅
**Fix:** Deleted nested `templates/templates/` subdirectory

### Tier 2: Major (Functionality Issues)

#### 4. Circular Import in 13 Scrapers ✅
**Fix:** Callback pattern via `source_log()` in `base.py`
```python
from .base import source_log  # Instead of: from app import log
```

#### 5. Open Image Proxy Vulnerability ✅
**Impact:** Open proxy for attackers, DDoS amplification risk
**Fix:** Whitelist of allowed manga domains (403 for others)

#### 6. Downloader Using Wrong Session ✅
**Impact:** Downloads failed for Cloudflare-protected sources
**Fix:** Use source's configured session (with curl_cffi/cloudscraper)

#### 7. Inefficient Fallback Logic ✅
**Impact:** Empty searches triggered full cascade (30-60s wasted)
**Fix:** Check `if result is not None` (not `!= []`)

### New Features

#### URL Detection System ✅
**Purpose:** Paste manga URLs directly (19 sources supported)

**Implementation:**
```python
# BaseConnector
url_patterns = [r'https?://mangadex\.org/title/([a-f0-9-]+)']

def matches_url(self, url: str) -> bool:
    return any(re.search(p, url, re.I) for p in self.url_patterns)

def extract_id_from_url(self, url: str) -> Optional[str]:
    for pattern in self.url_patterns:
        match = re.search(pattern, url, re.I)
        if match and match.groups():
            return match.group(1)
```

**Endpoint:** `POST /api/detect_url` → `{source_id, manga_id, source_name}`

#### New Sources

**LibGen Connector** (`sources/libgen.py`)
- Direct API access to Library Genesis (95TB+ comics)
- Multiple mirrors: libgen.rs, libgen.st, libgen.is
- MD5-based file identification

**Anna's Archive** (`sources/annasarchive.py`)
- Shadow library aggregator
- Complete volumes (CBZ/PDF/EPUB)
- "Chapters" = download mirrors

**ComicX** (`sources/comicx.py`)
- New aggregator site
- Standard BeautifulSoup scraping

---

## Quick Reference

### File Locations
| Purpose | Location |
|---------|----------|
| Server | `app.py` |
| Frontend | `templates/index.html` |
| Styles | `static/css/styles.css` |
| Library DB | `library.json` |
| Downloads | `static/downloads/` |

### Key Functions
| Function | Location | Purpose |
|----------|----------|---------|
| `MangaLogic.search()` | app.py:309 | Multi-source search |
| `MangaLogic.get_chapters()` | app.py:355 | Paginated chapters |
| `MangaLogic.download_worker()` | app.py:602 | Background downloads |
| `showMangaDetails()` | index.html:614 | Load manga view |
| `loadChapters()` | index.html:676 | Fetch chapters |
| `openReader()` | index.html:1183 | Fullscreen reader |

### Environment
| Key | Value |
|-----|-------|
| Python | 3.8+ |
| Flask | 3.0.0 |
| Platform | iOS Code App (Safari) |
| Sources | 31+ (Python + Lua) |
| Bypass | curl_cffi, cloudscraper |

---

## AI Assistant Guidelines

### When Modifying Code
1. Read entire file before editing
2. Follow existing naming/indentation
3. Test mobile viewport + themes
4. Update comments/docstrings

### When Adding Features
1. Check roadmap alignment
2. Consider dependencies/performance
3. Maintain simplicity (vanilla JS, single-file where possible)

### When Fixing Bugs
1. Understand root cause (frontend + backend)
2. Preserve existing behavior
3. Add proper error handling + logging

---

## Roadmap

**High Priority:**
- [ ] Offline CBZ reader
- [ ] Settings page
- [ ] Chapter read markers

**Medium Priority:**
- [ ] Search filters (genre, status, year)
- [ ] Swipe gestures
- [ ] Image preloading

**Low Priority:**
- [ ] Night shift mode
- [ ] Pull-to-refresh

---

## Support & Resources

**Official:**
- Repository: [github.com/bookers1897/Manga-Negus](https://github.com/bookers1897/Manga-Negus)
- Author: [@bookers1897](https://github.com/bookers1897)
- License: MIT

**External Docs:**
- [MangaDex API](https://api.mangadex.org/docs/)
- [Flask](https://flask.palletsprojects.com/)
- [HTMX](https://htmx.org/)
- [curl_cffi](https://github.com/yifeikong/curl_cffi)
- [lupa](https://github.com/scoder/lupa)
- [FMD](https://github.com/dazedcat19/FMD) - 590+ Lua modules

**Troubleshooting:**
1. Browser console (F12)
2. Server console
3. Built-in console panel
4. Network tab
5. `BREAKTHROUGH_NOTES.md` - HTMX patterns

**Common Fixes:**
- Empty results (200 OK) → Check for HTMX endpoints
- 403 Forbidden → Use curl_cffi `impersonate="chrome120"`
- Rate limiting → Adjust `rate_limit` in connector
- Lua errors → Ensure `.venv` activated, lupa installed

---

**Last Updated:** 2026-01-07
**Version:** 3.0.3 (Library Display Fix + PostgreSQL Integration)
**For:** AI Assistants (Claude Code)

**Recent Changes (Jan 7, 2026):**
- ✅ **Library Display Fix:** Fixed ES6 module initialization race condition causing library page not to display
- ✅ **DOM Ready Check:** Added `document.readyState` check in `main.js` for deferred module loading
- ✅ **PostgreSQL Database:** Migrated from JSON file storage to PostgreSQL with SQLAlchemy ORM
- ✅ **Database Fixes:** Fixed ReadingStatus import error and VARCHAR/integer type casting issues
- ✅ **Already Added State:** Library data caching working correctly, buttons show proper state
- ✅ **Portrait Cards:** Updated library grid to use portrait format (160px) matching search view
- ✅ **MAL Image Loading:** Direct CDN loading for MyAnimeList images without proxy

**Previous Changes (Jan 2, 2026):**
- ✅ **Backend Refactored:** Moved to `manganegus_app/` package with Flask blueprints
- ✅ **Frontend Modularized:** Split 704-line monolithic JS into 10 ES6 modules (1,553 lines total)
- ✅ **Code Cleanup:** Removed 195 lines of redundant Library/Downloader code
- ✅ **Flask Static Fix:** Added `static_folder='../static'` to resolve 404 errors
- ✅ **XSS Prevention:** All modules use safe DOM methods (createElement, textContent)
- ✅ **Event-Driven Architecture:** CustomEvents for cross-module communication
- ✅ **Testing Verified:** All 31 sources loaded, APIs functional, CSRF working

**Previous Changes (Dec 31, 2025):**
- ✅ Fixed 7 critical/major bugs
- ✅ Added URL detection (19 sources)
- ✅ Added LibGen + Anna's Archive
- ✅ Removed defunct ComicK (20-30s timeout fix)
- ✅ Circular import fix (callback pattern)
- ✅ Image proxy security (domain whitelist)
- ✅ Download session fix (Cloudflare sources)
- ✅ Fallback logic optimization
