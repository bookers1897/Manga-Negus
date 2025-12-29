# CLAUDE.md - MangaNegus v2.3

> AI Assistant Guide for MangaNegus Multi-Source Edition

## Project Overview

**MangaNegus v2.3** is a multi-source manga downloader, library manager, and in-app reader for iOS Code App. It features a HakuNeko-inspired connector architecture that supports multiple manga sources with automatic fallback, intelligent rate limiting, and CSRF protection.

**Target Platform:** iOS Code App (mobile Safari)
**Current Version:** 2.3
**Author:** [@bookers1897](https://github.com/bookers1897)
**Architecture:** Multi-source connector system with automatic fallback

---

## What's New in v2.3

### 🚨 Critical Bug Fixes

**Search Bug Fixed:**
- v2.2 had a critical bug where searching for one manga would return completely wrong results
- Example: Searching "Gachiakuta" would return "One Piece" chapters
- **Root Cause:** `BaseConnector.__init__()` set `self.session = None` without fallback
- **Fix:** Added `_create_default_session()` method with proper connection pooling
- All searches now return correct, accurate results

### Multi-Source Architecture

v2.3 continues the v2.2 multi-source architecture with bug fixes and enhancements:

- **19 Source Connectors**: MangaDex, ComicK, MangaFire, MangaHere, Manganato, MangaSee, WeebCentral, and more
- **Auto-Discovery**: Sources are automatically discovered and loaded at startup
- **Automatic Fallback**: If one source fails, automatically tries the next
- **Token Bucket Rate Limiting**: Prevents bans with per-source rate limits
- **Source Health Monitoring**: Real-time status tracking for all sources
- **CSRF Protection**: Secure POST requests with token validation
- **Async Download Support**: Concurrent downloads for massive speed boost (optional)
- **Cloudflare Bypass**: curl_cffi integration for protected sites (ComicK)
- **Selenium Support**: WebDriver for JavaScript-heavy sources (WeebCentral)

### Key Improvements from v2.1

| Feature | v2.1 | v2.2 | v2.3 |
|---------|------|------|------|
| Sources | MangaDex only | 5 sources | 19+ sources |
| Rate Limiting | Basic delays | Token bucket | Token bucket + cooldown |
| Security | None | CSRF protection | CSRF + input validation |
| Connector Pattern | Monolithic | Pluggable | Pluggable + async |
| Error Handling | Basic | Comprehensive | Comprehensive + retry |
| Windows Support | Emoji crashes | UTF-8 fixed | UTF-8 fixed |
| **Search Accuracy** | ✅ Accurate | ❌ **BROKEN** | ✅ **FIXED** |
| Cloudflare Bypass | ❌ No | ❌ No | ✅ curl_cffi |
| Selenium Support | ❌ No | ❌ No | ✅ WebDriver |
| Async Downloads | ❌ No | ❌ No | ✅ Optional |

---

## Architecture Overview

### Technology Stack

**Backend:**
- Flask 3.0 (Python 3.8+)
- BeautifulSoup4 (web scraping)
- Requests (HTTP client)
- curl_cffi (Cloudflare bypass - optional)

**Frontend:**
- Vanilla JavaScript (ES6+)
- Phosphor Icons
- CSS Grid/Flexbox (no framework)
- Glassmorphism design system

**Data Storage:**
- JSON file (`library.json`)
- In-memory caching with thread safety

**External APIs:**
- MangaDex API v5 (official)
- Various manga aggregator sites (scraped)

### Design Patterns

1. **Abstract Factory Pattern**: `BaseConnector` defines interface, sources implement it
2. **Singleton Pattern**: `SourceManager` global instance
3. **Token Bucket Algorithm**: Rate limiting per source
4. **Fallback Chain**: Try sources in priority order until success
5. **Observer Pattern**: Real-time logging via message queue
6. **Decorator Pattern**: CSRF protection on POST routes

---

## Project Structure

```
Manga-Negus-v2.3/
├── app.py                      # Flask application (817 lines)
├── requirements.txt            # Python dependencies
├── library.json                # User's manga library (JSON database)
├── CHANGELOG.md                # Version history
├── README.md                   # User documentation
├── CLAUDE.md                   # This file - AI guide
├── .gitignore                  # Git ignore rules
├── sources/                    # 🔥 Multi-source connectors
│   ├── __init__.py             # SourceManager (444 lines)
│   ├── base.py                 # BaseConnector abstract class (449 lines)
│   ├── mangadex.py             # MangaDex API connector
│   ├── mangafire.py            # MangaFire scraper
│   ├── mangahere.py            # MangaHere scraper
│   ├── mangasee.py             # MangaSee scraper
│   ├── mangakakalot.py         # Manganato scraper
│   ├── comick.py               # ComicK connector (defunct - service shut down)
│   └── [other sources]         # Additional experimental sources
├── templates/
│   └── index.html              # Main SPA (852 lines)
└── static/
    ├── css/
    │   └── styles.css          # All application styles
    ├── images/
    │   ├── sharingan.png       # App logo (customizable)
    │   └── placeholder.svg     # Fallback cover image
    └── downloads/              # Downloaded CBZ files (auto-created)
```

---

## Core Components

### 1. Source Manager (`sources/__init__.py`)

**Purpose:** Central hub for all manga sources with automatic fallback.

**Key Responsibilities:**
- Auto-discover and register all source connectors
- Manage active source preference
- Route requests with fallback chain
- Track source health status
- Share HTTP session across sources

**How Auto-Discovery Works:**
```python
# Scans sources/ directory for Python modules
# Instantiates any class inheriting from BaseConnector
# Registers them automatically - no manual imports needed!

def _discover_sources(self):
    for _, module_name, _ in pkgutil.iter_modules([sources_dir]):
        module = importlib.import_module(f'.{module_name}', 'sources')
        for attr in dir(module):
            if issubclass(attr, BaseConnector):
                connector = attr()
                self._sources[connector.id] = connector
```

**Fallback Priority Order:**
1. ComicK (most lenient, but shut down Sept 2025)
2. MangaDex (official API, reliable)
3. Manganato (fast aggregator)
4. MangaFire (new addition, fast CDN)
5. MangaHere (established site)
6. MangaSee (large library)

**Critical Methods:**

| Method | Purpose | Fallback? |
|--------|---------|-----------|
| `search(query, source_id)` | Search for manga | ✅ Yes |
| `get_popular(source_id, page)` | Get trending manga | ✅ Yes |
| `get_chapters(manga_id, source_id)` | Get chapter list | ❌ No (source-specific ID) |
| `get_pages(chapter_id, source_id)` | Get page URLs | ❌ No (source-specific ID) |
| `get_health_report()` | Get all source statuses | N/A |
| `reset_source(source_id)` | Reset rate limit | N/A |

### 2. Base Connector (`sources/base.py`)

**Purpose:** Abstract base class defining the connector interface.

**All connectors must implement:**
```python
class MySourceConnector(BaseConnector):
    # Required attributes
    id = "mysource"                    # Unique identifier
    name = "My Source"                 # Display name
    base_url = "https://mysource.com"  # Root URL
    icon = "📖"                        # Emoji for UI

    # Rate limiting (requests per second)
    rate_limit = 2.0                   # Sustained rate
    rate_limit_burst = 5               # Burst capacity

    # Required methods
    def search(self, query: str, page: int) -> List[MangaResult]:
        """Search for manga by title"""
        pass

    def get_chapters(self, manga_id: str, language: str) -> List[ChapterResult]:
        """Get chapter list for a manga"""
        pass

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page image URLs for a chapter"""
        pass
```

**Rate Limiting - Token Bucket Algorithm:**

Each source has its own rate limiter:
```python
# Token bucket refills at rate_limit tokens per second
# Burst capacity allows quick bursts without waiting
# Automatic cooldown on 429/403 responses

def _wait_for_rate_limit(self):
    now = time.time()
    elapsed = now - self._last_request_time

    # Refill tokens
    self._tokens = min(
        self.rate_limit_burst,
        self._tokens + elapsed * self.rate_limit
    )

    # Wait if no tokens available
    if self._tokens < 1:
        wait_time = (1 - self._tokens) / self.rate_limit
        time.sleep(wait_time)
        self._tokens = 0
    else:
        self._tokens -= 1
```

**Standardized Data Classes:**

```python
@dataclass
class MangaResult:
    id: str                         # Source-specific ID
    title: str                      # Display title
    source: str                     # Source identifier
    cover_url: Optional[str]        # Cover image URL
    description: Optional[str]
    author: Optional[str]
    status: str                     # "ongoing", "completed", "hiatus"
    genres: List[str]
    url: Optional[str]              # Direct link

@dataclass
class ChapterResult:
    id: str                         # Source-specific chapter ID
    chapter: str                    # Chapter number (string for "10.5")
    title: Optional[str]            # Chapter title
    volume: Optional[str]
    language: str                   # ISO code ("en")
    scanlator: Optional[str]        # Translation group
    source: str

@dataclass
class PageResult:
    url: str                        # Image URL
    index: int                      # Page number (0-indexed)
    headers: Dict[str, str]         # Required headers
    referer: Optional[str]          # Referer header (anti-hotlinking)
```

### 3. Flask Application (`app.py`)

**Purpose:** Main server handling routes, library management, downloads, and security.

**Key Components:**

**CSRF Protection (NEW in v2.3):**
```python
# Generate token per session
@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)

# Validate on POST requests
@csrf_protect
def protected_route():
    # Request.json must include X-CSRF-Token header
    # or _csrf_token field
```

**Library Manager:**
```python
class Library:
    """Thread-safe manga library with in-memory caching."""

    # Key format: "source:manga_id"
    # Example: "mangadex:abc123-def456"

    def add(manga_id, title, source, status, cover) -> str:
        """Add or update manga, returns library key"""

    def update_status(key, status):
        """Update reading status"""

    def update_progress(key, chapter):
        """Update last read chapter"""
```

**Downloader:**
```python
class Downloader:
    """Background chapter downloader with CBZ packaging."""

    def start(chapters, title, source_id) -> job_id:
        """
        Start download in background thread.

        Process:
        1. Fetch pages from source connector
        2. Download images with retries (3 attempts)
        3. Package into CBZ (Comic Book ZIP)
        4. Clean up temporary files
        5. Log progress to message queue
        """
```

**API Routes:**

| Route | Method | CSRF | Purpose |
|-------|--------|------|---------|
| `/` | GET | No | Serve main page |
| `/api/csrf-token` | GET | No | Get CSRF token |
| `/api/sources` | GET | No | List available sources |
| `/api/sources/active` | GET/POST | POST | Get/set active source |
| `/api/sources/health` | GET | No | Source health status |
| `/api/sources/<id>/reset` | POST | Yes | Reset source error state |
| `/api/search` | POST | Yes | Search for manga |
| `/api/popular` | GET | No | Get popular manga |
| `/api/latest` | GET | No | Get latest updates |
| `/api/chapters` | POST | Yes | Get chapter list |
| `/api/chapter_pages` | POST | Yes | Get page URLs |
| `/api/library` | GET | No | Get user library |
| `/api/save` | POST | Yes | Add to library |
| `/api/update_status` | POST | Yes | Update reading status |
| `/api/update_progress` | POST | Yes | Update last chapter |
| `/api/delete` | POST | Yes | Remove from library |
| `/api/download` | POST | Yes | Start download |
| `/api/download/cancel` | POST | Yes | Cancel download |
| `/api/downloaded_chapters` | POST | Yes | Get downloaded list |
| `/api/proxy/image` | GET | No | Proxy external images (CORS) |
| `/api/logs` | GET | No | Get console messages |
| `/downloads/<file>` | GET | No | Serve CBZ files |

### 4. Frontend SPA (`templates/index.html`)

**Purpose:** Single-page application with view management and API integration.

**Key Features:**

**CSRF Token Management:**
```javascript
const App = {
    csrfToken: null,

    async fetchCsrfToken() {
        const resp = await fetch('/api/csrf-token');
        const data = await resp.json();
        this.csrfToken = data.csrf_token;
    },

    async postJson(url, data = {}) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken  // Include token!
            },
            body: JSON.stringify(data)
        });
    }
};
```

**Security Functions:**
```javascript
// XSS Prevention
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// URL Sanitization (prevents javascript: protocol attacks)
function sanitizeUrl(url) {
    const parsed = new URL(url, window.location.origin);
    if (parsed.protocol === 'javascript:' || parsed.protocol === 'data:') {
        return PLACEHOLDER_IMAGE;
    }
    return url;
}

// Image Proxying (avoids CORS issues)
function proxyImageUrl(url) {
    if (url.startsWith('/')) return url;  // Local URL
    return `/api/proxy/image?url=${encodeURIComponent(url)}`;
}
```

**View Management:**
```javascript
// Three main views:
// 1. search-view - Browse and search manga
// 2. library-view - User's saved manga
// 3. details-view - Manga details + chapters

showView(viewName) {
    this.previousView = this.currentView;
    this.currentView = viewName;

    // Hide all panels
    document.querySelectorAll('.view-panel').forEach(panel => {
        panel.classList.remove('active');
    });

    // Show target panel
    document.getElementById(`${viewName}-view`).classList.add('active');
}
```

**State Management:**
```javascript
const App = {
    // Core state
    currentView: 'search',
    previousView: 'search',
    currentManga: null,          // {id, source, title}
    chapters: [],                // Loaded chapters
    selectedChapters: new Set(), // Selected for download

    // Source state
    sources: [],                 // Available sources
    activeSource: null,          // Current source ID

    // Pagination
    chapterOffset: 0,
    hasMoreChapters: false,

    // Security
    csrfToken: null,

    // Loading state
    isLoading: false
};
```

### 5. Library Data (`library.json`)

**Schema (v2.3):**
```json
{
  "source:manga_id": {
    "title": "Manga Title",
    "source": "mangadex",
    "manga_id": "abc123-def456",
    "status": "reading",
    "cover": "https://...",
    "last_chapter": "123.5",
    "added_at": "2025-12-29 10:00:00"
  }
}
```

**Key Format:**
- **v2.1:** Used manga_id as key (single source only)
- **v2.3:** Uses `source:manga_id` as key (multi-source support)

**Status Values:**
- `reading` - Currently reading
- `plan_to_read` - Planned to read
- `completed` - Finished reading
- `dropped` - Discontinued
- `on_hold` - Paused

**Thread Safety:**
- Uses `threading.RLock()` for nested locking
- In-memory cache to reduce disk I/O
- Atomic writes to prevent corruption

---

## Development Workflows

### Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Or manually:
pip install flask requests beautifulsoup4 lxml

# Run server
python app.py

# Access at
http://127.0.0.1:5000
```

**Environment Variables:**
```bash
# Security
export SECRET_KEY="your-secret-key-here"  # Flask session encryption

# Server config
export FLASK_HOST="0.0.0.0"               # Listen address (default: 127.0.0.1)
export FLASK_PORT="5000"                  # Port (default: 5000)
export FLASK_DEBUG="true"                 # Debug mode (default: false)
```

### Adding a New Source

**Step 1: Create connector file**

Create `sources/newsource.py`:

```python
from sources.base import BaseConnector, MangaResult, ChapterResult, PageResult
from bs4 import BeautifulSoup

class NewSourceConnector(BaseConnector):
    """
    Connector for NewSource manga site.

    API Documentation: https://newsource.com/api/docs
    Rate Limit: 2 requests/second
    """

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "newsource"                # Unique ID (lowercase, no spaces)
    name = "New Source"             # Display name
    base_url = "https://newsource.com"
    icon = "📖"                     # Emoji for UI

    # Rate limiting
    rate_limit = 2.0                # Requests per second
    rate_limit_burst = 5            # Burst capacity
    request_timeout = 15            # Timeout in seconds

    # Feature flags
    supports_latest = True          # Has "latest updates" endpoint
    supports_popular = True         # Has "popular" endpoint
    requires_cloudflare = False     # Needs Cloudflare bypass

    # =========================================================================
    # REQUIRED METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> list[MangaResult]:
        """
        Search for manga by title.

        Args:
            query: Search term
            page: Page number (1-indexed)

        Returns:
            List of manga results
        """
        url = f"{self.base_url}/search"
        params = {"q": query, "page": page}

        resp = self._request(url, params=params)
        soup = BeautifulSoup(resp.text, 'html.parser')

        results = []
        for item in soup.select('.manga-item'):
            results.append(MangaResult(
                id=item['data-id'],
                title=item.select_one('.title').text,
                source=self.id,
                cover_url=item.select_one('img')['src'],
                description=item.select_one('.desc').text,
                status=item.select_one('.status').text
            ))

        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> list[ChapterResult]:
        """
        Get chapter list for a manga.

        Args:
            manga_id: Source-specific manga ID
            language: ISO language code

        Returns:
            List of chapters, sorted by chapter number
        """
        url = f"{self.base_url}/manga/{manga_id}/chapters"

        resp = self._request(url)
        data = resp.json()

        chapters = []
        for ch in data['chapters']:
            chapters.append(ChapterResult(
                id=ch['id'],
                chapter=str(ch['number']),
                title=ch.get('title'),
                language=ch.get('lang', 'en'),
                source=self.id
            ))

        return sorted(chapters, key=lambda x: float(x.chapter or 0))

    def get_pages(self, chapter_id: str) -> list[PageResult]:
        """
        Get page image URLs for a chapter.

        Args:
            chapter_id: Source-specific chapter ID

        Returns:
            List of pages with URLs and metadata
        """
        url = f"{self.base_url}/chapter/{chapter_id}/pages"

        resp = self._request(url)
        data = resp.json()

        pages = []
        for i, page_url in enumerate(data['pages']):
            pages.append(PageResult(
                url=page_url,
                index=i,
                headers={'Referer': self.base_url},  # Anti-hotlinking
                referer=self.base_url
            ))

        return pages

    # =========================================================================
    # OPTIONAL METHODS
    # =========================================================================

    def get_popular(self, page: int = 1) -> list[MangaResult]:
        """Get popular manga (optional)."""
        url = f"{self.base_url}/popular"
        # Similar to search()
        ...

    def get_latest(self, page: int = 1) -> list[MangaResult]:
        """Get latest updates (optional)."""
        url = f"{self.base_url}/latest"
        # Similar to search()
        ...
```

**Step 2: Test the connector**

```python
# Test in Python console
from sources.newsource import NewSourceConnector

connector = NewSourceConnector()

# Test search
results = connector.search("one piece")
print(f"Found {len(results)} results")
print(results[0].title)

# Test chapters
chapters = connector.get_chapters(results[0].id)
print(f"Found {len(chapters)} chapters")

# Test pages
pages = connector.get_pages(chapters[0].id)
print(f"Chapter has {len(pages)} pages")
```

**Step 3: Restart app**

The source will be **automatically discovered** and added to the source selector!

```bash
python app.py

# Output:
# 📚 Loaded 6 sources:
#    ✅ 📖 New Source (newsource)
#    ✅ 🥭 MangaDex (mangadex)
#    ...
```

### Testing

**Manual Testing Checklist:**

```bash
# 1. Source Discovery
python app.py
# ✓ All sources load without errors
# ✓ Active source is set

# 2. Search
# In browser: Search for "naruto"
# ✓ Results appear
# ✓ Cover images load
# ✓ Can switch sources

# 3. Chapters
# Click a manga
# ✓ Chapters load
# ✓ Can select multiple
# ✓ Pagination works (Load More)

# 4. Reader
# Double-click a chapter
# ✓ Pages load in reader
# ✓ Can scroll through pages
# ✓ HD/SD toggle works

# 5. Downloads
# Select chapters, click Download
# ✓ Download starts
# ✓ Console shows progress
# ✓ CBZ files created in static/downloads/

# 6. Library
# Add manga to library
# ✓ Appears in library view
# ✓ Status updates work
# ✓ Progress tracking works

# 7. Rate Limiting
# Rapidly search/browse
# ✓ No 429 errors
# ✓ Sources don't get banned
# ✓ Automatic fallback on rate limit
```

**Unit Testing (Future):**

```python
# tests/test_source_manager.py
def test_fallback():
    manager = SourceManager()
    # Simulate first source failing
    # Assert next source is tried
    ...

# tests/test_rate_limit.py
def test_token_bucket():
    connector = TestConnector()
    # Make burst requests
    # Assert rate limit enforced
    ...
```

---

## Code Conventions

### Python (`app.py`, `sources/*.py`)

**Style:**
- PEP 8 compliant
- 4-space indentation
- 100-character line limit
- Type hints on all function signatures

**Docstrings:**
```python
def function_name(param: type) -> return_type:
    """
    Brief one-line description.

    Detailed explanation of what the function does,
    how it works, and any important notes.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ExceptionType: When this exception occurs
    """
```

**Error Handling:**
```python
# Always use specific exceptions
try:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
except requests.Timeout:
    log("⏳ Request timeout")
    return None
except requests.HTTPError as e:
    log(f"❌ HTTP {e.response.status_code}")
    return None
except Exception as e:
    log(f"❌ Unexpected error: {e}")
    return None
```

**Thread Safety:**
```python
# Use threading.RLock for resources accessed by multiple threads
class ThreadSafeClass:
    def __init__(self):
        self._lock = threading.RLock()
        self._data = {}

    def update(self, key, value):
        with self._lock:  # Automatic acquire/release
            self._data[key] = value
```

**Logging:**
```python
# Use emoji prefixes for log clarity
log("🔍 Searching...")     # Info
log("✅ Success")           # Success
log("⚠️ Warning")          # Warning
log("❌ Error")            # Error
log("📚 Library update")   # Library operation
log("⬇️ Downloading...")   # Download operation
```

### JavaScript (`templates/index.html`)

**Style:**
- ES6+ syntax
- 2-space indentation
- `const` for immutables, `let` for mutables
- Arrow functions preferred
- Template literals for strings

**Naming:**
```javascript
// Constants: UPPER_CASE
const API_BASE_URL = '/api';
const MAX_RESULTS = 100;

// Functions: camelCase
function loadChapters() { }
async function fetchData() { }

// Classes: PascalCase
class SourceManager { }

// Private members: _underscore prefix
const App = {
    _cache: {},
    _csrfToken: null
};
```

**Async/Await Pattern:**
```javascript
// Prefer async/await over .then()
async function fetchManga(id) {
    try {
        const resp = await fetch(`/api/manga/${id}`);

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Request failed');
        }

        const data = await resp.json();
        return data;

    } catch (e) {
        console.error('Failed to fetch manga:', e);
        this.log(`❌ ${e.message}`);
        return null;
    }
}
```

**Security - Always Escape User Input:**
```javascript
// NEVER do this:
element.innerHTML = `<h1>${userInput}</h1>`;  // XSS VULNERABILITY!

// ALWAYS do this:
element.innerHTML = `<h1>${escapeHtml(userInput)}</h1>`;  // Safe

// Or use textContent:
element.textContent = userInput;  // Automatically safe
```

**Event Listeners (not inline onclick):**
```javascript
// ❌ BAD: Inline handlers
<button onclick="doSomething()">Click</button>

// ✅ GOOD: Event listeners
const btn = document.getElementById('my-btn');
btn.addEventListener('click', () => doSomething());

// ✅ EVEN BETTER: Event delegation for dynamic elements
document.querySelector('.chapter-grid').addEventListener('click', (e) => {
    if (e.target.matches('.chapter-item')) {
        this.openChapter(e.target.dataset.id);
    }
});
```

### CSS (`static/css/styles.css`)

**Organization:**
```css
/* 1. CSS Variables */
:root {
    --color-primary: #ff453a;
}

/* 2. Reset & Base */
*, *::before, *::after { }

/* 3. Layout */
.app-container { }

/* 4. Components */
.glass-panel { }
.manga-card { }

/* 5. Utilities */
.hidden { }

/* 6. Media Queries */
@media (max-width: 768px) { }
```

**Naming (BEM-inspired):**
```css
.component { }              /* Block */
.component-element { }      /* Element */
.component--modifier { }    /* Modifier */

/* Examples */
.manga-card { }
.manga-card-cover { }
.manga-card-title { }
.manga-card--selected { }
```

**Mobile-First:**
```css
/* Base styles (mobile) */
.manga-card {
    width: 100%;
}

/* Desktop enhancement */
@media (min-width: 768px) {
    .manga-card {
        width: 50%;
    }
}
```

---

## Security Best Practices

### CSRF Protection

**Backend:**
```python
# Generate token per session
@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)

