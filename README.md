# MangaNegus v3.0.0-alpha

MangaNegus is a modern, web-based manga downloader and reader inspired by Free Manga Downloader (FMD). It features a glassmorphic UI, multi-source support with automatic fallback, and a Lua-based extension system.

## ✨ Key Features

- **Multi-Source Search**: Search across multiple manga sites simultaneously.
- **Lua Extension System**: Support for FMD Lua modules (590+ sources planned).
- **Advanced Cloudflare Bypass**: Powered by `curl_cffi` and TLS fingerprinting.
- **Smart Fallback**: Automatically tries alternative sources if one is down or rate-limited.
- **Background Downloads**: Download entire series as CBZ files with progress tracking.
- **Metadata Support**: Automatic `ComicInfo.xml` generation for library managers like Kavita/Komga.
- **In-App Reader**: Read your favorite manga directly in the browser.
- **Library Management**: Save manga to your library and track your reading progress.

## 📚 Supported Sources (30+)

- **MangaDex** (API) - Fast and reliable.
- **WeebCentral V2** - High performance with 700+ chapters for popular series.
- **Manganato / Manganelo** - Excellent coverage.
- **MangaFire** - Solid backup with fast CDN.
- **MangaSee / Manga4Life** - Official scanlation quality.
- **Annas Archive** & **LibGen** - Shadow library support for complete volumes.
- ... and many more via the Lua extension system.

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
