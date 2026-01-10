// MangaNegus Redesign - Main Application
// Integrates with existing Flask backend APIs

// ========================================
// State Management
// ========================================
const state = {
    activeView: 'discover',
    previousView: 'discover', // Track previous view for back button
    activeFilter: 'all',
    searchMode: 'title', // 'title' or 'url'
    searchQuery: '',
    searchHistory: [],
    liveSuggestions: [],
    suggestionTimer: null,
    currentSource: '',
    sources: [],
    library: [],
    currentManga: null,
    currentLibraryKey: null,
    lastRead: null,
    currentChapters: [],
    selectedChapters: new Set(),
    currentPage: 1,
    totalPages: 1,
    totalChaptersCount: 0,
    currentChaptersOffset: 0,
    history: [],
    viewPages: {
        discover: 1,
        popular: 1,
        trending: 1,
        history: 1,
    },
    readerPages: [],
    readerCurrentPage: 0,
    readerMode: 'strip', // 'strip' or 'paged'
    readerFitMode: 'fit-width', // 'fit-width', 'fit-height', 'fit-screen', 'fit-original'
    theme: 'dark', // 'dark', 'light', 'oled', 'sepia'
    readerObserver: null,
    readerImmersive: false,
    readerScrollRaf: null,
    progressSaveTimer: null,
    prefetchedChapterId: null,
    prefetchedChapterTitle: null,
    prefetchedPages: null,
    prefetchInFlight: false,
    currentChapterId: null,
    currentChapterTitle: '',
    currentChapterNumber: null,
    currentChapterIndex: -1,
    continueEntry: null,
    isSidebarOpen: false,
    csrfToken: '',
    toastTimer: null,
    // Download Queue
    downloadQueue: [],
    queuePaused: false,
    queuePollInterval: null,
    // AbortControllers for cancelling in-flight requests (race condition prevention)
    chaptersAbortController: null,
    searchAbortController: null
};

const PLACEHOLDER_COVER = '/static/images/placeholder.png';

// ========================================
// DOM Elements (will be initialized after DOM is ready)
// ========================================
let els = {};

// ========================================
// API Integration
// ========================================
const API = {
    async request(endpoint, options = {}) {
        try {
            const { silent, ...requestOptions } = options;
            const headers = {
                'Content-Type': 'application/json',
                ...requestOptions.headers
            };

            if (requestOptions.method === 'POST' && state.csrfToken) {
                headers['X-CSRF-Token'] = state.csrfToken;
            }

            // Support AbortController signal for request cancellation
            const fetchOptions = {
                ...requestOptions,
                headers
            };
            if (requestOptions.signal) {
                fetchOptions.signal = requestOptions.signal;
            }

            const response = await fetch(endpoint, fetchOptions);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            // Don't log or show toast for aborted requests
            if (error.name === 'AbortError') {
                throw error;
            }
            console.error(`API Error (${endpoint}):`, error);
            if (!options.silent) {
                showToast(`Error: ${error.message}`);
            }
            throw error;
        }
    },

    async getCsrfToken() {
        const data = await this.request('/api/csrf-token');
        state.csrfToken = data.csrf_token;
        return data.csrf_token;
    },

    async getSources() {
        const data = await this.request('/api/sources');
        return Array.isArray(data) ? data : (data.sources || []);
    },

    async getSourceHealth() {
        const data = await this.request('/api/sources/health');
        return data || {};
    },

    async search(query, limit = 15, signal = undefined) {
        const data = await this.request('/api/search', {
            method: 'POST',
            body: JSON.stringify({ query, limit }),
            signal
        });
        return data || [];
    },

    async searchSuggestions(query, limit = 6, signal = undefined) {
        const data = await this.request('/api/search', {
            method: 'POST',
            body: JSON.stringify({ query, limit }),
            signal,
            silent: true
        });
        return data || [];
    },

    async detectUrl(url) {
        const data = await this.request('/api/detect_url', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
        return data;
    },

    async getPopular(page = 1, limit = 24) {
        const data = await this.request(`/api/popular?page=${page}&limit=${limit}`);
        return Array.isArray(data) ? data : [];
    },

    async getTrending(page = 1, limit = 24) {
        const data = await this.request(`/api/trending?page=${page}&limit=${limit}`);
        return Array.isArray(data) ? data : [];
    },

    async getDiscover(page = 1, limit = 20) {
        const data = await this.request(`/api/discover?page=${page}&limit=${limit}`);
        return Array.isArray(data) ? data : [];
    },

    async getLatestFeed(sourceId = '', page = 1) {
        const url = `/api/latest_feed?page=${page}${sourceId ? `&source_id=${encodeURIComponent(sourceId)}` : ''}`;
        const data = await this.request(url);
        return Array.isArray(data) ? data : [];
    },

    async getHistory(limit = 50) {
        const data = await this.request(`/api/history?limit=${limit}`);
        return Array.isArray(data) ? data : [];
    },

    async addHistory(entry) {
        return this.request('/api/history', {
            method: 'POST',
            body: JSON.stringify(entry)
        });
    },

    async getChapters(mangaId, source, page = 1) {
        const data = await this.request('/api/chapters', {
            method: 'POST',
            body: JSON.stringify({ manga_id: mangaId, source, page })
        });
        return data;
    },

    async getChapterPages(chapterId, source) {
        console.log('[API DEBUG] getChapterPages called', { chapter_id: chapterId, source });
        const data = await this.request('/api/chapter_pages', {
            method: 'POST',
            body: JSON.stringify({ chapter_id: chapterId, source })
        });
        console.log('[API DEBUG] chapter_pages response:', data);
        const pages = data.pages || [];
        console.log('[API DEBUG] Extracted pages:', pages);
        return pages;
    },

    async getLibrary() {
        const data = await this.request('/api/library');
        // Convert dict to array
        return Object.entries(data).map(([key, value]) => ({
            key,
            ...value
        }));
    },

    async addToLibrary(mangaId, source, title, cover, status) {
        const data = await this.request('/api/library/save', {
            method: 'POST',
            body: JSON.stringify({
                id: mangaId,
                title,
                source,
                cover,
                status
            })
        });
        return data;
    },

    async updateStatus(key, status) {
        const data = await this.request('/api/library/update_status', {
            method: 'POST',
            body: JSON.stringify({ key, status })
        });
        return data;
    },

    async updateProgress(key, chapter, page = null, chapterId = null, totalChapters = null) {
        const payload = { key, chapter };
        if (page !== null) payload.page = page;
        if (chapterId) payload.chapter_id = chapterId;
        if (totalChapters !== null) payload.total_chapters = totalChapters;
        const data = await this.request('/api/library/update_progress', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        return data;
    },

    async removeFromLibrary(key) {
        const data = await this.request('/api/library/delete', {
            method: 'POST',
            body: JSON.stringify({ key })
        });
        return data;
    },

    async downloadChapter(mangaId, chapterId, source, title, chapterTitle, chapterNumber = '0') {
        // Backend expects chapters as a list
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
                manga_id: mangaId
            })
        });
        return data;
    },

    async downloadChapters(mangaId, chapters, source, title) {
        const data = await this.request('/api/download', {
            method: 'POST',
            body: JSON.stringify({
                chapters,
                title,
                source,
                manga_id: mangaId
            })
        });
        return data;
    },

    // Download Queue API
    async getDownloadQueue() {
        const data = await this.request('/api/download/queue');
        return data;
    },

    async pauseDownloads(jobId = null) {
        const data = await this.request('/api/download/pause', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId })
        });
        return data;
    },

    async resumeDownloads(jobId = null) {
        const data = await this.request('/api/download/resume', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId })
        });
        return data;
    },

    async cancelDownload(jobId) {
        const data = await this.request('/api/download/cancel', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId })
        });
        return data;
    },

    async clearCompletedDownloads() {
        const data = await this.request('/api/download/clear', {
            method: 'POST',
            body: JSON.stringify({})
        });
        return data;
    },

    async removeFromQueue(jobId) {
        const data = await this.request('/api/download/remove', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId })
        });
        return data;
    }
};

// ========================================
// UI Utilities
// ========================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function safeCreateIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
    }
}

function showToast(message) {
    if (state.toastTimer) clearTimeout(state.toastTimer);
    els.toastMessage.textContent = message;
    els.toast.classList.add('visible');
    state.toastTimer = setTimeout(() => {
        els.toast.classList.remove('visible');
    }, 3000);
}

function log(message) {
    const line = document.createElement('div');
    line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    line.style.marginBottom = '4px';
    els.consoleContent.appendChild(line);
    els.consoleContent.scrollTop = els.consoleContent.scrollHeight;
}

// ========================================
// Download Queue Management
// ========================================
async function fetchDownloadQueue() {
    try {
        const data = await API.getDownloadQueue();
        state.downloadQueue = data.queue || [];
        state.queuePaused = data.paused || false;
        updateQueueBadge();
        return data;
    } catch (error) {
        console.error('[Queue] Failed to fetch queue:', error);
        return { queue: [], paused: false };
    }
}

function updateQueueBadge() {
    const activeCount = state.downloadQueue.filter(
        item => ['queued', 'downloading', 'paused'].includes(item.status)
    ).length;

    if (activeCount > 0) {
        els.queueBadge.textContent = activeCount;
        els.queueBadge.classList.remove('hidden');
    } else {
        els.queueBadge.classList.add('hidden');
    }
}

function renderDownloadQueue() {
    if (!state.downloadQueue || state.downloadQueue.length === 0) {
        els.queueList.innerHTML = `
            <div class="empty-state">
                <p class="empty-title">No Downloads</p>
                <p class="empty-text">Download queue is empty</p>
            </div>
        `;
        els.queueSubtitle.textContent = 'No active downloads';
        return;
    }

    const activeCount = state.downloadQueue.filter(
        item => ['queued', 'downloading', 'paused'].includes(item.status)
    ).length;
    els.queueSubtitle.textContent = `${activeCount} active, ${state.downloadQueue.length} total`;

    const html = state.downloadQueue.map(item => {
        const progress = item.chapters_total > 0
            ? Math.round((item.chapters_done / item.chapters_total) * 100)
            : 0;

        const pageProgress = item.total_pages > 0
            ? `Page ${item.current_page}/${item.total_pages}`
            : '';

        let actions = '';
        if (item.status === 'downloading') {
            actions = `
                <button class="control-btn" onclick="pauseQueueItem('${item.job_id}')">
                    <i data-lucide="pause" width="12"></i> Pause
                </button>
                <button class="control-btn" onclick="cancelQueueItem('${item.job_id}')">
                    <i data-lucide="x" width="12"></i> Cancel
                </button>
            `;
        } else if (item.status === 'paused') {
            actions = `
                <button class="control-btn primary" onclick="resumeQueueItem('${item.job_id}')">
                    <i data-lucide="play" width="12"></i> Resume
                </button>
                <button class="control-btn" onclick="cancelQueueItem('${item.job_id}')">
                    <i data-lucide="x" width="12"></i> Cancel
                </button>
            `;
        } else if (item.status === 'queued') {
            actions = `
                <button class="control-btn" onclick="removeQueueItem('${item.job_id}')">
                    <i data-lucide="trash-2" width="12"></i> Remove
                </button>
            `;
        } else {
            actions = `
                <button class="control-btn" onclick="removeQueueItem('${item.job_id}')">
                    <i data-lucide="trash-2" width="12"></i> Remove
                </button>
            `;
        }

        return `
            <div class="queue-item ${item.status}">
                <div class="queue-item-header">
                    <span class="queue-item-title">${escapeHtml(item.title)}</span>
                    <span class="queue-item-status ${item.status}">${item.status}</span>
                </div>
                <div class="queue-item-progress">
                    <div class="queue-progress-bar">
                        <div class="queue-progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <span class="queue-progress-text">
                        Chapter ${item.chapters_done}/${item.chapters_total} (${progress}%)
                        ${pageProgress ? ' - ' + pageProgress : ''}
                    </span>
                </div>
                <div class="queue-item-actions">${actions}</div>
            </div>
        `;
    }).join('');

    els.queueList.innerHTML = html;
    safeCreateIcons();
}

