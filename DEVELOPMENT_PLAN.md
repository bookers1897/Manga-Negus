# MangaNegus v3.0 - Development Plan

> **Created:** 2025-12-30
> **Status:** In Development
> **Goal:** Transform MangaNegus into an FMD-like manga downloader with 590+ sources

---

## Vision

MangaNegus will be a web-based manga downloader similar to [FMD2](https://github.com/dazedcat19/FMD2) but with:
- Modern web GUI (Flask + Tailwind CSS)
- Python backend with Lua extension system
- 590+ manga sources via FMD's Lua modules
- Search & browse functionality (like MangaDex)
- Direct URL fallback for unsupported sites
- CBZ/ZIP download format

---

## Current State (v2.3)

### What Works
- Flask web application with glassmorphic UI
- 17 native Python source connectors
- MangaDex, ComicK, MangaNato working
- Library management (save, track progress)
- Chapter downloads as CBZ files
- In-app manga reader

### What's Broken
- Gallery-DL adapter (fundamentally flawed architecture)
- Some native sources (rate limited, site changes)
- Only 17 sources vs FMD's 590

---

## Architecture Comparison

| Feature | FMD2 | MangaNegus (Current) | MangaNegus (v3.0) |
|---------|------|---------------------|-------------------|
| Language | Pascal + Lua | Python | Python + Lua |
| Sources | 590 (Lua) | 17 (Python) | 590+ (Lua + Python) |
| Extension | Lua scripts | Python classes | Lua scripts |
| GUI | Desktop (Windows) | Web (Browser) | Web (Browser) |
| Direct URL | Yes | Broken | Yes |

---

## User Workflow (Target)

### Mode 1: Search & Browse (Primary)
```
1. User opens homepage
2. Sees trending/popular manga grid
3. Types "Gachiakuta" in search box
4. Results show: cover art, title, author, summary
5. Clicks manga → sees all chapters
6. Selects chapters → downloads as CBZ
```

### Mode 2: Direct URL (Fallback)
```
1. User pastes: https://mangadex.org/title/xxx/gachiakuta
2. App detects URL, finds matching Lua module
3. Extracts manga info and chapters
4. User downloads selected chapters
```

---

## Technical Architecture (v3.0)

```
┌─────────────────────────────────────────────────────────────┐
│                     Flask Web Server                         │
│                    (templates/index.html)                    │
├─────────────────────────────────────────────────────────────┤
│                    SourceManager (Python)                    │
│  ┌────────────────────┐    ┌────────────────────────────┐   │
│  │  Native Sources    │    │    Lua Runtime (lupa)      │   │
│  │  (Python Classes)  │    │                            │   │
│  │                    │    │  ┌──────────────────────┐  │   │
│  │  • MangaDex.py     │    │  │  lua/modules/        │  │   │
│  │  • ComicK.py       │    │  │  ├─ MangaDex.lua     │  │   │
│  │  • MangaNato.py    │    │  │  ├─ AsuraScans.lua   │  │   │
│  │                    │    │  │  ├─ Toonily.lua      │  │   │
│  │  (17 sources)      │    │  │  └─ ... (590 more)   │  │   │
│  └────────────────────┘    │  └──────────────────────┘  │   │
│                            └────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                  Direct URL Handler                          │
│     (Auto-detect site → Load matching module → Extract)     │
├─────────────────────────────────────────────────────────────┤
│                  Download Manager                            │
│     (Queue, progress, CBZ creation, library storage)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Lua Runtime Foundation (Day 1)
**Status:** ✅ COMPLETE

- [x] Install `lupa` Python-Lua bridge
- [x] Create `LuaSourceAdapter` class
- [x] Create `LuaRuntime` with FMD-compatible API
- [x] Implement HTTP module (GET, POST, Headers)
- [x] Implement XPath/JSON parsing helpers
- [x] Test MangaDex adapter - WORKING!
- [x] Integrate with SourceManager
- [x] Full workflow tested: Search → Chapters → Pages

**Files to create:**
```
sources/
├── lua_runtime.py      # Lua interpreter wrapper
├── lua_adapter.py      # LuaSourceAdapter class
└── lua/
    └── modules/
        └── MangaDex.lua  # First test module
```

### Phase 2: FMD Compatibility Layer (Day 2-3)
**Status:** Pending

- [ ] Port FMD's `base.lua` library
- [ ] Port FMD's `HTTP` module
- [ ] Port FMD's `CreateTXQuery` (XPath parser)
- [ ] Port FMD's `JSON.parse`
- [ ] Implement `GetInfo()`, `GetNameAndLink()`, `GetPageNumber()`

**FMD API Functions to Support:**
| Function | Purpose |
|----------|---------|
| `Init()` | Module initialization |
| `GetNameAndLink()` | Search/browse manga list |
| `GetInfo()` | Manga metadata + chapter list |
| `GetPageNumber()` | Chapter page URLs |
| `BeforeDownloadImage()` | Image pre-processing |

### Phase 3: Search & Browse UI (Day 4-5)
**Status:** Pending

- [ ] Homepage trending/popular grid
- [ ] Search results with cover art, metadata
- [ ] Manga detail page with chapter list
- [ ] Source selector dropdown
- [ ] Loading states and error handling

**UI Mockup:**
```
┌─────────────────────────────────────────────────┐
│  [🔍 Search...]              [Source: All ▼]    │
├─────────────────────────────────────────────────┤
│  🔥 TRENDING                                    │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐       │
│  │cover│ │cover│ │cover│ │cover│ │cover│       │
│  │     │ │     │ │     │ │     │ │     │       │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘       │
│  Title   Title   Title   Title   Title         │
│  Author  Author  Author  Author  Author        │
└─────────────────────────────────────────────────┘
```

### Phase 4: Direct URL Fallback (Day 6)
**Status:** Pending

- [ ] URL pattern matcher (detect site from URL)
- [ ] Auto-load matching Lua module
- [ ] Generic BeautifulSoup scraper for unknown sites
- [ ] User feedback when URL recognized/not recognized

**URL Detection Logic:**
```python
def detect_source(url):
    for module in lua_modules:
        if module.matches_url(url):
            return module
    return GenericScraper()  # Fallback
```

### Phase 5: Port Popular Sources (Week 2)
**Status:** Pending

Priority sources to port from FMD:
1. MangaDex
2. MangaSee
3. AsuraScans
4. Toonily
5. MangaKakalot
6. MangaNato
7. ComicK
8. ReaperScans
9. FlameScans
10. WeebCentral

### Phase 6: GUI Polish (Week 3+)
**Status:** Future

- [ ] Anime-style aesthetic
- [ ] Cover art lazy loading
- [ ] Smooth animations
- [ ] Mobile responsive improvements
- [ ] Dark/Light theme polish
- [ ] Download progress visualization

---

## File Structure (Target)

```
Manga-Negus/
├── app.py                      # Flask server
├── sources/
│   ├── __init__.py             # SourceManager
│   ├── base.py                 # BaseConnector
│   ├── lua_runtime.py          # NEW: Lua interpreter
│   ├── lua_adapter.py          # NEW: LuaSourceAdapter
│   ├── mangadex.py             # Native Python source
│   ├── comick.py               # Native Python source
│   └── lua/
│       ├── libs/
│       │   ├── base.lua        # FMD base library
│       │   ├── http.lua        # HTTP helpers
│       │   └── xpath.lua       # XPath helpers
│       └── modules/
│           ├── MangaDex.lua    # Ported from FMD
│           ├── AsuraScans.lua
│           ├── Toonily.lua
│           └── ... (590 more)
├── templates/
│   └── index.html              # Web UI
├── static/
│   ├── css/styles.css
│   └── downloads/              # CBZ files
├── library.json                # User library
├── DEVELOPMENT_PLAN.md         # This document
└── CLAUDE.md                   # AI guide
```

---

## Dependencies

### Current
- Flask 3.0
- requests
- beautifulsoup4
- lxml

### New for v3.0
- **lupa** (2.6) - Python-Lua bridge

### Optional (Enhanced Features)
- cloudscraper - Cloudflare bypass
- curl_cffi - TLS fingerprint bypass

---

## API Endpoints (No Changes)

The existing Flask API remains the same:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sources` | GET | List available sources |
| `/api/search` | POST | Search manga by title |
| `/api/popular` | GET | Get trending manga |
| `/api/chapters` | POST | Get chapter list |
| `/api/chapter_pages` | POST | Get page URLs |
| `/api/download` | POST | Start download |
| `/api/library` | GET | Get user library |

The SourceManager will route requests to either:
- Native Python sources (existing)
- Lua sources (new, via LuaSourceAdapter)

---

## Migration Path

### From v2.3 to v3.0

1. **Keep all existing code** - nothing deleted
2. **Add Lua runtime** alongside Python sources
3. **Lua sources appear in dropdown** with "(Lua)" suffix
4. **User chooses preferred source** - Python or Lua
5. **Gradual migration** - can remove Python sources later

### Backwards Compatibility

- Existing library.json format unchanged
- Existing downloads preserved
- Existing UI mostly unchanged
- API endpoints unchanged

---

## Success Metrics

### Phase 1 Complete When:
- [ ] Can load MangaDex.lua in Python
- [ ] Can call `GetInfo()` and get manga data
- [ ] Can call `GetPageNumber()` and get image URLs

### Phase 3 Complete When:
- [ ] Homepage shows trending manga with covers
- [ ] Search returns results with metadata
- [ ] Can view chapters and download

### v3.0 Complete When:
- [ ] 50+ Lua sources working
- [ ] Direct URL works for any supported site
- [ ] Full download workflow functional
- [ ] No major bugs

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| FMD Lua modules need adaptation | Create compatibility shims |
| Some sites have Cloudflare | Use cloudscraper/curl_cffi |
| Lua modules may break | Keep Python sources as fallback |
| Performance overhead | Cache Lua modules, optimize HTTP |

---

## Resources

- [FMD2 Repository](https://github.com/dazedcat19/FMD2)
- [FMD2 Lua Modules](https://github.com/dazedcat19/FMD2/tree/master/lua/modules)
- [Lupa Documentation](https://github.com/scoder/lupa)
- [MangaDex API](https://api.mangadex.org/docs/)

---

## Changelog

### 2025-12-30
- Created development plan
- Installed lupa Lua runtime
- Analyzed FMD architecture
- Decided on Python + Lua hybrid approach

---

**Next Step:** Implement `lua_runtime.py` with FMD-compatible HTTP module
