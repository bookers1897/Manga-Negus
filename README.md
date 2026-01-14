# MangaNegus v3.1

A modern, high-performance manga aggregator, reader, and downloader with a beautiful glassmorphic UI. Built with Flask and vanilla JavaScript, featuring multi-source support with intelligent fallback.

**Status:** 🚀 Production Ready (Testing Phase) | **Last Updated:** 2026-01-11

## ✨ Key Features

- **34+ Manga Sources** - Search across MangaDex, WeebCentral, MangaFire, Anna's Archive, and more
- **Intelligent Fallback** - Automatically tries multiple sources until it finds your manga
- **PWA Support** - Install as a progressive web app on mobile and desktop
- **Cloud Sync** - Sync your library across devices
- **Download Queue System** - Queue multiple chapters with pause/resume and progress tracking
- **In-App Reader** - Fullscreen reader with multiple fit modes and keyboard navigation
- **Library Management** - PostgreSQL-backed library with reading progress tracking
- **Theme System** - Dark, Light, OLED, and Sepia themes
- **CBZ Downloads** - Professional CBZ files with ComicInfo.xml metadata
- **URL Detection** - Paste manga URLs from 18+ sources to jump directly to manga
- **Modern UI** - Glassmorphism design optimized for 60fps performance

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+** (Python 3.13 recommended)
- **PostgreSQL** (optional, falls back to SQLite/JSON)
- **Git**

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/bookers1897/Manga-Negus.git
   cd Manga-Negus
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up database (optional):**
   ```bash
   # Create .env file
   echo "DATABASE_URL=postgresql://user:password@localhost/manganegus" > .env

   # Run migrations
   alembic upgrade head
   ```

5. **Run the server:**
   ```bash
   python run.py
   ```

6. **Open in browser:**
   ```
   http://127.0.0.1:5000
   ```

## 📚 Supported Sources

### Working Sources (Verified)
- **WeebCentral V2** ⭐ - 1170+ chapters for popular manga (HTMX + curl_cffi)
- **MangaFreak** - Reliable backup with good coverage
- **MangaDex** - Official API, fast and stable
- **MangaSee V2** - Cloudflare bypass
- **MangaNato V2** - Cloudflare bypass
- **MangaFire** - Solid backup source

### Additional Sources (30+)
AsuraScans, ComicK, ComicX, FlameScans, MangaBuddy, MangaHere, MangaKatana, MangaPark, MangaReader, ReaperScans, TCB Scans, and more via Gallery-DL integration.

### Lua Support (Experimental)
590+ FMD Lua modules supported (MangaDex Lua adapter included).

## 📁 Project Structure

```
Manga-Negus/
├── run.py                     # Flask entry point
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (create this)
├── manganegus_app/            # Flask application
│   ├── __init__.py            # App factory
│   ├── extensions.py          # Library, Downloader singletons
│   ├── models.py              # SQLAlchemy models
│   └── routes/                # API endpoints
│       ├── main_api.py        # Index, CSRF, image proxy
│       ├── manga_api.py       # Search, chapters, popular
│       ├── library_api.py     # Library CRUD
│       └── downloads_api.py   # Download queue
├── sources/                   # Source connectors
│   ├── __init__.py            # SourceManager (auto-discovery)
│   ├── base.py                # BaseConnector
│   ├── mangadex.py            # MangaDex API
│   ├── weebcentral_v2.py      # WeebCentral (curl_cffi)
│   └── [30+ other sources]
├── templates/
│   └── index.html             # Single-page application
├── static/
│   ├── css/
│   │   └── styles.css         # Glassmorphism styles
│   ├── js/
│   │   ├── main.js            # Main application (2777 lines)
│   │   └── legacy_modules/    # Archived modular files
│   ├── images/
│   │   └── sharingan.png      # Logo
│   └── downloads/             # CBZ files (auto-created)
└── alembic/                   # Database migrations
```

## 🎯 Features

