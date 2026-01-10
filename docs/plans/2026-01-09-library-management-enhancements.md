# Library Management Enhancements Design

**Date:** 2026-01-09
**Status:** Approved
**Version:** 1.0

## Overview

Complete overhaul of library management UI with card menus, multi-select deletion, passive download queue, and animated title branding.

## Goals

1. Fix broken single-item removal from library
2. Add context menus to cards (library and discovery views)
3. Implement multi-select deletion for bulk operations
4. Add passive download queue (queue without auto-start)
5. Add animated title cycling (Manga Negus → Manga King → マンガキング)

## Architecture

### Component Structure

**1. Menu System (CardMenu)**
- Reusable dropdown component for card actions
- Context-aware menu items (library vs discovery)
- Handles click-outside-to-close, positioning
- Event emitters: `menu:remove`, `menu:status`, `menu:download`, `menu:select-mode`

**2. Selection Manager (SelectionState)**
- Tracks selected cards during multi-select mode
- Manages mode state (on/off)
- Provides selection count and selected items array
- Handles bulk operations (delete, download)

**3. Passive Download Queue**
- New queue state: `paused_queue` (items added but not downloading)
- User reviews and confirms before starting downloads
- Prevents accidental bandwidth usage

**4. Title Cycler**
- Auto-cycles every 30 seconds
- Manual cycle on click
- Smooth fade transitions

### State Management

```javascript
// New state properties
state.selectionMode = false;              // Multi-select active?
state.selectedCards = new Set();          // Set of library keys/manga IDs
state.passiveQueue = [];                  // Paused download items
state.currentTitleIndex = 0;              // Title rotation index
```

## Implementation Details

### 1. Card Menu System

**HTML Structure:**
```html
<!-- Menu button (replaces trash button in library cards) -->
<button class="card-menu-btn" data-manga-id="..." data-source="...">
    <i data-lucide="more-vertical" width="16"></i>
</button>

<!-- Dropdown menu -->
<div class="card-menu-dropdown" style="display: none;">
    <!-- Library context -->
    <button class="menu-item" data-action="status">
        <i data-lucide="bookmark"></i> Change Status
    </button>
    <button class="menu-item" data-action="mark-read">
        <i data-lucide="check-circle"></i> Mark All Read
    </button>
    <button class="menu-item" data-action="select-mode">
        <i data-lucide="check-square"></i> Select Multiple
    </button>
    <button class="menu-item danger" data-action="remove">
        <i data-lucide="trash"></i> Remove
    </button>

    <!-- Discovery context -->
    <button class="menu-item" data-action="add-library">
        <i data-lucide="heart"></i> Add to Library
    </button>
    <button class="menu-item" data-action="queue-download">
        <i data-lucide="download"></i> Queue Download
    </button>
</div>
```

**Behavior:**
- Click "⋮" → menu appears below button
- Click outside or select action → menu closes
- Menu positioned to stay on screen (flips up if near bottom)
- Only one menu open at a time

**CSS:**
- Glassmorphic style (blur, semi-transparent)
- Smooth fade-in animation (150ms)
- Red text for destructive "Remove" action
- z-index: 1000 (above cards)

### 2. Multi-Select Mode

**Activation:**
- Click "Select Multiple" from any card menu
- OR click "Select" button in library header (optional)

**Visual Changes:**
```html
<!-- Checkbox overlay on each card -->
<div class="card-selection-overlay">
    <input type="checkbox" class="card-checkbox" />
</div>

<!-- Bottom action bar (slides up from bottom) -->
<div class="selection-action-bar">
    <span class="selection-count">3 selected</span>
    <button class="btn-delete-selected danger">
        <i data-lucide="trash"></i> Delete Selected
    </button>
    <button class="btn-download-selected">
        <i data-lucide="download"></i> Queue Selected
    </button>
    <button class="btn-cancel-selection secondary">Cancel</button>
</div>
```

