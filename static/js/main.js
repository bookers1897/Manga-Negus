// MangaNegus Redesign - Main Application
// Integrates with existing Flask backend APIs

// ========================================
// State Management
// ========================================
const state = {
    activeView: 'discover',
    activeFilter: 'all',
    searchMode: 'title', // 'title' or 'url'
    searchQuery: '',
    currentSource: '',
    sources: [],
    library: [],
    currentManga: null,
    currentChapters: [],
    selectedChapters: new Set(),
    currentPage: 1,
    totalPages: 1,
    history: [],
    viewPages: {
        discover: 1,
        popular: 1,
        trending: 1,
        history: 1,
    },
    readerPages: [],
    readerCurrentPage: 0,
    isSidebarOpen: false,
    csrfToken: '',
    toastTimer: null
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
            const headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };

            if (options.method === 'POST' && state.csrfToken) {
                headers['X-CSRF-Token'] = state.csrfToken;
            }

            const response = await fetch(endpoint, {
                ...options,
                headers
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            showToast(`Error: ${error.message}`);
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
        return data.sources || [];
    },

    async getSourceHealth() {
        const data = await this.request('/api/sources/health');
        return data || {};
    },

    async search(query, limit = 15) {
        const data = await this.request('/api/search', {
            method: 'POST',
            body: JSON.stringify({ query, limit })
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
        const data = await this.request('/api/chapter_pages', {
            method: 'POST',
            body: JSON.stringify({ chapter_id: chapterId, source })
        });
        return data.pages || [];
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

    async removeFromLibrary(key) {
        const data = await this.request('/api/library/delete', {
            method: 'POST',
            body: JSON.stringify({ key })
        });
        return data;
    },

    async downloadChapter(mangaId, chapterId, source, title, chapterTitle) {
        const data = await this.request('/api/download', {
            method: 'POST',
            body: JSON.stringify({
                manga_id: mangaId,
                chapter_id: chapterId,
                source,
                title,
                chapter_title: chapterTitle
            })
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

    // Attach event listeners
    document.querySelectorAll('.nav-item[data-view]').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            setView(view);
        });
    });
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

    // Attach event listeners
    document.querySelectorAll('.source-btn[data-source]').forEach(btn => {
        btn.addEventListener('click', () => {
            const sourceId = btn.dataset.source;
            setSource(sourceId);
        });
    });

    // Show all sources button
    const showAllBtn = document.getElementById('show-all-sources-btn');
    if (showAllBtn) {
        showAllBtn.addEventListener('click', showSourceStatus);
    }

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

function renderPagination(view, currentPage, totalPages = 20) {
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
        renderPagination('popular', page);
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
            <span class="loading-text">Loading trending...</span>
        </div>
    `;
    els.discoverEmpty.classList.add('hidden');
    log('Loading discover feed (trending + latest updates)...');

    try {
        // Rotate page every 10 minutes to keep content fresh but predictable unless user paginates manually
        const timeBucket = Math.floor(Date.now() / (10 * 60 * 1000));
        const autoPage = (timeBucket % 5) + 1;
        const chosenPage = page || autoPage;
        state.viewPages.discover = chosenPage;
        updateDiscoverSubtitle(`// TRENDING + LATEST // PAGE ${chosenPage}`);

        const trending = await API.getTrending(chosenPage, 20);
        const latest = await API.getLatestFeed(state.currentSource || '', chosenPage);
        const results = [...(trending || []), ...(latest || [])].slice(0, 40);

        if (!results || results.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return;
        }

        renderMangaGrid(results, els.discoverGrid, els.discoverEmpty);
        log(`✅ Loaded ${results.length} trending/latest manga`);
        renderPagination('discover', chosenPage);
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
        renderPagination('trending', page);
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

        const filteredLibrary = state.activeFilter === 'all'
            ? library
            : library.filter(item => item.status === state.activeFilter);

        els.libraryCount.textContent = `// ${filteredLibrary.length} ENTRIES`;

        if (filteredLibrary.length === 0) {
            els.libraryGrid.classList.add('hidden');
            els.libraryEmpty.classList.remove('hidden');
        } else {
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
                last_chapter: item.last_chapter
            }));

            renderMangaGrid(mangaItems, els.libraryGrid, els.libraryEmpty);
        }

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
                </div>
            </div>
        `;
    }).join('');

    safeCreateIcons();

    // Attach event listeners to cards
    gridEl.querySelectorAll('.card').forEach((card, index) => {
        const mangaId = card.dataset.mangaId;
        const source = card.dataset.source;
        const title = card.querySelector('.card-title').textContent;
        const coverImg = card.querySelector('.card-cover img');
        const coverUrl = coverImg ? coverImg.src : '';

        // Get original manga data
        const mangaData = manga[index];

        // Open details on card click
        card.addEventListener('click', (e) => {
            if (!e.target.closest('.bookmark-btn')) {
                openMangaDetails(mangaId, source, title, mangaData);
            }
        });

        // Bookmark button
        const bookmarkBtn = card.querySelector('.bookmark-btn');
        if (bookmarkBtn) {
            bookmarkBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (isInLibrary(mangaId, source)) {
                    showToast('Already in library');
                } else {
                    showLibraryStatusModal(mangaId, source, title, coverUrl);
                }
            });
        }

        const removeBtn = card.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
                try {
                    await removeFromLibrary(key);
                    showToast('Removed from library');
                    await loadLibrary();
                } catch (err) {
                    log(`❌ Remove failed: ${err.message}`);
                    showToast('Failed to remove');
                }
            });
        }
    });
}

// ========================================
// Manga Details
// ========================================
async function openMangaDetails(mangaId, source, title, mangaData = null) {
    state.currentManga = {
        id: mangaId,
        source,
        title,
        mal_id: mangaData?.mal_id,
        data: mangaData
    };
    state.currentChapters = [];
    state.selectedChapters.clear();
    state.currentPage = 1;

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

async function loadChapters(page = 1) {
    state.currentPage = page;

    els.chaptersList.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading chapters...</span>
        </div>
    `;

    log(`📖 Loading chapters (page ${page})...`);

    try {
        // Build request payload based on manga type
        const payload = {
            id: state.currentManga.id,
            title: state.currentManga.title,
            offset: (page - 1) * 100,
            limit: 100
        };

        // Add mal_id for Jikan manga or source for direct source manga
        if (state.currentManga.mal_id) {
            payload.mal_id = state.currentManga.mal_id;
            log(`Using MAL ID: ${state.currentManga.mal_id}`);
        } else if (state.currentManga.source) {
            payload.source = state.currentManga.source;
            log(`Using source: ${state.currentManga.source}`);
        }

        const response = await API.request('/api/chapters', {
            method: 'POST',
            body: JSON.stringify(payload)
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
        state.totalPages = Math.ceil((response.total || 0) / 100) || 1;

        renderChapters();
        renderPagination();

        log(`✅ Loaded ${state.currentChapters.length} chapters`);
    } catch (error) {
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
        return `
            <div class="chapter-item ${isSelected ? 'selected' : ''}" data-chapter-id="${escapeHtml(chapter.id)}">
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

    // Attach event listeners
    els.chaptersList.querySelectorAll('.chapter-item').forEach(item => {
        const chapterId = item.dataset.chapterId;
        const chapter = state.currentChapters.find(c => c.id === chapterId);

        // Toggle selection on item click (not on action buttons)
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.chapter-actions')) {
                toggleChapterSelection(chapterId);
            }
        });

        // Read button
        const readBtn = item.querySelector('[data-action="read"]');
        if (readBtn) {
            readBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openReader(chapterId, chapter.title);
            });
        }

        // Download button
        const downloadBtn = item.querySelector('[data-action="download"]');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                downloadChapter(chapterId, chapter.title);
            });
        }
    });
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

    for (const chapterId of state.selectedChapters) {
        const chapter = state.currentChapters.find(c => c.id === chapterId);
        if (chapter) {
            await downloadChapter(chapterId, chapter.title);
        }
    }
}

async function downloadChapter(chapterId, chapterTitle) {
    log(`Downloading: ${chapterTitle}...`);
    showToast(`Downloading: ${chapterTitle}`);

    try {
        await API.downloadChapter(
            state.currentManga.id,
            chapterId,
            state.currentManga.source,
            state.currentManga.title,
            chapterTitle
        );
        log(`Download complete: ${chapterTitle}`);
        showToast('Download complete');
    } catch (error) {
        log(`Download failed: ${error.message}`);
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

// ========================================
// Reader
// ========================================
async function openReader(chapterId, chapterTitle) {
    els.readerTitle.textContent = chapterTitle;
    els.readerContent.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading pages...</span>
        </div>
    `;
    els.readerContainer.classList.add('active');
    state.readerCurrentPage = 0;

    log(`Opening reader: ${chapterTitle}`);

    try {
        const pages = await API.getChapterPages(chapterId, state.currentManga.source);
        state.readerPages = pages;

        if (pages.length === 0) {
            els.readerContent.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">No pages available</p>';
            return;
        }

        renderReaderPages();
        updateReaderControls();
        log(`Loaded ${pages.length} pages`);
    } catch (error) {
        els.readerContent.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">Failed to load pages</p>';
        log(`Reader error: ${error.message}`);
    }
}

function renderReaderPages() {
    els.readerContent.innerHTML = state.readerPages.map((page, index) => {
        const proxyUrl = `/api/proxy/image?url=${encodeURIComponent(page.url)}`;
        return `<img src="${escapeHtml(proxyUrl)}" alt="Page ${index + 1}" class="reader-page" loading="lazy" />`;
    }).join('');
}

function updateReaderControls() {
    const total = state.readerPages.length;
    els.readerPageIndicator.textContent = `${state.readerCurrentPage + 1} / ${total}`;
    els.prevPageBtn.disabled = state.readerCurrentPage === 0;
    els.nextPageBtn.disabled = state.readerCurrentPage >= total - 1;
}

function closeReader() {
    els.readerContainer.classList.remove('active');
    state.readerPages = [];
    state.readerCurrentPage = 0;
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
        consoleContent: document.getElementById('console-content')
    };

    console.log('[DEBUG] Elements initialized');
    console.log('[DEBUG] els.sourceList:', els.sourceList);
    console.log('[DEBUG] els.sidebar:', els.sidebar);
}

// ========================================
// Initialization
// ========================================
async function init() {
    // Initialize DOM elements first
    initElements();

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
    });

    els.searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    els.clearSearchBtn.addEventListener('click', () => {
        state.searchQuery = '';
        els.searchInput.value = '';
        els.clearSearchBtn.classList.add('hidden');
        loadDiscover(state.viewPages.discover || 1);
    });

    els.searchBtn.addEventListener('click', () => {
        performSearch();
    });

    els.searchModeBtn.addEventListener('click', () => {
        state.searchMode = state.searchMode === 'title' ? 'url' : 'title';
        const isTitle = state.searchMode === 'title';
        els.searchInput.placeholder = isTitle
            ? 'Search titles...'
            : 'Paste manga URL (18 sources supported)...';
        els.searchInput.value = ''; // Clear input on mode change
        state.searchQuery = '';
        els.clearSearchBtn.classList.add('hidden');
        els.searchModeIcon.setAttribute('data-lucide', isTitle ? 'search' : 'link');
        safeCreateIcons();

        // Show toast to inform user
        showToast(isTitle ? 'Search Mode: Title' : 'Search Mode: URL');
        log(`🔄 Search mode: ${state.searchMode.toUpperCase()}`);
    });

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
        const previousView = state.library.length > 0 ? 'library' : 'discover';
        setView(previousView);
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
        if (state.readerCurrentPage > 0) {
            state.readerCurrentPage--;
            updateReaderControls();
        }
    });
    els.nextPageBtn.addEventListener('click', () => {
        if (state.readerCurrentPage < state.readerPages.length - 1) {
            state.readerCurrentPage++;
            updateReaderControls();
        }
    });

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

    // Window resize
    window.addEventListener('resize', () => {
        if (window.innerWidth < 1024) closeSidebar();
    });

    log('Initialization complete');
}

// Start application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