# Protect POST routes
@app.route('/api/save', methods=['POST'])
@csrf_protect  # <-- Decorator
def save_to_library():
    ...
```

**Frontend:**
```javascript
// Fetch token on app init
await this.fetchCsrfToken();

// Include in all POST requests
async postJson(url, data = {}) {
    return fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': this.csrfToken  // Critical!
        },
        body: JSON.stringify(data)
    });
}
```

### Input Validation

**Backend:**
```python
# Validate required fields
if not manga_id or not title:
    return jsonify({'error': 'Missing required fields'}), 400

# Validate string lengths
if len(str(manga_id)) > 500:
    return jsonify({'error': 'Field too long'}), 400

# Validate enums
valid_statuses = {'reading', 'plan_to_read', 'completed', 'dropped', 'on_hold'}
if status not in valid_statuses:
    return jsonify({'error': 'Invalid status'}), 400

# Validate numeric ranges
page = int(request.args.get('page', 1))
if page < 1 or page > 1000:
    return jsonify({'error': 'Page must be between 1 and 1000'}), 400
```

**Frontend:**
```javascript
// Always escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Sanitize URLs
function sanitizeUrl(url) {
    try {
        const parsed = new URL(url, window.location.origin);
        if (parsed.protocol === 'javascript:' || parsed.protocol === 'data:') {
            return PLACEHOLDER_IMAGE;
        }
        return url;
    } catch {
        return PLACEHOLDER_IMAGE;
    }
}
```

### Image Proxy (CORS Fix)

**Problem:** External manga images often block CORS requests.

**Solution:** Proxy through backend:

```python
@app.route('/api/proxy/image')
def proxy_image():
    """Proxy external images to avoid CORS issues."""
    url = request.args.get('url', '')

    # Validate URL domain (whitelist)
    allowed_domains = [
        'uploads.mangadex.org',
        'mangakakalot.com',
        'fanfox.net',
        # ...
    ]

    # Fetch and return image
    headers = {
        'User-Agent': 'Mozilla/5.0...',
        'Referer': url
    }
    resp = requests.get(url, headers=headers, timeout=10)

    return Response(
        resp.content,
        mimetype=resp.headers.get('Content-Type', 'image/jpeg'),
        headers={'Cache-Control': 'public, max-age=86400'}
    )
