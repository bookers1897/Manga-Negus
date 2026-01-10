# Library Management Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add card menus, multi-select deletion, passive download queue, and animated title cycling to MangaNegus.

**Architecture:** Frontend-heavy feature using vanilla JS event delegation, CSS animations, and new backend endpoints for passive queue. Three main systems: CardMenu (dropdown menus), SelectionManager (multi-select state), and PassiveQueue (queue without auto-start).

**Tech Stack:** Vanilla JavaScript ES6, CSS3 animations, Flask (Python), SQLAlchemy, Lucide icons

---

## Task 1: Fix Broken Remove Button

**Files:**
- Modify: `static/js/main.js:2740`

**Step 1: Fix the removeFromLibrary function call**

Find line 2740 in main.js and change:
```javascript
// BEFORE (broken):
removeFromLibrary(key)

// AFTER (fixed):
API.removeFromLibrary(key)
```

**Step 2: Test the fix**

Run: Open browser → Library view → Click trash button on a manga
Expected: Toast shows "Removed from library", manga disappears

**Step 3: Commit**

```bash
git add static/js/main.js
git commit -m "fix: correct API call for removeFromLibrary

The remove button was calling a non-existent function.
Now correctly calls API.removeFromLibrary()."
```

---

## Task 2: Add CSS for Card Menus and Selection Mode

**Files:**
- Modify: `static/css/styles.css` (append to end)

**Step 1: Add card menu styles**

Append to `static/css/styles.css`:

```css
/* Card Menu Button */
.card-menu-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    transition: background 150ms ease;
    display: flex;
    align-items: center;
    justify-content: center;
}

.card-menu-btn:hover {
    background: rgba(255, 255, 255, 0.1);
}

/* Card Menu Dropdown */
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
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    animation: menuFadeIn 150ms ease-out;
}

@keyframes menuFadeIn {
    from {
        opacity: 0;
        transform: translateY(-8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.card-menu-dropdown.flip-up {
    top: auto;
    bottom: 100%;
    margin-top: 0;
    margin-bottom: 4px;
}

/* Menu Items */
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
    transition: background 100ms ease;
}

.menu-item:hover {
    background: rgba(255, 255, 255, 0.1);
}

.menu-item.danger {
    color: var(--danger);
}

.menu-item.danger:hover {
    background: rgba(220, 38, 38, 0.1);
}

.menu-item svg {
    width: 16px;
    height: 16px;
}

/* Selection Mode Styles */
.card-selection-overlay {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 10;
    background: rgba(20, 20, 20, 0.9);
    backdrop-filter: blur(10px);
    border-radius: 4px;
    padding: 4px;
}

.card-checkbox {
    width: 20px;
    height: 20px;
    cursor: pointer;
    accent-color: var(--primary);
}

.selection-mode .card {
    cursor: pointer;
}

.selection-mode .card:hover {
    transform: translateY(-2px);
}

/* Selection Action Bar */
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
    box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.3);
}

@keyframes slideUp {
    from { transform: translateY(100%); }
    to { transform: translateY(0); }
}

.selection-action-bar.hidden {
    display: none;
}

.selection-count {
    margin-right: auto;
    font-weight: 500;
    color: var(--text-primary);
}

.btn-delete-selected,
.btn-download-selected,
.btn-cancel-selection {
    padding: 10px 20px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    font-weight: 500;
    transition: all 150ms ease;
    display: flex;
    align-items: center;
    gap: 8px;
}

.btn-delete-selected {
    background: var(--danger);
    color: white;
}

.btn-delete-selected:hover {
    background: #b91c1c;
}

.btn-download-selected {
    background: var(--primary);
    color: white;
}

.btn-download-selected:hover {
    background: #b91c1c;
}

.btn-cancel-selection {
    background: rgba(255, 255, 255, 0.1);
    color: var(--text-primary);
}

.btn-cancel-selection:hover {
    background: rgba(255, 255, 255, 0.15);
}

/* Paused Queue Badge */
#downloads-btn {
    position: relative;
}

#paused-badge {
    position: absolute;
    top: -4px;
    right: -4px;
    background: var(--danger);
    color: white;
    border-radius: 10px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
    text-align: center;
}

#paused-badge.hidden {
    display: none;
}

/* Queue Section Styling */
.queue-section {
    margin-bottom: 24px;
}

.queue-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.queue-section h3 {
    margin: 0;
    font-size: 16px;
    color: var(--text-primary);
}

.btn-start-all {
    padding: 6px 12px;
    background: var(--primary);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
}

.btn-start-all:hover {
    background: #b91c1c;
}

/* Title Cycling Animation */
.app-title {
    transition: opacity 300ms ease-in-out;
    cursor: pointer;
    user-select: none;
}

.app-title:hover {
    opacity: 0.8;
}
```

**Step 2: Verify CSS loads**

