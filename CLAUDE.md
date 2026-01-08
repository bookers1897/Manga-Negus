# CLAUDE.md

**MangaNegus v3.0.3** - Complete AI Assistant Guide

A comprehensive guide for AI assistants working with MangaNegus, a Flask-based manga aggregator, library manager, and reader.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture Deep Dive](#architecture-deep-dive)
3. [Database Schema](#database-schema)
4. [Backend Structure](#backend-structure)
5. [Frontend Architecture](#frontend-architecture)
6. [Source System](#source-system)
7. [Development Workflows](#development-workflows)
8. [Recent Changes & Bug Fixes](#recent-changes--bug-fixes)
9. [Troubleshooting](#troubleshooting)
10. [Design Philosophy](#design-philosophy)

---

## Project Overview

### What is MangaNegus?

MangaNegus is a **multi-source manga aggregator** that allows users to:
- Search and discover manga from 31+ sources
- Build and manage a personal library
- Download chapters as CBZ files
- Read manga in a fullscreen reader
- Track reading progress across different sources

**Target Platform:** iOS Code App (mobile Safari)
**Author:** [@bookers1897](https://github.com/bookers1897)
**Repository:** https://github.com/bookers1897/Manga-Negus

### Technology Stack

**Backend:**
- Flask 3.0.0 (Python web framework)
- PostgreSQL + SQLAlchemy ORM (database)
- Alembic (database migrations)
- BeautifulSoup4 (HTML parsing)
- lupa (Lua runtime for FMD modules)
- curl_cffi (Cloudflare bypass)
- cloudscraper (Alternative CF bypass)

**Frontend:**
- Vanilla JavaScript ES6 Modules (no framework!)
- Phosphor Icons (icon library)
- CSS3 with Glassmorphism design

**Data Storage:**
- PostgreSQL database (library, manga, reading progress)
- File system (CBZ downloads in `static/downloads/`)

### Key Features

1. **Multi-Source Aggregation:** 31+ manga sources including MangaDex, WeebCentral, MangaNato, Jikan (MyAnimeList)
2. **Hybrid Python + Lua Architecture:** Run 590+ FMD Lua modules alongside native Python connectors
3. **HTMX Bypass:** Special headers for modern dynamic sites using HTMX
4. **Token Bucket Rate Limiting:** Per-source rate limiting prevents IP bans
5. **Automatic Fallback:** Priority-based source routing when sources fail
6. **Glassmorphism UI:** iOS-inspired liquid glass design aesthetic
7. **CBZ Downloads:** Background threaded downloads with ComicInfo.xml metadata
8. **URL Detection:** Paste manga URLs from 18+ sources to jump directly to manga
9. **Library Management:** Track reading status (reading, completed, plan to read, on hold, dropped)
10. **Fullscreen Reader:** Swipe-friendly manga reader for mobile

---

## Architecture Deep Dive

### Application Flow

```
User Browser
    ↓
[index.html] - Single Page Application (SPA)
    ↓
[static/js/*.js] - ES6 Modules
    ↓
[Flask Routes] - API Endpoints
    ↓
[SourceManager] - Multi-source orchestration
    ↓
[BaseConnector] - Individual source connectors
    ↓
[PostgreSQL] - Persistent storage
```

### Request Lifecycle Example

**Searching for manga "Naruto":**

1. **User Input:** User types "Naruto" in search box
2. **Frontend (search.js):** Captures input, calls `api.search('naruto')`
3. **API Module (api.js):** Adds CSRF token, sends POST to `/api/search`
4. **Backend Route (manga_api.py):** Receives request, calls `SourceManager.search_all()`
5. **Source Manager (sources/__init__.py):** Tries sources in priority order:
   - WeebCentral (Lua) → 1170 chapters
   - MangaDex (Python) → Official API
   - Jikan (Python) → MyAnimeList metadata
6. **Connector (sources/weebcentral_lua.py):** Makes HTTP request with HTMX headers
7. **Parser:** Extracts manga data from HTML/JSON response
8. **Response:** Returns list of MangaResult objects
9. **Frontend (search.js):** Renders manga cards in results grid
10. **User Interaction:** User clicks card → triggers `openManga` event → loads chapters

### Design Patterns

**1. Factory Pattern (App Creation)**
```python
# run.py
from manganegus_app import create_app
app = create_app()
```

**2. Singleton Pattern (Shared Instances)**
```python
# manganegus_app/extensions.py
library_manager = LibraryManager()
downloader = Downloader()
```

**3. Observer Pattern (Event-Driven Frontend)**
```javascript
// Dispatch events
window.dispatchEvent(new CustomEvent('openManga', { detail: { manga } }));

// Listen for events
window.addEventListener('openManga', (e) => {
    showMangaDetails(e.detail.manga);
});
```

**4. Strategy Pattern (Source Selection)**
```python
# Different strategies for different sources
class MangaDexConnector(BaseConnector):
    def search(self, query): # API strategy

class WeebCentralConnector(BaseConnector):
    def search(self, query): # HTML scraping strategy
```

**5. Decorator Pattern (Rate Limiting)**
```python
def _request_with_rate_limit(self, func, *args, **kwargs):
    self._wait_for_rate_limit()  # Decorator behavior
    return func(*args, **kwargs)
```

---

## Database Schema

### PostgreSQL Tables

**Table: `manga`**
- Stores metadata about manga titles
- One entry per manga per source

```sql
CREATE TABLE manga (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(50) NOT NULL,           -- e.g., "mangadex", "jikan"
    source_manga_id VARCHAR(255) NOT NULL,    -- ID from source (stored as VARCHAR!)
    title VARCHAR(500) NOT NULL,
    cover_url TEXT,
    description TEXT,
    author VARCHAR(255),
    status VARCHAR(50),                       -- e.g., "ongoing", "completed"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, source_manga_id)
);
```

**Table: `library_entries`**
- User's personal library (which manga they're tracking)
- Links to `manga` table via foreign key

```sql
CREATE TABLE library_entries (
    id SERIAL PRIMARY KEY,
    manga_id INTEGER NOT NULL REFERENCES manga(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'reading',     -- reading, completed, plan_to_read, on_hold, dropped
    last_read_chapter VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Important Database Notes

**⚠️ Critical Type Casting Issue:**

The `source_manga_id` column is **VARCHAR**, but some sources (like Jikan/MyAnimeList) return integer IDs (e.g., `2`, `656`, `13`).

**Always convert to string when querying:**
```python
# CORRECT ✅
manga = session.query(Manga).filter_by(
    source_id='jikan',
    source_manga_id=str(manga_id)  # Convert to string!
).first()

# WRONG ❌ (causes PostgreSQL type error)
manga = session.query(Manga).filter_by(
    source_id='jikan',
    source_manga_id=manga_id  # Integer won't match VARCHAR
).first()
```

**Why VARCHAR instead of INTEGER?**
- Some sources use alphanumeric IDs (e.g., MangaDex: `"801513ba-a712-498c-8f57-cae55b38cc92"`)
- VARCHAR accommodates both formats

### Status Enums

**Reading Status Options:**
- `reading` - Currently reading
- `completed` - Finished reading
- `plan_to_read` - Want to read later
- `on_hold` - Paused temporarily
- `dropped` - Stopped reading

**Implementation:**
- Stored as **inline string enums** in database column definition
- NO separate `ReadingStatus` enum class exists
- Validation happens at application level

```python
# CORRECT ✅
valid_statuses = {'reading', 'completed', 'plan_to_read', 'dropped', 'on_hold'}
reading_status = status if status in valid_statuses else 'reading'

# WRONG ❌ (this class doesn't exist)
from .models import ReadingStatus  # ImportError!
```

---

## Backend Structure

### File Organization

```
manganegus_app/
├── __init__.py          # Flask app factory
├── extensions.py        # Singleton instances (LibraryManager, Downloader)
├── models.py            # SQLAlchemy ORM models (Manga, LibraryEntry)
├── log.py               # Thread-safe logging queue
├── csrf.py              # CSRF token generation
└── routes/
    ├── main_api.py      # Index page, CSRF, image proxy
    ├── sources_api.py   # Source health checks
    ├── manga_api.py     # Search, URL detection, popular manga
    ├── library_api.py   # Library CRUD operations
    └── downloads_api.py # CBZ downloads, file serving
```

### Flask Blueprints

MangaNegus uses **Flask blueprints** to organize routes:

| Blueprint | Prefix | File | Purpose |
|-----------|--------|------|---------|
| `main_bp` | `/` | `main_api.py` | Homepage, CSRF tokens, image proxy |
| `sources_bp` | `/api` | `sources_api.py` | Source status, health checks |
| `manga_bp` | `/api` | `manga_api.py` | Manga search, URL detection |
| `library_bp` | `/api` | `library_api.py` | Library management |
| `downloads_bp` | `/api` | `downloads_api.py` | Chapter downloads |

### Critical API Endpoints

**GET `/`**
- Serves main SPA (index.html)

**GET `/api/csrf-token`**
- Returns CSRF token for POST requests
- Required for all state-changing operations

**POST `/api/search`**
- **Body:** `{ "query": "naruto", "page": 1 }`
- **Returns:** List of manga results
- **Process:** Tries sources in priority order until success

**POST `/api/detect_url`**
- **Body:** `{ "url": "https://mangadex.org/title/..." }`
- **Returns:** `{ "source_id": "mangadex", "manga_id": "...", "source_name": "MangaDex" }`
- **Process:** Matches URL against 18 regex patterns

**GET `/api/library`**
- **Returns:** User's library as `{ "source:id": { manga_data } }` object
- **Format:** Key is `"{source_id}:{manga_id}"`, value is manga object

**POST `/api/save`**
- **Body:** `{ "manga": {...}, "status": "reading" }`
- **Process:** Adds manga to PostgreSQL library
- **Note:** Creates `manga` record if not exists, then `library_entry`

**POST `/api/chapters`**
- **Body:** `{ "manga_id": "...", "source": "mangadex" }`
- **Returns:** Paginated list of chapters (100 per page)

**POST `/api/download`**
- **Body:** `{ "manga_id": "...", "source": "...", "chapters": [...] }`
- **Process:** Starts background thread to download CBZ
- **Returns:** Immediately with download ID

**GET `/downloads/<filename>.cbz`**
- Serves downloaded CBZ file
- Files stored in `static/downloads/`

### LibraryManager (extensions.py)

**Purpose:** Handles all library database operations

**Key Methods:**

```python
def add_to_library(self, manga_data: dict, status: str = 'reading') -> bool:
    """
    Add manga to user's library.

    Args:
        manga_data: Dict with keys: id/manga_id, source, title, cover
        status: One of: reading, completed, plan_to_read, on_hold, dropped

    Returns:
        True if successful, False otherwise

    Process:
        1. Validate status string
        2. Convert manga_id to string (for PostgreSQL)
        3. Check if manga exists in manga table
        4. Create manga record if not exists
        5. Create library_entry record
        6. Fallback to library.json if database fails
    """
```

```python
def get_library(self) -> dict:
    """
    Get user's entire library.

    Returns:
        Dict mapping "source:id" to manga objects

    Example:
        {
            "jikan:13": {
                "title": "One Piece",
                "source": "jikan",
                "manga_id": "13",
                "cover": "https://...",
                "status": "reading",
                "last_chapter": "1050"
            }
        }
    """
```

### Downloader (extensions.py)

**Purpose:** Background CBZ creation with threading

**Key Features:**
- Downloads chapters in separate thread (non-blocking)
- Creates ComicInfo.xml metadata
- Compresses to CBZ format
- Rate limiting per source
- Progress tracking via logs

**Download Process:**
1. User clicks "Download Selected"
2. Frontend sends POST to `/api/download`
3. Backend starts background thread
4. Thread iterates through chapters:
   - Fetch page list for chapter
   - Download each image
   - Save to temp directory
5. Create ComicInfo.xml metadata
6. ZIP all files to CBZ
7. Move CBZ to `static/downloads/`
8. Clean up temp files
9. Log completion

---

## Frontend Architecture

### ES6 Module System

MangaNegus uses **native ES6 modules** (no build step required!):

```html
<!-- index.html -->
<script type="module" src="/static/js/main.js"></script>
```

**Benefits:**
- ✅ No webpack/vite/build tooling needed
- ✅ Native browser support
- ✅ Fast development (edit and refresh)
- ✅ Smaller bundle size (no React/Vue runtime)
- ✅ Works perfectly on iOS Code App

### Module Breakdown

**main.js (172 lines)** - Application Coordinator
```javascript
class MangaNegusApp {
    async init() {
        await api.fetchCsrfToken();      // Get CSRF token
        state.cacheElements();            // Cache DOM references
        this.bindEvents();                // Wire up event listeners
        library.initializeStatusModal();  // Initialize modals
        await sources.loadSources();      // Load source list
        search.loadPopular();             // Load trending manga
    }
}
```

**api.js (173 lines)** - CSRF-Protected API Singleton
```javascript
class API {
    csrfToken = null;

    async fetchCsrfToken() {
        const data = await this.get('/api/csrf-token');
        this.csrfToken = data.token;
    }

    async post(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken  // Required!
            },
            body: JSON.stringify(body)
        });
    }
}
```

**state.js (218 lines)** - Reactive State Container
```javascript
class State {
    currentView = 'search';
    previousView = null;
    selectedSource = '';
    libraryData = null;  // Cached for "Already Added" checks
    elements = {};       // Cached DOM references

    cacheElements() {
        this.elements = {
            searchInput: document.getElementById('search-input'),
            searchBtn: document.getElementById('search-btn'),
            resultsGrid: document.getElementById('results-grid'),
            libraryGrid: document.getElementById('library-grid'),
            // ... 30+ more elements
        };
    }
}
```

**utils.js (88 lines)** - XSS Prevention Utilities
```javascript
// ALWAYS use these when inserting user/API data!

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function sanitizeUrl(url) {
    try {
        const parsed = new URL(url);
        if (!['http:', 'https:'].includes(parsed.protocol)) {
            return '/static/images/placeholder.svg';
        }
        return url;
    } catch {
        return '/static/images/placeholder.svg';
    }
}

// Safe DOM manipulation - ALWAYS use createElement + textContent!
const card = document.createElement('div');
card.textContent = manga.title;  // Auto-escaped, safe!
// NEVER: card.innerHTML = manga.title;  // XSS vulnerability!
```

**sources.js (103 lines)** - Source Management
- Loads available sources from `/api/sources`
- Populates source dropdown
- Shows source health modal
- Handles source switching

**search.js (215 lines)** - Search, Trending, URL Detection
- Handles search form submission
- Loads trending/popular manga
- URL detection (paste manga URL to jump to it)
- Renders search results as cards
- Updates "Already Added" button states

**library.js (129 lines)** - Library CRUD Operations
```javascript
async function loadLibrary(filter = 'all') {
    const lib = await api.getLibrary();
    state.libraryData = lib;  // Cache for button states

    let items = Object.entries(lib);
    if (filter !== 'all') {
        items = items.filter(([k, m]) => m.status === filter);
    }

    // Render cards using safe DOM methods
    items.forEach(([key, manga]) => {
        const card = document.createElement('div');
        card.className = 'manga-card glass-panel';
        // ... build card structure ...
        libraryGrid.appendChild(card);
    });
}
```

**chapters.js (332 lines)** - Chapter Loading, Downloads
- Fetches paginated chapters (100 per page)
- Chapter selection (checkboxes)
- Range downloads (chapters 1-10)
- Selection downloads (selected chapters)
- CBZ download progress tracking

**reader.js (98 lines)** - Fullscreen Manga Reader
- Fullscreen overlay reader
- Lazy image loading
- Swipe navigation (mobile-friendly)
- Page indicators

**ui.js (59 lines)** - View Management, Logging
```javascript
function showView(view) {
    // Remove active from all views
    document.querySelectorAll('.view-panel').forEach(v =>
        v.classList.remove('active')
    );

    // Activate target view
    const targetView = document.getElementById(`${view}-view`);
    targetView.classList.add('active');

    // Trigger special events
    if (view === 'library') {
        window.dispatchEvent(new CustomEvent('loadLibrary'));
    }
}
```

### Event-Driven Communication

Modules communicate via **CustomEvents** (loose coupling):

```javascript
// Module A dispatches event
window.dispatchEvent(new CustomEvent('openManga', {
    detail: { manga: { id: '123', source: 'mangadex', title: 'Naruto' } }
}));

// Module B listens for event
window.addEventListener('openManga', (e) => {
    const { manga } = e.detail;
    showMangaDetails(manga);
});
```

**Key Events:**
- `openManga` - Open manga details view
- `addToLibrary` - Add manga to library
- `openReader` - Open fullscreen reader
- `showView` - Switch between views
- `loadLibrary` - Reload library data
- `log` - Display console message

### DOM Ready Race Condition Fix

**Problem:** ES6 modules load with `defer` attribute, so `DOMContentLoaded` may have already fired before module executes.

**Solution (main.js:169-179):**
```javascript
// Check if DOM is already loaded
if (document.readyState === 'loading') {
    // DOM still loading, wait for event
    document.addEventListener('DOMContentLoaded', () => {
        const app = new MangaNegusApp();
        app.init();
    });
} else {
    // DOM already loaded, initialize immediately
    const app = new MangaNegusApp();
    app.init();
}
```

This **fixes the library display bug** where event listeners weren't being attached.

---

## Source System

### BaseConnector Interface

All source connectors inherit from `BaseConnector`:

```python
class BaseConnector:
    id = "source_id"           # Unique identifier
    name = "Source Name"        # Display name
    base_url = "https://..."    # Base URL
    icon = "🔥"                 # Emoji icon
    url_patterns = []           # Regex patterns for URL detection
    rate_limit = 1.0            # Requests per second
    rate_limit_burst = 3        # Burst capacity
    request_timeout = 15        # Timeout in seconds

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search for manga by title"""

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        """Get chapter list for manga"""

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page URLs for chapter"""
```

### Source Priority Order

Sources are tried in priority order until one succeeds:

```python
priority_order = [
    "lua-weebcentral",  # 1170 chapters (HTMX breakthrough!)
    "mangadex",         # Official API, most reliable
    "jikan",            # MyAnimeList metadata
    "manganato",        # .gg domain
    "mangafire",        # Cloudflare bypass working
    # ... 26 more sources
]
```

### Rate Limiting (Token Bucket Algorithm)

Each source has its own rate limiter:

```python
def _wait_for_rate_limit(self):
    # Calculate elapsed time since last request
    elapsed = time.time() - self._last_request

    # Refill tokens based on elapsed time
    self._tokens = min(
        self.rate_limit_burst,
        self._tokens + elapsed * self.rate_limit
    )

    # Wait if no tokens available
    if self._tokens < 1.0:
        wait_time = (1.0 - self._tokens) / self.rate_limit
        time.sleep(wait_time)
        self._tokens = 0
    else:
        self._tokens -= 1.0

    self._last_request = time.time()
```

**Example:**
- MangaDex: 2.0 req/s, burst 5
- WeebCentral: 1.5 req/s, burst 3
- MangaFire: 2.0 req/s, burst 4

### Cloudflare Bypass Strategies

**1. curl_cffi (Best)**
```python
from curl_cffi import requests as curl_requests

session = curl_requests.Session()
resp = session.get(
    url,
    impersonate="chrome120",  # Mimics Chrome TLS fingerprint
    headers={"HX-Request": "true"},  # HTMX headers
    timeout=20
)
```

**2. cloudscraper (Fallback)**
```python
import cloudscraper

scraper = cloudscraper.create_scraper()
resp = scraper.get(url)
```

**3. Selenium (Last Resort)**
```python
from selenium import webdriver

driver = webdriver.Chrome()
driver.get(url)
html = driver.page_source
```

### HTMX Breakthrough (WeebCentral)

**Discovery (Dec 2025):** WeebCentral migrated from REST to HTMX endpoints.

**Problem:** HTTP 200 OK but empty results
**Root Cause:** Missing HTMX headers
**Solution:**
```python
headers = {
    "HX-Request": "true",
    "HX-Current-URL": f"{self.base_url}/search",
    "HX-Target": "results"
}
```

**Results:** 0 chapters → **1170 chapters** for One Piece!

**Lesson:** Always check DevTools Network tab for actual headers used.

### URL Detection System

Users can paste manga URLs to jump directly to manga:

```python
url_patterns = [
    r'https?://mangadex\.org/title/([a-f0-9-]+)',
    r'https?://.*weebcentral\.com/.*/manga/([a-z0-9-]+)',
    r'https?://.*manganato\.com/manga-([a-z0-9]+)',
    # ... 15 more patterns
]

def extract_id_from_url(self, url: str) -> Optional[str]:
    for pattern in self.url_patterns:
        match = re.search(pattern, url, re.I)
        if match and match.groups():
            return match.group(1)
    return None
```

**Supported Sources:**
MangaDex, WeebCentral, MangaNato, MangaFire, MangaSee, MangaHere, MangaKakalot, MangaFreak, MangaKatana, MangaPark, MangaBuddy, MangaReader, AsuraScans, FlameScans, TCBScans, ReaperScans, Comick, ZeroScans

---

## Development Workflows

### Setup & Installation

```bash
# 1. Clone repository
git clone https://github.com/bookers1897/Manga-Negus.git
cd Manga-Negus

# 2. Create virtual environment (recommended for Arch/externally-managed Python)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up PostgreSQL
sudo systemctl start postgresql
sudo -u postgres psql -c "CREATE DATABASE manganegus;"
sudo -u postgres psql -c "CREATE USER your_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE manganegus TO your_user;"

# 5. Configure environment
cp .env.example .env
# Edit .env and set DATABASE_URL

# 6. Initialize database
alembic upgrade head

# 7. Run development server
python run.py
# or: flask run

# Navigate to http://127.0.0.1:5000
```

### Environment Variables (.env)

```bash
# Database connection
DATABASE_URL=postgresql://user:password@localhost/manganegus

# Flask configuration
FLASK_ENV=development
SECRET_KEY=your-secret-key-here

# Optional: API keys for specific sources
MANGADEX_API_KEY=your-key-here
```

### Database Migrations

```bash
# Create new migration
alembic revision -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# View migration history
alembic history
```

### Testing Sources

```bash
# Test a specific source
python -c "from sources.mangadex import MangaDexConnector; print(MangaDexConnector().search('naruto'))"

# Test WeebCentral Lua adapter
python -c "from sources.weebcentral_lua import WeebCentralLuaAdapter; print(WeebCentralLuaAdapter().search('one piece'))"

# List all sources
python -c "from sources import get_source_manager; [print(s) for s in get_source_manager().list_sources()]"

# Test source health
curl http://127.0.0.1:5000/api/sources/health
```

### Adding a New Python Connector

**1. Create connector file:**
```bash
touch sources/newsource.py
```

**2. Implement BaseConnector:**
```python
from .base import BaseConnector, MangaResult, ChapterResult, PageResult

class NewSourceConnector(BaseConnector):
    id = "newsource"
    name = "New Source"
    base_url = "https://newsource.com"
    icon = "🆕"

    # URL detection patterns
    url_patterns = [r'https?://newsource\.com/manga/([a-z0-9-]+)']

    # Rate limiting
    rate_limit = 1.5
    rate_limit_burst = 3

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        url = f"{self.base_url}/search?q={query}&page={page}"
        html = self._request_html(url)
        soup = BeautifulSoup(html, 'html.parser')

        results = []
        for item in soup.select('.manga-item'):
            try:
                results.append(MangaResult(
                    id=item['data-id'],
                    title=item.select_one('.title').text.strip(),
                    source=self.id,
                    cover_url=item.select_one('img')['src']
                ))
            except Exception as e:
                self.log(f"Parse error: {e}")

        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        # Implement chapter fetching
        pass

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        # Implement page fetching
        pass
```

**3. Auto-discovery:**
No registration needed! `SourceManager` automatically discovers all `BaseConnector` subclasses.

**4. Add to priority order (optional):**
```python
# sources/__init__.py
priority_order = [
    "newsource",  # Add here
    "mangadex",
    # ...
]
```

### Git Workflow

```bash
# Make changes
git add file1.py file2.js

# Commit with descriptive message
git commit -m "Fix library display race condition

- Added document.readyState check in main.js
- Fixed PostgreSQL VARCHAR type casting in extensions.py
- Cleaned up debug logging

🤖 Generated with Claude Code
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Push to GitHub
git push origin main
```

---

## Recent Changes & Bug Fixes

### v3.0.3 (Jan 7, 2026)

**Critical Fixes:**

✅ **Library Display Bug (ES6 Module Race Condition)**
- **Problem:** Library page not displaying, event listeners not attached
- **Root Cause:** `DOMContentLoaded` event fires before ES6 module loads (modules have `defer` attribute)
- **Fix:** Added `document.readyState` check in `main.js:169-179`
- **Files:** `static/js/main.js`

✅ **PostgreSQL Type Casting**
- **Problem:** `operator does not exist: character varying = integer`
- **Root Cause:** `source_manga_id` is VARCHAR but Jikan returns integers
- **Fix:** Added `str(manga_id)` conversion in all database queries
- **Files:** `manganegus_app/extensions.py` (4 methods updated)

✅ **ReadingStatus Import Error**
- **Problem:** `cannot import name 'ReadingStatus' from manganegus_app.models`
- **Root Cause:** No `ReadingStatus` enum class exists (uses inline strings)
- **Fix:** Removed import, use string validation instead
- **Files:** `manganegus_app/extensions.py`

**Features:**
- Library page now displays correctly with portrait cards (160px width)
- "Already Added" state persists across navigation
- MAL/Jikan images load directly without proxy
- Cleaned up debug logging from `library.js` and `ui.js`

### v3.0.2 (Jan 2, 2026)

**Backend Refactoring:**
- ✅ Moved to `manganegus_app/` package structure
- ✅ Flask blueprints for route organization
- ✅ Removed 195 lines of redundant code
- ✅ Fixed Flask static folder path

**Frontend Modularization:**
- ✅ Split 704-line monolithic `index.html` into 10 ES6 modules (1,553 lines)
- ✅ XSS prevention with safe DOM methods
- ✅ Event-driven architecture (CustomEvents)
- ✅ All 31 sources working

### v3.0.1 (Dec 31, 2025)

**Critical Bug Fixes:**
1. ✅ NameError in `/api/detect_url` (import issue)
2. ✅ Defunct ComicK removed (20-30s timeout fix)
3. ✅ Duplicate templates directory removed
4. ✅ Circular import fix (13 scrapers) via callback pattern
5. ✅ Open image proxy vulnerability (domain whitelist)
6. ✅ Downloader session fix (Cloudflare sources)
7. ✅ Inefficient fallback logic (empty vs. None)

**New Features:**
- URL detection system (18 sources)
- LibGen connector (95TB+ comics)
- Anna's Archive connector (shadow library)
- ComicX connector

---

## Troubleshooting

### Library Page Not Loading

**Symptom:** Blank library page, no manga cards
**Diagnosis:**
```javascript
// Check browser console (F12)
// Should see:
// 🎯 showView() called with: library
// 📚 Dispatching loadLibrary event
// If missing, event listeners not attached
```

**Solution:** Ensure `main.js` has `document.readyState` check (v3.0.3 fix)

### Database Connection Errors

**Symptom:** `psycopg2.OperationalError: could not connect`
**Solution:**
```bash
# 1. Check PostgreSQL is running
sudo systemctl status postgresql

# 2. Verify database exists
sudo -u postgres psql -l | grep manganegus

# 3. Test connection
sudo -u postgres psql manganegus -c "SELECT 1;"

# 4. Check .env file
cat .env | grep DATABASE_URL
```

### Source Returning Empty Results (HTTP 200)

**Symptom:** Source responds with 200 OK but no manga found
**Diagnosis:**
1. Check if site uses HTMX (look for `hx-*` attributes in HTML)
2. Inspect DevTools Network tab for actual headers
3. Check for Cloudflare challenge page

**Solution:**
```python
# Add HTMX headers
headers = {
    "HX-Request": "true",
    "HX-Current-URL": f"{self.base_url}/search"
}

# Use curl_cffi for Cloudflare
from curl_cffi import requests
resp = requests.get(url, headers=headers, impersonate="chrome120")
```

### Rate Limiting (HTTP 429)

**Symptom:** Source returns "Too Many Requests"
**Solution:**
```python
# Adjust rate limit in connector
rate_limit = 0.5  # Slow down to 0.5 req/s
rate_limit_burst = 2  # Reduce burst capacity
```

### CBZ Downloads Failing

**Symptom:** Download starts but CBZ file not created
**Diagnosis:**
```bash
# Check logs in console panel
# Look for errors like:
# ❌ Failed to download page: timeout
# ❌ Failed to create CBZ: permission denied

# Check disk space
df -h

# Check static/downloads/ permissions
ls -la static/downloads/
```

**Solution:**
```bash
# Create downloads directory if missing
mkdir -p static/downloads/
chmod 755 static/downloads/

# Increase timeout for slow sources
request_timeout = 30  # in connector
```

### "Already Added" Button Not Updating

**Symptom:** After adding to library, button still shows "+ Add"
**Solution:** Ensure `state.libraryData` is cached when loading library:

```javascript
// library.js
export async function loadLibrary() {
    const lib = await api.getLibrary();
    state.libraryData = lib;  // CRITICAL: Cache for button states
    // ... render cards
}
```

---

## Design Philosophy

### Why Vanilla JavaScript?

**Decision:** Use vanilla JS instead of React/Vue/Angular

**Reasons:**
1. **No Build Step:** Edit and refresh, instant feedback
2. **Smaller Bundle:** No framework runtime (~100KB+ saved)
3. **Better Performance:** No virtual DOM overhead
4. **iOS Code App Compatible:** No build tooling required
5. **Educational:** Pure web standards, easier to understand
6. **Maintainability:** Less dependency churn

**When React Would Make Sense:**
- Large team collaboration
- Complex nested component hierarchies
- Need React ecosystem (Next.js, etc.)
- Shared component library across multiple apps

**For MangaNegus:**
- ✅ Solo developer
- ✅ Simple component hierarchy (views → cards)
- ✅ State management handled by simple object
- ✅ Event-driven communication works great

**Conclusion:** Vanilla JS is the right choice for this project.

### Why PostgreSQL Over JSON?

**Migration:** v3.0+ moved from `library.json` to PostgreSQL

**Benefits:**
1. **Data Integrity:** Foreign key constraints, transactions
2. **Query Performance:** Indexed searches, complex filters
3. **Concurrent Access:** Multiple users (future-proofing)
4. **Relationships:** Join manga and library data efficiently
5. **Migrations:** Schema changes with Alembic

**JSON Fallback:**
- Extensions.py still includes `library.json` fallback
- If PostgreSQL connection fails, uses JSON
- Graceful degradation

### Glassmorphism Design

**Aesthetic:** iOS-inspired liquid glass with blur effects

**Key Principles:**
1. **Blur + Transparency:** `backdrop-filter: blur(40px)` + `rgba()`
2. **Subtle Borders:** `0.5px solid rgba(255, 255, 255, 0.12)`
3. **Ambient Glow:** Animated radial gradients in background
4. **Red Accent:** `#ff453a` for interactive elements
5. **Dark Theme:** Dark glass panels on near-black background

**Implementation:**
```css
.glass-panel {
    background: rgba(28, 28, 30, 0.72);
    backdrop-filter: blur(40px) saturate(180%);
    -webkit-backdrop-filter: blur(40px) saturate(180%);
    border: 0.5px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
```

**Mobile-First:** Optimized for iOS Safari, touch-friendly

---

## Quick Reference

### File Locations

| Purpose | Path |
|---------|------|
| Main entry | `run.py` |
| App factory | `manganegus_app/__init__.py` |
| Database models | `manganegus_app/models.py` |
| Library manager | `manganegus_app/extensions.py` |
| API routes | `manganegus_app/routes/*.py` |
| Frontend SPA | `templates/index.html` |
| JavaScript modules | `static/js/*.js` |
| Stylesheets | `static/css/styles.css` |
| Source connectors | `sources/*.py` |
| Downloads | `static/downloads/*.cbz` |
| Database migrations | `alembic/versions/*.py` |

### Key Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `create_app()` | `manganegus_app/__init__.py:15` | Flask app factory |
| `get_source_manager()` | `sources/__init__.py:200` | Get SourceManager singleton |
| `search_all()` | `sources/__init__.py:150` | Multi-source search |
| `add_to_library()` | `manganegus_app/extensions.py:95` | Add manga to library |
| `get_library()` | `manganegus_app/extensions.py:180` | Get user's library |
| `download_worker()` | `manganegus_app/extensions.py:400` | Background CBZ download |
| `showView()` | `static/js/ui.js:11` | Switch between views |
| `loadLibrary()` | `static/js/library.js:10` | Load library cards |
| `search()` | `static/js/search.js:80` | Search manga |
| `showMangaDetails()` | `static/js/chapters.js:30` | Show manga details |

### Environment

| Key | Value |
|-----|-------|
| Python | 3.8+ |
| Flask | 3.0.0 |
| PostgreSQL | 12+ |
| Database | `manganegus` |
| Platform | iOS Code App (Safari) |
| Sources | 31+ (Python + Lua) |
| Bypass | curl_cffi, cloudscraper |

---

## Support & Resources

**Official:**
- Repository: [github.com/bookers1897/Manga-Negus](https://github.com/bookers1897/Manga-Negus)
- Author: [@bookers1897](https://github.com/bookers1897)
- License: MIT

**External Documentation:**
- [MangaDex API](https://api.mangadex.org/docs/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [Alembic Migrations](https://alembic.sqlalchemy.org/)
- [HTMX](https://htmx.org/)
- [curl_cffi](https://github.com/yifeikong/curl_cffi)
- [lupa (Lua)](https://github.com/scoder/lupa)
- [FMD Lua Modules](https://github.com/dazedcat19/FMD)

**Debugging:**
1. Browser console (F12)
2. Flask server console
3. Built-in console panel (bottom drawer)
4. Network tab (DevTools)
5. PostgreSQL logs: `sudo journalctl -u postgresql`

**Common Fixes:**
- Empty results (200 OK) → Check for HTMX endpoints
- 403 Forbidden → Use `curl_cffi` with `impersonate="chrome120"`
- Rate limiting → Adjust `rate_limit` in connector
- Lua errors → Ensure `.venv` activated, lupa installed
- Library not loading → Check `document.readyState` in main.js
- Database errors → Convert `manga_id` to string in queries

---

**Last Updated:** 2026-01-07
**Version:** 3.0.3 (Library Display Fix + PostgreSQL Integration)
**For:** AI Assistants (Claude, GPT-4, etc.)

**Critical Knowledge for AI Assistants:**

1. **Always convert `manga_id` to string** when querying PostgreSQL
2. **No `ReadingStatus` enum class exists** - use string validation
3. **ES6 modules require `document.readyState` check** to avoid race conditions
4. **Use `createElement` + `textContent`** for XSS prevention (never `innerHTML`)
5. **HTMX sites need special headers** (`HX-Request: true`)
6. **Cloudflare bypass with `curl_cffi`** using `impersonate="chrome120"`
7. **Event-driven frontend** - dispatch CustomEvents for cross-module communication
8. **Rate limiting is per-source** - adjust in individual connectors
9. **PostgreSQL with JSON fallback** - graceful degradation
10. **Original design at `/`** - preview routes at `/modern` and `/sidebar`

This document contains everything needed to understand, maintain, and extend MangaNegus. Happy coding! 🚀