async function pauseQueueItem(jobId) {
    try {
        await API.pauseDownloads(jobId);
        await fetchDownloadQueue();
        renderDownloadQueue();
        showToast('Download paused');
    } catch (error) {
        showToast('Failed to pause download');
    }
}

async function resumeQueueItem(jobId) {
    try {
        await API.resumeDownloads(jobId);
        await fetchDownloadQueue();
        renderDownloadQueue();
        showToast('Download resumed');
    } catch (error) {
        showToast('Failed to resume download');
    }
}

async function cancelQueueItem(jobId) {
    try {
        await API.cancelDownload(jobId);
        await fetchDownloadQueue();
        renderDownloadQueue();
        showToast('Download cancelled');
    } catch (error) {
        showToast('Failed to cancel download');
    }
}

async function removeQueueItem(jobId) {
    try {
        await API.removeFromQueue(jobId);
        await fetchDownloadQueue();
        renderDownloadQueue();
    } catch (error) {
        showToast('Failed to remove from queue');
    }
}

async function pauseAllDownloads() {
    try {
        await API.pauseDownloads();
        state.queuePaused = true;
        await fetchDownloadQueue();
        renderDownloadQueue();
        showToast('All downloads paused');
    } catch (error) {
        showToast('Failed to pause downloads');
    }
}

async function resumeAllDownloads() {
    try {
        await API.resumeDownloads();
        state.queuePaused = false;
        await fetchDownloadQueue();
        renderDownloadQueue();
        showToast('Downloads resumed');
    } catch (error) {
        showToast('Failed to resume downloads');
    }
}

async function clearCompletedDownloads() {
    try {
        const data = await API.clearCompletedDownloads();
        await fetchDownloadQueue();
        renderDownloadQueue();
        showToast(`Cleared ${data.removed || 0} completed downloads`);
    } catch (error) {
        showToast('Failed to clear completed');
    }
}

function openDownloadQueue() {
    fetchDownloadQueue().then(() => {
        renderDownloadQueue();
        els.downloadQueueModal.classList.add('active');

        // Start polling for updates
        if (state.queuePollInterval) clearInterval(state.queuePollInterval);
        state.queuePollInterval = setInterval(async () => {
            const hasActive = state.downloadQueue.some(
                item => item.status === 'downloading'
            );
            if (hasActive) {
                await fetchDownloadQueue();
                renderDownloadQueue();
            }
        }, 2000);
    });
}

function closeDownloadQueue() {
    els.downloadQueueModal.classList.remove('active');
    if (state.queuePollInterval) {
        clearInterval(state.queuePollInterval);
        state.queuePollInterval = null;
    }
}

// Make queue functions globally accessible for onclick handlers
window.pauseQueueItem = pauseQueueItem;
window.resumeQueueItem = resumeQueueItem;
window.cancelQueueItem = cancelQueueItem;
window.removeQueueItem = removeQueueItem;

// ========================================
// Sidebar & Navigation
// ========================================
function toggleSidebar() {
    // Check actual DOM state, not state variable
    const isOpen = els.sidebar.classList.contains('is-open');
    console.log('[DEBUG] toggleSidebar - isOpen:', isOpen);

    if (isOpen) {
        closeSidebar();
    } else {
        openSidebar();
    }
}

function openSidebar() {
    console.log('[DEBUG] openSidebar called');
    els.sidebar.classList.add('is-open');
    els.overlay.classList.add('active');
    els.menuBtn.classList.add('active');
    if (window.innerWidth >= 1024) {
        els.body.classList.add('sidebar-expanded');
    }
    state.isSidebarOpen = true;
    console.log('[DEBUG] Sidebar opened - classes:', els.sidebar.className);
}

function closeSidebar() {
    console.log('[DEBUG] closeSidebar called');
    els.sidebar.classList.remove('is-open');
    els.overlay.classList.remove('active');
    els.menuBtn.classList.remove('active');
    els.body.classList.remove('sidebar-expanded');
    state.isSidebarOpen = false;
    console.log('[DEBUG] Sidebar closed - classes:', els.sidebar.className);
}

function setSidebar(isOpen) {
    if (isOpen) {
        openSidebar();
    } else {
        closeSidebar();
    }
}

function renderNav() {
    const navItems = [
        { id: 'discover', label: 'Discover', icon: 'compass' },
        { id: 'trending', label: 'Trending', icon: 'trending-up' },
        { id: 'popular', label: 'Popular', icon: 'flame' },
        { id: 'library', label: 'Library', icon: 'library', count: state.library.length },
        { id: 'history', label: 'History', icon: 'clock' }
    ];

    els.navList.innerHTML = `<p class="nav-label">Menu</p>` +
        navItems.map(item => {
            const isActive = state.activeView === item.id;
            const count = item.count || 0;

            return `
                <button data-view="${item.id}" class="nav-item ${isActive ? 'active' : ''}">
                    <i data-lucide="${item.icon}"></i>
                    <span class="nav-text">${escapeHtml(item.label)}</span>
                    ${count > 0 ? `<span class="nav-count">${count}</span>` : ''}
                </button>
            `;
        }).join('');

    safeCreateIcons();
    // Event delegation handled by setupEventDelegation() - no per-button listeners needed
}

function renderSources() {
    console.log('[DEBUG] renderSources called');
    console.log('[DEBUG] els.sourceList:', els.sourceList);
    console.log('[DEBUG] state.sources.length:', state.sources.length);

    if (!els.sourceList) {
        log('❌ Source list element not found');
        console.error('[ERROR] els.sourceList is null or undefined');
        return;
    }

    if (state.sources.length === 0) {
        els.sourceList.innerHTML = '<p style="padding: 0 24px; color: var(--text-muted); font-size: 12px;">Loading sources...</p>';
        console.log('[DEBUG] No sources, showing loading message');
        return;
    }

    log(`Rendering ${state.sources.length} sources...`);

    // Show only top sources for cleaner sidebar
    const topSources = [
        'weebcentral-v2',
        'mangadex',
        'manganato',
        'mangafire-v2',
        'mangasee-v2',
        'asurascans'
    ];

    const displaySources = state.sources.filter(s => topSources.includes(s.id));
    const otherSources = state.sources.filter(s => !topSources.includes(s.id));

    // If no top sources found, show first 6
    const sourcesToDisplay = displaySources.length > 0 ? displaySources : state.sources.slice(0, 6);

    els.sourceList.innerHTML = sourcesToDisplay.map(source => {
        const isActive = state.currentSource === source.id;
        return `
            <button class="source-btn ${isActive ? 'active' : ''}" data-source="${escapeHtml(source.id)}">
                <span>${escapeHtml(source.name)}</span>
                ${isActive ? '<div class="status-dot"></div>' : ''}
            </button>
        `;
    }).join('');

    // Add "All Sources" button
    els.sourceList.innerHTML += `
        <button class="source-btn" id="show-all-sources-btn">
            <span>All Sources (${state.sources.length})</span>
            <i data-lucide="chevron-right" width="16"></i>
        </button>
    `;

    safeCreateIcons();
    // Event delegation handled by setupEventDelegation() - no per-button listeners needed

    log(`✅ Rendered ${sourcesToDisplay.length} sources in sidebar`);
}

function setSource(sourceId) {
    state.currentSource = sourceId;
    renderSources();
    if (state.activeView === 'discover' && !state.searchQuery) {
        loadPopular();
    }
    showToast(`Source: ${state.sources.find(s => s.id === sourceId)?.name || sourceId}`);
}