Run: Refresh browser, open DevTools → Sources → Check styles.css loaded
Expected: New styles visible in Sources tab

**Step 3: Commit**

```bash
git add static/css/styles.css
git commit -m "style: add CSS for card menus and selection mode

- Card menu dropdown with glassmorphic style
- Selection mode with checkboxes and action bar
- Paused queue badge styling
- Title cycling animation"
```

---

## Task 3: Add HTML Elements for Selection Bar and Badge

**Files:**
- Modify: `templates/index.html:76` (downloads button)
- Modify: `templates/index.html:380` (before closing main-content div)

**Step 1: Add badge to downloads button**

Find the downloads button (around line 76) and modify:
```html
<!-- BEFORE -->
<button id="downloads-btn" class="nav-btn" title="Downloads">
    <i data-lucide="download" width="24"></i>
</button>

<!-- AFTER -->
<button id="downloads-btn" class="nav-btn" title="Downloads">
    <i data-lucide="download" width="24"></i>
    <span id="paused-badge" class="hidden">0</span>
</button>
```

**Step 2: Add selection action bar**

Add before the closing `</div><!-- main-content -->` tag (around line 380):
```html
<!-- Selection Action Bar (appears in multi-select mode) -->
<div id="selection-action-bar" class="selection-action-bar hidden">
    <span id="selection-count" class="selection-count">0 selected</span>
    <button id="btn-delete-selected" class="btn-delete-selected">
        <i data-lucide="trash" width="18"></i>
        Delete Selected
    </button>
    <button id="btn-download-selected" class="btn-download-selected">
        <i data-lucide="download" width="18"></i>
        Queue Selected
    </button>
    <button id="btn-cancel-selection" class="btn-cancel-selection">
        Cancel
    </button>
</div>
```

**Step 3: Verify HTML structure**

Run: View page source, search for "paused-badge" and "selection-action-bar"
Expected: Both elements present in HTML

**Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: add HTML for paused badge and selection bar

- Paused queue count badge on downloads button
- Selection action bar for multi-select mode"
```

---

## Task 4: Add Selection State and Menu State to JavaScript

**Files:**
- Modify: `static/js/main.js:30` (state object)
- Modify: `static/js/main.js:100` (els object in initElements)

**Step 1: Add state properties**

Find the `state` object (around line 30) and add:
```javascript
const state = {
    // ... existing properties ...
    selectionMode: false,
    selectedCards: new Set(),
    currentTitleIndex: 0,
    activeMenu: null  // Track open menu
};
```

**Step 2: Add element references in initElements()**

Find `initElements()` (around line 100) and add to the `els` object:
```javascript
els = {
    // ... existing elements ...
    pausedBadge: document.getElementById('paused-badge'),
    selectionActionBar: document.getElementById('selection-action-bar'),
    selectionCount: document.getElementById('selection-count'),
    btnDeleteSelected: document.getElementById('btn-delete-selected'),
    btnDownloadSelected: document.getElementById('btn-download-selected'),
    btnCancelSelection: document.getElementById('btn-cancel-selection'),
    appTitle: document.querySelector('.app-title')
};
```

**Step 3: Verify state initialized**

Run: Browser console → type `state`
Expected: Object with selectionMode, selectedCards, etc.

**Step 4: Commit**

```bash
git add static/js/main.js
git commit -m "feat: add selection and menu state management

- State properties for selection mode and menu tracking
- Element references for new UI components"
```

---

## Task 5: Implement Title Cycling Feature

**Files:**
- Modify: `static/js/main.js:2900` (add new functions at end)
- Modify: `static/js/main.js:3100` (init function)

**Step 1: Add title cycling functions**

Add before the `init()` function:
```javascript
// ==================== Title Cycling ====================

const titles = [
    'Manga Negus',
    'Manga King',
    'マンガキング'  // Japanese: Manga Kingu
];

function updateTitle() {
    if (!els.appTitle) return;

    els.appTitle.style.opacity = '0';

    setTimeout(() => {
        els.appTitle.textContent = titles[state.currentTitleIndex];
        els.appTitle.style.opacity = '1';
    }, 150);
}

function cycleTitle() {
    state.currentTitleIndex = (state.currentTitleIndex + 1) % titles.length;
    updateTitle();
}

function startTitleCycling() {
    if (!els.appTitle) return;

    // Auto-cycle every 30 seconds
    setInterval(cycleTitle, 30000);

    // Manual cycle on click
    els.appTitle.addEventListener('click', cycleTitle);
}
```

**Step 2: Call startTitleCycling in init()**

Find the `init()` function and add near the end:
```javascript
async function init() {
    initElements();
    // ... existing init code ...

    // Start title cycling
    startTitleCycling();

    log('✅ MangaNegus initialized');
}
```

**Step 3: Test title cycling**

Run: Refresh browser → Click app title → Wait 30 seconds
Expected: Title cycles through Manga Negus → Manga King → マンガキング

**Step 4: Commit**

```bash
git add static/js/main.js
git commit -m "feat: add animated title cycling