### Search & Discovery
- **Multi-source search** - Tries all sources until it finds results
- **URL paste detection** - Paste manga URLs from 18+ sources
- **Trending feed** - Powered by MyAnimeList/Jikan
- **Hidden gems** - Discover lesser-known manga
- **Live search suggestions** - As you type
- **Search history** - Recent searches saved

### Library Management
- **PostgreSQL backend** - Durable, concurrent-safe storage
- **Reading statuses** - Reading, Completed, Plan to Read, On Hold, Dropped
- **Progress tracking** - Last chapter read, page position
- **Continue reading** - Quick resume from last position
- **Library filters** - Filter by status

### Reader
- **Fullscreen mode** - Immersive reading experience
- **Fit modes** - Fit Width, Fit Height, Fit Screen, Original Size
- **Reading modes** - Strip (continuous scroll) or Paged
- **Keyboard navigation** - Arrow keys, Space, Home/End, 1-9 for jumps
- **Auto-save progress** - Remembers your position
- **Next chapter prefetch** - Seamless reading flow

### Download Queue
- **Queue system** - Download multiple manga/chapters
- **Pause/Resume** - Control individual or all downloads
- **Progress tracking** - Real-time chapter/page progress
- **CBZ format** - Compatible with all comic readers
- **ComicInfo.xml** - Metadata for Kavita/Komga/Komelia
- **Background processing** - Non-blocking downloads

### Theme System
- **Dark** - Default OLED-friendly dark theme
- **Light** - Clean light theme for daytime reading
- **OLED** - Pure black for OLED displays
- **Sepia** - Easy on the eyes for long reading sessions

## 🔧 API Endpoints

### Core
- `GET /` - Main application
- `GET /api/csrf-token` - Get CSRF token for POST requests
- `GET /api/sources` - List all 33 sources
- `GET /api/sources/health` - Check source availability

### Manga
- `POST /api/search` - Search manga (auto-fallback)
- `GET /api/popular` - Get popular manga from Jikan
- `POST /api/detect_url` - Detect source from URL
- `POST /api/chapters` - Get chapters (paginated, 100/page)
- `POST /api/chapter_pages` - Stream reader pages

### Library
- `GET /api/library` - Get user's library
- `POST /api/library/save` - Add manga to library
- `POST /api/library/update_status` - Update reading status
- `POST /api/library/update_progress` - Update chapter/page progress
- `POST /api/library/delete` - Remove from library

### Downloads
- `POST /api/download` - Add to download queue
- `GET /api/download/queue` - Get queue status
- `POST /api/download/pause` - Pause downloads
- `POST /api/download/resume` - Resume downloads
- `POST /api/download/cancel` - Cancel download
- `POST /api/download/clear` - Clear completed downloads
- `GET /downloads/<file>` - Serve CBZ files

## 🔨 Development

### Adding a New Source

Create `sources/newsource.py`:

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

The source will be **automatically discovered** on startup!

### Database Migrations

```bash
# Create new migration
alembic revision -m "Add new field"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

### Virtual Environment

**CRITICAL:** Always activate the virtual environment before running:

```bash
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

## ⌨️ Keyboard Shortcuts

### Reader
- `←` / `A` - Previous page
- `→` / `D` / `Space` - Next page
- `Escape` - Close reader
- `F` - Toggle fullscreen/immersive mode
- `M` - Toggle reading mode (strip/paged)
- `Home` - First page
- `End` - Last page
- `1-9` - Jump to 10%-90% through chapter

## 🐛 Troubleshooting

### Chapter Loading Failed (404)
The app now tries multiple sources automatically. If all sources fail:
- The manga might have a different title on other sites
- Try searching for it manually in the search bar
- Check source health in the sidebar

### Downloads Not Working
- Make sure you're using the correct payload format (chapters array)
- Check the download queue modal for errors
- Verify CSRF token is being sent

### Images Not Loading
- Some sources require specific referer headers (now handled automatically)
- Check if the source is blocked in your region
- Try switching to a different source

### Database Issues
- If PostgreSQL fails, the app falls back to SQLite/JSON
- Check your `DATABASE_URL` in `.env`
- Run `alembic upgrade head` to apply migrations

## 📊 Rate Limiting

Each source has token bucket rate limiting to prevent IP bans:

| Source | Rate Limit | Burst | Notes |
|--------|------------|-------|-------|
| WeebCentral V2 | 2.0 req/sec | 5 | curl_cffi + HTMX |
| MangaDex | 2.0 req/sec | 5 | Official API |
| MangaFreak | 1.5 req/sec | 3 | Reliable backup |
| MangaSee V2 | 1.5 req/sec | 3 | Cloudflare bypass |
| MangaFire | 2.5 req/sec | 5 | Fast CDN |

## 🎨 Tech Stack

**Backend:**
- Flask 3.0.0 - Web framework
- SQLAlchemy - ORM for PostgreSQL
- Alembic - Database migrations
- BeautifulSoup4 - HTML parsing
- curl_cffi - Cloudflare bypass with TLS fingerprinting
- cloudscraper - Alternative CF bypass
- lupa - Lua runtime for FMD modules

**Frontend:**
- Vanilla JavaScript ES6 Modules - No framework!
- Lucide Icons - Clean, modern icons
- CSS3 - Glassmorphism with backdrop-filter
- CSS Custom Properties - Theme system

**Storage:**
- PostgreSQL - Primary (library, metadata, progress)
- SQLite/JSON - Fallback mode
- File system - CBZ downloads

## 🆕 Recent Updates (January 2026)

### Performance & Bug Fixes
- ✅ **60fps Scroll Performance** - Optimized GPU usage (50-70% reduction)
- ✅ **Memory Leak Fixes** - Fixed 4 critical memory leaks (pagination, observers, timers)
- ✅ **Scroll Optimization** - Debounced scroll handlers (97% reduction in calls)
- ✅ **Web Worker** - Created background worker for heavy filtering operations
- ✅ **Sidebar Toggle Bug** - Fixed sidebar not closing in fullscreen mode
- ✅ **Accessibility** - Added ARIA labels, WCAG 2.1 Level A compliance

### Security Hardening
- ✅ **Enhanced SSRF Protection** - DNS rebinding prevention, multi-IP validation
- ✅ **Path Traversal Protection** - Comprehensive validation (null bytes, dangerous characters)
- ✅ **Database Optimization** - N+1 query fix (99% reduction: 101 → 1 query)

**Performance Impact:**
- Memory: 15-70 KB saved per interaction cycle
- Database: 95-98% faster library loading (2-5s → 50-100ms)
- FPS: 30-40fps → 60fps during scroll

## 🗺️ Roadmap

### Completed
- [x] Download queue with pause/resume
- [x] Theme system (Dark, Light, OLED, Sepia)
- [x] Reader fit modes and keyboard navigation
- [x] Auto-fallback between sources
- [x] PWA support with offline capabilities
- [x] Cloud sync across devices
- [x] Performance optimization (60fps, memory leaks fixed)
- [x] Security hardening (SSRF, path traversal, N+1 queries)

### Planned
- [ ] Authentication system (Flask-Login)
- [ ] Rate limiting per user/IP
- [ ] Web Worker integration (async filtering)
- [ ] Advanced search filters (genre, status, year)
- [ ] Chapter read markers
- [ ] Swipe gestures for mobile
- [ ] User profiles & social features
- [ ] Automated testing (pytest, Jest)
- [ ] CI/CD pipeline (GitHub Actions)

## 🤝 Contributing

Contributions welcome! Feel free to:
- Report bugs via GitHub Issues
- Submit feature requests
- Add new source connectors
- Improve existing code

## 📄 License

MIT License - feel free to use and modify!

## 🙏 Acknowledgments

- [MangaDex](https://mangadex.org/) for the excellent API
- [Free Manga Downloader](https://github.com/dazedcat19/FMD) for Lua module inspiration
- [Lucide Icons](https://lucide.dev/) for the beautiful icon set
- [HakuNeko](https://github.com/manga-download/hakuneko) for architecture patterns

---

**Made with ❤️ by [@bookers1897](https://github.com/bookers1897)**

**Target Platform:** iOS Code App, Desktop Browsers
**Version:** 3.1.0 (Redesign Edition)
