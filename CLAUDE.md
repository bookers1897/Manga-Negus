# CLAUDE.md

**MangaNegus v3.1** - Complete AI Assistant Guide

A comprehensive guide for AI assistants working with MangaNegus, a Flask-based manga aggregator, library manager, and reader.

**Last Updated:** 2026-01-08
**Version:** 3.1.0 (Redesign Edition)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Environment Setup](#environment-setup)
3. [Architecture Deep Dive](#architecture-deep-dive)
4. [Frontend Redesign (v3.1)](#frontend-redesign-v31)
5. [Backend Structure](#backend-structure)
6. [Database Schema](#database-schema)
7. [Source System](#source-system)
8. [Development Workflows](#development-workflows)
9. [Cleanup & File Reorganization](#cleanup--file-reorganization)
10. [Recent Bug Fixes](#recent-bug-fixes)
11. [Troubleshooting](#troubleshooting)

---

## Project Overview

### What is MangaNegus?

MangaNegus is a **multi-source manga aggregator** that allows users to:
- Search and discover manga from 34+ sources
- Build and manage a personal library with PostgreSQL backend
- Download chapters as CBZ files with ComicInfo.xml metadata
- Read manga in a fullscreen reader
- Track reading progress across different sources
- Paste URLs from 18+ sources for instant manga loading

**Target Platform:** iOS Code App (mobile Safari)
**Author:** [@bookers1897](https://github.com/bookers1897)
**Repository:** https://github.com/bookers1897/Manga-Negus

### Technology Stack

**Backend:**
- Flask 3.0.0 (Python web framework with blueprints)
- PostgreSQL + SQLAlchemy ORM (database)
- Alembic (database migrations)
- BeautifulSoup4 (HTML parsing)
- lupa (Lua runtime for FMD modules)
- curl_cffi (Cloudflare bypass with TLS fingerprinting)
- cloudscraper (Alternative CF bypass)

**Frontend:**
- Vanilla JavaScript ES6 Modules (no framework!)
- Lucide Icons (formerly Phosphor)
- CSS3 with modern glassmorphism design
- Modal overlays with blur backgrounds

**Data Storage:**
- PostgreSQL database (library, manga metadata, reading progress)
- File system (CBZ downloads in `static/downloads/`)

### Key Features

1. **34+ Manga Sources:** MangaDex, WeebCentral, MangaNato, MangaSee, Jikan (MyAnimeList), Anna's Archive, LibGen, and more
2. **Hybrid Python + Lua Architecture:** Run 590+ FMD Lua modules alongside native Python connectors
3. **HTMX Bypass:** Special headers for modern dynamic sites using HTMX
4. **Token Bucket Rate Limiting:** Per-source rate limiting prevents IP bans
5. **Automatic Fallback:** Priority-based source routing when sources fail
6. **Modern Glassmorphism UI:** Dark theme with blur effects and smooth animations
7. **CBZ Downloads:** Background threaded downloads with ComicInfo.xml metadata
8. **URL Detection:** Paste manga URLs from 18+ sources to jump directly to manga
9. **Library Management:** PostgreSQL-backed library with status tracking
10. **Fullscreen Reader:** Mobile-friendly manga reader with lazy loading

---

## Environment Setup

### Python Virtual Environment

**Location:** `/home/kingwavy/projects/Manga-Negus/.venv/`

**Activation:**
```bash
source .venv/bin/activate
```

**Python Version:** Python 3.13 (symlinked from `/usr/bin/python`)

**Important:** Always activate the virtual environment before running Flask or installing packages:
```bash
cd /home/kingwavy/projects/Manga-Negus
source .venv/bin/activate
python run.py
```

### Why Virtual Environment is Critical

- **Isolated dependencies:** Prevents conflicts with system Python packages
- **lupa installation:** Lua runtime requires specific compilation flags
- **Arch Linux compatibility:** System has externally-managed Python, venv is required
- **Consistent environment:** All team members and AI assistants use same package versions

### Quick Start Commands

```bash
# Activate venv and start server
cd /home/kingwavy/projects/Manga-Negus
source .venv/bin/activate
python run.py

# Install new packages
source .venv/bin/activate
pip install <package-name>

# Run database migrations
source .venv/bin/activate
alembic upgrade head

# Check installed packages
source .venv/bin/activate
pip list
```

### Storage Modes

- **PostgreSQL (set `DATABASE_URL`):** Durable, concurrent-safe library/metadata; supports Alembic migrations and multi-user access.
- **File fallback (no `DATABASE_URL`):** Uses `library.json`/SQLite; zero setup but single-user oriented and less resilient to concurrent writes.

```bash
# Example .env entry for Postgres
DATABASE_URL=postgresql://user:password@localhost/manganegus
```

### Codex/AI Assistant Note

**If you're having trouble finding the Python environment:**
1. Always look for `.venv/` directory first
2. Use `source .venv/bin/activate` before any Python commands
3. The virtual environment is hidden (starts with dot) - use `ls -la` to see it
4. Never use system Python directly - always activate venv first

---

## Architecture Deep Dive

### Application Flow

```
User Browser
    ↓
[index-redesign.html] - Single Page Application (SPA) with modern UI
    ↓
[static/js/redesign.js] - Main application module
    ↓
[Flask Routes] - API Endpoints via blueprints
    ↓
[SourceManager] - Multi-source orchestration
    ↓
[BaseConnector] - Individual source connectors
    ↓
[PostgreSQL] - Persistent storage
```

### Request Lifecycle Example

**Searching for manga "Naruto":**

1. **User Input:** User types "Naruto" in search box, clicks search button
2. **Frontend (redesign.js):** `performSearch()` calls `API.search('naruto')`
3. **API Module:** Adds CSRF token, sends POST to `/api/search`
4. **Flask Route (manga_api.py):** `/api/search` endpoint receives request
5. **SourceManager:** Tries sources in priority order (WeebCentral V2, MangaDex, etc.)
6. **Source Connector:** Scrapes/API calls specific source for results
7. **Response:** JSON array of manga objects returned to frontend
8. **Frontend Rendering:** `renderMangaGrid()` creates card elements with covers, scores, authors, tags

### Project Structure

```
Manga-Negus/
├── .venv/                      # Python virtual environment (CRITICAL!)
├── run.py                      # Flask entry point
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (DB connection)
├── manganegus.db              # SQLite fallback database
├── library.json               # Legacy file-based library (deprecated)
├── manganegus_app/            # Flask application package
│   ├── __init__.py            # App factory (create_app)
│   ├── extensions.py          # Library, Downloader singletons
│   ├── models.py              # SQLAlchemy models
│   ├── log.py                 # Thread-safe logging
│   ├── csrf.py                # CSRF protection
│   └── routes/                # Flask blueprints
│       ├── main_api.py        # Index, CSRF, image proxy, /redesign route
│       ├── sources_api.py     # Source health, list
│       ├── manga_api.py       # Search, detect_url, popular
│       ├── library_api.py     # Library CRUD, status, progress
│       └── downloads_api.py   # Download, serve CBZ
├── templates/
│   ├── index.html             # Original UI (v3.0)
│   └── index-redesign.html    # New modern UI (v3.1) - TO BE RENAMED
├── static/
│   ├── css/
│   │   ├── styles.css         # Original styles (v3.0)
│   │   └── redesign.css       # New modern styles (v3.1) - TO BE RENAMED
│   ├── js/
│   │   ├── main.js            # Original app coordinator (v3.0)
│   │   ├── api.js             # CSRF-protected API singleton
│   │   ├── state.js           # Reactive state container
│   │   ├── utils.js           # XSS prevention utilities
│   │   ├── sources.js         # Source management
│   │   ├── search.js          # Search, trending, URL detection
│   │   ├── library.js         # Library CRUD operations
│   │   ├── chapters.js        # Chapter loading, downloads
│   │   ├── reader.js          # Fullscreen manga reader
│   │   ├── ui.js              # View management, logging
│   │   └── redesign.js        # New unified module (v3.1) - TO BE RENAMED
│   ├── images/                # Logos, placeholders
│   └── downloads/             # CBZ files (auto-created)
├── sources/
│   ├── __init__.py            # SourceManager (auto-discovery, fallback)
│   ├── base.py                # BaseConnector (rate limiting, logging)
│   ├── webdriver.py           # Selenium helpers
│   ├── lua_runtime.py         # Lua interpreter wrapper
│   ├── lua_adapter.py         # Base Lua adapter
│   ├── weebcentral_lua.py     # HTMX + curl_cffi (1170 chapters!)
│   ├── mangadex.py            # Official API
│   ├── annasarchive.py        # Shadow library
│   ├── libgen.py              # LibGen API
│   └── [30+ other sources]
├── alembic/                   # Database migration scripts
├── alembic.ini                # Alembic configuration
├── claude_md_backup/          # Backup folder for old documentation
└── CLAUDE.md                  # This file!
```

---

## Frontend Redesign (v3.1)

### Overview

The v3.1 redesign is a complete UI overhaul with:
- **Modern glassmorphism design** with dark theme
- **Blur effects** on modals and overlays
- **Smooth animations** with elastic easing
- **Better organization** - unified JavaScript module instead of 10 separate files
- **Enhanced UX** - search button, console modal, source switching sidebar
- **Responsive design** - works on mobile and desktop

### Key Design Changes

**Visual:**
- Dark background (#0a0a0a) with subtle gradient mesh
- Glass panels with backdrop-blur and transparency
- Red accent color (#dc2626) for primary actions
- Lucide icons (cleaner than Phosphor)
- Card-based layout with hover effects

**Functional:**
- **Sidebar Navigation:** 4 sections (Discover, Popular, Library, History)
- **Source Selector:** Top 6 sources in sidebar + "All Sources" modal
- **Search Bar:** Hybrid mode - toggle between title search and URL paste
- **Console Modal:** Popup with blur background showing debug logs
- **Better Cards:** Score badge, author, genre tags, view count

### File Structure (Current)

- **Default UI (redesign):** `templates/index.html`, `static/css/styles.css`, `static/js/main.js`; served at `/` and `/redesign`.
- **Legacy UI (v3.0):** `templates/legacy_v3.0/index.html`, `static/legacy_v3.0/styles.css`, `static/legacy_v3.0/main.js`; served at `/legacy`. Sidebar/modern previews reference the legacy JS.

### Implementation Details

**HTML (`index.html`):**
- Modern semantic structure
- Modal overlays for library status, source status, console logs
- Sidebar with navigation and source selection
- Search bar with mode toggle button
- Clean card grid layouts

**CSS (`styles.css`):**
- CSS custom properties for theming
- Glassmorphism effects (backdrop-filter: blur)
- Smooth transitions with cubic-bezier easing
- Responsive breakpoints for mobile/desktop
- Hover states and animations

**JavaScript (`main.js`):**
- **Critical Fix:** DOM elements initialized in `initElements()` after DOM ready
- Single unified module (easier to maintain than 10 separate files)
- State management object
- API integration with CSRF protection
- Event-driven architecture
- Modal management
- Source switching
- Search mode toggle
- Console logging to modal

---

## Backend Structure

### Flask Blueprints

MangaNegus uses Flask blueprints for modular API organization:

| Blueprint | Prefix | File | Routes |
|-----------|--------|------|--------|
| main_bp | / | main_api.py | Index, CSRF token, image proxy, /redesign |
| sources_bp | /api | sources_api.py | Source health, list sources |
| manga_bp | /api | manga_api.py | Search, detect_url, popular |
| library_bp | /api/library | library_api.py | Library CRUD, status, progress |
| downloads_bp | /api | downloads_api.py | Download, serve CBZ |

### Critical API Endpoints

```python
# Main
GET  /                           # Original UI (v3.0)
GET  /redesign                   # New UI (v3.1)
GET  /api/csrf-token             # Get CSRF token for POST requests
GET  /api/image-proxy            # Proxy images through server (CORS bypass)

# Sources
GET  /api/sources                # List all 34 sources with metadata
GET  /api/sources/health         # Check availability of all sources

# Manga
POST /api/search                 # Search manga by title
POST /api/detect_url             # Detect source from URL (18 patterns)
GET  /api/popular                # Get popular manga from Jikan API
POST /api/chapters               # Get chapters (paginated, 100/page)
POST /api/chapter_pages          # Stream reader pages

# Library (PostgreSQL backend)
GET  /api/library                # Get user's library (returns dict)
POST /api/library/save           # Add manga to library
POST /api/library/update_status  # Update reading status
POST /api/library/update_progress # Update last chapter read
POST /api/library/delete         # Remove from library

# Downloads
POST /api/download               # Background download (threading)
GET  /downloads/<file>           # Serve CBZ files
```

### Database Models (models.py)

```python
class Manga(Base):
    """PostgreSQL model for manga metadata"""
    id = Column(Integer, primary_key=True)
    source_id = Column(String(50))           # e.g., 'mangadex', 'weebcentral-v2'
    source_manga_id = Column(String(500))     # Source's internal ID
    title = Column(String(500))
    cover_url = Column(Text)
    status = Column(String(50))               # 'reading', 'completed', etc.
    last_chapter = Column(String(50))
    added_at = Column(DateTime)

    # Computed key format: "source:manga_id"
    # e.g., "mangadex:abc123", "jikan:13"
```

**Key Format:** Library uses composite keys like `"mangadex:abc-123-def"` or `"jikan:13"`

**Status Values:** `'reading'`, `'completed'`, `'plan_to_read'`, `'on_hold'`, `'dropped'`

---

## Database Schema

### PostgreSQL Setup

**Environment Variable (.env):**
```bash
DATABASE_URL=postgresql://user:password@localhost/manganegus
```

**Migration Commands:**
```bash
source .venv/bin/activate
alembic upgrade head          # Apply all migrations
alembic revision -m "message" # Create new migration
```

### Library Table Structure

```sql
CREATE TABLE manga (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(50) NOT NULL,
    source_manga_id VARCHAR(500) NOT NULL,
    title VARCHAR(500) NOT NULL,
    cover_url TEXT,
    status VARCHAR(50) DEFAULT 'reading',
    last_chapter VARCHAR(50),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, source_manga_id)
);
```

### Query Patterns

**Get library (dictionary format):**
```python
library = {}
mangas = session.query(Manga).all()
for manga in mangas:
    key = f"{manga.source_id}:{manga.source_manga_id}"
    library[key] = {
        'manga_id': manga.source_manga_id,
        'source': manga.source_id,
        'title': manga.title,
        'cover': manga.cover_url,
        'status': manga.status,
        'last_chapter': manga.last_chapter,
        'added_at': manga.added_at.isoformat()
    }
```

**Add to library:**
```python
key = f"{source}:{manga_id}"
manga = Manga(
    source_id=source,
    source_manga_id=str(manga_id),  # MUST convert to string for VARCHAR
    title=title,
    cover_url=cover,
    status=status or 'reading'
)
session.add(manga)
session.commit()
```

---

## Source System

### Multi-Source Architecture

**SourceManager** (`sources/__init__.py`) auto-discovers all source connectors:

```python
# Priority order for fallback
priority_order = [
    "weebcentral-v2",   # HTMX bypass, 1170 chapters for One Piece
    "mangadex",         # Official API, reliable
    "manganato",        # .gg domain
    "mangafire-v2",     # Cloudflare bypass
    "mangasee-v2",      # Updated connector
    "asurascans",       # Fast updates
    # ... 28 more sources
]
```

### Source Categories

**Tier 1 (Official APIs):**
- MangaDex (api.mangadex.org)
- Jikan / MyAnimeList (api.jikan.moe)

**Tier 2 (HTMX Sites):**
- WeebCentral V2 (curl_cffi + HTMX headers)
- MangaFire V2 (playwright-stealth)

**Playwright note:** In restricted environments you can skip Playwright-backed sources (e.g., `mangafire_v2`) by setting `SKIP_PLAYWRIGHT_SOURCES=1` before startup. Otherwise, ensure Chromium sandbox is available.

**Tier 3 (Standard Scraping):**
- MangaNato, MangaSee, AsuraScans, etc. (BeautifulSoup4)

**Tier 4 (Archives):**
- Anna's Archive (shadow library)
- Library Genesis (95TB+ collection)

**Tier 5 (Gallery-DL Wrappers):**
- Dynasty Scans, Imgur, MangaPark, Tapas, Webtoon via gallery-dl

**Tier 6 (Lua Adapters):**
- 590+ FMD Lua modules (experimental)

### Rate Limiting

Each source has token bucket rate limiting:

```python
# base.py
def _wait_for_rate_limit(self):
    elapsed = time.time() - self._last_request
    self._tokens = min(self.rate_limit_burst, self._tokens + elapsed * self.rate_limit)
    if self._tokens < 1.0:
        time.sleep((1.0 - self._tokens) / self.rate_limit)
```

**Example Configuration:**
```python
class MangaDexConnector(BaseConnector):
    rate_limit = 2.0        # 2 requests per second
    rate_limit_burst = 5    # Burst up to 5 requests
    request_timeout = 20    # 20 second timeout
```

### Cloudflare Bypass Strategies

1. **curl_cffi** (Best for HTMX sites)
   ```python
   from curl_cffi import requests as curl_requests
   session = curl_requests.Session()
   response = session.get(url, impersonate="chrome120")
   ```

2. **cloudscraper** (Basic JS challenges)
   ```python
   import cloudscraper
   scraper = cloudscraper.create_scraper()
   html = scraper.get(url).text
   ```

3. **playwright-stealth** (Heavy JS sites)
   ```python
   from playwright.sync_api import sync_playwright
   # Used for MangaFire V2
   ```

---

## Development Workflows

### Starting Development Server

```bash
# Activate virtual environment
cd /home/kingwavy/projects/Manga-Negus
source .venv/bin/activate

# Start Flask development server
python run.py

# Server runs on: http://127.0.0.1:5000
# Redesign UI: http://127.0.0.1:5000/redesign
```

### Testing Sources

```bash
source .venv/bin/activate

# Test specific source
python -c "
from sources import get_source_manager
sm = get_source_manager()
results = sm.get_source('mangadex').search('naruto')
print(f'Found {len(results)} results')
"

# List all sources
python -c "
from sources import get_source_manager
sm = get_source_manager()
print('\n'.join(s.name for s in sm.list_sources()))
"
```

### Adding a New Source

1. Create `sources/newsource.py`:
```python
from .base import BaseConnector, MangaResult, ChapterResult, PageResult

class NewSourceConnector(BaseConnector):
    id = "newsource"
    name = "New Source"
    base_url = "https://newsource.com"
    icon = "🆕"

    # URL detection patterns
    url_patterns = [r'https?://newsource\.com/manga/([a-z0-9-]+)']

    rate_limit = 1.5
    rate_limit_burst = 3

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        # Implement search
        pass

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        # Implement chapter fetching
        pass

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        # Implement page fetching
        pass
```

2. **Auto-discovery:** SourceManager automatically finds it - no registration needed!

### Database Migrations

```bash
source .venv/bin/activate

# Create new migration
alembic revision -m "Add new field to manga table"

# Edit the generated file in alembic/versions/

# Apply migration
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

### Frontend Development

**Redesign UI (v3.1):**
```bash
# Edit files
templates/index-redesign.html
static/css/redesign.css
static/js/redesign.js

# Flask auto-reloads on file changes in debug mode
# Just refresh browser to see changes
```

**Browser Console:**
- Open DevTools (F12)
- Check console for `[DEBUG]` logs showing DOM initialization, API calls, etc.
- Use `console.log('[DEBUG] ...')` for tracing issues

---

## Cleanup & File Reorganization

### Current State (Messy)

The project currently has **duplicate frontend files** due to the redesign process:

**Old UI (v3.0):**
- `templates/index.html` (704 lines - original)
- `static/css/styles.css` (original styles)
- `static/js/*.js` (10 separate modules - main.js, api.js, state.js, etc.)

**New UI (v3.1):**
- `templates/index-redesign.html` (332 lines - modern)
- `static/css/redesign.css` (779 lines - glassmorphism)
- `static/js/redesign.js` (1,200+ lines - unified module)

**Problem:**
- Confusing to have both `index.html` and `index-redesign.html`
- `redesign.css` and `redesign.js` should be the default `styles.css` and `main.js`
- Two different codebases doing the same thing
- Hard for AI assistants to know which files to edit

### Cleanup Plan

**Step 1: Backup Old Files**
```bash
# Create backup directory
mkdir -p static/legacy_v3.0

# Move old frontend files
mv templates/index.html static/legacy_v3.0/
mv static/css/styles.css static/legacy_v3.0/
mv static/js/main.js static/legacy_v3.0/
mv static/js/ui.js static/legacy_v3.0/
# (keep api.js, state.js, utils.js - still useful)
```

**Step 2: Rename Redesign Files to Primary Names**
```bash
# Rename template
mv templates/index-redesign.html templates/index.html

# Rename CSS
mv static/css/redesign.css static/css/styles.css

# Rename JavaScript
mv static/js/redesign.js static/js/main.js
```

**Step 3: Update Route in main_api.py**
```python
# Change from:
@main_bp.route('/redesign')
def redesign():
    return render_template('index-redesign.html')

# To:
@main_bp.route('/')
def index():
    return render_template('index.html')

# Remove old /redesign route
```

**Step 4: Update HTML References**
```html
<!-- In templates/index.html -->
<!-- Change from: -->
<link rel="stylesheet" href="/static/css/redesign.css">
<script type="module" src="/static/js/redesign.js"></script>

<!-- To: -->
<link rel="stylesheet" href="/static/css/styles.css">
<script type="module" src="/static/js/main.js"></script>
```

**Step 5: Clean Up Unused Files**
```bash
# Remove documentation files that are outdated
rm -rf claude_md_backup/  # After confirming new CLAUDE.md is good
rm *.txt  # Old debugging notes
rm *_gemini_solution.md  # Old AI solution attempts
rm *.png  # Screenshots (move to docs/ folder if needed)
```

**Step 6: Organize Documentation**
```bash
# Create docs directory
mkdir -p docs

# Move documentation
mv DEBUGGING_SESSION.md docs/
mv DATABASE_SETUP.md docs/
mv QUICK_START.md docs/
mv architectural_review*.md docs/
mv refactor_report*.md docs/
mv BREAKTHROUGH_NOTES.md docs/

# Keep in root:
# - CLAUDE.md (this file)
# - README.md
# - SETUP_GUIDE.md (if exists)
```

**Step 7: Git Cleanup**
```bash
# Remove untracked files from git
git clean -n  # Preview what will be deleted
git clean -f  # Actually delete untracked files
git clean -fd # Delete untracked files and directories

# Add new structure to git
git add templates/index.html
git add static/css/styles.css
git add static/js/main.js
git commit -m "Reorganize: Redesign files now primary, old files backed up"
```

### After Cleanup Structure

```
Manga-Negus/
├── .venv/                 # Virtual environment
├── manganegus_app/        # Flask app
├── sources/               # Source connectors
├── templates/
│   └── index.html         # Primary UI (was index-redesign.html)
├── static/
│   ├── css/
│   │   └── styles.css     # Primary styles (was redesign.css)
│   ├── js/
│   │   ├── main.js        # Primary app (was redesign.js)
│   │   ├── api.js         # Shared API module
│   │   ├── state.js       # Shared state module
│   │   └── utils.js       # Shared utilities
│   ├── legacy_v3.0/       # Backup of old UI
│   └── downloads/
├── docs/                  # Documentation files
├── alembic/               # Database migrations
├── CLAUDE.md              # This file
└── README.md              # User-facing documentation
```

### Benefits of Cleanup

1. **Clarity:** One UI, one set of files, no confusion
2. **Maintainability:** AI assistants know exactly which files to edit
3. **Performance:** No unused code loaded
4. **Git History:** Clean commits without duplicate files
5. **Onboarding:** New contributors understand structure immediately

---

## Recent Bug Fixes

### Session 2026-01-08: Critical DOM Initialization Bug

**Problem 1: Sources Not Loading in Sidebar**

**Root Cause:** DOM elements were being selected BEFORE the DOM was ready:
```javascript
// BEFORE (BROKEN):
const els = {
    sourceList: document.getElementById('source-list'), // Returns null!
    sidebar: document.getElementById('sidebar'),         // Returns null!
    // ... all elements were null
};
```

**Why This Failed:**
- Script loads and executes `const els = {...}` immediately
- DOM elements don't exist yet (HTML not parsed)
- All `document.getElementById()` calls return `null`
- Later when `renderSources()` runs, `els.sourceList` is still `null`
- Sources fail to render silently

**Solution:**
```javascript
// Initialize as empty object
let els = {};

// New function to populate elements AFTER DOM ready
function initElements() {
    els = {
        sourceList: document.getElementById('source-list'),
        sidebar: document.getElementById('sidebar'),
        // ... now all elements exist and work
    };
}

// Call in init() as first step
async function init() {
    initElements();  // MUST be first!
    // ... rest of initialization
}
```

**Impact:** Fixed sources loading, sidebar toggle, console modal, all DOM interactions

---

**Problem 2: Sidebar Not Collapsing**

**Root Cause:** Same DOM initialization issue - `els.sidebar`, `els.overlay`, `els.menuBtn` were all `null`

**Solution:** Fixed by `initElements()` function above

**Verification:**
```javascript
// Added debug logging
console.log('[DEBUG] toggleSidebar - isOpen:', isOpen);
console.log('[DEBUG] Sidebar opened - classes:', els.sidebar.className);
```

---

**Problem 3: Console Button Did Nothing**

**Root Cause:** Console panel was using wrong HTML structure (simple div instead of modal)

**Solution:**
```html
<!-- BEFORE: -->
<div id="console-panel" class="toast" style="display: none;">...</div>

<!-- AFTER: -->
<div id="console-modal" class="modal-overlay">
    <div class="modal-panel" style="max-width: 700px;">
        <button class="modal-close" id="console-close">
            <i data-lucide="x" width="16"></i>
        </button>
        <h2 class="modal-title">Console Logs</h2>
        <div id="console-content">...</div>
    </div>
</div>
```

**JavaScript Update:**
```javascript
// BEFORE:
els.consolePanel.style.display = isVisible ? 'none' : 'block';

// AFTER:
els.consoleModal.classList.add('active');  // Shows modal with blur
```

---

**Problem 4: No Search Button**

**Solution:** Added search button with arrow icon next to search input
```html
<button id="search-btn" class="icon-btn" style="margin-left: 4px;">
    <i data-lucide="arrow-right" width="20"></i>
</button>
```

```javascript
els.searchBtn.addEventListener('click', () => {
    performSearch();
});
```

---

### Previous Session: Library API Integration

**Problem:** Library using wrong endpoints and payload structure

**Fixes:**
- Changed `/api/save` to `/api/library/save`
- Fixed payload: use `id` not `manga_id`
- Fixed response parsing: dict → array conversion
- Fixed key format: `"source:manga_id"`

---

### v3.0 Bug Fixes (December 2025)

**Tier 1: Critical**
1. NameError in `/api/detect_url` - Missing import
2. Defunct ComicK in priority order - 20-30s timeout on every search
3. Duplicate templates directory

**Tier 2: Major**
4. Circular imports in 13 scrapers - Callback pattern via `source_log()`
5. Open image proxy vulnerability - Domain whitelist
6. Downloader using wrong session - Cloudflare sources failed
7. Inefficient fallback logic - Empty searches triggered full cascade

---

## Troubleshooting

### Common Issues

**Issue: "ModuleNotFoundError: No module named 'dotenv'"**
```bash
# Solution: Activate virtual environment first
source .venv/bin/activate
pip install python-dotenv
```

**Issue: Sources not loading / Sidebar empty**
```bash
# Check browser console (F12)
# Should see: [DEBUG] Elements initialized
#             [DEBUG] Sources loaded: 34
#             [DEBUG] Rendering 34 sources...

# If not, check:
1. Server running? (python run.py)
2. /api/sources returns data? (curl http://localhost:5000/api/sources)
3. JavaScript errors in console?
```

**Issue: Sidebar won't close**
```bash
# Fixed in v3.1 - check browser console for:
# [DEBUG] toggleSidebar - isOpen: true
# [DEBUG] closeSidebar called
# [DEBUG] Sidebar closed - classes: sidebar

# If missing, elements not initialized - reload page
```

**Issue: PostgreSQL connection failed**
```bash
# Check .env file exists:
cat .env | grep DATABASE_URL

# Test connection:
source .venv/bin/activate
python -c "
from sqlalchemy import create_engine
from manganegus_app.models import Base
import os
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))
print('Connection successful!')
"
```

**Issue: Flask server won't start**
```bash
# 1. Check if already running
ps aux | grep python | grep run.py

# 2. Kill existing process
pkill -f "python.*run.py"

# 3. Activate venv and start fresh
source .venv/bin/activate
python run.py

# 4. Check logs
tail -f /tmp/manganegus-server.log
```

**Issue: Rate limiting / IP banned**
```bash
# Sources have automatic rate limiting
# If you hit limits, wait or adjust rate_limit in source connector:

# sources/mangadex.py
class MangaDexConnector(BaseConnector):
    rate_limit = 1.0  # Slower = safer (was 2.0)
```

**Issue: Manga images not loading**
```bash
# Use image proxy to bypass CORS:
# /api/image-proxy?url=<image_url>

# Check if domain is whitelisted in main_api.py:
ALLOWED_DOMAINS = [
    'mangadex.org',
    'weebcentral.com',
    # ... add your domain
]
```

---

## Design Philosophy

### Code Style

**Python:**
- Comprehensive docstrings (Google style)
- Type hints for function parameters
- `except Exception as e:` with logging (never bare `except:`)
- Thread-safe logging via `source_log()`
- PEP 8 compliant

**JavaScript:**
- camelCase for functions/variables
- Async/await pattern (no callbacks)
- Check API responses before use
- Use `textContent` for untrusted data (XSS prevention)
- Single module when possible (v3.1 approach)

**CSS:**
- BEM-inspired naming
- CSS variables for theming
- Mobile-first responsive design
- Smooth transitions with cubic-bezier

### Security Principles

1. **CSRF Protection:** All POST requests require CSRF token
2. **XSS Prevention:** Never use `innerHTML` with user data, use `textContent`
3. **SQL Injection:** SQLAlchemy ORM prevents injection
4. **Open Proxy:** Image proxy has domain whitelist
5. **Rate Limiting:** Prevent IP bans and DoS attacks
6. **Input Validation:** All API endpoints validate required fields

### Performance Optimization

1. **Lazy Loading:** Images load as needed
2. **Pagination:** Chapters load 100 at a time
3. **Token Bucket:** Rate limiting prevents throttling
4. **Session Reuse:** HTTP sessions persist across requests
5. **Background Downloads:** Threading for CBZ generation
6. **Auto-discovery:** No manual source registration

---

## Quick Reference

### File Locations (After Cleanup)

| Purpose | Location |
|---------|----------|
| Server entry | `run.py` |
| Flask app | `manganegus_app/__init__.py` |
| Primary UI | `templates/index.html` |
| Primary CSS | `static/css/styles.css` |
| Primary JS | `static/js/main.js` |
| API routes | `manganegus_app/routes/*.py` |
| Sources | `sources/*.py` |
| Database models | `manganegus_app/models.py` |
| Migrations | `alembic/versions/*.py` |
| Virtual env | `.venv/` |
| Documentation | `CLAUDE.md` (this file) |

### Key Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `create_app()` | manganegus_app/__init__.py | Flask app factory |
| `initElements()` | static/js/main.js | Initialize DOM elements |
| `renderSources()` | static/js/main.js | Display sources in sidebar |
| `toggleSidebar()` | static/js/main.js | Open/close sidebar |
| `performSearch()` | static/js/main.js | Execute search query |
| `loadPopular()` | static/js/main.js | Fetch Jikan popular manga |
| `addToLibrary()` | static/js/main.js | Save manga to PostgreSQL |
| `get_source_manager()` | sources/__init__.py | Get SourceManager singleton |

### Environment Variables

| Key | Value |
|-----|-------|
| DATABASE_URL | `postgresql://user:pass@localhost/manganegus` |
| FLASK_ENV | `development` |
| FLASK_DEBUG | `1` |

### Server Commands

```bash
# Start server
source .venv/bin/activate && python run.py

# Run in background
nohup python run.py > /tmp/server.log 2>&1 &

# Stop server
pkill -f "python.*run.py"

# Check logs
tail -f /tmp/manganegus-server.log

# Database migrations
alembic upgrade head

# Test source
python -c "from sources import get_source_manager; print(get_source_manager().list_sources())"
```

---

**Last Updated:** 2026-01-08
**Version:** 3.1.0 (Redesign Edition)
**Author:** [@bookers1897](https://github.com/bookers1897)
**For:** AI Assistants (Claude Code, Codex, etc.)

**Backup Location:** `claude_md_backup/CLAUDE_v3.0.3_backup.md`

---

## Changes Summary (v3.0.3 → v3.1.0)

**Added:**
- Environment Setup section with virtual environment location
- Frontend Redesign (v3.1) detailed documentation
- Cleanup & File Reorganization section with step-by-step instructions
- Recent Bug Fixes section documenting DOM initialization issue
- DOM element initialization pattern (`initElements()`)
- Console modal implementation
- Search button addition
- Debug logging patterns

**Updated:**
- Project version from v3.0.3 to v3.1.0
- Table of Contents with new sections
- File structure showing redesign files
- Frontend architecture explaining unified module approach
- Technology stack (Lucide icons instead of Phosphor)
- Source count (34 sources instead of 31)

**Fixed:**
- Documentation of critical DOM ready bug
- Sidebar toggle behavior
- Console modal functionality
- Source rendering in sidebar

**Next Steps:**
- Execute cleanup plan (backup old files, rename redesign files)
- Update routes to use new file names
- Test all functionality with renamed files
- Remove old documentation files
- Create docs/ directory for organized documentation