- Auto-cycles every 30 seconds
- Manual cycle on click
- Smooth fade transition between titles"
```

---

## Task 6: Implement Card Menu System

**Files:**
- Modify: `static/js/main.js:2950` (add menu functions)
- Modify: `static/js/main.js:1550` (modify renderMangaGrid)

**Step 1: Add menu management functions**

Add after title cycling functions:
```javascript
// ==================== Card Menu System ====================

function createCardMenu(context, mangaId, source, key, title, coverUrl) {
    const menu = document.createElement('div');
    menu.className = 'card-menu-dropdown';
    menu.style.display = 'none';

    const items = context === 'library' ? [
        { action: 'status', icon: 'bookmark', label: 'Change Status' },
        { action: 'mark-read', icon: 'check-circle', label: 'Mark All Read' },
        { action: 'select-mode', icon: 'check-square', label: 'Select Multiple' },
        { action: 'remove', icon: 'trash', label: 'Remove', danger: true }
    ] : [
        { action: 'add-library', icon: 'heart', label: 'Add to Library' },
        { action: 'queue-download', icon: 'download', label: 'Queue Download' }
    ];

    menu.innerHTML = items.map(item => `
        <button class="menu-item ${item.danger ? 'danger' : ''}" data-action="${item.action}">
            <i data-lucide="${item.icon}"></i>
            ${item.label}
        </button>
    `).join('');

    // Store data for event handlers
    menu.dataset.mangaId = mangaId;
    menu.dataset.source = source;
    menu.dataset.key = key || '';
    menu.dataset.title = title || '';
    menu.dataset.coverUrl = coverUrl || '';

    return menu;
}

function openCardMenu(button, menu) {
    closeAllMenus();

    // Position menu
    const rect = button.getBoundingClientRect();
    const menuHeight = 180; // Approximate

    // Check if menu would go off bottom of screen
    const flipUp = (rect.bottom + menuHeight) > window.innerHeight;

    if (flipUp) {
        menu.classList.add('flip-up');
    } else {
        menu.classList.remove('flip-up');
    }

    menu.style.display = 'block';
    state.activeMenu = menu;

    // Re-render icons
    safeCreateIcons();

    // Add menu item click handlers
    menu.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            const action = item.dataset.action;
            handleMenuAction(action, menu);
        });
    });
}

function closeAllMenus() {
    if (state.activeMenu) {
        state.activeMenu.style.display = 'none';
        state.activeMenu = null;
    }
    document.querySelectorAll('.card-menu-dropdown').forEach(menu => {
        menu.style.display = 'none';
    });
}

async function handleMenuAction(action, menu) {
    const mangaId = menu.dataset.mangaId;
    const source = menu.dataset.source;
    const key = menu.dataset.key;
    const title = menu.dataset.title;
    const coverUrl = menu.dataset.coverUrl;

    closeAllMenus();

    switch (action) {
        case 'remove':
            await removeFromLibraryWithConfirm(key, title);
            break;

        case 'status':
            showLibraryStatusModal(mangaId, source, title, coverUrl, key);
            break;

        case 'mark-read':
            showToast('Mark all read - Coming soon!');
            break;

        case 'select-mode':
            enterSelectionMode();
            break;

        case 'add-library':
            if (isInLibrary(mangaId, source)) {
                showToast('Already in library');
            } else {
                showLibraryStatusModal(mangaId, source, title, coverUrl);
            }
            break;

        case 'queue-download':
            await queueDownloadPassive(mangaId, source, title);
            break;

        default:
            log(`Unknown menu action: ${action}`);
    }
}

async function removeFromLibraryWithConfirm(key, title) {
    const confirmed = confirm(`Remove "${title}" from library?`);
    if (!confirmed) return;

    try {
        await API.removeFromLibrary(key);
        showToast('Removed from library');
        await loadLibrary();
    } catch (error) {
        log(`❌ Remove failed: ${error.message}`);
        showToast('Failed to remove');
    }
}

// Click outside to close menus
document.addEventListener('click', (e) => {
    if (!e.target.closest('.card-menu-btn') && !e.target.closest('.card-menu-dropdown')) {
        closeAllMenus();
    }
});
```

**Step 2: Modify renderMangaGrid to add menu buttons**

Find `renderMangaGrid()` function (around line 1550) and modify the card badges section:
```javascript
// Find this section (around line 1552):
<div class="card-badges">
    <span class="badge-score"><i data-lucide="flame"></i> ${escapeHtml(String(score))}</span>
    <button class="bookmark-btn ${inLibrary ? 'active' : ''}" data-action="bookmark">
        <i data-lucide="heart" width="16" height="16" fill="${inLibrary ? 'currentColor' : 'none'}"></i>
    </button>
    ${isLibraryView ? `<button class="remove-btn" data-action="remove" title="Remove from library"><i data-lucide="trash" width="14"></i></button>` : ''}