async function showSourceStatus() {
    els.sourceStatusModal.classList.add('active');
    els.sourceStatusGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Checking sources...</span>
        </div>
    `;

    try {
        const health = await API.getSourceHealth();
        const sourceCards = (health.sources || []).map(source => `
            <div class="source-status-item">
                <span class="source-status-name">${escapeHtml(source.name)}</span>
                <div class="source-status-indicator">
                    <div class="status-dot ${source.is_available ? '' : 'offline'}"></div>
                    <span>${source.is_available ? 'ONLINE' : 'OFFLINE'}</span>
                </div>
                ${source.last_error ? `<p class="source-status-note">${escapeHtml(source.last_error)}</p>` : ''}
            </div>
        `);

        const skippedCards = (health.skipped || []).map(s => `
            <div class="source-status-item">
                <span class="source-status-name">${escapeHtml(s.name)} (skipped)</span>
                <div class="source-status-indicator">
                    <div class="status-dot offline"></div>
                    <span>SKIPPED</span>
                </div>
                <p class="source-status-note">Reason: ${escapeHtml(s.reason || 'disabled')}</p>
            </div>
        `);

        els.sourceStatusGrid.innerHTML = [...sourceCards, ...skippedCards].join('') || '<p style="padding: 24px; text-align: center; color: var(--text-muted);">No sources available</p>';
        safeCreateIcons();
    } catch (error) {
        els.sourceStatusGrid.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">Failed to load sources</p>';
    }
}

// ========================================
// View Management
// ========================================
function setView(viewId) {
    // Track previous view (but not if we're going to details view)
    if (viewId !== 'details' && state.activeView !== 'details') {
        state.previousView = state.activeView;
    }
    state.activeView = viewId;
    hidePagination();

    // Hide all views
    els.discoverView.classList.add('hidden');
    els.libraryView.classList.add('hidden');
    els.detailsView.classList.add('hidden');

    // Show active view
    switch (viewId) {
        case 'discover':
            els.discoverView.classList.remove('hidden');
            els.discoverTitle.textContent = 'Discover';
            state.viewPages.discover = 1;
            if (!state.searchQuery) loadDiscover(1);
            break;
        case 'trending':
            els.discoverView.classList.remove('hidden');
            els.discoverTitle.textContent = 'Trending';
            state.viewPages.trending = 1;
            loadTrendingView(1);
            break;
        case 'popular':
            els.discoverView.classList.remove('hidden');
            els.discoverTitle.textContent = 'Popular';
            state.viewPages.popular = 1;
            loadPopular(1);
            break;
        case 'library':
            els.libraryView.classList.remove('hidden');
            loadLibrary();
            break;
        case 'history':
            els.discoverView.classList.remove('hidden');
            els.discoverTitle.textContent = 'History';
            state.viewPages.history = 1;
            loadHistory();
            break;
        case 'details':
            els.detailsView.classList.remove('hidden');
            break;
    }

    renderNav();
    if (window.innerWidth < 1024) closeSidebar();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateDiscoverSubtitle(text) {
    if (els.discoverSubtitle) {
        els.discoverSubtitle.textContent = text;
    }
}

// ========================================
// Search Suggestions + History
// ========================================
function loadSearchHistory() {
    try {
        const raw = localStorage.getItem('manganegus.searchHistory');
        state.searchHistory = raw ? JSON.parse(raw) : [];
    } catch {
        state.searchHistory = [];
    }
}

function loadLastRead() {
    try {
        const raw = localStorage.getItem('manganegus.lastRead');
        state.lastRead = raw ? JSON.parse(raw) : null;
    } catch {
        state.lastRead = null;
    }
}

function saveLastRead(entry) {
    state.lastRead = entry;
    try {
        localStorage.setItem('manganegus.lastRead', JSON.stringify(entry));
    } catch {
        // Ignore storage failures
    }
}

function clearLiveSuggestions() {
    state.liveSuggestions = [];
    if (state.searchAbortController) {
        state.searchAbortController.abort();
        state.searchAbortController = null;
    }
}

function saveSearchHistory(query) {
    const trimmed = query.trim();
    if (!trimmed) return;
    const existing = state.searchHistory.filter(item => item.toLowerCase() !== trimmed.toLowerCase());
    state.searchHistory = [trimmed, ...existing].slice(0, 8);
    localStorage.setItem('manganegus.searchHistory', JSON.stringify(state.searchHistory));
}

function renderSearchSuggestions(query) {
    if (!els.searchSuggestions) return;
    if (state.searchMode === 'url') {
        hideSearchSuggestions();
        return;
    }
    const needle = (query || '').toLowerCase();
    const historyMatches = needle
        ? state.searchHistory.filter(item => item.toLowerCase().includes(needle))
        : state.searchHistory;
    const liveMatches = (state.liveSuggestions || []).map(item => ({
        title: item.title || item.name || '',
        payload: item
    })).filter(item => item.title);

    if (historyMatches.length === 0 && liveMatches.length === 0) {
        els.searchSuggestions.classList.add('hidden');
        els.searchSuggestions.innerHTML = '';
        return;
    }

    const used = new Set(historyMatches.map(item => item.toLowerCase()));
    const liveUnique = liveMatches.filter(item => !used.has(item.title.toLowerCase())).slice(0, 6);

    let html = '';
    if (liveUnique.length > 0) {
        html += `<div class="search-suggestion-header">Suggestions</div>`;
        html += liveUnique.map(item => `
        <div class="search-suggestion-item" data-value="${escapeHtml(item.title)}">
            <span class="label">${escapeHtml(item.title)}</span>
            <span class="hint">Live</span>
        </div>
        `).join('');
    }

    if (historyMatches.length > 0) {
        html += `<div class="search-suggestion-header">Recent</div>`;
        html += historyMatches.map(item => `
        <div class="search-suggestion-item" data-value="${escapeHtml(item)}">
            <span class="label">${escapeHtml(item)}</span>
            <span class="hint">Recent</span>
        </div>
        `).join('');
        html += `
            <div class="search-suggestion-item" data-action="clear">
                <span class="label">Clear search history</span>
            </div>
        `;
    }

    els.searchSuggestions.innerHTML = html;
    els.searchSuggestions.classList.remove('hidden');
}

function hideSearchSuggestions() {
    if (els.searchSuggestions) {
        els.searchSuggestions.classList.add('hidden');
    }
}

function scheduleLiveSuggestions(query) {
    if (state.suggestionTimer) {
        clearTimeout(state.suggestionTimer);
        state.suggestionTimer = null;
    }

    const trimmed = (query || '').trim();
    if (!trimmed || trimmed.length < 2 || state.searchMode !== 'title') {
        clearLiveSuggestions();
        renderSearchSuggestions(query);
        return;
    }

    state.suggestionTimer = setTimeout(() => {
        state.suggestionTimer = null;
        fetchLiveSuggestions(trimmed);
    }, 250);
}

async function fetchLiveSuggestions(query) {
    if (state.searchAbortController) {
        state.searchAbortController.abort();
    }
    state.searchAbortController = new AbortController();
    try {
        const results = await API.searchSuggestions(query, 6, state.searchAbortController.signal);
        if (query !== state.searchQuery) {
            return;
        }
        state.liveSuggestions = Array.isArray(results) ? results.slice(0, 6) : [];
    } catch (error) {
        if (error.name !== 'AbortError') {
            log(`Search suggestions failed: ${error.message}`);
        }
        state.liveSuggestions = [];
    }
    renderSearchSuggestions(query);
}

function renderDiscoverPagination(view, currentPage, totalPages = 20) {
    if (!els.discoverPagination) return;
    els.discoverPagination.classList.remove('hidden');
    els.discoverPagination.innerHTML = `
        <button id="${view}-prev" ${currentPage <= 1 ? 'disabled' : ''}>Prev</button>
        <span class="page-indicator">Page ${currentPage} / ${totalPages}</span>
        <button id="${view}-next" ${currentPage >= totalPages ? 'disabled' : ''}>Next</button>
    `;

    const prevBtn = document.getElementById(`${view}-prev`);
    const nextBtn = document.getElementById(`${view}-next`);
    prevBtn?.addEventListener('click', () => handlePageChange(view, currentPage - 1));
    nextBtn?.addEventListener('click', () => handlePageChange(view, currentPage + 1));
}

function hidePagination() {
    if (els.discoverPagination) {
        els.discoverPagination.classList.add('hidden');
        els.discoverPagination.innerHTML = '';
    }
}

function handlePageChange(view, page) {
    if (page < 1) return;
    switch (view) {
        case 'discover':
            loadDiscover(page);
            break;
        case 'popular':
            loadPopular(page);
            break;
        case 'trending':
            loadTrendingView(page);
            break;
        case 'history':
            loadHistory(page);
            break;
        default:
            break;
    }
}

// ========================================
// Search Functionality
// ========================================
async function performSearch() {
    const query = state.searchQuery.trim();
    if (!query) {
        loadDiscover(state.viewPages.discover || 1);
        return;
    }

    if (state.searchMode === 'url') {
        await detectUrl(query);
    } else {
        await searchManga(query);
    }
}

async function searchManga(query) {
    hidePagination();
    els.discoverGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Searching...</span>
        </div>
    `;
    els.discoverEmpty.classList.add('hidden');

    log(`🔍 Searching Jikan for: ${query}`);

    try {
        saveSearchHistory(query);
        hideSearchSuggestions();
        clearLiveSuggestions();
        const results = await API.search(query);
        if (results.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
        } else {
            renderMangaGrid(results, els.discoverGrid, els.discoverEmpty);
        }
        log(`✅ Found ${results.length} results`);
    } catch (error) {
        log(`❌ Search error: ${error.message}`);
        els.discoverGrid.innerHTML = `
            <div style="grid-column: 1/-1; padding: 48px 24px; text-align: center;">
                <div class="empty-icon-box" style="margin: 0 auto 16px;">
                    <i data-lucide="alert-circle" width="32" height="32"></i>
                </div>
                <p style="color: var(--text-muted); font-size: 14px; font-family: monospace;">
                    Search failed<br/>
                    ${escapeHtml(error.message)}
                </p>
            </div>
        `;
        safeCreateIcons();
    }
}

async function detectUrl(url) {
    els.discoverGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Detecting URL...</span>
        </div>
    `;

    log(`Detecting URL: ${url}`);

    try {
        const result = await API.detectUrl(url);
        if (result.source_id && result.manga_id) {
            showToast(`Detected: ${result.source_name}`);
            log(`Detected source: ${result.source_name}, manga ID: ${result.manga_id}`);
            openMangaDetails(result.manga_id, result.source_id, 'Detected Manga');
        } else {
            showToast('Could not detect source from URL');
            log('URL detection failed');
            els.discoverGrid.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">URL not recognized</p>';
        }
    } catch (error) {
        els.discoverGrid.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">URL detection failed</p>';
        log(`URL detection error: ${error.message}`);
    }
}

async function loadPopular(page = 1) {
    els.discoverGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading popular...</span>
        </div>
    `;
    els.discoverEmpty.classList.add('hidden');
    updateDiscoverSubtitle(`// MOST POPULAR // PAGE ${page}`);

    log('Loading popular manga from Jikan (MyAnimeList)...');

    try {
        state.viewPages.popular = page;
        const results = await API.getPopular(page, 24);

        if (!results || results.length === 0) {
            log('No results returned from API');
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return;
        }

        log(`✅ Loaded ${results.length} popular manga (page ${page})`);
        renderMangaGrid(results, els.discoverGrid, els.discoverEmpty);
        renderDiscoverPagination('popular', page);
    } catch (error) {
        log(`❌ ERROR loading popular: ${error.message}`);
        els.discoverGrid.innerHTML = `
            <div style="grid-column: 1/-1; padding: 48px 24px; text-align: center;">
                <div class="empty-icon-box" style="margin: 0 auto 16px;">
                    <i data-lucide="alert-circle" width="32" height="32"></i>
                </div>
                <p style="color: var(--text-muted); font-size: 14px; font-family: monospace;">
                    Failed to load manga<br/>
                    ${escapeHtml(error.message)}
                </p>
            </div>
        `;
        safeCreateIcons();
    }
}

async function loadDiscover(page = 1) {
    els.discoverGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading hidden gems...</span>
        </div>
    `;
    els.discoverEmpty.classList.add('hidden');
    log('Loading discover feed (hidden gems - lesser-known quality manga)...');

    try {
        // Rotate page every 10 minutes for variety, unless user paginates manually
        const timeBucket = Math.floor(Date.now() / (10 * 60 * 1000));
        const autoPage = (timeBucket % 5) + 1;
        const chosenPage = page || autoPage;
        state.viewPages.discover = chosenPage;
        updateDiscoverSubtitle(`// HIDDEN GEMS // PAGE ${chosenPage}`);

        const results = await API.getDiscover(chosenPage, 20);

        if (!results || results.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return;
        }

        renderMangaGrid(results, els.discoverGrid, els.discoverEmpty);
        log(`✅ Loaded ${results.length} hidden gems`);
        renderDiscoverPagination('discover', chosenPage);
    } catch (error) {
        log(`❌ ERROR loading discover: ${error.message}`);
        els.discoverGrid.innerHTML = `
            <div style="grid-column: 1/-1; padding: 48px 24px; text-align: center;">
                <div class="empty-icon-box" style="margin: 0 auto 16px;">
                    <i data-lucide="alert-circle" width="32" height="32"></i>
                </div>
                <p style="color: var(--text-muted); font-size: 14px; font-family: monospace;">
                    Failed to load discover feed<br/>
                    ${escapeHtml(error.message)}
                </p>
            </div>
        `;
        safeCreateIcons();
    }
}

async function loadHistory() {
    hidePagination();
    els.discoverGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading history...</span>
        </div>
    `;
    els.discoverEmpty.classList.add('hidden');
    updateDiscoverSubtitle('// RECENTLY VIEWED');

    try {
        const results = await API.getHistory(50);
        state.history = results;
        if (!results || results.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            els.discoverEmpty.querySelector('.empty-title').textContent = 'No History Yet';
            els.discoverEmpty.querySelector('.empty-text').textContent = 'Start reading to see items here';
            return;
        }
        renderMangaGrid(results, els.discoverGrid, els.discoverEmpty);
        log(`✅ Loaded ${results.length} history items`);
    } catch (error) {
        log(`❌ ERROR loading history: ${error.message}`);
        els.discoverGrid.innerHTML = `
            <div style="grid-column: 1/-1; padding: 48px 24px; text-align: center;">
                <div class="empty-icon-box" style="margin: 0 auto 16px;">
                    <i data-lucide="alert-circle" width="32" height="32"></i>
                </div>
                <p style="color: var(--text-muted); font-size: 14px; font-family: monospace;">
                    Failed to load history<br/>
                    ${escapeHtml(error.message)}
                </p>
            </div>
        `;
        safeCreateIcons();
    }
}

async function loadTrendingView(page = 1) {
    els.discoverGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading trending...</span>
        </div>
    `;
    els.discoverEmpty.classList.add('hidden');
    updateDiscoverSubtitle(`// TRENDING // PAGE ${page}`);
    state.viewPages.trending = page;

    log(`Loading trending page ${page}...`);

    try {
        const results = await API.getTrending(page, 24);
        if (!results || results.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return;
        }
        renderMangaGrid(results, els.discoverGrid, els.discoverEmpty);
        renderDiscoverPagination('trending', page);
        log(`✅ Loaded ${results.length} trending manga (page ${page})`);
    } catch (error) {
        log(`❌ ERROR loading trending: ${error.message}`);
        els.discoverGrid.innerHTML = `
            <div style="grid-column: 1/-1; padding: 48px 24px; text-align: center;">
                <div class="empty-icon-box" style="margin: 0 auto 16px;">
                    <i data-lucide="alert-circle" width="32" height="32"></i>
                </div>
                <p style="color: var(--text-muted); font-size: 14px; font-family: monospace;">
                    Failed to load trending<br/>
                    ${escapeHtml(error.message)}
                </p>
            </div>
        `;
        safeCreateIcons();
    }
}