```

```javascript
// Usage in frontend
function proxyImageUrl(url) {
    if (!url || url.startsWith('/')) return url;
    return `/api/proxy/image?url=${encodeURIComponent(url)}`;
}

// Apply to all images
<img src="${proxyImageUrl(manga.cover)}" />
```

---

## Common Tasks

### Task 1: Fix a Rate-Limited Source

**Symptoms:**
- Source shows "rate_limited" status
- HTTP 429 errors in logs
- Source unavailable in dropdown

**Solution:**

```python
# Option 1: Increase rate limit in connector
class MangaDexConnector(BaseConnector):
    rate_limit = 1.0  # Decrease from 2.0 to 1.0 req/sec
    rate_limit_burst = 3  # Reduce burst capacity

# Option 2: Add cooldown after 429
def _request(self, url, **kwargs):
    try:
        resp = self.session.get(url, **kwargs)

        if resp.status_code == 429:
            self._status = SourceStatus.RATE_LIMITED
            self._cooldown_until = time.time() + 300  # 5 min cooldown
            raise Exception("Rate limited")

        return resp
    except:
        ...
```

**User Fix:**
1. Click source status button (pulse icon)
2. Click "Reset" button for the source
3. Wait a few minutes before using again

### Task 2: Add Cloudflare Bypass

**Problem:** Some sources use Cloudflare protection.

**Solution:**

```python
# Install cloudscraper
# pip install cloudscraper