</div>

// Replace with:
<div class="card-badges">
    <span class="badge-score"><i data-lucide="flame"></i> ${escapeHtml(String(score))}</span>
    ${!isLibraryView ? `
        <button class="bookmark-btn ${inLibrary ? 'active' : ''}" data-action="bookmark">
            <i data-lucide="heart" width="16" height="16" fill="${inLibrary ? 'currentColor' : 'none'}"></i>
        </button>
    ` : ''}
    <button class="card-menu-btn" data-action="menu">
        <i data-lucide="more-vertical" width="16"></i>
    </button>
</div>
```

**Step 3: Add menu click handler in handleGridClick**

Find `handleGridClick()` function (around line 2720) and add before the remove button handler:
```javascript
// Add this BEFORE the existing removeBtn handler:

// Handle menu button
const menuBtn = e.target.closest('.card-menu-btn');
if (menuBtn) {
    e.stopPropagation();

    const context = gridEl === els.libraryGrid ? 'library' : 'discovery';
    const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
    const title = card.querySelector('.card-title')?.textContent || '';
    const coverUrl = card.querySelector('.card-image')?.src || '';

    // Create or find existing menu
    let menu = card.querySelector('.card-menu-dropdown');
    if (!menu) {
        menu = createCardMenu(context, mangaId, source, key, title, coverUrl);
        card.appendChild(menu);
    }

    openCardMenu(menuBtn, menu);
    return;
}
```

**Step 4: Test card menus**

Run: Refresh → Library view → Click "⋮" on any card
Expected: Menu appears with 4 options (Change Status, Mark Read, Select Multiple, Remove)

Run: Discover view → Click "⋮" on any card
Expected: Menu appears with 2 options (Add to Library, Queue Download)

**Step 5: Commit**

```bash
git add static/js/main.js
git commit -m "feat: implement card menu system

- Context-aware menus (library vs discovery)
- Menu positioning with flip-up for screen edges
- Click outside to close
- Menu actions: remove, status, select mode, queue"
```

---

## Task 7: Implement Multi-Select Mode

**Files:**
- Modify: `static/js/main.js:3100` (add selection functions)
- Modify: `static/js/main.js:1550` (modify renderMangaGrid for checkboxes)

**Step 1: Add selection mode functions**

Add after menu functions:
```javascript
// ==================== Multi-Select Mode ====================

function enterSelectionMode() {
    state.selectionMode = true;
    state.selectedCards.clear();

    // Add selection-mode class to body
    document.body.classList.add('selection-mode');

    // Re-render library with checkboxes
    renderLibraryFromState();

    // Show action bar
    els.selectionActionBar.classList.remove('hidden');
    updateSelectionCount();

    log('📋 Entered selection mode');
}