// ========================================
// Library Management
// ========================================
function renderContinueReading() {
    if (!els.continueReading) return;

    const libraryCandidates = state.library.filter(entry => entry.last_chapter_id || entry.last_read_at);
    const libraryLatest = libraryCandidates.length
        ? libraryCandidates.sort((a, b) => {
            const aTime = a.last_read_at ? Date.parse(a.last_read_at) : 0;
            const bTime = b.last_read_at ? Date.parse(b.last_read_at) : 0;
            return bTime - aTime;
        })[0]
        : null;

    const localLatest = state.lastRead && state.lastRead.last_read_at ? state.lastRead : null;

    let mostRecent = libraryLatest;
    if (localLatest && (!libraryLatest || Date.parse(localLatest.last_read_at) > Date.parse(libraryLatest.last_read_at || 0))) {
        mostRecent = localLatest;
    }

    if (!mostRecent || !mostRecent.last_chapter_id) {
        els.continueReading.classList.add('hidden');
        state.continueEntry = null;
        return;
    }

    state.continueEntry = mostRecent;
    const coverUrl = mostRecent.cover || PLACEHOLDER_COVER;
    if (els.continueCover.dataset.src !== coverUrl) {
        els.continueCover.src = coverUrl;
        els.continueCover.dataset.src = coverUrl;
    }
    els.continueCover.onerror = () => {
        if (els.continueCover.dataset.src !== PLACEHOLDER_COVER) {
            els.continueCover.src = PLACEHOLDER_COVER;
            els.continueCover.dataset.src = PLACEHOLDER_COVER;
        }
    };
    els.continueTitle.textContent = mostRecent.title || 'Continue Reading';

    const progressBits = [];
    if (mostRecent.last_chapter) {
        const chapterLabel = String(mostRecent.last_chapter);
        progressBits.push(
            chapterLabel.toLowerCase().includes('chapter') ? chapterLabel : `Ch ${chapterLabel}`
        );
    }
    if (mostRecent.last_page != null) {
        progressBits.push(`Page ${mostRecent.last_page}`);
    }
    if (mostRecent.total_chapters) {
        progressBits.push(`${mostRecent.total_chapters} total`);
    }
    els.continueProgress.textContent = progressBits.join(' | ');
    els.continueReading.classList.remove('hidden');
}

async function resumeContinueReading() {
    const entry = state.continueEntry;
    if (!entry) return;
    if (!entry.last_chapter_id) {
        showToast('No recent chapter saved');
        return;
    }

    state.currentManga = {
        id: entry.manga_id || entry.id,
        source: entry.source,
        title: entry.title,
        mal_id: entry.mal_id,
        cover: entry.cover,
        data: null
    };
    state.currentLibraryKey = entry.key || null;
    state.currentChapters = [];
    state.currentChaptersOffset = 0;
    state.totalChaptersCount = entry.total_chapters || state.totalChaptersCount;

    const startPage = entry.last_page ? Math.max(0, Number(entry.last_page) - 1) : 0;
    const rawChapter = entry.last_chapter ? String(entry.last_chapter) : '';
    const chapterLabel = rawChapter
        ? (rawChapter.toLowerCase().includes('chapter') ? rawChapter : `Chapter ${rawChapter}`)
        : 'Chapter';
    await openReader(entry.last_chapter_id, chapterLabel, startPage, entry.last_chapter, entry.total_chapters);
}

function renderLibraryFromState() {
    const filteredLibrary = state.activeFilter === 'all'
        ? state.library
        : state.library.filter(item => item.status === state.activeFilter);

    els.libraryCount.textContent = `// ${filteredLibrary.length} ENTRIES`;

    if (filteredLibrary.length === 0) {
        els.libraryGrid.classList.add('hidden');
        els.libraryEmpty.classList.remove('hidden');
        return;
    }

    // Convert library format to manga format for rendering
    const mangaItems = filteredLibrary.map(item => ({
        key: item.key,
        id: item.manga_id,
        mal_id: item.mal_id,
        source: item.source,
        title: item.title,
        cover_url: item.cover,
        author: item.author || 'Unknown',
        genres: item.genres || [],
        tags: item.tags || [],
        status: item.status,
        last_chapter: item.last_chapter,
        last_chapter_id: item.last_chapter_id,
        last_page: item.last_page,
        total_chapters: item.total_chapters,
        last_read_at: item.last_read_at
    }));

    renderMangaGrid(mangaItems, els.libraryGrid, els.libraryEmpty);
}

function findLibraryKeyForManga(mangaId, source, title, malId = null) {
    if (!mangaId || !source) return null;
    const directKey = getLibraryKey(mangaId, source);
    if (state.library.some(entry => entry.key === directKey)) {
        return directKey;
    }

    if (malId) {
        const match = state.library.find(entry => String(entry.mal_id || '') === String(malId));
        if (match) return match.key;
    }

    if (title) {
        const normalized = title.trim().toLowerCase();
        const match = state.library.find(entry => (entry.title || '').trim().toLowerCase() === normalized);
        if (match) return match.key;
    }

    return null;
}

function resolveCurrentLibraryKey() {
    if (state.currentLibraryKey && state.library.some(entry => entry.key === state.currentLibraryKey)) {
        return state.currentLibraryKey;
    }
    if (!state.currentManga) return null;
    const key = findLibraryKeyForManga(
        state.currentManga.id,
        state.currentManga.source,
        state.currentManga.title,
        state.currentManga.mal_id
    );
    if (key) {
        state.currentLibraryKey = key;
    }
    return key;
}

async function loadLibrary() {
    hidePagination();
    els.libraryGrid.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading library...</span>
        </div>
    `;
    els.libraryEmpty.classList.add('hidden');

    log('📚 Loading library...');

    try {
        const library = await API.getLibrary();
        state.library = library;
        renderLibraryFromState();
        renderContinueReading();

        renderNav(); // Update library count in nav
        log(`✅ Loaded ${library.length} library items`);
    } catch (error) {
        log(`❌ Library loading error: ${error.message}`);
        els.libraryGrid.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">Failed to load library</p>';
    }
}

function isInLibrary(mangaId, source) {
    const key = `${source}:${mangaId}`;
    return state.library.some(item => item.key === key);
}

function getLibraryKey(mangaId, source) {
    return `${source}:${mangaId}`;
}

async function addToLibrary(mangaId, source, title, cover, status) {
    try {
        await API.addToLibrary(mangaId, source, title, cover, status);
        showToast('Added to Library');
        log(`✅ Added to library: ${title} (${status})`);
        await loadLibrary(); // Refresh library
        renderNav();
        if (state.currentManga && state.currentManga.id === mangaId && state.currentManga.source === source) {
            state.currentLibraryKey = getLibraryKey(mangaId, source);
        }

        // Update details view button if currently viewing this manga
        if (state.currentManga && state.currentManga.id === mangaId && state.currentManga.source === source) {
            els.addToLibraryBtn.innerHTML = '<i data-lucide="check" width="20"></i> In Library';
            els.addToLibraryBtn.classList.add('secondary');
            safeCreateIcons();
        }
    } catch (error) {
        log(`❌ Failed to add to library: ${error.message}`);
        showToast('Failed to add to library');
    }
}

// ========================================
// Manga Grid Rendering
// ========================================
function renderMangaGrid(manga, gridEl, emptyEl) {
    if (manga.length === 0) {
        gridEl.classList.add('hidden');
        emptyEl.classList.remove('hidden');
        return;
    }

    emptyEl.classList.add('hidden');
    gridEl.classList.remove('hidden');
    gridEl.innerHTML = manga.map(item => {
        // For Jikan manga, use mal_id as the ID and 'jikan' as pseudo-source
        const mangaId = item.mal_id || item.id || item.manga_id || `item-${Math.random().toString(36).slice(2)}`;
        const source = item.mal_id ? 'jikan' : (item.source || 'unknown');
        const isLibraryView = state.activeView === 'library';
        const libraryKey = item.key || (source && mangaId ? `${source}:${mangaId}` : '');

        const inLibrary = isInLibrary(mangaId, source);
        const coverUrl = item.cover_url || item.cover || PLACEHOLDER_COVER;

        // Use actual data from API
        const score = item.rating?.average || item.score || (8.0 + Math.random() * 2).toFixed(1);
        const author = item.author || 'Unknown Author';
        const tags = item.tags || item.genres || ['Manga'];
        const tag = Array.isArray(tags) ? tags[0] : tags;
        const views = item.rating?.count ? `${(item.rating.count / 1000).toFixed(0)}k` : `${Math.floor(Math.random() * 5000)}k`;

        let progressHtml = '';
        if (isLibraryView && item.total_chapters && item.last_chapter) {
            const total = parseFloat(item.total_chapters);
            const current = parseFloat(item.last_chapter);
            if (!Number.isNaN(total) && total > 0 && !Number.isNaN(current)) {
                const percent = Math.min(100, Math.max(0, (current / total) * 100));
                progressHtml = `
                    <div class="progress-wrap">
                        <div class="progress-bar" style="width: ${percent.toFixed(0)}%"></div>
                        <span class="progress-text">Ch ${escapeHtml(String(item.last_chapter))} / ${escapeHtml(String(item.total_chapters))} · ${percent.toFixed(0)}%</span>
                    </div>
                `;
            }
        }

        return `
            <div class="card" data-manga-id="${escapeHtml(String(mangaId))}" data-source="${escapeHtml(source)}" data-library-key="${escapeHtml(libraryKey)}">
                <div class="card-cover">
                    ${coverUrl ? `<img src="${escapeHtml(coverUrl)}" alt="${escapeHtml(item.title)}" loading="lazy" onerror="this.src='${PLACEHOLDER_COVER}'; this.onerror=null;" />` : '<i data-lucide="book-open" width="48" height="48"></i>'}
                    <div class="card-overlay">
                        <button class="read-btn">Read</button>
                    </div>
                    <div class="card-badges">
                        <span class="badge-score"><i data-lucide="flame"></i> ${escapeHtml(String(score))}</span>
                        <button class="bookmark-btn ${inLibrary ? 'active' : ''}" data-action="bookmark">
                            <i data-lucide="heart" width="16" height="16" fill="${inLibrary ? 'currentColor' : 'none'}"></i>
                        </button>
                        ${isLibraryView ? `<button class="remove-btn" data-action="remove" title="Remove from library"><i data-lucide="trash" width="14"></i></button>` : ''}
                    </div>
                </div>
                <div class="card-info">
                    <div>
                        <h3 class="card-title">${escapeHtml(item.title)}</h3>
                        <p class="card-author">${escapeHtml(author)}</p>
                    </div>
                    <div class="card-footer">
                        <span class="tag">${escapeHtml(tag)}</span>
                        <span class="views">${escapeHtml(String(views))}</span>
                    </div>
                    ${progressHtml}
                </div>
            </div>
        `;
    }).join('');

    safeCreateIcons();
    // Store manga data for event delegation access
    gridEl._mangaData = manga;
    // Event delegation handled by setupEventDelegation() - no per-card listeners needed
}

// ========================================
// Manga Details
// ========================================
async function openMangaDetails(mangaId, source, title, mangaData = null) {
    // Save current view before switching to details (for back button)
    if (state.activeView !== 'details') {
        state.previousView = state.activeView;
    }

    state.currentManga = {
        id: mangaId,
        source,
        title,
        mal_id: mangaData?.mal_id,
        cover: mangaData?.cover_url || mangaData?.cover,
        data: mangaData
    };
    state.currentLibraryKey = findLibraryKeyForManga(
        mangaId,
        source,
        title,
        mangaData?.mal_id
    );
    state.currentChapters = [];
    state.selectedChapters.clear();
    state.currentPage = 1;
    state.totalChaptersCount = 0;
    state.currentChaptersOffset = 0;

    // Track history (non-blocking)
    try {
        await API.addHistory({
            id: mangaId,
            source,
            title,
            cover: mangaData?.cover_url || mangaData?.cover || PLACEHOLDER_COVER,
            mal_id: mangaData?.mal_id,
            payload: {
                author: mangaData?.author,
                tags: mangaData?.tags || mangaData?.genres || []
            }
        });
    } catch (error) {
        log(`⚠️ History track failed: ${error.message}`);
    }

    setView('details');

    // Set initial details
    els.detailsTitle.textContent = title;

    // Show description if available
    if (mangaData?.synopsis) {
        els.detailsDescription.textContent = mangaData.synopsis;
    } else {
        els.detailsDescription.textContent = 'Loading description...';
    }

    // Show meta if available
    if (mangaData) {
        const metaItems = [];
        if (mangaData.author) metaItems.push(`<span class="meta-item"><i data-lucide="user"></i> ${escapeHtml(mangaData.author)}</span>`);
        if (mangaData.status) metaItems.push(`<span class="meta-item"><i data-lucide="info"></i> ${escapeHtml(mangaData.status)}</span>`);
        if (mangaData.year) metaItems.push(`<span class="meta-item"><i data-lucide="calendar"></i> ${escapeHtml(String(mangaData.year))}</span>`);
        if (mangaData.rating?.average) metaItems.push(`<span class="meta-item"><i data-lucide="star"></i> ${mangaData.rating.average.toFixed(2)}</span>`);
        els.detailsMeta.innerHTML = metaItems.join('');
    } else {
        els.detailsMeta.innerHTML = '';
    }

    // Set cover if available
    if (mangaData?.cover_url) {
        els.detailsCoverImg.src = mangaData.cover_url;
    }

    // Update "Add to Library" button state
    const inLibrary = isInLibrary(mangaId, source);
    if (inLibrary) {
        els.addToLibraryBtn.innerHTML = '<i data-lucide="check" width="20"></i> In Library';
        els.addToLibraryBtn.classList.add('secondary');
    } else {
        els.addToLibraryBtn.innerHTML = '<i data-lucide="heart" width="20"></i> Add to Library';
        els.addToLibraryBtn.classList.remove('secondary');
    }
    safeCreateIcons();

    // Load chapters
    await loadChapters(1);
}

function buildChaptersPayload(page = 1) {
    if (!state.currentManga) return null;
    const payload = {
        id: state.currentManga.id,
        title: state.currentManga.title,
        offset: (page - 1) * 100,
        limit: 100
    };

    if (state.currentManga.mal_id) {
        payload.mal_id = state.currentManga.mal_id;
    } else if (state.currentManga.source) {
        payload.source = state.currentManga.source;
    }

    return payload;
}

async function fetchChaptersPage(page = 1, { updateState = false } = {}) {
    const payload = buildChaptersPayload(page);
    if (!payload) return null;
    const response = await API.request('/api/chapters', {
        method: 'POST',
        body: JSON.stringify(payload)
    });

    if (response?.total) {
        state.totalChaptersCount = response.total;
        state.totalPages = Math.ceil((response.total || 0) / 100) || 1;
    }

    if (updateState && Array.isArray(response?.chapters)) {
        state.currentChapters = response.chapters;
        state.currentPage = page;
        state.currentChaptersOffset = (page - 1) * 100;
        renderChapters();
        renderPagination();
    }

    return response;
}

async function loadChapters(page = 1) {
    state.currentPage = page;

    // Cancel any previous in-flight chapters request (race condition prevention)
    if (state.chaptersAbortController) {
        state.chaptersAbortController.abort();
    }
    state.chaptersAbortController = new AbortController();
    const signal = state.chaptersAbortController.signal;

    els.chaptersList.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading chapters...</span>
        </div>
    `;

    log(`📖 Loading chapters (page ${page})...`);

    try {
        const payload = buildChaptersPayload(page);
        if (!payload) {
            throw new Error('Missing manga details for chapters');
        }
        if (payload.mal_id) {
            log(`Using MAL ID: ${payload.mal_id}`);
        } else if (payload.source) {
            log(`Using source: ${payload.source}`);
        }

        const response = await API.request('/api/chapters', {
            method: 'POST',
            body: JSON.stringify(payload),
            signal
        });

        // Update current manga with resolved source/id from backend (important for downloads/library)
        if (response.source_id) {
            state.currentManga.source = response.source_id;
            log(`Using resolved source: ${response.source_id}`);
        }
        if (response.manga_id) {
            state.currentManga.id = response.manga_id;
        }

        state.currentChapters = response.chapters || [];
        state.totalChaptersCount = response.total || state.currentChapters.length;
        state.currentChaptersOffset = (page - 1) * 100;
        state.totalPages = Math.ceil((response.total || 0) / 100) || 1;

        renderChapters();
        renderPagination();

        log(`✅ Loaded ${state.currentChapters.length} chapters`);
    } catch (error) {
        // Silently ignore aborted requests
        if (error.name === 'AbortError') {
            return;
        }
        log(`❌ Chapters loading error: ${error.message}`);
        els.chaptersList.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">Failed to load chapters</p>';
    }
}