from cloudscraper import create_scraper

class CloudflareSourceConnector(BaseConnector):
    requires_cloudflare = True

    def __init__(self):
        super().__init__()
        self.scraper = create_scraper()  # Bypasses Cloudflare

    def _request(self, url, **kwargs):
        """Override to use cloudscraper instead of requests."""
        return self.scraper.get(url, timeout=self.request_timeout, **kwargs)
```

### Task 3: Debug Download Failures

**Common Issues:**

1. **Image URLs Expired:**
```python
# Some sources (MangaDex) have time-limited URLs
# Fetch pages immediately before download
def download_worker(chapters):
    for ch in chapters:
        # ✅ Fetch pages just-in-time
        pages = source.get_pages(ch['id'])

        # ❌ Don't cache pages for long
        # URLs may expire after 15-30 minutes
```

2. **Missing Referer Header:**
```python
# Anti-hotlinking protection
class PageResult:
    url: str
    referer: str = "https://source.com"  # Required!

# In downloader
headers = {'Referer': page.referer}
resp = session.get(page.url, headers=headers)
```

3. **Rate Limiting During Download:**
```python
# Add delays between page downloads
for page in pages:
    download_image(page)
    time.sleep(0.1)  # 100ms delay between pages
```

### Task 4: Update a Source's Domain

**Example:** Manganato changed from `.com` to `.gg`

```python
# sources/mangakakalot.py