function exitSelectionMode() {
    state.selectionMode = false;
    state.selectedCards.clear();

    // Remove selection-mode class
    document.body.classList.remove('selection-mode');

    // Hide action bar
    els.selectionActionBar.classList.add('hidden');

    // Re-render library without checkboxes
    renderLibraryFromState();

    log('✅ Exited selection mode');
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

function updateSelectionCount() {
    const count = state.selectedCards.size;
    els.selectionCount.textContent = `${count} selected`;

    // Enable/disable action buttons
    const hasSelection = count > 0;
    els.btnDeleteSelected.disabled = !hasSelection;
    els.btnDownloadSelected.disabled = !hasSelection;
}

function updateCheckboxStates() {
    document.querySelectorAll('.card-checkbox').forEach(checkbox => {
        const key = checkbox.closest('.card').dataset.libraryKey;
        checkbox.checked = state.selectedCards.has(key);
    });
}

async function deleteSelected() {
    const keys = Array.from(state.selectedCards);
    const count = keys.length;

    if (count === 0) {
        showToast('No items selected');
        return;
    }

    const confirmed = confirm(`Remove ${count} manga from library?`);
    if (!confirmed) return;

    try {
        log(`🗑️ Deleting ${count} items...`);

        // Delete all in parallel
        await Promise.all(keys.map(key => API.removeFromLibrary(key)));

        showToast(`Removed ${count} manga from library`);
        exitSelectionMode();
        await loadLibrary();

        log(`✅ Deleted ${count} items`);
    } catch (error) {
        log(`❌ Bulk delete failed: ${error.message}`);
        showToast('Some deletions failed');
    }
}

async function downloadSelected() {
    showToast('Bulk download - Coming soon!');
    // TODO: Implement bulk passive queue
}
```

**Step 2: Add selection bar event listeners in init()**

Find `init()` function and add:
```javascript
// Selection mode handlers
els.btnDeleteSelected.addEventListener('click', deleteSelected);
els.btnDownloadSelected.addEventListener('click', downloadSelected);
els.btnCancelSelection.addEventListener('click', exitSelectionMode);
```

**Step 3: Modify renderMangaGrid to show checkboxes in selection mode**

In `renderMangaGrid()`, modify the card HTML to include checkbox overlay:
```javascript
// Add this at the start of the card HTML (after opening <div class="card">):
${state.selectionMode && isLibraryView ? `
    <div class="card-selection-overlay">
        <input type="checkbox" class="card-checkbox" />
    </div>
` : ''}
```

**Step 4: Modify handleGridClick to handle checkbox clicks in selection mode**

In `handleGridClick()`, add at the very start:
```javascript
function handleGridClick(gridEl, e) {
    // Handle selection mode
    if (state.selectionMode && gridEl === els.libraryGrid) {
        const card = e.target.closest('.card');
        if (!card) return;

        const checkbox = e.target.closest('.card-checkbox');
        const clickedCard = e.target.closest('.card') && !e.target.closest('.card-menu-btn');

        if (checkbox || clickedCard) {
            e.stopPropagation();
            const key = card.dataset.libraryKey;
            toggleCardSelection(key);
            return;
        }
    }

    // ... rest of existing function
}
```

**Step 5: Test multi-select mode**

Run: Library → Click "⋮" → "Select Multiple"
Expected: Checkboxes appear, action bar slides up

Run: Click multiple cards
Expected: Checkboxes toggle, count updates

Run: Click "Delete Selected"
Expected: Confirmation modal → Delete → Library refreshes

Run: Click "Cancel"
Expected: Exit selection mode, checkboxes disappear

**Step 6: Commit**

```bash
git add static/js/main.js templates/index.html
git commit -m "feat: implement multi-select deletion mode

- Enter/exit selection mode
- Checkbox overlays on library cards
- Selection action bar with delete/cancel
- Bulk deletion with confirmation
- Toggle selection by clicking cards or checkboxes"
```

---

## Task 8: Backend - Add Passive Queue Support

**Files:**
- Modify: `manganegus_app/extensions.py:523` (DownloadItem class)
- Modify: `manganegus_app/extensions.py:620` (Downloader.add_to_queue)
- Modify: `manganegus_app/extensions.py:750` (add new method)

**Step 1: Add paused_queue status to DownloadItem**

Find `DownloadItem` class (around line 523) and update docstring:
```python
class DownloadItem:
    """Represents a single download job in the queue.

    Status values:
    - paused_queue: Added but not started (user must manually start)
    - queued: Ready to download
    - downloading: Currently downloading
    - paused: User paused
    - completed: Finished
    - failed: Error occurred
    - cancelled: User cancelled
    """
```

**Step 2: Add start_immediately parameter to add_to_queue**

Find `Downloader.add_to_queue()` (around line 620) and modify:
```python
def add_to_queue(self, chapters: List[Dict], title: str, source_id: str, manga_id: str = "", start_immediately: bool = True) -> str:
    """Add chapters to download queue.

    Args:
        chapters: List of chapter dicts with id, chapter, title
        title: Manga title
        source_id: Source identifier
        manga_id: Manga ID
        start_immediately: If False, status set to 'paused_queue'

    Returns:
        job_id: Unique identifier for this job
    """
    with self._lock:
        job_id = str(uuid.uuid4())
        item = DownloadItem(job_id, chapters, title, source_id, manga_id)

        # Set initial status based on start_immediately
        if not start_immediately:
            item.status = "paused_queue"

        self._queue.append(item)
        log(f"📥 Added to queue: {title} ({len(chapters)} chapters) - {'auto-start' if start_immediately else 'paused'}")
        return job_id
```

**Step 3: Add start_paused_items method**

Add new method to `Downloader` class (around line 750):
```python
def start_paused_items(self, job_ids: List[str] = None):
    """Start paused queue items.

    Args:
        job_ids: List of job IDs to start. If None, start all paused items.
    """
    with self._lock:
        started_count = 0
        for item in self._queue:
            if item.status == "paused_queue":
                if job_ids is None or item.job_id in job_ids:
                    item.status = "queued"
                    started_count += 1

        if started_count > 0:
            log(f"▶️ Started {started_count} paused downloads")
```

**Step 4: Modify get_queue to include paused count**

Find `Downloader.get_queue()` and update to return paused count:
```python
def get_queue(self) -> List[Dict]:
    """Get current queue status with paused count."""
    with self._lock:
        queue_data = []
        paused_count = 0

        for item in self._queue:
            if item.status == "paused_queue":
                paused_count += 1

            queue_data.append({
                'job_id': item.job_id,
                'title': item.title,
                'source': item.source_id,
                'status': item.status,
                'chapters': [
                    {
                        'id': ch['id'],
                        'chapter': ch.get('chapter', '0'),
                        'title': ch.get('title', f"Chapter {ch.get('chapter', '0')}")
                    } for ch in item.chapters
                ],
                'current_chapter': item.current_chapter_index,
                'current_page': item.current_page,
                'total_pages': item.total_pages,
                'error': item.error
            })

        return {
            'queue': queue_data,
            'paused_count': paused_count
        }
```

**Step 5: Test backend changes**

Run: Start Flask server
Expected: No errors on startup

**Step 6: Commit**

```bash
git add manganegus_app/extensions.py
git commit -m "feat: add passive queue backend support

- Add paused_queue status for downloads
- Add start_immediately parameter to add_to_queue
- Add start_paused_items method
- Include paused_count in queue response"
```

---

## Task 9: Backend - Add API Endpoints for Passive Queue

**Files:**
- Modify: `manganegus_app/routes/downloads_api.py:20` (download endpoint)
- Modify: `manganegus_app/routes/downloads_api.py:95` (add new endpoint)
- Modify: `manganegus_app/routes/downloads_api.py:50` (get_queue endpoint)

**Step 1: Update download endpoint to accept start_immediately**

Find `/api/download` endpoint (around line 20) and modify:
```python
@downloads_bp.route('/api/download', methods=['POST'])
@csrf_protect
def download_chapter():
    """Add chapters to download queue."""
    data = request.get_json(silent=True) or {}

    chapters = data.get('chapters', [])
    title = data.get('title', 'Unknown Manga')
    source_id = data.get('source', 'unknown')
    manga_id = data.get('manga_id', '')
    start_immediately = data.get('start_immediately', True)  # NEW

    if not chapters:
        return jsonify({'error': 'No chapters provided'}), 400

    job_id = downloader.add_to_queue(
        chapters=chapters,
        title=title,
        source_id=source_id,
        manga_id=manga_id,
        start_immediately=start_immediately  # NEW
    )

    return jsonify({
        'status': 'ok',
        'job_id': job_id,
        'message': f'{"Queued" if start_immediately else "Added to passive queue"} {len(chapters)} chapter(s)'
    })
```

**Step 2: Update get_queue endpoint to return dict**

Find `/api/download/queue` endpoint (around line 50) and ensure it returns the dict from get_queue():
```python
@downloads_bp.route('/api/download/queue', methods=['GET'])
def get_download_queue():
    """Get the current download queue status."""
    queue_data = downloader.get_queue()
    return jsonify(queue_data)  # Now returns dict with 'queue' and 'paused_count'
```

**Step 3: Add new endpoint for starting paused items**

Add new endpoint after the queue endpoint:
```python
@downloads_bp.route('/api/download/start_paused', methods=['POST'])
@csrf_protect
def start_paused_downloads():
    """Start paused queue items.

    Body: { job_ids: ["id1", "id2"] }  // Empty array or omit to start all
    """
    data = request.get_json(silent=True) or {}
    job_ids = data.get('job_ids')  # None or list of IDs

    downloader.start_paused_items(job_ids)

    return jsonify({
        'status': 'ok',
        'message': 'Paused downloads started'
    })
```

**Step 4: Test API endpoints**

Run: Start server
Expected: No errors

Run: curl test (passive queue):
```bash
curl -X POST http://localhost:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{"chapters":[{"id":"123","chapter":"1"}],"title":"Test","source":"test","start_immediately":false}'
```
Expected: 200 response, job added with paused_queue status

**Step 5: Commit**

```bash
git add manganegus_app/routes/downloads_api.py
git commit -m "feat: add passive queue API endpoints

- Update /api/download to accept start_immediately param
- Update /api/download/queue to return paused_count
- Add /api/download/start_paused endpoint"
```

---

## Task 10: Frontend - Add Passive Queue API Methods

**Files:**
- Modify: `static/js/main.js:260` (API object)

**Step 1: Add API methods for passive queue**

Find the `API` object (around line 260) and add:
```javascript
async startPausedDownloads(jobIds = null) {
    const data = await this.request('/api/download/start_paused', {
        method: 'POST',
        body: JSON.stringify({ job_ids: jobIds })
    });
    return data;
},
```

**Step 2: Modify downloadChapter to accept start_immediately**

Find `API.downloadChapter` and add parameter:
```javascript
async downloadChapter(mangaId, chapterId, source, title, chapterTitle, chapterNumber = '0', startImmediately = true) {
    const chapters = [{
        id: chapterId,
        chapter: chapterNumber,
        title: chapterTitle
    }];
    const data = await this.request('/api/download', {
        method: 'POST',
        body: JSON.stringify({
            chapters,
            title,
            source,
            manga_id: mangaId,
            start_immediately: startImmediately
        })
    });
    return data;
},
```

**Step 3: Add downloadChapters with start_immediately**

Find `API.downloadChapters` and add parameter:
```javascript
async downloadChapters(mangaId, chapters, source, title, startImmediately = true) {
    const data = await this.request('/api/download', {
        method: 'POST',
        body: JSON.stringify({
            chapters,
            title,
            source,
            manga_id: mangaId,
            start_immediately: startImmediately
        })
    });
    return data;
},
```

**Step 4: Commit**

```bash
git add static/js/main.js
git commit -m "feat: add passive queue API methods

- Add startPausedDownloads API method
- Add start_immediately parameter to download methods"
```

---

## Task 11: Frontend - Implement Passive Queue UI

**Files:**
- Modify: `static/js/main.js:3200` (add passive queue functions)
- Modify: `static/js/main.js:580` (modify fetchDownloadQueue)
- Modify: `static/js/main.js:620` (modify renderDownloadQueue)

**Step 1: Add passive queue functions**

Add after selection mode functions:
```javascript
// ==================== Passive Download Queue ====================

async function queueDownloadPassive(mangaId, source, title) {
    // Show chapter selection modal (reuse existing modal)
    state.currentManga = { id: mangaId, source, title };

    try {
        log(`📋 Loading chapters for passive queue: ${title}`);
        const chapters = await API.getChapters(mangaId, source);

        if (!chapters || chapters.length === 0) {
            showToast('No chapters available');
            return;
        }

        // Show modal with chapters
        // For now, just queue first chapter as demo
        await API.downloadChapter(
            mangaId,
            chapters[0].id,
            source,
            title,
            chapters[0].title || `Chapter ${chapters[0].chapter}`,
            chapters[0].chapter,
            false  // start_immediately = false
        );

        showToast('Added to passive queue');
        await fetchDownloadQueue();

    } catch (error) {
        log(`❌ Failed to queue download: ${error.message}`);
        showToast('Failed to queue download');
    }
}

async function startAllPaused() {
    try {
        await API.startPausedDownloads();
        showToast('Starting paused downloads');
        await fetchDownloadQueue();
    } catch (error) {
        log(`❌ Failed to start paused: ${error.message}`);
        showToast('Failed to start downloads');
    }
}

async function startPausedItem(jobId) {
    try {
        await API.startPausedDownloads([jobId]);
        showToast('Starting download');
        await fetchDownloadQueue();
    } catch (error) {
        log(`❌ Failed to start: ${error.message}`);
        showToast('Failed to start download');
    }
}
```

**Step 2: Modify fetchDownloadQueue to handle paused count**

Find `fetchDownloadQueue()` (around line 580) and update:
```javascript
async function fetchDownloadQueue() {
    try {
        const data = await API.getDownloadQueue();
        state.downloadQueue = data.queue || [];

        // Update paused badge
        const pausedCount = data.paused_count || 0;
        if (pausedCount > 0) {
            els.pausedBadge.textContent = pausedCount;
            els.pausedBadge.classList.remove('hidden');
        } else {
            els.pausedBadge.classList.add('hidden');
        }

        renderDownloadQueue();
    } catch (error) {
        log(`❌ Failed to fetch queue: ${error.message}`);
    }
}
```

**Step 3: Modify renderDownloadQueue to show sections**

Find `renderDownloadQueue()` (around line 620) and update:
```javascript
function renderDownloadQueue() {
    if (!state.downloadQueue || state.downloadQueue.length === 0) {
        els.queueList.innerHTML = '<p style="padding: 16px; color: var(--text-muted); text-align: center;">Queue is empty</p>';
        return;
    }

    // Separate by status
    const paused = state.downloadQueue.filter(item => item.status === 'paused_queue');
    const active = state.downloadQueue.filter(item =>
        ['queued', 'downloading', 'paused'].includes(item.status)
    );
    const completed = state.downloadQueue.filter(item =>
        ['completed', 'failed', 'cancelled'].includes(item.status)
    );

    let html = '';

    // Paused section
    if (paused.length > 0) {
        html += `
            <div class="queue-section">
                <div class="queue-section-header">
                    <h3>Paused Queue (${paused.length})</h3>
                    <button class="btn-start-all" id="btn-start-all-paused">Start All</button>
                </div>
                ${paused.map(item => renderQueueItem(item, true)).join('')}
            </div>
        `;
    }

    // Active section
    if (active.length > 0) {
        html += `
            <div class="queue-section">
                <h3>Active Downloads (${active.length})</h3>
                ${active.map(item => renderQueueItem(item, false)).join('')}
            </div>
        `;
    }

    // Completed section
    if (completed.length > 0) {
        html += `
            <div class="queue-section">
                <h3>Completed (${completed.length})</h3>
                ${completed.map(item => renderQueueItem(item, false)).join('')}
            </div>
        `;
    }

    els.queueList.innerHTML = html;

    // Add event listener for "Start All" button
    const startAllBtn = document.getElementById('btn-start-all-paused');
    if (startAllBtn) {
        startAllBtn.addEventListener('click', startAllPaused);
    }

    // Add event listeners for individual start buttons
    document.querySelectorAll('.btn-start-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const jobId = btn.dataset.jobId;
            startPausedItem(jobId);
        });
    });
}

