# 👑 MangaNegus v2.2 - Multi-Source Edition (2025 Update)

A native manga downloader, library manager, and **in-app reader** for iOS Code App. Now with **5 working sources** and **proper rate limiting** to prevent bans!

![MangaNegus](https://img.shields.io/badge/version-2.2-red)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![Flask](https://img.shields.io/badge/flask-3.0-green)
![Status](https://img.shields.io/badge/status-active-success)

**Author:** [@bookers1897](https://github.com/bookers1897)
**Repository:** [github.com/bookers1897/Manga-Negus](https://github.com/bookers1897/Manga-Negus)

---

## ✨ What's New in v2.2 (December 2025)

### 🔄 Updated Source List
- **5 working manga sources**:
  - 🥭 **MangaDex** - Official API with proper rate limiting
  - 🔥 **MangaFire** - Fast and reliable aggregator
  - 📕 **MangaHere** - Well-established manga site
  - 📙 **Manganato** - Updated to new .gg domain
  - 📗 **MangaSee** - Large library with quality scans
- **Automatic fallback** - If one source fails, tries the next
- **Source selector** - Switch between sources in the UI
- **Health monitoring** - See which sources are online/rate-limited

### 🐛 Bug Fixes
- ✅ **Fixed Windows emoji encoding** - No more UnicodeEncodeError!
- ✅ **Updated Manganato** - Now uses working .gg domain
- ✅ **Removed ComicK** - Service shut down September 2025
- ✅ **Added new working sources** - MangaFire and MangaHere

### 🛡️ Rate Limiting (Prevents Bans!)
- **Token bucket algorithm** per source
- **Conservative defaults** (2 req/sec for MangaDex)
- **Proper User-Agent** identification (no more browser spoofing)
- **429/403 handling** with automatic cooldown
- **No more getting banned!**

### 🏗️ HakuNeko-Inspired Architecture
- **Abstract base connector** class
- **Standardized interface**: search → chapters → pages
- **Easy to add new sources** (just extend BaseConnector)
- **Per-source configuration** (rate limits, headers, etc.)

---

## 📁 Project Structure

```
manga-negus-v2.2/
├── app.py                    # Flask backend server
├── requirements.txt          # Python dependencies
├── library.json              # User's saved manga
├── sources/                  # Multi-source connectors
│   ├── __init__.py           # SourceManager (auto-discovery)
│   ├── base.py               # BaseConnector abstract class
│   ├── mangadex.py           # MangaDex connector
│   ├── mangafire.py          # MangaFire connector (NEW!)
│   ├── mangahere.py          # MangaHere connector (NEW!)
│   ├── mangasee.py           # MangaSee connector
│   └── mangakakalot.py       # Manganato connector (UPDATED)
├── templates/
│   └── index.html            # Main UI template
└── static/
    ├── css/
    │   └── styles.css        # iOS Liquid Glass styling
    ├── images/
    │   └── sharingan.png     # App logo (add your own!)
    └── downloads/            # Downloaded .cbz files
```

---

## 🚀 Installation

### Prerequisites
- **iOS Code App** ([App Store](https://apps.apple.com/us/app/code-app/id1512938504))
- Python 3.8+

### Setup Steps

1. **Clone or download** the project:
   ```bash
   git clone https://github.com/bookers1897/Manga-Negus.git
   cd Manga-Negus
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or manually:
   ```bash
   pip install flask requests beautifulsoup4
   ```

3. **Add your logo** (optional):
   - Place `sharingan.png` in `static/images/`

4. **Run the server:**
   ```bash
   python app.py
   ```

5. **Open in Safari:**
   ```
   http://127.0.0.1:5000
   ```

---

## 📱 Features

### 🔍 Search & Discovery
- Search across multiple sources
- Browse trending/popular manga
- Switch sources with dropdown selector
- Cover art displayed for all results

### 📚 Library Management
- **Currently Reading** - Active manga
- **Plan to Read** - Your backlog
- **Completed** - Finished series
- Reading progress tracking

### 📖 In-App Reader
- **Stream chapters** directly (no download required)
- **Double-click** any chapter to read
- Chapter navigation (prev/next)

### ⬇️ Downloads
- Download individual chapters
- Batch download by range
- Select multiple chapters
- Auto-packaged as .cbz files

### 🎛️ Source Management
- View source health status
- Reset rate-limited sources
- Automatic fallback between sources

---

## 🔧 Adding New Sources

Create a new file in `sources/` (e.g., `sources/newsource.py`):

```python
from sources.base import BaseConnector, MangaResult, ChapterResult, PageResult

class NewSourceConnector(BaseConnector):
    def __init__(self, session):
        super().__init__(session)
        self.id = "newsource"
        self.name = "New Source"
        self.base_url = "https://newsource.com"
        self.icon = "📖"
        self.rate_limit = 2.0  # requests per second
    
    def search(self, query: str, page: int = 1) -> list[MangaResult]:
        # Implement search
        pass
    
    def get_chapters(self, manga_id: str, language: str = "en") -> list[ChapterResult]:
        # Implement chapter fetching
        pass
    
    def get_pages(self, chapter_id: str) -> list[PageResult]:
        # Implement page fetching
        pass
```

The source will be **automatically discovered** on startup!

---

## 🔒 Rate Limiting Details

| Source | Rate Limit | Burst | Notes |
|--------|------------|-------|-------|
| MangaDex | 2 req/sec | 3 | Conservative (API allows 5) |
| MangaFire | 2.5 req/sec | 5 | Fast and reliable |
| MangaHere | 2 req/sec | 4 | Browser-like headers |
| MangaSee | 1.5 req/sec | 3 | Scraping target |
| Manganato | 2 req/sec | 4 | Updated to .gg domain |

The **token bucket algorithm** ensures:
- Requests are spaced properly
- Burst capacity for quick operations
- Automatic recovery after rate limiting
- Random jitter to prevent thundering herd

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sources` | GET | List available sources |
| `/api/sources/active` | GET/POST | Get/set active source |
| `/api/sources/health` | GET | Get source health status |
| `/api/search` | POST | Search for manga |
| `/api/popular` | GET | Get popular manga |
| `/api/chapters` | POST | Get chapters for manga |
| `/api/chapter_pages` | POST | Get page URLs |
| `/api/library` | GET | Get user's library |
| `/api/save` | POST | Add to library |
| `/api/download` | POST | Start download |
| `/api/logs` | GET | Get console messages |

---

## 🗺️ Roadmap

- [ ] **More sources** - MangaPlus, Webtoons, etc.
- [ ] **Offline CBZ reader** - Read downloaded files
- [ ] **Search filters** - Genre, status, year
- [ ] **Chapter read markers** - Visual indicators
- [ ] **Swipe gestures** - Mobile-friendly reading
- [ ] **Image preloading** - Smoother experience
- [ ] **CloudFlare bypass** - For protected sources

---

## 🐛 Troubleshooting

### "Source unavailable" error
- Check source health status (pulse icon)
- Try resetting the source
- Switch to a different source

### Rate limited by MangaDex
- Wait 5-15 minutes for cooldown
- The app will automatically recover
- Use ComicK as fallback in the meantime

### Images not loading
- Some sources require specific headers
- Try a different source
- Check your internet connection

---

## 🤝 Contributing

Contributions welcome! Feel free to:
- Report bugs via GitHub Issues
- Submit feature requests
- Add new source connectors
- Improve existing code

---

## 📄 License

MIT License - feel free to use and modify!

---

## 🙏 Acknowledgments

- [MangaDex](https://mangadex.org/) for the API
- [ComicK](https://comick.io/) for fast CDN
- [HakuNeko](https://github.com/manga-download/hakuneko) for architecture inspiration
- [Phosphor Icons](https://phosphoricons.com/) for the icon set

---

**Made with ❤️ by [@bookers1897](https://github.com/bookers1897)**