class MangakanalotConnector(BaseConnector):
    id = "manganato"
    name = "Manganato"
    base_url = "https://mangakakalot.gg"  # Updated domain

    # Update all URL constructions
    def search(self, query, page=1):
        url = f"{self.base_url}/search/{query}"  # Uses new domain
        ...
```

**Testing:**
```bash
# Restart server
python app.py

# Try searching
# If it works, update README.md and CHANGELOG.md
```

---

## Troubleshooting

### Source Status Indicators

| Status | Icon | Meaning | Solution |
|--------|------|---------|----------|
| `online` | ✅ | Working normally | None needed |
| `rate_limited` | ⏳ | Too many requests | Wait 5-15 min, then reset |
| `cloudflare` | 🛡️ | Blocked by protection | Needs cloudscraper |
| `offline` | ❌ | Site down or broken | Try different source |
| `unknown` | ❓ | Not yet tested | Use to see status |

### Common Errors

**1. UnicodeEncodeError (Windows)**

**Error:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '📚'
```

**Fix:** Already handled in app.py:
```python
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
```

**2. "Invalid CSRF token"**

**Causes:**
- Forgot to fetch CSRF token on init
- Token not included in POST headers
- Session expired

**Fix:**
```javascript
// Ensure token is fetched
await this.fetchCsrfToken();

// Include in POST
headers: {
    'X-CSRF-Token': this.csrfToken  // Critical!
}
```