function renderQueueItem(item, isPaused) {
    const statusClass = item.status === 'completed' ? 'completed' :
                       item.status === 'failed' ? 'failed' :
                       item.status === 'downloading' ? 'downloading' : '';

    const progress = item.total_pages > 0 ?
        Math.round((item.current_page / item.total_pages) * 100) : 0;

    return `
        <div class="queue-item ${statusClass}" data-job-id="${item.job_id}">
            <div class="queue-item-info">
                <div class="queue-item-title">${escapeHtml(item.title)}</div>
                <div class="queue-item-meta">
                    ${item.chapters.length} chapter(s) · ${item.source}
                    ${item.status === 'downloading' ? ` · ${progress}%` : ''}
                </div>
            </div>
            <div class="queue-item-actions">
                ${isPaused ? `
                    <button class="btn-start-item icon-btn" data-job-id="${item.job_id}" title="Start download">
                        <i data-lucide="play" width="16"></i>
                    </button>
                ` : ''}
                ${item.status === 'downloading' ? `
                    <button class="icon-btn" onclick="pauseQueueItem('${item.job_id}')">
                        <i data-lucide="pause" width="16"></i>
                    </button>
                ` : ''}
                ${item.status === 'paused' ? `
                    <button class="icon-btn" onclick="resumeQueueItem('${item.job_id}')">
                        <i data-lucide="play" width="16"></i>
                    </button>
                ` : ''}
                <button class="icon-btn" onclick="cancelQueueItem('${item.job_id}')">
                    <i data-lucide="x" width="16"></i>
                </button>
            </div>
        </div>
    `;
}
```

**Step 4: Test passive queue**

Run: Discovery → "⋮" → "Queue Download"
Expected: Chapter added to passive queue, badge shows "1"

Run: Click downloads button → See paused section
Expected: "Paused Queue (1)" section with "Start All" button

Run: Click "Start All"
Expected: Download begins, badge clears

**Step 5: Commit**

```bash
git add static/js/main.js
git commit -m "feat: implement passive queue UI

