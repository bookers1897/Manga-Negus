# Changelog

All notable changes to MangaNegus will be documented in this file.

## [v2.2] - 2025-12-03

### 🎉 Added
- **MangaFire connector** - New working source with fast CDN
- **MangaHere connector** - Well-established manga site with broad selection
- **Windows UTF-8 support** - Fixed emoji encoding issues on Windows console
- **Updated source priority** - Optimized fallback order for better reliability

### 🔧 Fixed
- **CRITICAL: Windows UnicodeEncodeError** - Fixed crash on startup due to emoji characters in print statements
- **Manganato domain update** - Updated to new .gg domain (was .com)
- **Removed defunct directory** - Cleaned up malformed `{sources,static` directory

### ❌ Removed
- **ComicK connector** - Service permanently shut down in September 2025

### 📝 Changed
- **Source priority order** - Now: MangaDex → MangaFire → MangaHere → Manganato → MangaSee
- **Manganato base URL** - Changed from manganato.com to mangakakalot.gg
- **README documentation** - Updated to reflect current working sources

### 📊 Current Source Status
| Source | Status | Type | Rate Limit |
|--------|--------|------|------------|
| MangaDex | ✅ Online | API | 2 req/sec |
| MangaFire | ✅ Online | Scraper | 2.5 req/sec |
| MangaHere | ✅ Online | Scraper | 2 req/sec |
| Manganato | ✅ Online | Scraper | 2 req/sec |
| MangaSee | ✅ Online | Scraper | 1.5 req/sec |

---

## [v2.1] - 2024

### Added
- Multi-source architecture with automatic fallback
- Token bucket rate limiting to prevent bans
- Source health monitoring
- Background chapter downloader
- CBZ file packaging
- In-app manga reader

### Sources
- MangaDex (API)
- ComicK (API) - *Later shut down*
- MangaSee (Scraper)
- Manganato (Scraper)

---

## [v1.0] - 2024

### Initial Release
- Basic manga search and download
- MangaDex integration
- Flask web interface
- Library management