**3. "Source not found"**

**Causes:**
- Source file has syntax error
- Class doesn't inherit from BaseConnector
- Source directory not on Python path

**Fix:**
```python
# Check source file loads
python -c "from sources.newsource import NewSourceConnector; print('OK')"

# Check inheritance
class NewSourceConnector(BaseConnector):  # Must inherit!
    ...
```

**4. Images Not Loading**

**Causes:**
- CORS blocking
- Missing referer header
- URL expired

**Fix:**
```javascript
// Use image proxy
<img src="${proxyImageUrl(manga.cover)}" />

// Check browser console for errors
// Look for CORS errors or 403 Forbidden
```

**5. Chapters Not Loading**

**Causes:**
- Source rate limited
- Invalid manga ID
- Source changed HTML structure

**Fix:**
```python
# Add debug logging
def get_chapters(self, manga_id, language):
    log(f"🔍 Fetching chapters for {manga_id}")

    resp = self._request(url)
    log(f"✅ Response: {resp.status_code}")
    log(f"📄 HTML length: {len(resp.text)}")

    # Parse and return
    ...
```

---

## Performance Optimization

### Backend

**1. Connection Pooling:**
```python
# Already implemented in SourceManager
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,  # Connection pool size
    pool_maxsize=20,      # Max connections per host
    max_retries=2         # Auto-retry failed requests
)
```