- Queue downloads without auto-start
- Paused badge on downloads button
- Queue modal with sections (Paused, Active, Completed)
- Start All and individual start buttons
- Update queue rendering for new structure"
```

---

## Task 12: Final Testing and Polish

**Files:**
- Test all features end-to-end

**Step 1: Test single removal**

Run: Library → "⋮" → Remove → Confirm
Expected: ✅ Manga removed, library refreshes

**Step 2: Test multi-select deletion**

Run: Library → "⋮" → Select Multiple → Click 3 cards → Delete Selected
Expected: ✅ Confirmation modal → All 3 deleted

**Step 3: Test passive queue**

Run: Discovery → "⋮" → Queue Download → Add
Expected: ✅ Badge shows count, paused section in queue

Run: Queue modal → Start All
Expected: ✅ Downloads begin

**Step 4: Test title cycling**

Run: Click app title 3 times
Expected: ✅ Cycles through Manga Negus → Manga King → マンガキング

Run: Wait 30 seconds
Expected: ✅ Auto-cycles

**Step 5: Test menu positioning**

Run: Card at bottom of screen → "⋮"
Expected: ✅ Menu flips up to stay on screen

**Step 6: Create final commit**

```bash
git add -A
git commit -m "feat: library management enhancements complete

Complete implementation:
- Fixed broken remove button
- Card menus (library and discovery contexts)
- Multi-select deletion mode with checkboxes
- Passive download queue with start confirmation
- Animated title cycling (auto + manual)
- Menu positioning with flip-up
- Queue sections (Paused, Active, Completed)
- Paused queue badge

All features tested and working."
```

---

## Task 13: Push to GitHub

**Files:**
- Push all commits

**Step 1: Push to main**

```bash
git push origin main
```

**Step 2: Verify on GitHub**

Visit: https://github.com/bookers1897/Manga-Negus
Expected: All commits visible, code updated

---

## Success Criteria

- ✅ Remove button works (calls API.removeFromLibrary)
- ✅ Card menus appear in library and discovery views
- ✅ Multi-select mode with checkboxes and bulk delete
- ✅ Passive queue prevents auto-downloading
- ✅ Title cycles automatically every 30s and on click
- ✅ Paused badge shows count on downloads button
- ✅ Queue modal has three sections
- ✅ Menu positioning works at screen edges
- ✅ All features work without errors

## Next Steps (Out of Scope)

After this implementation is complete, consider:
- Chapter read markers (roadmap feature)
- Advanced search filters (roadmap feature)
- MangaPlus support (roadmap feature)
- Webtoon vertical scroll support
- Swipe gestures for mobile
- Offline CBZ reader