**Behavior:**
- Enter mode → checkboxes appear on all cards
- Click card → toggles checkbox (doesn't open details)
- Click checkbox → toggles selection
- Action bar floats at bottom (fixed position)
- "Delete Selected" → confirmation modal: "Delete 3 manga from library?"
- "Cancel" → exits mode, clears selections

**Functions:**
```javascript
function enterSelectionMode() {
    state.selectionMode = true;
    state.selectedCards.clear();
    renderLibraryFromState(); // Re-render with checkboxes
    showSelectionActionBar();
}

function exitSelectionMode() {
    state.selectionMode = false;
    state.selectedCards.clear();
    hideSelectionActionBar();
    renderLibraryFromState();
}

function toggleCardSelection(key) {
    if (state.selectedCards.has(key)) {
        state.selectedCards.delete(key);
    } else {
        state.selectedCards.add(key);
    }
    updateSelectionCount();
    updateCheckboxStates();
}

async function deleteSelected() {
    const keys = Array.from(state.selectedCards);
    const count = keys.length;

    // Show confirmation modal
    const confirmed = await showConfirmModal(
        'Delete from Library',
        `Remove ${count} manga from your library?`,
        'Delete',
        'Cancel'
    );

    if (!confirmed) return;

    // Delete all in parallel
    try {
        await Promise.all(keys.map(key => API.removeFromLibrary(key)));
        showToast(`Removed ${count} manga from library`);
        exitSelectionMode();
        await loadLibrary();
    } catch (error) {
        log(`❌ Bulk delete failed: ${error.message}`);
        showToast('Some deletions failed');
    }
}
```

### 3. Passive Download Queue

**New Backend States:**
- `paused_queue` - Added to queue but not started
- `queued` - Ready to download
- `downloading` - Currently downloading
- `completed` - Finished
- `failed` - Error occurred
- `cancelled` - User cancelled

**API Changes:**

```javascript
// Modified download endpoint
POST /api/download
{
    chapters: [...],
    title: "...",
    source: "...",
    manga_id: "...",
    start_immediately: false  // NEW: if false, status = "paused_queue"
}

// Queue response includes paused count
GET /api/download/queue
→ {
    queue: [...],
    paused_count: 3,      // NEW
    active_count: 1,
    completed_count: 5
}

// New endpoint to start paused items
POST /api/download/start_paused
{
    job_ids: ["abc", "def"]  // Empty array = start all paused
}
```

**Frontend Flow:**
1. Discovery card → "⋮" → "Queue Download"
2. Chapter selection modal appears
3. Select chapters → "Add to Queue" button
4. POST with `start_immediately: false`
5. Items added as `paused_queue`
6. Badge on downloads button: "Downloads (3)"
7. Open queue modal → "Paused" section shows items
8. Click "Start All" or individual "Start" buttons
9. POST /api/download/start_paused
10. Items change to `queued`, downloads begin

**UI Components:**

```html
<!-- Download button with badge -->
<button id="downloads-btn">
    <i data-lucide="download"></i>
    <span class="badge" id="paused-badge">3</span>
</button>

<!-- Queue modal with sections -->
<div class="queue-section">
    <h3>Paused Queue <button class="btn-start-all">Start All</button></h3>
    <!-- Paused items here -->
</div>

<div class="queue-section">
    <h3>Active Downloads</h3>
    <!-- Active/downloading items here -->
</div>

<div class="queue-section">
    <h3>Completed</h3>
    <!-- Completed items here -->
</div>
```

### 4. Title Cycling Animation

**Implementation:**
```javascript
const titles = [
    'Manga Negus',    // Default
    'Manga King',     // English translation
    'マンガキング'      // Japanese: Manga Kingu
];
let currentTitleIndex = 0;

function updateTitle() {
    els.appTitle.style.opacity = '0';

    setTimeout(() => {
        els.appTitle.textContent = titles[currentTitleIndex];
        els.appTitle.style.opacity = '1';
    }, 150); // Half of transition duration
}

// Auto-cycle every 30 seconds
setInterval(() => {
    currentTitleIndex = (currentTitleIndex + 1) % titles.length;
    updateTitle();
}, 30000);

// Manual cycle on click
els.appTitle.addEventListener('click', () => {
    currentTitleIndex = (currentTitleIndex + 1) % titles.length;
    updateTitle();
});
```

**CSS:**
```css
.app-title {
    transition: opacity 300ms ease-in-out;
    cursor: pointer;
}

.app-title:hover {
    opacity: 0.8;
}
```

## Visual Design Changes

### Library Cards
**Before:**
```
[Card with Heart bookmark + Trash button in top-right]
```

**After:**
```
[Card with "⋮" menu button only in top-right]
- Menu contains: Change Status, Mark Read, Select Multiple, Remove
```

### Discovery Cards
**Before:**
```
[Card with Heart bookmark button in top-right]
```

**After:**
```
[Card with Heart bookmark + "⋮" menu in top-right]
- Menu contains: Add to Library, Queue Download
```

### Multi-Select Mode
```
[All cards show checkbox overlay in top-left]
[Bottom action bar with: "3 selected | Delete | Queue | Cancel"]
```

## CSS Classes

```css
/* Card menu button */
.card-menu-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
}

.card-menu-btn:hover {
    background: rgba(255, 255, 255, 0.1);
}

/* Menu dropdown */
.card-menu-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 4px;
    min-width: 180px;
    background: rgba(20, 20, 20, 0.95);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 4px;
    z-index: 1000;
    animation: menuFadeIn 150ms ease-out;
}

@keyframes menuFadeIn {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Menu items */
.menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 12px;
    background: transparent;
    border: none;
    color: var(--text-primary);
    text-align: left;
    cursor: pointer;
    border-radius: 4px;
    font-size: 14px;
}

.menu-item:hover {
    background: rgba(255, 255, 255, 0.1);
}

.menu-item.danger {
    color: var(--danger);
}

/* Selection mode */
.card-selection-overlay {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 10;
}

.card-checkbox {
    width: 20px;
    height: 20px;
    cursor: pointer;
}

.selection-action-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(20, 20, 20, 0.98);
    backdrop-filter: blur(20px);
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    z-index: 1000;
    animation: slideUp 200ms ease-out;
}

@keyframes slideUp {
    from { transform: translateY(100%); }
    to { transform: translateY(0); }
}

.selection-count {
    margin-right: auto;
    font-weight: 500;
}

/* Paused queue badge */
.downloads-btn .badge {
    position: absolute;
    top: -4px;
    right: -4px;
    background: var(--danger);
    color: white;
    border-radius: 10px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}
```

## File Changes

### Frontend (`static/js/main.js`)

**New Functions:**
```javascript
// Menu system
function openCardMenu(button, context) { }
function closeAllMenus() { }
function handleMenuAction(action, mangaId, source, key) { }

// Selection mode
function enterSelectionMode() { }
function exitSelectionMode() { }
function toggleCardSelection(key) { }
function updateSelectionCount() { }
function deleteSelected() { }
function downloadSelected() { }

// Title cycling
function updateTitle() { }
function startTitleCycling() { }

// Passive queue
function queueDownloadPassive(mangaId, source, title) { }
function startPausedDownloads(jobIds = []) { }
function renderQueueSections() { }
```

**Modified Functions:**
```javascript
// renderMangaGrid() - Add menu button, remove trash button
// handleGridClick() - Fix removeFromLibrary call to API.removeFromLibrary
// renderDownloadQueue() - Add paused section
// fetchDownloadQueue() - Show paused badge
```

### Backend (`manganegus_app/extensions.py`)

**DownloadItem Changes:**
```python
class DownloadItem:
    # Add new status
    self.status = "paused_queue"  # New option
```

**Downloader Changes:**
```python
def add_to_queue(self, ..., start_immediately=True):
    """Add download with optional auto-start."""
    item = DownloadItem(...)
    if not start_immediately:
        item.status = "paused_queue"
    self._queue.append(item)

def start_paused_items(self, job_ids=None):
    """Start paused queue items."""
    for item in self._queue:
        if item.status == "paused_queue":
            if job_ids is None or item.job_id in job_ids:
                item.status = "queued"
```

### Backend (`manganegus_app/routes/downloads_api.py`)

**New Endpoint:**
```python
@downloads_bp.route('/api/download/start_paused', methods=['POST'])
@csrf_protect
def start_paused_downloads():
    """Start paused queue items."""
    data = request.get_json(silent=True) or {}
    job_ids = data.get('job_ids')  # None = start all
    downloader.start_paused_items(job_ids)
    return jsonify({'status': 'ok'})
```

**Modified Endpoint:**
```python
@downloads_bp.route('/api/download', methods=['POST'])
@csrf_protect
def download_chapter():
    data = request.get_json(silent=True) or {}
    start_immediately = data.get('start_immediately', True)  # NEW
    job_id = downloader.add_to_queue(..., start_immediately=start_immediately)
    return jsonify({'status': 'ok', 'job_id': job_id})
```

## Testing Plan

1. **Card Menu**
   - ✅ Click "⋮" → menu appears
   - ✅ Click outside → menu closes
   - ✅ Click menu item → action executes, menu closes
   - ✅ Only one menu open at a time

2. **Single Removal**
   - ✅ Library card → "⋮" → Remove → confirms → removed
   - ✅ Library refreshes after removal

3. **Multi-Select**
   - ✅ Enter selection mode → checkboxes appear
   - ✅ Click cards → checkboxes toggle
   - ✅ Action bar shows correct count
   - ✅ Delete selected → confirmation → all deleted
   - ✅ Cancel → exits mode cleanly

4. **Passive Queue**
   - ✅ Discovery card → Queue Download → modal appears
   - ✅ Select chapters → Add to Queue → items paused
   - ✅ Badge shows count on downloads button
   - ✅ Queue modal shows paused section
   - ✅ Start All → downloads begin
   - ✅ Individual start button works

5. **Title Cycling**
   - ✅ Auto-cycles every 30s
   - ✅ Click title → cycles immediately
   - ✅ Smooth fade transition
   - ✅ Loops through all 3 titles

## Success Criteria

- ✅ Broken remove button fixed (calls API.removeFromLibrary)
- ✅ Card menus work in both library and discovery views
- ✅ Multi-select mode allows bulk deletion
- ✅ Passive queue prevents auto-downloading
- ✅ Title cycles automatically and on click
- ✅ UI feels polished and responsive
- ✅ No regressions in existing functionality

## Future Enhancements (Not in Scope)

- Undo deletion with toast action
- Select all / deselect all buttons
- Drag-to-select cards
- Keyboard shortcuts for selection (Ctrl+A, Delete key)
- Export/import library as JSON
- Bulk status changes (mark 10 manga as "Completed")

---

**Approved by:** User
**Implementation:** Ready for planning phase