**2. In-Memory Caching:**
```python
class Library:
    def __init__(self):
        self._cache = None  # In-memory cache

    def load(self):
        if self._cache is not None:
            return self._cache.copy()  # Serve from cache

        # Load from disk only once
        self._cache = load_from_disk()
        return self._cache.copy()
```

**3. Async Downloads (Future Enhancement):**
```python
# Currently: Sequential downloads (one at a time)
# Future: Use asyncio for concurrent downloads

import asyncio
import aiohttp

async def download_pages_async(pages):
    async with aiohttp.ClientSession() as session:
        tasks = [download_page(session, page) for page in pages]
        return await asyncio.gather(*tasks)
```

### Frontend

**1. Lazy Loading Images:**
```html
<img src="..." loading="lazy">  <!-- Already implemented -->
```

**2. Pagination:**
```javascript
// Load chapters in batches of 100
const limit = 100;
const offset = this.chapterOffset;

const chapters = await fetchChapters(manga_id, offset, limit);
```

**3. Event Delegation:**
```javascript
// ❌ Bad: Add listener to each card
cards.forEach(card => {
    card.addEventListener('click', ...);
});

// ✅ Good: Single listener on parent
grid.addEventListener('click', (e) => {
    if (e.target.matches('.manga-card')) {
        // Handle click
    }
});
```

---

## Deployment

### Production Checklist

```bash
# 1. Set secret key
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# 2. Disable debug mode
export FLASK_DEBUG=false

# 3. Bind to all interfaces
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000

# 4. Use production WSGI server
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# 5. Enable HTTPS (recommended)
# Use nginx reverse proxy with Let's Encrypt SSL
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name manga.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name manga.example.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/manga.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/manga.example.com/privkey.pem;

    # Proxy to Flask app
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files (optional optimization)
    location /static/ {
        alias /path/to/Manga-Negus/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create volumes for persistent data
VOLUME ["/app/static/downloads", "/app/library.json"]

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

```bash
# Build and run
docker build -t manganegus:v2.3 .
docker run -d -p 5000:5000 -v manga-data:/app/static/downloads manganegus:v2.3
```

---

## Migration Guide

### Upgrading from v2.1 to v2.3

**1. Library Format Change:**

v2.1 library.json:
```json
{
  "manga-uuid": {
    "title": "Manga",
    "status": "reading"
  }
}
```

v2.3 library.json:
```json
{
  "mangadex:manga-uuid": {
    "title": "Manga",
    "source": "mangadex",
    "manga_id": "manga-uuid",
    "status": "reading"
  }
}
```

**Migration script:**
```python
import json

# Load v2.1 library
with open('library.json', 'r') as f:
    old_lib = json.load(f)