function renderChapters() {
    if (state.currentChapters.length === 0) {
        els.chaptersList.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">No chapters available</p>';
        return;
    }

    els.chaptersList.innerHTML = state.currentChapters.map(chapter => {
        const isSelected = state.selectedChapters.has(chapter.id);
        const chapterNum = chapter.chapter || '0';
        return `
            <div class="chapter-item ${isSelected ? 'selected' : ''}" data-chapter-id="${escapeHtml(chapter.id)}" data-chapter-title="${escapeHtml(chapter.title)}" data-chapter-number="${escapeHtml(String(chapterNum))}">
                <div class="chapter-info">
                    <div class="chapter-checkbox"></div>
                    <span class="chapter-name">${escapeHtml(chapter.title)}</span>
                </div>
                <div class="chapter-actions">
                    <button class="icon-btn" data-action="read" title="Read">
                        <i data-lucide="book-open" width="16"></i>
                    </button>
                    <button class="icon-btn" data-action="download" title="Download">
                        <i data-lucide="download" width="16"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    safeCreateIcons();
    // Event delegation handled by setupChapterEventDelegation() - no per-item listeners needed
}

function toggleChapterSelection(chapterId) {
    if (state.selectedChapters.has(chapterId)) {
        state.selectedChapters.delete(chapterId);
    } else {
        state.selectedChapters.add(chapterId);
    }
    renderChapters();
}

function selectAllChapters() {
    state.currentChapters.forEach(chapter => {
        state.selectedChapters.add(chapter.id);
    });
    renderChapters();
}

function deselectAllChapters() {
    state.selectedChapters.clear();
    renderChapters();
}

async function downloadSelectedChapters() {
    if (state.selectedChapters.size === 0) {
        showToast('No chapters selected');
        return;
    }

    showToast(`Downloading ${state.selectedChapters.size} chapter(s)...`);

    // Collect all selected chapters for batch download
    const chaptersToDownload = [];
    for (const chapterId of state.selectedChapters) {
        const chapter = state.currentChapters.find(c => c.id === chapterId);
        if (chapter) {
            chaptersToDownload.push({
                id: chapter.id,
                chapter: chapter.chapter || '0',
                title: chapter.title
            });
        }
    }

    if (chaptersToDownload.length > 0) {
        try {
            await API.downloadChapters(
                state.currentManga.id,
                chaptersToDownload,
                state.currentManga.source,
                state.currentManga.title
            );
            showToast(`Added ${chaptersToDownload.length} chapter(s) to queue`);
            fetchDownloadQueue();
        } catch (error) {
            showToast(`Download failed: ${error.message}`);
        }
    }
}

async function downloadChapter(chapterId, chapterTitle, chapterNumber = '0') {
    log(`Downloading: ${chapterTitle}...`);
    showToast(`Downloading: ${chapterTitle}`);

    try {
        await API.downloadChapter(
            state.currentManga.id,
            chapterId,
            state.currentManga.source,
            state.currentManga.title,
            chapterTitle,
            chapterNumber
        );
        log(`Download queued: ${chapterTitle}`);
        showToast('Added to download queue');
        // Update queue badge
        fetchDownloadQueue();
    } catch (error) {
        log(`Download failed: ${error.message}`);
        showToast(`Download failed: ${error.message}`);
    }
}

function renderPagination() {
    if (state.totalPages <= 1) {
        els.chaptersPagination.classList.add('hidden');
        return;
    }

    els.chaptersPagination.classList.remove('hidden');
    els.chaptersPagination.innerHTML = `
        <button class="pagination-btn" id="prev-chapters-page" ${state.currentPage === 1 ? 'disabled' : ''}>
            <i data-lucide="chevron-left" width="16"></i>
            Prev
        </button>
        <span class="pagination-info">Page ${state.currentPage} of ${state.totalPages}</span>
        <button class="pagination-btn" id="next-chapters-page" ${state.currentPage === state.totalPages ? 'disabled' : ''}>
            Next
            <i data-lucide="chevron-right" width="16"></i>
        </button>
    `;

    safeCreateIcons();

    document.getElementById('prev-chapters-page')?.addEventListener('click', () => {
        if (state.currentPage > 1) loadChapters(state.currentPage - 1);
    });

    document.getElementById('next-chapters-page')?.addEventListener('click', () => {
        if (state.currentPage < state.totalPages) loadChapters(state.currentPage + 1);
    });
}

function inferChapterOrder(chapters = state.currentChapters) {
    if (!chapters || chapters.length < 2) return 'desc';
    const first = parseFloat(chapters[0]?.chapter);
    const last = parseFloat(chapters[chapters.length - 1]?.chapter);
    if (!Number.isNaN(first) && !Number.isNaN(last)) {
        if (first > last) return 'desc';
        if (first < last) return 'asc';
    }
    return 'desc';
}

function getChapterNumberForProgress(chapter, index) {
    const parsed = parseFloat(chapter?.chapter);
    if (!Number.isNaN(parsed)) {
        return parsed;
    }

    const total = state.totalChaptersCount || state.currentChapters.length || 0;
    if (!total) return null;
    const absoluteIndex = (state.currentChaptersOffset || 0) + index + 1;
    const order = inferChapterOrder();
    if (order === 'desc') {
        return Math.max(1, total - absoluteIndex + 1);
    }
    return absoluteIndex;
}

function updateLocalLibraryProgress(key, data) {
    const entry = state.library.find(item => item.key === key);
    if (!entry) return;
    Object.assign(entry, data);
    entry.last_read_at = new Date().toISOString();
    state.currentLibraryKey = key;
    renderContinueReading();

    if (state.activeView === 'library') {
        renderLibraryFromState();
    }
}

function scheduleProgressSave(immediate = false) {
    if (state.progressSaveTimer) {
        clearTimeout(state.progressSaveTimer);
        state.progressSaveTimer = null;
    }
    if (immediate) {
        void saveReadingProgress();
        return;
    }
    state.progressSaveTimer = setTimeout(() => {
        state.progressSaveTimer = null;
        void saveReadingProgress();
    }, 1200);
}

async function saveReadingProgress() {
    if (!state.currentManga) return;
    const key = resolveCurrentLibraryKey();
    if (!key) {
        const lastReadEntry = {
            id: state.currentManga.id,
            manga_id: state.currentManga.id,
            source: state.currentManga.source,
            title: state.currentManga.title,
            cover: state.currentManga.cover || state.currentManga.data?.cover_url || state.currentManga.data?.cover || PLACEHOLDER_COVER,
            last_chapter: state.currentChapterNumber != null ? String(state.currentChapterNumber) : state.currentChapterTitle,
            last_chapter_id: state.currentChapterId,
            last_page: state.readerCurrentPage + 1,
            total_chapters: state.totalChaptersCount || null,
            last_read_at: new Date().toISOString()
        };
        saveLastRead(lastReadEntry);
        renderContinueReading();
        return;
    }
    let chapterValue = state.currentChapterNumber;

    if (chapterValue == null && state.currentChapterIndex >= 0) {
        const chapterMeta = state.currentChapters[state.currentChapterIndex];
        chapterValue = getChapterNumberForProgress(chapterMeta, state.currentChapterIndex);
        state.currentChapterNumber = chapterValue;
    }

    if (chapterValue == null && state.currentChapterTitle) {
        chapterValue = state.currentChapterTitle;
    }

    if (chapterValue == null) return;

    const pageValue = state.readerCurrentPage + 1;
    const totalChapters = state.totalChaptersCount || state.currentChapters.length || null;

    try {
        await API.updateProgress(
            key,
            String(chapterValue),
            pageValue,
            state.currentChapterId,
            totalChapters
        );
        const updateData = {
            last_chapter: String(chapterValue),
            last_page: pageValue,
            last_chapter_id: state.currentChapterId
        };
        if (totalChapters !== null) {
            updateData.total_chapters = totalChapters;
        }
        updateLocalLibraryProgress(key, updateData);
    } catch (error) {
        log(`Progress save failed: ${error.message}`);
    }
}

function setReaderPage(index, options = {}) {
    const total = state.readerPages.length;
    if (total === 0) return;
    const clamped = Math.max(0, Math.min(index, total - 1));
    if (clamped === state.readerCurrentPage && !options.force) return;
    state.readerCurrentPage = clamped;
    updateReaderControls({ scroll: options.scroll !== false });
    scheduleProgressSave();
}

function clearReaderObserver() {
    if (state.readerObserver) {
        state.readerObserver.disconnect();
        state.readerObserver = null;
    }
}

function setupReaderObserver() {
    clearReaderObserver();
    if (!('IntersectionObserver' in window)) return;
    if (state.readerMode !== 'strip') return;
    const pages = els.readerContent.querySelectorAll('.reader-page');
    if (pages.length === 0) return;

    state.readerObserver = new IntersectionObserver((entries) => {
        const visible = entries
            .filter(entry => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length === 0) return;
        const index = Number(visible[0].target.dataset.pageIndex || 0);
        if (!Number.isNaN(index)) {
            setReaderPage(index, { scroll: false });
        }
    }, {
        root: els.readerContent,
        threshold: [0.6]
    });

    pages.forEach(page => state.readerObserver.observe(page));
}

function applyReaderMode() {
    if (state.readerMode === 'paged') {
        els.readerContainer.classList.add('paged');
        clearReaderObserver();
    } else {
        els.readerContainer.classList.remove('paged');
        setupReaderObserver();
    }

    if (els.readerModeLabel) {
        els.readerModeLabel.textContent = state.readerMode === 'paged' ? 'Paged' : 'Strip';
    }

    updateReaderControls({ scroll: true });
}

function handleReaderScroll() {
    if (state.readerMode !== 'strip') return;
    if (state.readerScrollRaf) return;
    state.readerScrollRaf = requestAnimationFrame(() => {
        state.readerScrollRaf = null;
        const pages = els.readerContent.querySelectorAll('.reader-page');
        if (pages.length === 0) return;
        const containerTop = els.readerContent.getBoundingClientRect().top;
        let closestIndex = 0;
        let closestDistance = Infinity;
        pages.forEach((page, index) => {
            const rect = page.getBoundingClientRect();
            const distance = Math.abs(rect.top - containerTop);
            if (distance < closestDistance) {
                closestDistance = distance;
                closestIndex = index;
            }
        });
        setReaderPage(closestIndex, { scroll: false });
    });
}

function setReaderMode(mode) {
    state.readerMode = mode;
    localStorage.setItem('manganegus.readerMode', mode);
    applyReaderMode();
}

function toggleReaderMode() {
    const next = state.readerMode === 'strip' ? 'paged' : 'strip';
    setReaderMode(next);
    showToast(`Reader Mode: ${next === 'strip' ? 'Strip' : 'Paged'}`);
}

function toggleReaderImmersive() {
    state.readerImmersive = !state.readerImmersive;
    els.readerContainer.classList.toggle('immersive', state.readerImmersive);
}

// ========================================
// Reader Fit Mode
// ========================================

const FIT_MODE_LABELS = {
    'fit-width': 'Fit Width',
    'fit-height': 'Fit Height',
    'fit-screen': 'Fit Screen',
    'fit-original': 'Original'
};

function setReaderFitMode(mode) {
    state.readerFitMode = mode;
    localStorage.setItem('manganegus.readerFitMode', mode);
    applyReaderFitMode();

    // Update button label
    if (els.readerFitLabel) {
        els.readerFitLabel.textContent = FIT_MODE_LABELS[mode] || 'Fit Width';
    }

    // Update active state in menu
    if (els.readerSettingsMenu) {
        els.readerSettingsMenu.querySelectorAll('[data-fit]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.fit === mode);
        });
    }

    showToast(`Fit Mode: ${FIT_MODE_LABELS[mode] || mode}`);
}

function applyReaderFitMode() {
    const modes = ['fit-width', 'fit-height', 'fit-screen', 'fit-original'];
    modes.forEach(m => els.readerContainer.classList.remove(m));
    els.readerContainer.classList.add(state.readerFitMode);
}

// ========================================
// Theme Management
// ========================================

const THEMES = ['dark', 'light', 'oled', 'sepia'];
const THEME_ICONS = {
    'dark': 'moon',
    'light': 'sun',
    'oled': 'moon',
    'sepia': 'coffee'
};
const THEME_LABELS = {
    'dark': 'Dark',
    'light': 'Light',
    'oled': 'OLED Black',
    'sepia': 'Sepia'
};

function setTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'dark';
    state.theme = theme;
    localStorage.setItem('manganegus.theme', theme);
    applyTheme();
    showToast(`Theme: ${THEME_LABELS[theme]}`);
}

function applyTheme() {
    // Remove existing theme
    document.documentElement.removeAttribute('data-theme');

    // Apply new theme (dark is default, so no attribute needed)
    if (state.theme !== 'dark') {
        document.documentElement.setAttribute('data-theme', state.theme);
    }

    // Update theme icon
    updateThemeIcon();
}

function updateThemeIcon() {
    if (!els.themeIcon) return;

    const iconName = THEME_ICONS[state.theme] || 'moon';
    els.themeIcon.setAttribute('data-lucide', iconName);
    safeCreateIcons();
}

function cycleTheme() {
    const currentIndex = THEMES.indexOf(state.theme);
    const nextIndex = (currentIndex + 1) % THEMES.length;
    setTheme(THEMES[nextIndex]);
}

// ========================================
// Keyboard Navigation
// ========================================

function handleKeyboardNavigation(event) {
    // Only handle when reader is open
    if (!els.readerContainer.classList.contains('active')) return;

    // Don't handle if user is typing in an input
    if (event.target.matches('input, textarea, select')) return;

    switch (event.key) {
        case 'ArrowLeft':
        case 'a':
        case 'A':
            event.preventDefault();
            setReaderPage(state.readerCurrentPage - 1);
            break;

        case 'ArrowRight':
        case 'd':
        case 'D':
        case ' ': // Space
            event.preventDefault();
            if (state.readerCurrentPage >= state.readerPages.length - 1) {
                advanceToNextChapter();
            } else {
                setReaderPage(state.readerCurrentPage + 1);
            }
            break;

        case 'ArrowUp':
            event.preventDefault();
            if (state.readerMode === 'strip') {
                els.readerContent.scrollBy({ top: -200, behavior: 'smooth' });
            } else {
                setReaderPage(state.readerCurrentPage - 1);
            }
            break;

        case 'ArrowDown':
            event.preventDefault();
            if (state.readerMode === 'strip') {
                els.readerContent.scrollBy({ top: 200, behavior: 'smooth' });
            } else {
                setReaderPage(state.readerCurrentPage + 1);
            }
            break;

        case 'Escape':
            event.preventDefault();
            closeReader();
            break;

        case 'f':
        case 'F':
            event.preventDefault();
            toggleReaderImmersive();
            break;

        case 'm':
        case 'M':
            event.preventDefault();
            toggleReaderMode();
            break;

        case 'Home':
            event.preventDefault();
            setReaderPage(0);
            break;

        case 'End':
            event.preventDefault();
            setReaderPage(state.readerPages.length - 1);
            break;

        // Number keys 1-9 for percentage jump
        case '1': case '2': case '3': case '4': case '5':
        case '6': case '7': case '8': case '9':
            event.preventDefault();
            const percent = parseInt(event.key) * 10;
            const targetPage = Math.floor((percent / 100) * state.readerPages.length);
            setReaderPage(Math.min(targetPage, state.readerPages.length - 1));
            showToast(`Jumped to ${percent}%`);
            break;
    }
}

async function resolveNextChapterForPrefetch() {
    if (!state.currentChapters.length || state.currentChapterIndex < 0) return null;

    const nextIndex = state.currentChapterIndex + 1;
    if (nextIndex < state.currentChapters.length) {
        return state.currentChapters[nextIndex];
    }

    if (state.currentPage < state.totalPages) {
        const nextPage = state.currentPage + 1;
        try {
            const response = await fetchChaptersPage(nextPage);
            return response?.chapters?.[0] || null;
        } catch (error) {
            log(`Prefetch chapter list failed: ${error.message}`);
            return null;
        }
    }

    return null;
}

async function prefetchNextChapter() {
    if (state.prefetchInFlight) return;
    if (!state.currentManga?.source) return;
    if (!state.currentChapters.length || state.currentChapterIndex < 0) return;

    const nextChapter = await resolveNextChapterForPrefetch();
    if (!nextChapter) return;

    if (state.prefetchedChapterId === nextChapter.id) return;

    state.prefetchInFlight = true;
    try {
        const pages = await API.getChapterPages(nextChapter.id, state.currentManga.source);
        state.prefetchedChapterId = nextChapter.id;
        state.prefetchedChapterTitle = nextChapter.title;
        state.prefetchedPages = pages;
        log(`Prefetched next chapter (${nextChapter.title || nextChapter.id})`);
    } catch (error) {
        log(`Prefetch failed: ${error.message}`);
    } finally {
        state.prefetchInFlight = false;
    }
}

async function advanceToNextChapter() {
    if (!state.currentChapters.length || state.currentChapterIndex < 0) {
        showToast('No next chapter available');
        return;
    }

    let nextChapter = null;
    let nextIndex = state.currentChapterIndex + 1;
    if (nextIndex < state.currentChapters.length) {
        nextChapter = state.currentChapters[nextIndex];
    } else if (state.currentPage < state.totalPages) {
        const response = await fetchChaptersPage(state.currentPage + 1, { updateState: true });
        nextChapter = response?.chapters?.[0] || null;
        nextIndex = 0;
    }

    if (!nextChapter) {
        showToast('No next chapter available');
        return;
    }

    const chapterNumber = getChapterNumberForProgress(nextChapter, nextIndex);
    await openReader(nextChapter.id, nextChapter.title || 'Chapter', 0, chapterNumber, state.totalChaptersCount);
}

function handleReaderTap(event) {
    if (!els.readerContainer.classList.contains('active')) return;
    if (event.target.closest('.reader-controls') || event.target.closest('#close-reader-btn')) return;

    const rect = els.readerContent.getBoundingClientRect();
    if (!rect.width) return;
    const x = event.clientX - rect.left;
    const ratio = x / rect.width;

    if (ratio < 0.33) {
        setReaderPage(state.readerCurrentPage - 1);
    } else if (ratio > 0.66) {
        if (state.readerCurrentPage >= state.readerPages.length - 1) {
            advanceToNextChapter();
        } else {
            setReaderPage(state.readerCurrentPage + 1);
        }
    } else {
        toggleReaderImmersive();
    }
}

// ========================================
// Reader
// ========================================
async function openReader(chapterId, chapterTitle, startPage = 0, chapterNumberOverride = null, totalChaptersOverride = null) {
    console.log('[READER DEBUG] openReader called', { chapterId, chapterTitle, source: state.currentManga?.source });

    if (!state.currentManga?.source) {
        showToast('Missing manga source');
        return;
    }
    state.currentChapterId = chapterId;
    state.currentChapterTitle = chapterTitle;
    state.currentChapterNumber = chapterNumberOverride;
    state.currentChapterIndex = state.currentChapters.findIndex(chapter => chapter.id === chapterId);

    if (state.currentChapterIndex >= 0) {
        const chapterMeta = state.currentChapters[state.currentChapterIndex];
        if (!chapterTitle && chapterMeta?.title) {
            chapterTitle = chapterMeta.title;
            state.currentChapterTitle = chapterTitle;
        }
        if (chapterNumberOverride == null) {
            state.currentChapterNumber = getChapterNumberForProgress(chapterMeta, state.currentChapterIndex);
        }
    }

    if (totalChaptersOverride) {
        state.totalChaptersCount = totalChaptersOverride;
    } else if (!state.totalChaptersCount && state.currentChapters.length) {
        state.totalChaptersCount = state.currentChapters.length;
    }

    els.readerTitle.textContent = chapterTitle;
    els.readerContent.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading pages...</span>
        </div>
    `;
    els.readerContainer.classList.add('active');
    state.readerCurrentPage = 0;

    log(`📖 Opening reader: ${chapterTitle}`);
    console.log('[READER DEBUG] Current manga:', state.currentManga);

    try {
        console.log('[READER DEBUG] Calling API.getChapterPages...');
        let pages = null;
        if (state.prefetchedChapterId === chapterId && Array.isArray(state.prefetchedPages)) {
            pages = state.prefetchedPages;
            state.prefetchedChapterId = null;
            state.prefetchedChapterTitle = null;
            state.prefetchedPages = null;
        } else {
            pages = await API.getChapterPages(chapterId, state.currentManga.source);
        }
        console.log('[READER DEBUG] Pages received:', pages, 'Type:', typeof pages, 'IsArray:', Array.isArray(pages));

        state.readerPages = pages;

        if (pages.length === 0) {
            console.error('[READER DEBUG] No pages returned!');
            els.readerContent.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">No pages available</p>';
            return;
        }

        console.log('[READER DEBUG] Rendering', pages.length, 'pages');
        state.readerCurrentPage = Math.max(0, Math.min(startPage, pages.length - 1));
        renderReaderPages();
        applyReaderMode();
        log(`✅ Loaded ${pages.length} pages`);
        scheduleProgressSave(true);
        prefetchNextChapter();
    } catch (error) {
        console.error('[READER DEBUG] Error:', error);
        els.readerContent.innerHTML = `<p style="padding: 24px; text-align: center; color: var(--text-muted);">Failed to load pages<br/>${escapeHtml(error.message)}</p>`;
        log(`❌ Reader error: ${error.message}`);
    }
}

function renderReaderPages() {
    console.log('[READER DEBUG] renderReaderPages called, state.readerPages:', state.readerPages);

    const html = state.readerPages.map((page, index) => {
        // Handle both string URLs and object with url property
        const pageUrl = typeof page === 'string' ? page : page.url;
        const referer = typeof page === 'object'
            ? (page.referer || page.headers?.Referer || page.headers?.referer || '')
            : '';
        console.log(`[READER DEBUG] Page ${index + 1}:`, { page, pageUrl });

        const proxyUrl = referer
            ? `/api/proxy/image?url=${encodeURIComponent(pageUrl)}&referer=${encodeURIComponent(referer)}`
            : `/api/proxy/image?url=${encodeURIComponent(pageUrl)}`;
        return `<img src="${escapeHtml(proxyUrl)}" alt="Page ${index + 1}" class="reader-page" data-page-index="${index}" loading="lazy" />`;
    }).join('');

    console.log('[READER DEBUG] Generated HTML length:', html.length);
    els.readerContent.innerHTML = html;
    console.log('[READER DEBUG] Rendered', state.readerPages.length, 'page elements');
    setupReaderObserver();
}

function updateReaderControls(options = {}) {
    const total = state.readerPages.length;
    if (!total) {
        els.readerPageIndicator.textContent = '0 / 0';
        els.prevPageBtn.disabled = true;
        els.nextPageBtn.disabled = true;
        return;
    }

    els.readerPageIndicator.textContent = `${state.readerCurrentPage + 1} / ${total}`;
    els.prevPageBtn.disabled = state.readerCurrentPage === 0;
    els.nextPageBtn.disabled = state.readerCurrentPage >= total - 1;

    // Scroll to current page
    const pages = els.readerContent.querySelectorAll('.reader-page');
    if (state.readerMode === 'paged') {
        pages.forEach((page, index) => {
            page.classList.toggle('active', index === state.readerCurrentPage);
        });
        if (options.scroll !== false && pages[state.readerCurrentPage]) {
            pages[state.readerCurrentPage].scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    } else if (options.scroll !== false && pages[state.readerCurrentPage]) {
        pages[state.readerCurrentPage].scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }
}

async function closeReader() {
    await saveReadingProgress();
    clearReaderObserver();
    if (state.progressSaveTimer) {
        clearTimeout(state.progressSaveTimer);
        state.progressSaveTimer = null;
    }
    if (state.readerScrollRaf) {
        cancelAnimationFrame(state.readerScrollRaf);
        state.readerScrollRaf = null;
    }
    els.readerContainer.classList.remove('active');
    els.readerContainer.classList.remove('immersive');
    state.readerImmersive = false;
    state.readerPages = [];
    state.readerCurrentPage = 0;
    state.currentChapterId = null;
    state.currentChapterTitle = '';
    state.currentChapterNumber = null;
    state.currentChapterIndex = -1;
}

// ========================================
// Modals
// ========================================
function showLibraryStatusModal(mangaId, source, title, coverUrl) {
    els.libraryStatusModal.classList.add('active');

    // Remove existing listeners and add new ones
    document.querySelectorAll('.status-option-btn').forEach(btn => {
        const newBtn = btn.cloneNode(true);
        btn.replaceWith(newBtn);

        newBtn.addEventListener('click', async () => {
            const status = newBtn.dataset.status;
            await addToLibrary(mangaId, source, title, coverUrl, status);
            els.libraryStatusModal.classList.remove('active');
        });
    });

    safeCreateIcons();
}

// ========================================
// DOM Element Initialization
// ========================================
function initElements() {
    els = {
        // Body & Layout
        body: document.body,
        sidebar: document.getElementById('sidebar'),
        overlay: document.getElementById('overlay'),
        mainContent: document.getElementById('main-content'),
        menuBtn: document.getElementById('menu-btn'),
        brandBtn: document.getElementById('brand-btn'),

        // Header Search
        searchInput: document.getElementById('search-input'),
        searchModeBtn: document.getElementById('search-mode-btn'),
        searchModeIcon: document.getElementById('search-mode-icon'),
        clearSearchBtn: document.getElementById('clear-search'),
        searchBtn: document.getElementById('search-btn'),
        searchSuggestions: document.getElementById('search-suggestions'),

        // Navigation
        navList: document.getElementById('nav-list'),
        sourceList: document.getElementById('source-list'),
        sourceStatusBtn: document.getElementById('source-status-btn'),

        // Views
        discoverView: document.getElementById('discover-view'),
        libraryView: document.getElementById('library-view'),
        detailsView: document.getElementById('details-view'),

        // Discover
        discoverGrid: document.getElementById('discover-grid'),
        discoverEmpty: document.getElementById('discover-empty'),
        discoverTitle: document.getElementById('discover-title'),
        discoverSubtitle: document.getElementById('discover-subtitle'),
        discoverPagination: document.getElementById('discover-pagination'),
        continueReading: document.getElementById('continue-reading'),
        continueBtn: document.getElementById('continue-btn'),
        continueTitle: document.getElementById('continue-title'),
        continueCover: document.getElementById('continue-cover'),
        continueProgress: document.getElementById('continue-progress'),

        // Library
        libraryGrid: document.getElementById('library-grid'),
        libraryEmpty: document.getElementById('library-empty'),
        libraryCount: document.getElementById('library-count'),

        // Details
        backBtn: document.getElementById('back-btn'),
        detailsCoverImg: document.getElementById('details-cover-img'),
        detailsTitle: document.getElementById('details-title'),
        detailsMeta: document.getElementById('details-meta'),
        detailsDescription: document.getElementById('details-description'),
        addToLibraryBtn: document.getElementById('add-to-library-btn'),
        downloadAllBtn: document.getElementById('download-all-btn'),
        chaptersList: document.getElementById('chapters-list'),
        chaptersPagination: document.getElementById('chapters-pagination'),
        selectAllChaptersBtn: document.getElementById('select-all-chapters'),
        deselectAllChaptersBtn: document.getElementById('deselect-all-chapters'),
        downloadSelectedBtn: document.getElementById('download-selected-btn'),

        // Reader
        readerContainer: document.getElementById('reader-container'),
        closeReaderBtn: document.getElementById('close-reader-btn'),
        readerTitle: document.getElementById('reader-title'),
        readerContent: document.getElementById('reader-content'),
        readerPageIndicator: document.getElementById('reader-page-indicator'),
        prevPageBtn: document.getElementById('prev-page-btn'),
        nextPageBtn: document.getElementById('next-page-btn'),
        readerModeBtn: document.getElementById('reader-mode-btn'),
        readerModeLabel: document.getElementById('reader-mode-label'),
        readerSettingsBtn: document.getElementById('reader-settings-btn'),
        readerSettingsMenu: document.getElementById('reader-settings-menu'),
        readerFitLabel: document.getElementById('reader-fit-label'),

        // Modals
        libraryStatusModal: document.getElementById('library-status-modal'),
        closeLibraryModal: document.getElementById('close-library-modal'),
        sourceStatusModal: document.getElementById('source-status-modal'),
        closeSourceModal: document.getElementById('close-source-modal'),
        sourceStatusGrid: document.getElementById('source-status-grid'),

        // Toast & Console
        toast: document.getElementById('toast'),
        toastMessage: document.getElementById('toast-message'),
        consoleModal: document.getElementById('console-modal'),
        consoleToggleBtn: document.getElementById('console-toggle-btn'),
        consoleClose: document.getElementById('console-close'),
        consoleContent: document.getElementById('console-content'),

        // Download Queue
        downloadQueueBtn: document.getElementById('download-queue-btn'),
        queueBadge: document.getElementById('queue-badge'),
        downloadQueueModal: document.getElementById('download-queue-modal'),
        closeQueueModal: document.getElementById('close-queue-modal'),
        queueList: document.getElementById('queue-list'),
        queueSubtitle: document.getElementById('queue-subtitle'),
        queuePauseAllBtn: document.getElementById('queue-pause-all'),
        queueResumeAllBtn: document.getElementById('queue-resume-all'),
        queueClearCompletedBtn: document.getElementById('queue-clear-completed'),

        // Theme
        themeToggleBtn: document.getElementById('theme-toggle-btn'),
        themeIcon: document.getElementById('theme-icon')
    };

    console.log('[DEBUG] Elements initialized');
    console.log('[DEBUG] els.sourceList:', els.sourceList);
    console.log('[DEBUG] els.sidebar:', els.sidebar);
}

// ========================================
// Initialization
// ========================================
// ========================================
// Event Delegation Setup (prevents memory leaks)
// ========================================
function setupEventDelegation() {
    // Navigation click delegation
    els.navList.addEventListener('click', (e) => {
        const navBtn = e.target.closest('.nav-item[data-view]');
        if (navBtn) {
            const view = navBtn.dataset.view;
            setView(view);
        }
    });

    // Source list click delegation
    els.sourceList.addEventListener('click', (e) => {
        const sourceBtn = e.target.closest('.source-btn[data-source]');
        if (sourceBtn) {
            const sourceId = sourceBtn.dataset.source;
            setSource(sourceId);
            return;
        }
        const showAllBtn = e.target.closest('#show-all-sources-btn');
        if (showAllBtn) {
            showSourceStatus();
        }
    });

    // Manga grid click delegation helper
    function handleGridClick(gridEl, e) {
        const card = e.target.closest('.card');
        if (!card) return;

        const mangaId = card.dataset.mangaId;
        const source = card.dataset.source;
        const titleEl = card.querySelector('.card-title');
        const title = titleEl ? titleEl.textContent : '';
        const coverImg = card.querySelector('.card-cover img');
        const coverUrl = coverImg ? coverImg.src : '';

        // Get manga data from stored array
        const allCards = Array.from(gridEl.querySelectorAll('.card'));
        const index = allCards.indexOf(card);
        const mangaData = gridEl._mangaData ? gridEl._mangaData[index] : null;

        // Handle remove button
        const removeBtn = e.target.closest('.remove-btn');
        if (removeBtn) {
            e.stopPropagation();
            const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
            removeFromLibrary(key)
                .then(() => {
                    showToast('Removed from library');
                    return loadLibrary();
                })
                .catch(err => {
                    log(`❌ Remove failed: ${err.message}`);
                    showToast('Failed to remove');
                });
            return;
        }

        // Handle bookmark button
        const bookmarkBtn = e.target.closest('.bookmark-btn');
        if (bookmarkBtn) {
            e.stopPropagation();
            if (isInLibrary(mangaId, source)) {
                showToast('Already in library');
            } else {
                showLibraryStatusModal(mangaId, source, title, coverUrl);
            }
            return;
        }

        // Handle card click (open details)
        openMangaDetails(mangaId, source, title, mangaData);
    }

    // Discover grid delegation
    els.discoverGrid.addEventListener('click', (e) => handleGridClick(els.discoverGrid, e));

    // Library grid delegation
    els.libraryGrid.addEventListener('click', (e) => handleGridClick(els.libraryGrid, e));

    // Chapter list delegation
    els.chaptersList.addEventListener('click', (e) => {
        const chapterItem = e.target.closest('.chapter-item');
        if (!chapterItem) return;

        const chapterId = chapterItem.dataset.chapterId;
        const chapterTitle = chapterItem.dataset.chapterTitle;

        // Handle read button
        const readBtn = e.target.closest('[data-action="read"]');
        if (readBtn) {
            e.stopPropagation();
            openReader(chapterId, chapterTitle);
            return;
        }

        // Handle download button
        const downloadBtn = e.target.closest('[data-action="download"]');
        if (downloadBtn) {
            e.stopPropagation();
            const chapterNumber = chapterItem.dataset.chapterNumber || '0';
            downloadChapter(chapterId, chapterTitle, chapterNumber);
            return;
        }

        // Handle checkbox/item click (toggle selection)
        if (!e.target.closest('.chapter-actions')) {
            toggleChapterSelection(chapterId);
        }
    });
}

async function init() {
    // Initialize DOM elements first
    initElements();

    // Load search history for suggestions
    loadSearchHistory();
    loadLastRead();

    // Setup event delegation (once, prevents memory leaks)
    setupEventDelegation();

    const savedReaderMode = localStorage.getItem('manganegus.readerMode');
    if (savedReaderMode === 'strip' || savedReaderMode === 'paged') {
        state.readerMode = savedReaderMode;
    }
    applyReaderMode();

    // Load saved fit mode
    const savedFitMode = localStorage.getItem('manganegus.readerFitMode');
    if (savedFitMode && ['fit-width', 'fit-height', 'fit-screen', 'fit-original'].includes(savedFitMode)) {
        state.readerFitMode = savedFitMode;
    }
    applyReaderFitMode();
    // Update fit label
    if (els.readerFitLabel) {
        els.readerFitLabel.textContent = FIT_MODE_LABELS[state.readerFitMode] || 'Fit Width';
    }

    // Load saved theme
    const savedTheme = localStorage.getItem('manganegus.theme');
    if (savedTheme && THEMES.includes(savedTheme)) {
        state.theme = savedTheme;
    }
    applyTheme();

    log('Initializing MangaNegus...');
    console.log('[DEBUG] Init started');

    // Get CSRF token
    await API.getCsrfToken();
    log('CSRF token obtained');

    // Load sources
    state.sources = await API.getSources();
    console.log('[DEBUG] Sources loaded:', state.sources.length);
    if (state.sources.length > 0) {
        state.currentSource = state.sources[0].id;
    }
    renderSources();
    log(`Loaded ${state.sources.length} sources`);

    // Load library
    state.library = await API.getLibrary();
    log(`Loaded ${state.library.length} library items`);
    renderContinueReading();

    // Render navigation
    renderNav();

    // Initialize Lucide icons
    safeCreateIcons();

    // Load initial content
    loadDiscover();

    // Event Listeners

    // Sidebar
    els.menuBtn.addEventListener('click', toggleSidebar);
    els.overlay.addEventListener('click', closeSidebar);
    els.brandBtn.addEventListener('click', () => setView('discover'));

    // Search
    els.searchInput.addEventListener('input', (e) => {
        state.searchQuery = e.target.value.trim();
        els.clearSearchBtn.classList.toggle('hidden', !state.searchQuery);
        renderSearchSuggestions(state.searchQuery);
        scheduleLiveSuggestions(state.searchQuery);
    });

    els.searchInput.addEventListener('focus', () => {
        renderSearchSuggestions(state.searchQuery);
    });

    els.searchInput.addEventListener('blur', () => {
        setTimeout(() => hideSearchSuggestions(), 150);
    });

    els.searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    els.clearSearchBtn.addEventListener('click', () => {
        state.searchQuery = '';
        els.searchInput.value = '';
        els.clearSearchBtn.classList.add('hidden');
        clearLiveSuggestions();
        loadDiscover(state.viewPages.discover || 1);
        hideSearchSuggestions();
    });

    els.searchBtn.addEventListener('click', () => {
        performSearch();
    });

    if (els.searchSuggestions) {
        els.searchSuggestions.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            const item = e.target.closest('.search-suggestion-item');
            if (!item) return;
            const action = item.dataset.action;
            if (action === 'clear') {
                state.searchHistory = [];
                localStorage.removeItem('manganegus.searchHistory');
                hideSearchSuggestions();
                return;
            }
            const value = item.dataset.value || '';
            if (value) {
                els.searchInput.value = value;
                state.searchQuery = value;
                els.clearSearchBtn.classList.remove('hidden');
                performSearch();
            }
        });
    }

    els.searchModeBtn.addEventListener('click', () => {
        state.searchMode = state.searchMode === 'title' ? 'url' : 'title';
        const isTitle = state.searchMode === 'title';
        els.searchInput.placeholder = isTitle
            ? 'Search titles...'
            : 'Paste manga URL (18 sources supported)...';
        els.searchInput.value = ''; // Clear input on mode change
        state.searchQuery = '';
        clearLiveSuggestions();
        els.clearSearchBtn.classList.add('hidden');
        els.searchModeIcon.setAttribute('data-lucide', isTitle ? 'search' : 'link');
        safeCreateIcons();

        // Show toast to inform user
        showToast(isTitle ? 'Search Mode: Title' : 'Search Mode: URL');
        log(`🔄 Search mode: ${state.searchMode.toUpperCase()}`);
    });

    if (els.continueBtn) {
        els.continueBtn.addEventListener('click', () => {
            resumeContinueReading();
        });
    }

    // Source Status Modal
    els.closeSourceModal.addEventListener('click', () => {
        els.sourceStatusModal.classList.remove('active');
    });

    // Library Modal
    els.closeLibraryModal.addEventListener('click', () => {
        els.libraryStatusModal.classList.remove('active');
    });

    // Library Filters
    document.querySelectorAll('.control-btn[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.control-btn[data-filter]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.activeFilter = btn.dataset.filter;
            loadLibrary();
        });
    });

    // Details View
    els.backBtn.addEventListener('click', () => {
        // Go back to the view we came from (discover, trending, popular, library, history)
        setView(state.previousView || 'discover');
    });

    els.addToLibraryBtn.addEventListener('click', () => {
        if (!isInLibrary(state.currentManga.id, state.currentManga.source)) {
            showLibraryStatusModal(
                state.currentManga.id,
                state.currentManga.source,
                state.currentManga.title,
                ''
            );
        }
    });

    els.selectAllChaptersBtn.addEventListener('click', selectAllChapters);
    els.deselectAllChaptersBtn.addEventListener('click', deselectAllChapters);
    els.downloadSelectedBtn.addEventListener('click', downloadSelectedChapters);

    // Reader
    els.closeReaderBtn.addEventListener('click', closeReader);
    els.prevPageBtn.addEventListener('click', () => {
        setReaderPage(state.readerCurrentPage - 1);
    });
    els.nextPageBtn.addEventListener('click', () => {
        if (state.readerCurrentPage >= state.readerPages.length - 1) {
            advanceToNextChapter();
        } else {
            setReaderPage(state.readerCurrentPage + 1);
        }
    });
    if (els.readerModeBtn) {
        els.readerModeBtn.addEventListener('click', toggleReaderMode);
    }
    els.readerContent.addEventListener('click', handleReaderTap);
    els.readerContent.addEventListener('scroll', handleReaderScroll, { passive: true });

    // Reader settings dropdown
    if (els.readerSettingsBtn && els.readerSettingsMenu) {
        els.readerSettingsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            els.readerSettingsMenu.classList.toggle('active');
        });

        // Fit mode buttons
        els.readerSettingsMenu.querySelectorAll('[data-fit]').forEach(btn => {
            btn.addEventListener('click', () => {
                const fitMode = btn.dataset.fit;
                setReaderFitMode(fitMode);
                els.readerSettingsMenu.classList.remove('active');
            });
        });

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.reader-settings-dropdown')) {
                els.readerSettingsMenu.classList.remove('active');
            }
        });
    }

    // Keyboard navigation for reader
    document.addEventListener('keydown', handleKeyboardNavigation);

    // Theme toggle
    if (els.themeToggleBtn) {
        els.themeToggleBtn.addEventListener('click', cycleTheme);
    }

    // Console
    els.consoleToggleBtn.addEventListener('click', () => {
        els.consoleModal.classList.add('active');
        safeCreateIcons();
    });
    els.consoleClose.addEventListener('click', () => {
        els.consoleModal.classList.remove('active');
    });
    els.consoleModal.addEventListener('click', (e) => {
        if (e.target === els.consoleModal) {
            els.consoleModal.classList.remove('active');
        }
    });

    // Download Queue
    if (els.downloadQueueBtn) {
        els.downloadQueueBtn.addEventListener('click', openDownloadQueue);
    }
    if (els.closeQueueModal) {
        els.closeQueueModal.addEventListener('click', closeDownloadQueue);
    }
    if (els.downloadQueueModal) {
        els.downloadQueueModal.addEventListener('click', (e) => {
            if (e.target === els.downloadQueueModal) {
                closeDownloadQueue();
            }
        });
    }
    if (els.queuePauseAllBtn) {
        els.queuePauseAllBtn.addEventListener('click', pauseAllDownloads);
    }
    if (els.queueResumeAllBtn) {
        els.queueResumeAllBtn.addEventListener('click', resumeAllDownloads);
    }
    if (els.queueClearCompletedBtn) {
        els.queueClearCompletedBtn.addEventListener('click', clearCompletedDownloads);
    }

    // Fetch initial queue status for badge
    fetchDownloadQueue();

    // Window resize
    window.addEventListener('resize', () => {
        if (window.innerWidth < 1024) closeSidebar();
    });

    log('Initialization complete');
}

// Global unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('[UNHANDLED REJECTION]', event.reason);
    log(`❌ Unhandled error: ${event.reason?.message || event.reason}`);
    // Prevent the default handling (which may crash)
    event.preventDefault();
});

// Global error handler
window.addEventListener('error', (event) => {
    console.error('[GLOBAL ERROR]', event.error);
    log(`❌ Global error: ${event.error?.message || event.message}`);
});

// Start application when DOM is ready with proper error handling
async function safeInit() {
    try {
        await init();
    } catch (error) {
        console.error('[INIT FAILED]', error);
        log(`❌ Initialization failed: ${error.message}`);
        // Show user-friendly error
        const body = document.body;
        if (body) {
            const errorDiv = document.createElement('div');
            errorDiv.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#1a1a1a;color:#fff;padding:2rem;border-radius:8px;z-index:9999;text-align:center;';
            errorDiv.innerHTML = `<h2>Initialization Error</h2><p>${error.message}</p><button onclick="location.reload()" style="margin-top:1rem;padding:0.5rem 1rem;cursor:pointer;">Reload</button>`;
            body.appendChild(errorDiv);
        }
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeInit);
} else {
    safeInit();
}
