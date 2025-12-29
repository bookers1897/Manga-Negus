# CLAUDE.md - MangaNegus v2.1

> AI Assistant Guide for MangaNegus Codebase

## Project Overview

**MangaNegus** is a native manga downloader, library manager, and in-app reader for iOS Code App. It's a Flask-based web application that interfaces with the MangaDex API to search, browse, read, and download manga chapters as CBZ files.

**Target Platform:** iOS Code App (mobile Safari)
**Current Version:** 2.1
**Author:** [@bookers1897](https://github.com/bookers1897)
**Primary Language:** Python (Flask backend) + Vanilla JavaScript (frontend)

---

## Architecture Overview

### Technology Stack

- **Backend:** Flask 3.0 (Python 3.8+)
- **Frontend:** Vanilla JavaScript + Tailwind CSS (CDN)
- **Icons:** Phosphor Icons
- **Data Storage:** JSON file (`library.json`)
- **External API:** MangaDex API v5
- **File Format:** CBZ (Comic Book ZIP) for downloads

### Key Design Patterns

1. **Single-Page Application (SPA):** View switching via JavaScript without page reloads
2. **Glassmorphism UI:** iOS-inspired liquid glass design with backdrop-filter effects
3. **RESTful API:** Flask routes serve JSON data to frontend
4. **Thread-Safe Logging:** Queue-based logging for real-time console updates
5. **Background Downloads:** Threading for non-blocking chapter downloads

---

## Project Structure

```
Manga-Negus/
├── app.py                      # Flask backend server (1029 lines)
├── library.json                # User's manga library (JSON database)
├── README.md                   # User-facing documentation
├── CLAUDE.md                   # This file - AI assistant guide
├── templates/
│   └── index.html              # Main SPA template (1373 lines)
├── static/
│   ├── css/
│   │   └── styles.css          # All application styles (fully commented)
│   ├── images/
│   │   └── sharingan.png       # App logo (customizable)
│   └── downloads/              # Downloaded CBZ files (auto-created)
└── archives/
    └── Index-v1.html           # V1 backup (deprecated)
```

---

## Core Application Files

### 1. `app.py` - Backend Server

**Purpose:** Flask application handling all server-side logic.

**Key Components:**

- **MangaLogic Class** (lines 77-731): Core manga operations
  - Library management (save, load, delete, update status/progress)
  - MangaDex API communication (search, popular, chapters, pages)
  - Cover art URL construction
  - Chapter downloading (background worker)
  - Downloaded chapter tracking

- **Flask Routes** (lines 741-1007):
  ```python
  # Library
  GET  /api/library              # Get user's library
  POST /api/save                 # Add manga to library
  POST /api/update_status        # Update reading status
  POST /api/update_progress      # Save last read chapter
  POST /api/delete               # Remove from library

  # Discovery
  GET  /api/popular              # Get trending manga
  POST /api/search               # Search by title

  # Chapters
  POST /api/chapters             # Get chapters (paginated)
  POST /api/all_chapters         # Get all chapters (for downloads)
  POST /api/downloaded_chapters  # Get locally downloaded chapters

  # Reader
  POST /api/chapter_pages        # Get page URLs for streaming reader

  # Downloads
  POST /api/download             # Start background download
  GET  /downloads/<filename>     # Serve CBZ files

  # Logging
  GET  /api/logs                 # Poll for console messages
  ```

**Important Constants:**
- `BASE_URL = "https://api.mangadex.org"` - MangaDex API endpoint
- `DOWNLOAD_DIR` - Static downloads folder
- `LIBRARY_FILE` - JSON database location
- `msg_queue` - Thread-safe message queue for logging

**API Communication Notes:**
- Uses `requests.Session()` with User-Agent header
- Implements retry logic for rate limiting (HTTP 429)
- Timeout set to 15-20 seconds for reliability
- Cover art cached to reduce API calls

### 2. `templates/index.html` - Frontend SPA

**Purpose:** Single-page application with all UI and client-side logic.

**Structure:**
- **Lines 1-428:** HTML markup
- **Lines 429-1370:** Embedded JavaScript

**Views (View Panels):**
1. `view-search` - Search & trending manga
2. `view-library` - User's saved manga (reading/plan_to_read/completed)
3. `view-details` - Manga details + chapter list

**Key JavaScript State Variables:**
```javascript
currentManga        // Currently viewed manga {id, title, cover}
currentChapters     // Loaded chapters array
selectedIndices     // Set of selected chapter indices
isAscending         // Chapter sort order
nextOffset          // Pagination offset
downloadedChapters  // List of downloaded chapter numbers
readerChapters      // Chapters available in reader
currentChapterIndex // Active chapter in reader
useDataSaver        // HD/SD quality toggle
previousView        // For back navigation
```

**Critical Functions:**
- `openManga(id, title, cover)` - Load manga details view
- `loadChapters()` - Fetch chapters with pagination
- `downloadRange()` / `downloadSelection()` - Initiate downloads
- `openReader(chapterIndex)` - Open fullscreen manga reader
- `toggleTheme()` - Dark/light mode switch
- `refreshLogs()` - Poll server for console logs (2s interval)

### 3. `static/css/styles.css` - Stylesheet

**Design System:**

**CSS Variables (Theme):**
```css
/* Dark Theme (Default) */
--bg-primary: rgba(28, 28, 30, 0.72);     # Glass panels
--bg-secondary: rgba(44, 44, 46, 0.65);   # Secondary surfaces
--accent-color: #ff453a;                  # Red accent (manga theme)
--text-primary: #ffffff;                  # Main text
--text-secondary: rgba(235, 235, 245, 0.6); # Dimmed text

/* Light Theme */
[data-theme="light"] {
  --bg-primary: rgba(255, 255, 255, 0.72);
  --accent-color: #007aff;                # Blue accent
  --text-primary: #1c1c1e;
}
```

**Key Component Classes:**
- `.glass-panel` - Glassmorphic surfaces with backdrop-filter
- `.glass-btn` / `.glass-btn-accent` - Button styles
- `.manga-card` - Search result cards
- `.chapter-item` - Chapter grid items
- `.reader-container` - Fullscreen reader overlay
- `.console-panel` - Resizable console

**Animations:**
- Ambient gradient background (30s loop)
- Smooth view transitions (0.3s cubic-bezier)
- Hover/click feedback on interactive elements

### 4. `library.json` - Data Storage

**Schema:**
```json
{
  "manga_id_uuid": {
    "title": "Manga Title",
    "status": "reading" | "plan_to_read" | "completed",
    "cover": "https://...",
    "last_chapter": "123.5"
  }
}
```

**Persistence:**
- Automatically created on first save
- Written synchronously on every update
- Backwards compatible (missing fields auto-filled)

---

## Development Workflows

### Running the Application

```bash
# Install dependencies
pip install flask==3.0.0 requests markupsafe==2.1.3 werkzeug==3.0.1

# Run server
python app.py

# Access at
# http://127.0.0.1:5000
```

**Server Configuration:**
- Host: `0.0.0.0` (network accessible)
- Port: `5000`
- Debug: `True` (with reloader disabled)

### Common Development Tasks

#### 1. Adding a New API Endpoint

```python
# In app.py
@app.route('/api/new_endpoint', methods=['POST'])
def new_endpoint():
    data = request.json
    # Your logic here
    return jsonify({'status': 'ok', 'data': result})
```

#### 2. Adding a New View Panel

```html
<!-- In index.html -->
<div id="view-newview" class="view-panel">
  <!-- Your content -->
</div>
```

```javascript
// Switch to view
showView('newview');
```

#### 3. Customizing the UI

**Logo:**
- Replace `static/images/sharingan.png`
- Fallback icon shows if missing

**App Title:**
```html
<!-- Line 127 in index.html -->
<h1 class="app-title">漫画キング</h1>
```

**Accent Color:**
```css
/* In styles.css */
:root {
  --accent-color: #ff453a;  /* Change this */
}
```

**Background Animation:**
```css
/* In styles.css - search for .ambient-bg */
background: linear-gradient(...);
```

---

## Code Conventions & Best Practices

### Python (app.py)

1. **Docstrings:** Every function has comprehensive docstrings
   ```python
   def function_name(param):
       """
       Brief description.

       Detailed explanation of what the function does.

       Args:
           param (type): Description

       Returns:
           type: Description
       """
   ```

2. **Error Handling:**
   - Use try/except blocks for API calls
   - Return empty arrays/dicts on failure (don't crash)
   - Log errors to console via `log()` function

3. **Thread Safety:**
   - Use `queue.Queue()` for cross-thread communication
   - Run downloads in separate threads (`threading.Thread`)

4. **API Rate Limiting:**
   - Implement retry logic (max 3 attempts)
   - Sleep between requests (0.2-2s)
   - Handle HTTP 429 explicitly

### JavaScript (index.html)

1. **Naming Conventions:**
   - Functions: `camelCase` (e.g., `loadChapters()`)
   - Variables: `camelCase` (e.g., `currentManga`)
   - Constants: Uppercase (e.g., already defined in Python)

2. **Async/Await Pattern:**
   ```javascript
   async function fetchData() {
       const data = await post('/api/endpoint', {param: value});
       if (data) {
           // Handle success
       }
   }
   ```

3. **Error Handling:**
   - Always check if API response exists
   - Show user-friendly messages (alerts/empty states)
   - Log to console for debugging

4. **DOM Manipulation:**
   - Use `innerHTML` for batch updates
   - Use event listeners for dynamic elements
   - Avoid inline onclick for complex logic

### CSS (styles.css)

1. **Organization:**
   - Grouped by component (see Table of Contents)
   - CSS variables for theming
   - Mobile-first approach

2. **Naming:**
   - BEM-inspired: `component-element-modifier`
   - Example: `manga-card`, `manga-card-cover`, `manga-card-title`

3. **Responsive Design:**
   - Use media queries (`@media (max-width: 768px)`)
   - Test on mobile (target: iPhone viewport)
   - Use `rem` for scalable sizing

---

## MangaDex API Integration

### Base URL
```
https://api.mangadex.org
```

### Common Endpoints Used

**Search Manga:**
```
GET /manga?title={query}&limit=15&includes[]=cover_art
```

**Get Chapters:**
```
GET /chapter?manga={manga_id}&translatedLanguage[]=en&limit=100&offset={offset}
```

**Get Chapter Pages:**
```
GET /at-home/server/{chapter_id}
```

**Response Format:**
```json
{
  "data": [...],
  "total": 123,
  "limit": 100,
  "offset": 0
}
```

### Cover Art URLs
```
https://uploads.mangadex.org/covers/{manga_id}/{filename}.256.jpg
```

### Rate Limiting
- Be respectful to MangaDex servers
- Implement delays between requests
- Handle HTTP 429 (Too Many Requests)
- Use persistent session with proper User-Agent

---

## State Management

### Frontend State Flow

```
User Action
    ↓
JavaScript Function
    ↓
API Call (POST/GET)
    ↓
Flask Route
    ↓
MangaLogic Method
    ↓
MangaDex API / library.json
    ↓
Return JSON Response
    ↓
Update Frontend State
    ↓
Re-render UI
```

### Data Persistence

**Session Data (JavaScript variables):**
- Lost on page reload
- Stored in memory during session
- Examples: `currentManga`, `selectedIndices`

**LocalStorage:**
- Theme preference (`theme`)
- Persists across sessions

**Server-Side (library.json):**
- Manga library
- Reading status
- Last read chapter
- Persists permanently

---

## Testing & Debugging

### Console Panel

The app includes a built-in console panel for real-time logging:

1. **Server Logs:**
   ```python
   log("Message here")  # Sends to frontend console
   ```

2. **Frontend Access:**
   - Click console toggle button
   - Auto-polls every 2 seconds
   - Resizable panel

### Browser Console

```javascript
// Check current state
console.log(currentManga);
console.log(currentChapters);

// Test API directly
post('/api/search', {query: 'naruto'}).then(console.log);
```

### Common Issues

**1. Chapters not loading:**
- Check MangaDex API status
- Verify manga ID is valid
- Check browser console for errors
- Look for HTTP 429 (rate limit)

**2. Downloads failing:**
- Check `static/downloads/` permissions
- Verify disk space
- Check console panel for error messages

**3. Cover images not showing:**
- Check network tab for 404s
- Verify cover URL construction
- Fallback SVG should show if missing

**4. Reader not opening:**
- Check if `chapter_pages` API returns data
- Verify chapter ID is valid
- Check for JavaScript errors

---

## Mobile Optimization

### iOS-Specific Meta Tags

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
```

### Touch Interactions

- Tap highlight disabled: `-webkit-tap-highlight-color: transparent`
- Swipe gestures: Not implemented (future feature)
- Scroll momentum: Native iOS behavior
- Haptic feedback: Not implemented

### Performance Considerations

- Lazy loading images: `loading="lazy"` on images
- Paginated chapter loading (100 at a time)
- Image quality toggle (HD/SD) for data saving
- CSS animations use GPU acceleration

---

## Security Considerations

### Input Sanitization

1. **File Naming:**
   ```python
   safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
   ```

2. **HTML Injection Prevention:**
   ```javascript
   const safeTitle = title.replace(/'/g, "\\'");  // Escape quotes
   ```

3. **API Input Validation:**
   - Flask automatically handles JSON parsing
   - Always check for required fields

### API Security

- No authentication required (read-only MangaDex API)
- User-Agent header prevents bot blocking
- No sensitive data stored
- Downloads stored locally (not uploaded)

---

## Feature Implementation Guide

### Adding a New Feature: Example Walkthrough

**Goal:** Add a "Mark as Read" button to chapters

**Step 1: Backend Route**
```python
# In app.py
@app.route('/api/mark_read', methods=['POST'])
def mark_read():
    data = request.json
    manga_id = data['manga_id']
    chapter_num = data['chapter']

    # Update logic here
    logic.update_last_chapter(manga_id, chapter_num)

    return jsonify({'status': 'ok'})
```

**Step 2: Frontend Function**
```javascript
// In index.html <script> section
async function markAsRead(chapterNum) {
    const result = await post('/api/mark_read', {
        manga_id: currentManga.id,
        chapter: chapterNum
    });

    if (result) {
        alert('✅ Marked as read!');
    }
}
```

**Step 3: UI Button**
```javascript
// In renderChapters() function, add to chapter item:
item.innerHTML = `
    ...
    <button onclick="event.stopPropagation(); markAsRead('${chNum}')">
        Mark Read
    </button>
`;
```

---

## Git Workflow

### Branch Structure

- `main` - Stable releases
- `claude/claude-md-*` - Claude development branches
- Feature branches as needed

### Commit Messages

Follow existing style:
```
Type: Brief description

Optional detailed explanation
```

Examples:
- "Add: Dark mode toggle with localStorage persistence"
- "Fix: Chapter input overflow on mobile devices"
- "Update: Improve API error handling with retry logic"

### Important Files to Commit

**Always commit:**
- `app.py`
- `templates/index.html`
- `static/css/styles.css`
- `README.md`
- `CLAUDE.md`

**Never commit:**
- `library.json` (user data)
- `static/downloads/*` (large files)
- `.git/`
- `__pycache__/`
- `.DS_Store`

---

## Roadmap & Future Features

From README.md roadmap:

- [ ] **Offline CBZ Reader** - Read downloaded files in-app
- [ ] **Search Filters** - Genre, status, year
- [ ] **Pull-to-Refresh** - Native mobile feel
- [ ] **Chapter Read Markers** - Visual indicators
- [ ] **Night Shift Mode** - Warm tones for nighttime reading
- [ ] **Swipe Gestures** - Swipe between pages/chapters
- [ ] **Image Preloading** - Smoother reading experience
- [ ] **Settings Page** - Customize reader behavior

### Implementation Priorities

**High Priority:**
1. CBZ reader integration
2. Settings page (currently placeholder)
3. Chapter read markers

**Medium Priority:**
4. Search filters
5. Swipe gestures
6. Image preloading

**Low Priority:**
7. Night shift mode
8. Pull-to-refresh

---

## AI Assistant Guidelines

### When Modifying Code

1. **Read Before Writing:**
   - Always read the entire file before modifying
   - Understand existing patterns and conventions
   - Preserve code style and comments

2. **Maintain Consistency:**
   - Follow existing naming conventions
   - Match indentation style (4 spaces in Python, 2 in HTML/JS)
   - Keep comprehensive comments

3. **Test Implications:**
   - Consider mobile viewport (iPhone)
   - Test both dark and light themes
   - Verify API error handling

4. **Document Changes:**
   - Update relevant comments
   - Add docstrings to new functions
   - Update this CLAUDE.md if architecture changes

### When Adding Features

1. **Check Roadmap:**
   - See if feature is already planned
   - Align with project goals (iOS manga reader)

2. **Consider Dependencies:**
   - Will this require new Python packages?
   - Does it affect mobile performance?
   - Is it MangaDex API compatible?

3. **Maintain Simplicity:**
   - Avoid over-engineering
   - Keep single-file structure where possible
   - Preserve vanilla JavaScript approach

### When Fixing Bugs

1. **Understand Root Cause:**
   - Check both frontend and backend
   - Review API responses
   - Test on mobile viewport

2. **Preserve Existing Behavior:**
   - Don't break working features
   - Maintain backwards compatibility
   - Keep user data safe (library.json)

3. **Add Safeguards:**
   - Implement proper error handling
   - Add fallbacks for missing data
   - Log errors appropriately

---

## Quick Reference

### File Locations

| Purpose | Location |
|---------|----------|
| Server code | `app.py` |
| Frontend UI | `templates/index.html` |
| Styles | `static/css/styles.css` |
| Logo | `static/images/sharingan.png` |
| Downloads | `static/downloads/` |
| Library data | `library.json` |

### Key Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `MangaLogic.search()` | app.py:309 | Search MangaDex |
| `MangaLogic.get_chapters()` | app.py:355 | Fetch chapters with pagination |
| `MangaLogic.download_worker()` | app.py:602 | Background chapter downloader |
| `openManga()` | index.html:880 | Open manga details |
| `loadChapters()` | index.html:920 | Load chapters into UI |
| `openReader()` | index.html:1183 | Open fullscreen reader |
| `toggleTheme()` | index.html:475 | Switch dark/light mode |

### Environment

| Key | Value |
|-----|-------|
| Python Version | 3.8+ |
| Flask Version | 3.0.0 |
| Target Platform | iOS Code App (Safari) |
| Design Style | iOS Glassmorphism |
| External API | MangaDex API v5 |

---

## Support & Resources

### Official Links

- **Repository:** [github.com/bookers1897/Manga-Negus](https://github.com/bookers1897/Manga-Negus)
- **Author:** [@bookers1897](https://github.com/bookers1897)
- **License:** MIT

### External Documentation

- [MangaDex API Docs](https://api.mangadex.org/docs/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Phosphor Icons](https://phosphoricons.com/)

### Troubleshooting

For common issues, check:
1. Browser console (F12)
2. Server console (terminal running `python app.py`)
3. Built-in console panel (in app)
4. Network tab (API responses)

---

**Last Updated:** 2025-12-29
**Version:** 2.1
**For:** AI Assistants (Claude Code)