# Convert to v2.3 format
new_lib = {}
for manga_id, data in old_lib.items():
    key = f"mangadex:{manga_id}"  # Assume MangaDex
    new_lib[key] = {
        **data,
        "source": "mangadex",
        "manga_id": manga_id
    }

# Save v2.3 library
with open('library.json', 'w') as f:
    json.dump(new_lib, f, indent=4)
```

**2. API Changes:**

| v2.1 Endpoint | v2.3 Endpoint | Changes |
|---------------|---------------|---------|
| `/api/popular` | `/api/popular` | Now supports `?source_id=` param |
| `/api/search` | `/api/search` | Requires CSRF token |
| `/api/chapters` | `/api/chapters` | Now requires `source` field |
| N/A | `/api/sources` | New: List sources |
| N/A | `/api/proxy/image` | New: Image proxy |

**3. Frontend Changes:**

```javascript
// v2.1: Single source
const results = await post('/api/search', {query});

// v2.3: Multi-source with CSRF
const results = await this.postJson('/api/search', {query});
// postJson() includes CSRF token automatically
```

---

## Quick Reference

### Key File Locations

| Purpose | Path |
|---------|------|
| Main server | `app.py` |
| Source manager | `sources/__init__.py` |
| Base connector | `sources/base.py` |
| Frontend | `templates/index.html` |
| Styles | `static/css/styles.css` |
| Library data | `library.json` |
| Downloads | `static/downloads/` |
| Dependencies | `requirements.txt` |

### Important Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `SourceManager.search()` | sources/__init__.py:294 | Search with fallback |
| `BaseConnector._request()` | sources/base.py | Rate-limited HTTP request |
| `Library.add()` | app.py:158 | Add manga to library |
| `Downloader.start()` | app.py:238 | Start background download |
| `App.postJson()` | index.html:287 | POST with CSRF token |
| `escapeHtml()` | index.html:223 | Prevent XSS |

### Rate Limits

| Source | Rate Limit | Burst | Notes |
|--------|------------|-------|-------|
| MangaDex | 2 req/sec | 3 | Conservative (API allows 5) |
| MangaFire | 2.5 req/sec | 5 | Fast and reliable |
| MangaHere | 2 req/sec | 4 | Browser-like headers |
| Manganato | 2 req/sec | 4 | Updated domain (.gg) |
| MangaSee | 1.5 req/sec | 3 | Scraping target |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | Random | Flask session encryption |
| `FLASK_HOST` | `127.0.0.1` | Bind address |
| `FLASK_PORT` | `5000` | Server port |
| `FLASK_DEBUG` | `false` | Debug mode |

---

## AI Assistant Guidelines

### When Analyzing Code

1. **Understand Multi-Source Architecture:**
   - Don't assume single source (v2.1 style)
   - Remember `source` field is required for manga/chapter operations
   - Check source connector implementations, not just manager

2. **Check Thread Safety:**
   - Look for shared state (caches, queues)
   - Verify proper locking (`threading.RLock()`)
   - Consider race conditions in downloads

3. **Validate Security:**
   - Ensure CSRF protection on POST routes
   - Check input validation and sanitization
   - Verify HTML escaping in frontend

### When Modifying Code

1. **Backend (Python):**
   - Add type hints to all functions
   - Use comprehensive docstrings
   - Handle exceptions gracefully (don't crash)
   - Log errors with emoji prefixes
   - Test with multiple sources

2. **Frontend (JavaScript):**
   - Always escape user input (`escapeHtml()`)
   - Include CSRF token in POST requests
   - Use event delegation for dynamic elements
   - Provide loading states for async operations

3. **Source Connectors:**
   - Inherit from `BaseConnector`
   - Implement required methods: `search()`, `get_chapters()`, `get_pages()`
   - Use `self._request()` for rate limiting
   - Return standardized data classes
   - Handle errors gracefully

### When Adding Features

1. **Check Existing Patterns:**
   - How do other sources implement this?
   - Is there a base class method to override?
   - Does it need fallback support?

2. **Consider Multi-Source:**
   - Does this feature work with all sources?
   - Does it need source-specific handling?
   - Should it have automatic fallback?

3. **Test Edge Cases:**
   - What if source is rate-limited?
   - What if manga ID is from different source?
   - What if user switches sources mid-operation?

---

## Resources

### Official Links

- **Repository:** [github.com/bookers1897/Manga-Negus](https://github.com/bookers1897/Manga-Negus)
- **Author:** [@bookers1897](https://github.com/bookers1897)
- **License:** MIT

### External Documentation

- [MangaDex API](https://api.mangadex.org/docs/) - Official API documentation
- [Flask Documentation](https://flask.palletsprojects.com/) - Python web framework
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) - HTML parsing
- [Phosphor Icons](https://phosphoricons.com/) - Icon set used in UI

### Inspiration

- [HakuNeko](https://github.com/manga-download/hakuneko) - Multi-source manga downloader (730+ connectors)
- [Tachiyomi](https://github.com/tachiyomiorg/tachiyomi) - Android manga reader with extensions

---

**Last Updated:** 2025-12-29
**Version:** 2.3
**Branch:** v2.2-source-updates
**For:** AI Assistants (Claude Code)
