// MangaNegus Redesign - Main Application
// Integrates with existing Flask backend APIs

import { Storage } from './storage.js';

// ========================================
// Debug Mode
// ========================================
const DEBUG_MODE = false; // Set to true for development debugging

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
    filters: {
        genres: [],
        exclude: [],
        demographics: [],
        status: '',
        type: '',
        yearStart: '',
        yearEnd: '',
        scoreMin: '',
        scoreMax: '',
        sort: 'popularity',
        order: 'desc',
        density: 'normal',
        showMeta: true,
        dataSaver: false,
        pagination: 'paged',
        source: ''
    },
    librarySort: 'recent',
    smartFilter: '',
    collectionFilter: '',
    bulkStatusKeys: null,
    currentSource: '',
    sources: [],
    favoriteSources: new Set(),
    hiddenSources: new Set(),
    favoriteManga: new Set(),
    hiddenManga: new Set(),
    autoDownloadFavorites: false,
    autoBackupEnabled: false,
    lastAutoDownloadCheck: 0,
    autoDownloadTimer: null,
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
    mergeChapters: false,
    currentMangaSources: [],
    history: [],
    chapterFilters: {
        language: '',
        group: '',
        translation: ''
    },
    viewPages: {
        discover: 1,
        popular: 1,
        trending: 1,
        history: 1,
    },
    viewScrollPositions: {
        discover: 0,
        popular: 0,
        trending: 0,
        library: 0,
        history: 0,
    },
    feedCache: {
        discover: [],
        popular: [],
        trending: [],
    },
    isLoadingFeed: false,
    readerPages: [],
    readerCurrentPage: 0,
    readerMode: 'strip', // 'strip', 'paged', or 'webtoon'
    readerFitMode: 'fit-width', // 'fit-width', 'fit-height', 'fit-screen', 'fit-original'
    readerDirection: 'ltr', // 'ltr' or 'rtl'
    readerBackground: 'dark', // 'dark', 'light', 'sepia', 'black', 'white'
    readerSpread: false,
    readerEnhance: {
        brightness: 100,
        contrast: 100,
        sharpen: 0,
        crop: 0
    },
    prefetchDistance: 1,
    theme: 'dark', // 'dark', 'light', 'oled', 'sepia'
    themeSchedule: 'off',
    accentColor: '',
    manualTheme: 'dark',
    deferredInstallPrompt: null,
    readerObserver: null,
    imageObserver: null,
    readerImmersive: false,
    readerSessionStart: null,
    readerSessionPageStart: 0,
    readerScrollRaf: null,
    readerPreviousScrollY: 0, // Save scroll position when entering reader
    progressSaveTimer: null,
    prefetchedChapterId: null,
    prefetchedChapterTitle: null,
    prefetchedPages: null,
    prefetchedChapters: new Map(),
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
    pausedQueueCount: 0,
    queuePollInterval: null,
    // Offline & Sync
    offlineQueue: [],
    cloudSyncId: '',
    cloudSyncEnabled: false,
    cloudSyncLastSync: 0,
    cloudSyncTimer: null,
    // AbortControllers for cancelling in-flight requests (race condition prevention)
    chaptersAbortController: null,
    searchAbortController: null,
    paginationController: null,  // For cleaning up pagination event listeners
    // Selection Mode
    selectionMode: false,
    selectedCards: new Set(),
    currentTitleIndex: 0,
    activeMenu: null,  // Track open menu
    longPressTimer: null,
    touchStart: null,
    readerTouchStart: null,
    readerSwipeConsumed: false,
    notesSaveTimer: null,
    pageTotals: {},
    readerSpreadPages: new Set(),
    prefetchedCovers: new Set(),
    readingStats: {
        totalMinutes: 0,
        daily: {}
    }
};

// ========================================
// Global Debug Access (for Browser Console)
// ========================================
if (DEBUG_MODE) {
    window.DEBUG_STATE = state;
    window.DEBUG_ELS = null; // Will be set after initElements()
    console.log('[DEBUG] Debug mode enabled. Access state via window.DEBUG_STATE');
}

// ========================================
// Debounce Utility & Web Worker Setup
// ========================================
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Initialize Web Worker for heavy filtering operations
const filterWorker = new Worker('/static/js/worker.js');
const workerCallbacks = new Map();

filterWorker.onmessage = (e) => {
    const { id, result, error } = e.data;
    if (workerCallbacks.has(id)) {
        const { resolve, reject } = workerCallbacks.get(id);
        workerCallbacks.delete(id);
        if (error) reject(new Error(error));
        else resolve(result);
    }
};

function runFilterTask(taskType, payload) {
    return new Promise((resolve, reject) => {
        const id = Date.now() + Math.random();
        workerCallbacks.set(id, { resolve, reject });
        filterWorker.postMessage({ id, type: taskType, ...payload });
    });
}

const PLACEHOLDER_COVER = '/static/images/placeholder.png';

// ========================================
// Performance: Chunked Rendering
// ========================================
// Threshold for using chunked rendering (items count)
const CHUNKED_RENDER_THRESHOLD = 100;
const CHUNK_SIZE = 50;  // Items per frame

/**
 * Render items in chunks using requestAnimationFrame to avoid blocking UI.
 * Only used for large datasets (>100 items).
 */
async function renderChunked(items, container, renderFn, options = {}) {
    const { onProgress, onComplete, chunkSize = CHUNK_SIZE } = options;
    const total = items.length;
    let rendered = 0;

    // Clear container
    container.innerHTML = '';

    // Create document fragment for batch insertion
    const fragment = document.createDocumentFragment();

    return new Promise((resolve) => {
        function renderChunk() {
            const chunkEnd = Math.min(rendered + chunkSize, total);

            for (let i = rendered; i < chunkEnd; i++) {
                const html = renderFn(items[i], i);
                const temp = document.createElement('div');
                temp.innerHTML = html;
                fragment.appendChild(temp.firstElementChild);
            }

            // Append chunk to container
            container.appendChild(fragment);

            rendered = chunkEnd;

            if (onProgress) {
                onProgress(rendered, total);
            }

            if (rendered < total) {
                // Schedule next chunk
                requestAnimationFrame(renderChunk);
            } else {
                // Done rendering
                if (onComplete) {
                    onComplete();
                }
                resolve();
            }
        }

        // Start rendering
        requestAnimationFrame(renderChunk);
    });
}
const COVER_PROXY_HOSTS = new Set([
    'cdn.myanimelist.net',
    'uploads.mangadex.org',
    'mangadex.org',
    'cover.nep.li',
    'mangakakalot.com',
    'chapmanganato.com',
    'v1.mkklcdnv6tempv5.com',
    'v2.mkklcdnv6tempv5.com',
    'temp.compsci88.com',
    'hot.planeptune.us',
    'official.lowee.us',
    'official-ongoing-1.ivalice.us',
    'official-ongoing-2.ivalice.us',
    'official-complete-1.ivalice.us',
    'official-complete-2.ivalice.us'
]);
const STATUS_LABELS = {
    reading: 'Reading',
    completed: 'Completed',
    plan_to_read: 'Plan to Read',
    on_hold: 'On Hold',
    dropped: 'Dropped'
};

const memoryCache = new Map();
function getCached(key) {
    const entry = memoryCache.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expires) {
        memoryCache.delete(key);
        return null;
    }
    return entry.value;
}
function setCached(key, value, ttlMs) {
    memoryCache.set(key, { value, expires: Date.now() + ttlMs });
}

const PERSIST_CACHE_PREFIX = 'manganegus.cache:';
function getPersistentCache(key) {
    try {
        const raw = localStorage.getItem(`${PERSIST_CACHE_PREFIX}${key}`);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || Date.now() > parsed.expires) {
            localStorage.removeItem(`${PERSIST_CACHE_PREFIX}${key}`);
            return null;
        }
        return parsed.value ?? null;
    } catch {
        return null;
    }
}

function setPersistentCache(key, value, ttlMs) {
    try {
        localStorage.setItem(`${PERSIST_CACHE_PREFIX}${key}`, JSON.stringify({
            value,
            expires: Date.now() + ttlMs
        }));
    } catch {
        // Ignore storage errors
    }
}

function getCacheValue(key) {
    return getCached(key) ?? getPersistentCache(key);
}

function setCacheValue(key, value, ttlMs) {
    setCached(key, value, ttlMs);
    setPersistentCache(key, value, ttlMs);
}

function clearPersistentCache() {
    try {
        Object.keys(localStorage).forEach((key) => {
            if (key.startsWith(PERSIST_CACHE_PREFIX)) {
                localStorage.removeItem(key);
            }
        });
    } catch {
        // Ignore
    }
}

const FEED_CACHE_KEY = 'manganegus.feedCache';
const LIBRARY_CACHE_KEY = 'manganegus.libraryCache';
const HISTORY_CACHE_KEY = 'manganegus.historyCache';
const OFFLINE_QUEUE_KEY = 'manganegus.offlineQueue';

function loadFeedCache() {
    try {
        const raw = localStorage.getItem(FEED_CACHE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === 'object') {
                state.feedCache = { ...state.feedCache, ...parsed };
            }
        }
    } catch {
        // Ignore
    }
}

function saveFeedCache() {
    try {
        localStorage.setItem(FEED_CACHE_KEY, JSON.stringify(state.feedCache));
    } catch {
        // Ignore
    }
}

/**
 * Load cached library from IndexedDB (async).
 * Falls back to localStorage if IndexedDB unavailable.
 */
async function loadCachedLibrary() {
    try {
        const library = await Storage.getLibrary();
        return library && library.length > 0 ? library : null;
    } catch (error) {
        console.warn('[Storage] Failed to load library from IndexedDB, falling back to localStorage:', error);
        try {
            const raw = localStorage.getItem(LIBRARY_CACHE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }
}

/**
 * Save library to IndexedDB (async).
 * Non-blocking - doesn't wait for completion.
 */
function saveCachedLibrary() {
    // Use async but don't await - fire and forget for better UX
    Storage.setLibrary(state.library || []).catch(error => {
        console.warn('[Storage] Failed to save library to IndexedDB:', error);
        // Fallback to localStorage
        try {
            localStorage.setItem(LIBRARY_CACHE_KEY, JSON.stringify(state.library || []));
        } catch {
            // Ignore
        }
    });
}

/**
 * Load cached history from IndexedDB (async).
 * Falls back to localStorage if IndexedDB unavailable.
 */
async function loadCachedHistory() {
    try {
        const history = await Storage.getHistory();
        return history && history.length > 0 ? history : null;
    } catch (error) {
        console.warn('[Storage] Failed to load history from IndexedDB, falling back to localStorage:', error);
        try {
            const raw = localStorage.getItem(HISTORY_CACHE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    }
}

/**
 * Save history to IndexedDB (async).
 * Non-blocking - doesn't wait for completion.
 */
function saveCachedHistory() {
    // Use async but don't await - fire and forget for better UX
    Storage.setHistory(state.history || []).catch(error => {
        console.warn('[Storage] Failed to save history to IndexedDB:', error);
        // Fallback to localStorage
        try {
            localStorage.setItem(HISTORY_CACHE_KEY, JSON.stringify(state.history || []));
        } catch {
            // Ignore
        }
    });
}

function loadOfflineQueue() {
    try {
        const raw = localStorage.getItem(OFFLINE_QUEUE_KEY);
        state.offlineQueue = raw ? JSON.parse(raw) : [];
    } catch {
        state.offlineQueue = [];
    }
}

function saveOfflineQueue() {
    try {
        localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(state.offlineQueue || []));
    } catch {
        // Ignore
    }
}

function queueOfflineAction(action) {
    if (!action || !action.type) return;
    state.offlineQueue.push({ ...action, queued_at: Date.now() });
    saveOfflineQueue();
}

async function flushOfflineQueue() {
    if (!navigator.onLine || !state.offlineQueue.length) return;
    const pending = [...state.offlineQueue];
    state.offlineQueue = [];
    saveOfflineQueue();

    for (const item of pending) {
        try {
            if (item.type === 'add_library') {
                await API.addToLibrary(item.payload);
            } else if (item.type === 'update_status') {
                await API.updateStatus(item.payload.key, item.payload.status);
            } else if (item.type === 'update_progress') {
                await API.updateProgress(
                    item.payload.key,
                    item.payload.chapter,
                    item.payload.page,
                    item.payload.chapter_id,
                    item.payload.total_chapters,
                    item.payload.page_total
                );
            } else if (item.type === 'remove_library') {
                await API.removeFromLibrary(item.payload.key);
            } else if (item.type === 'history') {
                await API.addHistory(item.payload);
            }
        } catch (error) {
            log(`Offline sync failed for ${item.type}: ${error.message}`);
        }
    }
}

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
            const { silent, retries = 0, retryDelay = 400, ...requestOptions } = options;
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
            let attempt = 0;
            while (true) {
                try {
                    const response = await fetch(endpoint, fetchOptions);
                    const contentType = response.headers.get('content-type') || '';
                    const isJson = contentType.includes('application/json');
                    const data = isJson ? await response.json() : null;

                    if (!response.ok) {
                        let message = data?.error || data?.message || `HTTP ${response.status}: ${response.statusText}`;
                        if (response.status === 429) {
                            message = 'Rate limited. Please try again in a moment.';
                        }
                        if (response.status === 403) {
                            message = 'Access blocked by security policy.';
                        }
                        throw new Error(message);
                    }

                    return data;
                } catch (error) {
                    if (error.name === 'AbortError') {
                        throw error;
                    }
                    if (attempt >= retries) {
                        throw error;
                    }
                    const delay = retryDelay * (2 ** attempt);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    attempt += 1;
                }
            }
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

    async search(query, limit = 15, filters = null, signal = undefined) {
        const payload = { query, limit };
        if (filters) {
            payload.filters = filters;
        }
        const sourceFilter = payload.filters?.source || '';
        const cacheKey = `search:${query}:${limit}:${JSON.stringify(payload.filters || {})}:${sourceFilter}`;
        const cached = getCacheValue(cacheKey);
        if (cached) return cached;
        const data = await this.request('/api/search', {
            method: 'POST',
            body: JSON.stringify(payload),
            signal
        });
        const results = data || [];
        setCacheValue(cacheKey, results, 5 * 60 * 1000);
        return results;
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

    async smartSearch(query, limit = 5) {
        const data = await this.request('/api/search/smart', {
            method: 'POST',
            body: JSON.stringify({ query, limit, enrich_metadata: false }),
            silent: true
        });
        return data?.results || [];
    },

    async detectUrl(url) {
        const data = await this.request('/api/detect_url', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
        return data;
    },

    async getPopular(page = 1, limit = 24) {
        const data = await this.request(`/api/popular?page=${page}&limit=${limit}`, { retries: 2, retryDelay: 500 });
        return Array.isArray(data) ? data : [];
    },

    async getTrending(page = 1, limit = 24) {
        const data = await this.request(`/api/trending?page=${page}&limit=${limit}`, { retries: 2, retryDelay: 500 });
        return Array.isArray(data) ? data : [];
    },

    async getDiscover(page = 1, limit = 20) {
        const data = await this.request(`/api/discover?page=${page}&limit=${limit}`, { retries: 2, retryDelay: 500 });
        return Array.isArray(data) ? data : [];
    },

    async getRecommendations(malId, limit = 8) {
        if (!malId) return [];
        const cacheKey = `recommendations:${malId}`;
        const cached = getCacheValue(cacheKey);
        if (cached) return cached;
        const data = await this.request(`/api/recommendations/${malId}?limit=${limit}`, {
            silent: true,
            retries: 1,
            retryDelay: 300
        });
        const results = Array.isArray(data) ? data : [];
        setCacheValue(cacheKey, results, 30 * 60 * 1000); // Cache for 30 mins
        return results;
    },

    async getLatestFeed(sourceId = '', page = 1) {
        const url = `/api/latest_feed?page=${page}${sourceId ? `&source_id=${encodeURIComponent(sourceId)}` : ''}`;
        const data = await this.request(url);
        return Array.isArray(data) ? data : [];
    },

    async getHistory(limit = 50) {
        const data = await this.request(`/api/history?limit=${limit}`, { retries: 1, retryDelay: 500 });
        return Array.isArray(data) ? data : [];
    },

    async cloudPush(syncId, payload) {
        return this.request('/api/cloud/push', {
            method: 'POST',
            body: JSON.stringify({ sync_id: syncId, payload })
        });
    },

    async cloudPull(syncId) {
        return this.request(`/api/cloud/pull?sync_id=${encodeURIComponent(syncId)}`, { retries: 1, retryDelay: 500 });
    },

    async addHistory(entry) {
        return this.request('/api/history', {
            method: 'POST',
            body: JSON.stringify(entry)
        });
    },

    async getChapters(mangaId, source, page = 1, title = null, malId = null, options = {}) {
        const payload = {
            id: mangaId,
            source,
            offset: (page - 1) * 100,
            limit: 100
        };
        if (title) payload.title = title;
        if (malId) payload.mal_id = malId;

        const data = await this.request('/api/chapters', {
            method: 'POST',
            body: JSON.stringify(payload),
            retries: 1,
            retryDelay: 500,
            ...options
        });
        return data;
    },

    async getAllChapters(mangaId, source, options = {}) {
        const data = await this.request('/api/all_chapters', {
            method: 'POST',
            body: JSON.stringify({ id: mangaId, source }),
            ...options
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
        // Use pages_data (with referer info) if available, fallback to pages (strings only)
        const pages = data.pages_data || data.pages || [];
        console.log('[API DEBUG] Extracted pages:', pages.length, 'items, hasReferer:', !!(pages[0]?.referer));
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

    async exportLibrary() {
        return this.request('/api/library/export');
    },

    async importLibrary(entries) {
        return this.request('/api/library/import', {
            method: 'POST',
            body: JSON.stringify({ entries })
        });
    },

    async importHistory(entries) {
        return this.request('/api/history/import', {
            method: 'POST',
            body: JSON.stringify({ entries })
        });
    },

    async getPreferences() {
        return this.request('/api/library/preferences', { silent: true });
    },

    async savePreferences(payload) {
        return this.request('/api/library/preferences', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
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

    async updateProgress(key, chapter, page = null, chapterId = null, totalChapters = null, pageTotal = null) {
        const payload = { key, chapter };
        if (page !== null) payload.page = page;
        if (chapterId) payload.chapter_id = chapterId;
        if (totalChapters !== null) payload.total_chapters = totalChapters;
        if (pageTotal !== null) payload.page_total = pageTotal;
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

    async downloadChapter(mangaId, chapterId, source, title, chapterTitle, chapterNumber = '0', startImmediately = true) {
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
                manga_id: mangaId,
                start_immediately: startImmediately
            })
        });
        return data;
    },

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

    // Download Queue API
    async getDownloadQueue() {
        const data = await this.request('/api/download/queue');
        return data;
    },

    async startPausedDownloads(jobIds = null) {
        const data = await this.request('/api/download/start_paused', {
            method: 'POST',
            body: JSON.stringify({ job_ids: jobIds })
        });
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

/**
 * Show a custom confirm modal (replacement for native confirm())
 * @param {string} title - Modal title
 * @param {string} message - Modal message
 * @param {string} confirmText - Text for confirm button (default: 'Confirm')
 * @returns {Promise<boolean>} - Resolves true if confirmed, false if cancelled
 */
function showConfirmModal(title, message, confirmText = 'Confirm') {
    return new Promise((resolve) => {
        if (!els.confirmModal) {
            // Fallback to native confirm if modal elements don't exist
            resolve(confirm(message));
            return;
        }

        els.confirmTitle.textContent = title;
        els.confirmMessage.textContent = message;
        els.confirmOkBtn.textContent = confirmText;
        els.confirmModal.classList.add('active');

        const cleanup = () => {
            els.confirmModal.classList.remove('active');
            els.confirmOkBtn.removeEventListener('click', handleConfirm);
            els.confirmCancelBtn.removeEventListener('click', handleCancel);
            els.confirmModal.removeEventListener('click', handleOverlayClick);
        };

        const handleConfirm = () => {
            cleanup();
            resolve(true);
        };

        const handleCancel = () => {
            cleanup();
            resolve(false);
        };

        const handleOverlayClick = (e) => {
            if (e.target === els.confirmModal) {
                cleanup();
                resolve(false);
            }
        };

        els.confirmOkBtn.addEventListener('click', handleConfirm);
        els.confirmCancelBtn.addEventListener('click', handleCancel);
        els.confirmModal.addEventListener('click', handleOverlayClick);
    });
}

// ========================================
// Download Queue Management
// ========================================
async function fetchDownloadQueue() {
    try {
        const data = await API.getDownloadQueue();
        state.downloadQueue = data.queue || [];
        state.queuePaused = data.paused || false;
        state.pausedQueueCount = Number.isFinite(data.paused_count) ? data.paused_count : 0;
        updateQueueBadge();
        return data;
    } catch (error) {
        console.error('[Queue] Failed to fetch queue:', error);
        return { queue: [], paused: false, paused_count: 0 };
    }
}

function updateQueueBadge() {
    const activeCount = state.downloadQueue.filter(
        item => ['queued', 'downloading', 'paused'].includes(item.status)
    ).length;

    if (els.queueBadge) {
        if (activeCount > 0) {
            els.queueBadge.textContent = activeCount;
            els.queueBadge.classList.remove('hidden');
        } else {
            els.queueBadge.classList.add('hidden');
        }
    }

    const pausedCount = Number.isFinite(state.pausedQueueCount)
        ? state.pausedQueueCount
        : state.downloadQueue.filter(item => item.status === 'paused_queue').length;

    if (els.pausedBadge) {
        if (pausedCount > 0) {
            els.pausedBadge.textContent = pausedCount;
            els.pausedBadge.classList.remove('hidden');
        } else {
            els.pausedBadge.classList.add('hidden');
        }
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

    const paused = state.downloadQueue.filter(item => item.status === 'paused_queue');
    const active = state.downloadQueue.filter(item => ['queued', 'downloading', 'paused'].includes(item.status));
    const completed = state.downloadQueue.filter(item => ['completed', 'failed', 'cancelled'].includes(item.status));

    els.queueSubtitle.textContent = `${active.length} active, ${paused.length} paused, ${state.downloadQueue.length} total`;

    let html = '';

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

    if (active.length > 0) {
        html += `
            <div class="queue-section">
                <h3>Active Downloads (${active.length})</h3>
                ${active.map(item => renderQueueItem(item, false)).join('')}
            </div>
        `;
    }

    if (completed.length > 0) {
        html += `
            <div class="queue-section">
                <h3>Completed (${completed.length})</h3>
                ${completed.map(item => renderQueueItem(item, false)).join('')}
            </div>
        `;
    }

    els.queueList.innerHTML = html;
    safeCreateIcons();

    const startAllBtn = document.getElementById('btn-start-all-paused');
    if (startAllBtn) {
        startAllBtn.addEventListener('click', startAllPaused);
    }

    document.querySelectorAll('.btn-start-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const jobId = btn.dataset.jobId;
            startPausedItem(jobId);
        });
    });
}

function renderQueueItem(item, isPausedSection) {
    const statusClass = item.status === 'paused_queue' ? 'paused' : item.status;
    const statusLabel = item.status === 'paused_queue' ? 'paused' : item.status;
    const totalChapters = Number.isFinite(item.chapters_total)
        ? item.chapters_total
        : (item.chapters?.length || 0);
    const chaptersDone = Number.isFinite(item.chapters_done) ? item.chapters_done : 0;

    const progress = totalChapters > 0
        ? Math.round((chaptersDone / totalChapters) * 100)
        : 0;

    const pageProgress = item.total_pages > 0
        ? `Page ${item.current_page}/${item.total_pages}`
        : '';

    let actions = '';
    if (isPausedSection) {
        actions = `
            <button class="control-btn primary btn-start-item" data-job-id="${item.job_id}">
                <i data-lucide="play" width="12"></i> Start
            </button>
            <button class="control-btn" onclick="cancelQueueItem('${item.job_id}')">
                <i data-lucide="x" width="12"></i> Cancel
            </button>
        `;
    } else if (item.status === 'downloading') {
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
        <div class="queue-item ${statusClass}">
            <div class="queue-item-header">
                <span class="queue-item-title">${escapeHtml(item.title)}</span>
                <span class="queue-item-status ${statusClass}">${statusLabel}</span>
            </div>
            <div class="queue-item-progress">
                <div class="queue-progress-bar">
                    <div class="queue-progress-fill" style="width: ${progress}%"></div>
                </div>
                <span class="queue-progress-text">
                    Chapter ${chaptersDone}/${totalChapters} (${progress}%)
                    ${pageProgress ? ' - ' + pageProgress : ''}
                </span>
            </div>
            <div class="queue-item-actions">${actions}</div>
        </div>
    `;
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

async function startAllPaused() {
    try {
        await API.startPausedDownloads();
        showToast('Starting paused downloads');
        await fetchDownloadQueue();
        renderDownloadQueue();
    } catch (error) {
        showToast('Failed to start paused downloads');
    }
}

async function startPausedItem(jobId) {
    try {
        await API.startPausedDownloads([jobId]);
        showToast('Starting download');
        await fetchDownloadQueue();
        renderDownloadQueue();
    } catch (error) {
        showToast('Failed to start download');
    }
}

function openDownloadQueue() {
    fetchDownloadQueue().then(() => {
        renderDownloadQueue();
        els.downloadQueueModal.classList.add('active');

        // Start polling for updates
        if (state.queuePollInterval) clearInterval(state.queuePollInterval);
        const interval = state.filters.dataSaver ? 8000 : 2000;
        state.queuePollInterval = setInterval(async () => {
            const hasActive = state.downloadQueue.some(
                item => item.status === 'downloading'
            );
            if (hasActive) {
                await fetchDownloadQueue();
                renderDownloadQueue();
            }
        }, interval);
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
    // Safety: If reader-active is on body but reader is not actually active,
    // remove it (handles edge case where reader closed unexpectedly)
    if (document.body.classList.contains('reader-active') &&
        !els.readerContainer.classList.contains('active')) {
        console.log('[DEBUG] toggleSidebar - cleaning up orphaned reader-active class');
        document.body.classList.remove('reader-active');
    }

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

    const hiddenSources = state.hiddenSources;
    const favoriteSources = state.favoriteSources;
    const visibleSources = state.sources.filter(source => !hiddenSources.has(source.id));

    if (!visibleSources.length) {
        els.sourceList.innerHTML = '<p style="padding: 0 24px; color: var(--text-muted); font-size: 12px;">All sources hidden</p>';
        return;
    }

    // Show only top sources for cleaner sidebar
    const topSources = [
        'weebcentral-v2',
        'mangadex',
        'manganato',
        'mangafire-v2',
        'mangasee-v2',
        'asurascans'
    ];

    const favorites = visibleSources.filter(s => favoriteSources.has(s.id));
    const topList = visibleSources.filter(s => topSources.includes(s.id));

    let sourcesToDisplay = [];
    if (favorites.length) {
        sourcesToDisplay = [...favorites];
        const remaining = visibleSources.filter(s => !favoriteSources.has(s.id));
        const fillFromTop = remaining.filter(s => topSources.includes(s.id));
        if (sourcesToDisplay.length < 6) {
            sourcesToDisplay = sourcesToDisplay.concat(fillFromTop.slice(0, 6 - sourcesToDisplay.length));
        }
        if (sourcesToDisplay.length < 6) {
            const fillFromOther = remaining.filter(s => !topSources.includes(s.id));
            sourcesToDisplay = sourcesToDisplay.concat(fillFromOther.slice(0, 6 - sourcesToDisplay.length));
        }
    } else if (topList.length) {
        sourcesToDisplay = topList.slice(0, 6);
    } else {
        sourcesToDisplay = visibleSources.slice(0, 6);
    }

    const renderSourceButton = (source) => {
        const isActive = state.currentSource === source.id;
        const isFavorite = favoriteSources.has(source.id);
        return `
            <button class="source-btn ${isActive ? 'active' : ''}" data-source="${escapeHtml(source.id)}" type="button">
                <span class="source-name">${escapeHtml(source.name)}</span>
                <span class="source-actions">
                    <span class="source-fav-toggle ${isFavorite ? 'active' : ''}" data-action="source-favorite" data-source="${escapeHtml(source.id)}" aria-label="Toggle favorite source" role="button" tabindex="0">
                        <i data-lucide="star" width="14"></i>
                    </span>
                    ${isActive ? '<div class="status-dot"></div>' : ''}
                </span>
            </button>
        `;
    };

    els.sourceList.innerHTML = sourcesToDisplay.map(renderSourceButton).join('');

    // Add "All Sources" button
    els.sourceList.innerHTML += `
        <button class="source-btn" id="show-all-sources-btn">
            <span>All Sources (${state.sources.length})</span>
            <i data-lucide="chevron-right" width="16"></i>
        </button>
    `;

    populateFilterSources();
    safeCreateIcons();
    // Event delegation handled by setupEventDelegation() - no per-button listeners needed

    log(`✅ Rendered ${sourcesToDisplay.length} sources in sidebar`);
}

function loadSourcePreferences() {
    try {
        const favRaw = localStorage.getItem('manganegus.sourceFavorites');
        const hiddenRaw = localStorage.getItem('manganegus.sourceHidden');
        const favList = favRaw ? JSON.parse(favRaw) : [];
        const hiddenList = hiddenRaw ? JSON.parse(hiddenRaw) : [];
        state.favoriteSources = new Set(Array.isArray(favList) ? favList : []);
        state.hiddenSources = new Set(Array.isArray(hiddenList) ? hiddenList : []);
    } catch {
        state.favoriteSources = new Set();
        state.hiddenSources = new Set();
    }
}

function saveSourcePreferences() {
    try {
        localStorage.setItem('manganegus.sourceFavorites', JSON.stringify(Array.from(state.favoriteSources)));
        localStorage.setItem('manganegus.sourceHidden', JSON.stringify(Array.from(state.hiddenSources)));
    } catch {
        // Ignore
    }
}

function toggleFavoriteSource(sourceId) {
    if (!sourceId) return;
    if (state.favoriteSources.has(sourceId)) {
        state.favoriteSources.delete(sourceId);
    } else {
        state.favoriteSources.add(sourceId);
    }
    saveSourcePreferences();
    renderSources();
}

function toggleHiddenSource(sourceId) {
    if (!sourceId) return;
    if (state.hiddenSources.has(sourceId)) {
        state.hiddenSources.delete(sourceId);
    } else {
        state.hiddenSources.add(sourceId);
        if (state.currentSource === sourceId) {
            state.currentSource = '';
        }
    }
    saveSourcePreferences();
    renderSources();
}

function populateFilterSources() {
    if (!els.filterSource) return;
    const visibleSources = state.sources.filter(source => !state.hiddenSources.has(source.id));
    const options = ['<option value="">All Sources</option>']
        .concat(visibleSources
            .slice()
            .sort((a, b) => String(a.name).localeCompare(String(b.name)))
            .map(source => `<option value="${escapeHtml(source.id)}">${escapeHtml(source.name)}</option>`));
    els.filterSource.innerHTML = options.join('');
    els.filterSource.value = state.filters.source || '';
}

function setSource(sourceId) {
    if (state.hiddenSources.has(sourceId)) {
        showToast('Source hidden - unhide it from All Sources');
        return;
    }
    state.currentSource = sourceId;
    state.filters.source = sourceId;
    try {
        localStorage.setItem('manganegus.currentSource', sourceId);
    } catch {
        // Ignore
    }
    renderSources();
    saveFilters();
    updateFilterButtonState();
    if (els.filterSource) {
        els.filterSource.value = state.filters.source || '';
    }
    reloadActiveView();
    showToast(`Source: ${state.sources.find(s => s.id === sourceId)?.name || sourceId}`);
}

function getSourceDisplayName(sourceId) {
    if (!sourceId) return '';
    return state.sources.find(source => source.id === sourceId)?.name || sourceId;
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
        const sourceCards = (health.sources || []).map(source => {
            const isFavorite = state.favoriteSources.has(source.id);
            const isHidden = state.hiddenSources.has(source.id);
            const statusLabel = source.status ? source.status.replace('_', ' ').toUpperCase() : (source.is_available ? 'ONLINE' : 'OFFLINE');
            const cooldown = source.cooldown_remaining ? Math.ceil(source.cooldown_remaining) : 0;
            const rateLimitPerMin = source.rate_limit_per_minute ? Math.round(source.rate_limit_per_minute) : 0;
            const isRateLimited = source.status === 'rate_limited' || cooldown > 0;
            const rateLabel = isRateLimited
                ? `Rate limited${cooldown ? ` · ${cooldown}s` : ''}`
                : (rateLimitPerMin ? `Rate limit: ${rateLimitPerMin}/min` : '');
            const rateClass = isRateLimited ? 'rate-warning' : '';
            return `
                <div class="source-status-item source-pref-item ${isHidden ? 'hidden' : ''}">
                    <div>
                        <span class="source-status-name">${escapeHtml(source.name)}</span>
                        <div class="source-status-indicator">
                            <div class="status-dot ${source.is_available ? '' : 'offline'}"></div>
                            <span>${escapeHtml(statusLabel)}</span>
                        </div>
                        ${rateLabel ? `<p class="source-status-note ${rateClass}">${escapeHtml(rateLabel)}</p>` : ''}
                        ${source.last_error ? `<p class="source-status-note">${escapeHtml(source.last_error)}</p>` : ''}
                    </div>
                    <div class="source-pref-actions">
                        <button class="source-toggle ${isFavorite ? 'active' : ''}" data-action="source-favorite" data-source="${escapeHtml(source.id)}">
                            ${isFavorite ? 'Favorited' : 'Favorite'}
                        </button>
                        <button class="source-toggle ${isHidden ? 'active' : ''}" data-action="source-hide" data-source="${escapeHtml(source.id)}">
                            ${isHidden ? 'Hidden' : 'Hide'}
                        </button>
                    </div>
                </div>
            `;
        });

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
    if (DEBUG_MODE) {
        console.log(`[DEBUG] setView called: ${state.activeView} → ${viewId}`);
    }

    // Track previous view (but not if we're going to details view)
    if (viewId !== 'details' && state.activeView !== 'details') {
        state.previousView = state.activeView;
    }
    if (state.viewScrollPositions && Object.prototype.hasOwnProperty.call(state.viewScrollPositions, state.activeView)) {
        state.viewScrollPositions[state.activeView] = window.scrollY;
    }

    // Cleanup IntersectionObserver to prevent memory leak
    clearImageObserver();

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
            state.viewPages.discover = state.viewPages.discover || 1;
            if (!state.searchQuery) {
                loadDiscover(state.viewPages.discover);
            } else {
                setupLazyImages(els.discoverGrid);
            }
            break;
        case 'trending':
            els.discoverView.classList.remove('hidden');
            els.discoverTitle.textContent = 'Trending';
            state.viewPages.trending = state.viewPages.trending || 1;
            loadTrendingView(state.viewPages.trending);
            break;
        case 'popular':
            els.discoverView.classList.remove('hidden');
            els.discoverTitle.textContent = 'Popular';
            state.viewPages.popular = state.viewPages.popular || 1;
            loadPopular(state.viewPages.popular);
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

    if (els.randomBtn) {
        const showRandom = ['discover', 'popular', 'trending'].includes(viewId);
        els.randomBtn.classList.toggle('hidden', !showRandom);
    }
    if (els.historyTools) {
        els.historyTools.classList.toggle('hidden', viewId !== 'history');
    }
    if (els.historyCalendar) {
        els.historyCalendar.classList.toggle('hidden', viewId !== 'history');
    }
    if (els.recommendationsSection && !['discover', 'popular', 'trending'].includes(viewId)) {
        els.recommendationsSection.classList.add('hidden');
    }

    renderNav();
    if (window.innerWidth < 1024) closeSidebar();
    const targetScroll = viewId === 'details'
        ? 0
        : (state.viewScrollPositions?.[viewId] ?? 0);
    requestAnimationFrame(() => {
        window.scrollTo({ top: targetScroll, behavior: 'auto' });
    });

    if (DEBUG_MODE) {
        console.log(`[DEBUG] setView complete. Active view: ${viewId}`);
        console.log(`[DEBUG] View visibility:`, {
            discover: !els.discoverView.classList.contains('hidden'),
            library: !els.libraryView.classList.contains('hidden'),
            details: !els.detailsView.classList.contains('hidden')
        });
    }
}

function updateDiscoverSubtitle(text) {
    if (els.discoverSubtitle) {
        els.discoverSubtitle.textContent = text;
    }
}

// ========================================
// Filters + Display Settings
// ========================================
function loadFilters() {
    try {
        const raw = localStorage.getItem('manganegus.filters');
        if (raw) {
            const parsed = JSON.parse(raw);
            state.filters = { ...state.filters, ...parsed };
        }
    } catch {
        // Ignore
    }
}

function saveFilters() {
    localStorage.setItem('manganegus.filters', JSON.stringify(state.filters));
}

function parseFilterList(value) {
    return (value || '')
        .split(',')
        .map(item => item.trim().toLowerCase())
        .filter(Boolean);
}

function isFilterActive() {
    const f = state.filters;
    return Boolean(
        (f.genres && f.genres.length) ||
        (f.exclude && f.exclude.length) ||
        (f.demographics && f.demographics.length) ||
        f.status ||
        f.type ||
        f.yearStart ||
        f.yearEnd ||
        f.scoreMin ||
        f.scoreMax ||
        (f.density && f.density !== 'normal') ||
        f.showMeta === false ||
        f.dataSaver ||
        (f.pagination && f.pagination !== 'paged') ||
        f.source
    );
}

function updateFilterButtonState() {
    if (!els.filterBtn) return;
    els.filterBtn.classList.toggle('active', isFilterActive());
}

function applyGridDensity() {
    const density = state.filters.density || 'normal';
    document.body.classList.remove('density-compact', 'density-comfortable', 'density-list');
    if (density === 'compact') {
        document.body.classList.add('density-compact');
    } else if (density === 'comfortable') {
        document.body.classList.add('density-comfortable');
    } else if (density === 'list') {
        document.body.classList.add('density-list');
    }
    document.body.classList.toggle('hide-card-meta', state.filters.showMeta === false);
}

function getEffectivePrefetchDistance() {
    return state.filters.dataSaver ? 0 : state.prefetchDistance;
}

function getDataSaverDownloadLimit() {
    return state.filters.dataSaver ? 5 : Infinity;
}

function applyFiltersToList(list) {
    const f = state.filters;
    if (!Array.isArray(list)) return [];
    let results = [...list];

    results = results.filter(item => {
        const mangaId = item.mal_id || item.id || item.manga_id;
        const sourceId = item.source || item.source_id || (item.mal_id ? 'jikan' : '');
        if (!mangaId || !sourceId) return true;
        return !isHiddenManga(mangaId, sourceId);
    });

    if (f.source) {
        results = results.filter(item => {
            const sourceId = item.source || item.source_id || (item.mal_id ? 'jikan' : '');
            return sourceId ? sourceId === f.source : false;
        });
    }

    if (f.genres?.length) {
        results = results.filter(item => {
            const tags = (item.genres || item.tags || []).map(tag => String(tag).toLowerCase());
            return f.genres.every(tag => tags.includes(tag));
        });
    }
    if (f.exclude?.length) {
        results = results.filter(item => {
            const tags = (item.genres || item.tags || []).map(tag => String(tag).toLowerCase());
            return !f.exclude.some(tag => tags.includes(tag));
        });
    }
    if (f.demographics?.length) {
        results = results.filter(item => {
            const tags = (item.demographics || item.tags || item.genres || []).map(tag => String(tag).toLowerCase());
            return f.demographics.every(tag => tags.includes(tag));
        });
    }
    if (f.status) {
        results = results.filter(item => (item.status || '').toLowerCase().includes(f.status));
    }
    if (f.type) {
        results = results.filter(item => (item.type || '').toLowerCase().includes(f.type));
    }
    if (f.yearStart) {
        results = results.filter(item => Number(item.year || 0) >= Number(f.yearStart));
    }
    if (f.yearEnd) {
        results = results.filter(item => Number(item.year || 0) <= Number(f.yearEnd));
    }
    if (f.scoreMin) {
        results = results.filter(item => Number(item.rating?.average || item.score || 0) >= Number(f.scoreMin));
    }
    if (f.scoreMax) {
        results = results.filter(item => Number(item.rating?.average || item.score || 0) <= Number(f.scoreMax));
    }

    const sortKey = f.sort || 'popularity';
    const order = f.order === 'asc' ? 1 : -1;
    results.sort((a, b) => {
        const aScore = a.rating?.average || a.score || 0;
        const bScore = b.rating?.average || b.score || 0;
        const aPop = a.popularity || a.rank || a.rating?.count || 0;
        const bPop = b.popularity || b.rank || b.rating?.count || 0;
        const aCh = a.chapters || 0;
        const bCh = b.chapters || 0;
        const aYear = a.year || 0;
        const bYear = b.year || 0;
        switch (sortKey) {
            case 'score':
                return (aScore - bScore) * order;
            case 'title':
                return String(a.title || '').localeCompare(String(b.title || '')) * order;
            case 'chapters':
                return (aCh - bCh) * order;
            case 'year':
                return (aYear - bYear) * order;
            case 'popularity':
            default:
                return (aPop - bPop) * order;
        }
    });

    return results;
}

function syncFilterModal() {
    if (!els.filterModal) return;
    if (els.filterGenres) els.filterGenres.value = state.filters.genres.join(', ');
    if (els.filterExclude) els.filterExclude.value = state.filters.exclude.join(', ');
    if (els.filterDemographics) els.filterDemographics.value = state.filters.demographics.join(', ');
    if (els.filterStatus) els.filterStatus.value = state.filters.status || '';
    if (els.filterType) els.filterType.value = state.filters.type || '';
    if (els.filterYearStart) els.filterYearStart.value = state.filters.yearStart || '';
    if (els.filterYearEnd) els.filterYearEnd.value = state.filters.yearEnd || '';
    if (els.filterScoreMin) els.filterScoreMin.value = state.filters.scoreMin || '';
    if (els.filterScoreMax) els.filterScoreMax.value = state.filters.scoreMax || '';
    if (els.filterSort) els.filterSort.value = state.filters.sort || 'popularity';
    if (els.filterOrder) els.filterOrder.value = state.filters.order || 'desc';
    if (els.filterDensity) els.filterDensity.value = state.filters.density || 'normal';
    if (els.filterMeta) els.filterMeta.value = state.filters.showMeta === false ? 'off' : 'on';
    if (els.filterDataSaver) els.filterDataSaver.value = state.filters.dataSaver ? 'on' : 'off';
    if (els.filterSource) els.filterSource.value = state.filters.source || '';
    if (els.filterPagination) els.filterPagination.value = state.filters.pagination || 'paged';
}

function openFilterModal() {
    if (!els.filterModal) return;
    syncFilterModal();
    els.filterModal.classList.add('active');
}

function closeFilterModal() {
    if (!els.filterModal) return;
    els.filterModal.classList.remove('active');
}

function updateOfflineBanner() {
    if (!els.offlineBanner) return;
    els.offlineBanner.classList.toggle('hidden', navigator.onLine);
}

function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.register('/static/sw.js').catch(error => {
        log(`Service worker registration failed: ${error.message}`);
    });
}

function resetFilters() {
    state.filters = {
        ...state.filters,
        genres: [],
        exclude: [],
        demographics: [],
        status: '',
        type: '',
        yearStart: '',
        yearEnd: '',
        scoreMin: '',
        scoreMax: '',
        sort: 'popularity',
        order: 'desc',
        density: 'normal',
        showMeta: true,
        dataSaver: false,
        pagination: 'paged',
        source: ''
    };
    saveFilters();
    applyGridDensity();
    updateFilterButtonState();
    applyDataSaverMode();
    reloadActiveView();
}

function applyFiltersFromModal() {
    state.filters.genres = parseFilterList(els.filterGenres?.value);
    state.filters.exclude = parseFilterList(els.filterExclude?.value);
    state.filters.demographics = parseFilterList(els.filterDemographics?.value);
    state.filters.status = (els.filterStatus?.value || '').toLowerCase();
    state.filters.type = (els.filterType?.value || '').toLowerCase();
    state.filters.yearStart = els.filterYearStart?.value || '';
    state.filters.yearEnd = els.filterYearEnd?.value || '';
    state.filters.scoreMin = els.filterScoreMin?.value || '';
    state.filters.scoreMax = els.filterScoreMax?.value || '';
    state.filters.sort = els.filterSort?.value || 'popularity';
    state.filters.order = els.filterOrder?.value || 'desc';
    state.filters.density = els.filterDensity?.value || 'normal';
    state.filters.showMeta = (els.filterMeta?.value || 'on') === 'on';
    state.filters.dataSaver = (els.filterDataSaver?.value || 'off') === 'on';
    state.filters.source = els.filterSource?.value || '';
    state.filters.pagination = els.filterPagination?.value || 'paged';
    saveFilters();
    applyGridDensity();
    updateFilterButtonState();
    applyDataSaverMode();
    closeFilterModal();
    reloadActiveView();
}

function applyDataSaverMode() {
    scheduleAutoDownloadChecks();
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
        <button class="search-suggestion-item" type="button" data-value="${escapeHtml(item.title)}">
            <span class="label">${escapeHtml(item.title)}</span>
            <span class="hint">Live</span>
        </button>
        `).join('');
    }

    if (historyMatches.length > 0) {
        html += `<div class="search-suggestion-header">Recent</div>`;
        html += historyMatches.map(item => `
        <button class="search-suggestion-item" type="button" data-value="${escapeHtml(item)}">
            <span class="label">${escapeHtml(item)}</span>
            <span class="hint">Recent</span>
        </button>
        `).join('');
        html += `
            <button class="search-suggestion-item" type="button" data-action="clear">
                <span class="label">Clear search history</span>
            </button>
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

    if (state.filters.dataSaver) {
        clearLiveSuggestions();
        renderSearchSuggestions(query);
        return;
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
    if (state.filters.pagination === 'infinite') {
        els.discoverPagination.classList.add('hidden');
        els.discoverPagination.innerHTML = '';
        return;
    }

    // Cleanup previous event listeners to prevent memory leak
    if (state.paginationController) {
        state.paginationController.abort();
    }
    state.paginationController = new AbortController();
    const { signal } = state.paginationController;

    els.discoverPagination.classList.remove('hidden');
    els.discoverPagination.innerHTML = `
        <button id="${view}-prev" ${currentPage <= 1 ? 'disabled' : ''}>Prev</button>
        <span class="page-indicator">Page ${currentPage} / ${totalPages}</span>
        <button id="${view}-next" ${currentPage >= totalPages ? 'disabled' : ''}>Next</button>
        <span class="pagination-jump">
            <input type="number" min="1" max="${totalPages}" value="${currentPage}" id="${view}-jump-input" aria-label="Page number" />
            <button id="${view}-jump-btn">Go</button>
        </span>
    `;

    const prevBtn = document.getElementById(`${view}-prev`);
    const nextBtn = document.getElementById(`${view}-next`);
    const jumpBtn = document.getElementById(`${view}-jump-btn`);
    const jumpInput = document.getElementById(`${view}-jump-input`);
    prevBtn?.addEventListener('click', () => handlePageChange(view, currentPage - 1), { signal });
    nextBtn?.addEventListener('click', () => handlePageChange(view, currentPage + 1), { signal });
    jumpBtn?.addEventListener('click', () => {
        const value = parseInt(jumpInput?.value || '', 10);
        if (!Number.isNaN(value)) {
            handlePageChange(view, value);
        }
    }, { signal });
}

function renderGridSkeleton(gridEl, count = 12) {
    if (!gridEl) return;
    gridEl.classList.remove('hidden');
    const cards = Array.from({ length: count }).map(() => '<div class="skeleton-card"></div>').join('');
    gridEl.innerHTML = `<div class="grid-skeleton">${cards}</div>`;
}

function clearImageObserver() {
    if (state.imageObserver) {
        state.imageObserver.disconnect();
        state.imageObserver = null;
    }
}

function loadLazyImage(img) {
    if (!img || !img.dataset?.src) return;
    img.dataset.srcLoaded = '1';
    img.src = img.dataset.src;
    img.removeAttribute('data-src');
}

function setupLazyImages(container = document) {
    const images = Array.from(container.querySelectorAll('img[data-src]'));
    if (!images.length) return;

    if (!('IntersectionObserver' in window)) {
        images.forEach(loadLazyImage);
        return;
    }

    clearImageObserver();
    state.imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            loadLazyImage(entry.target);
            observer.unobserve(entry.target);
        });
    }, { rootMargin: '200px' });

    images.forEach(img => state.imageObserver.observe(img));
}

function renderErrorState(container, title, message, actions = []) {
    if (!container) return;
    const actionButtons = actions.map((action, index) => `
        <button class="control-btn" data-error-action="${index}">${escapeHtml(action.label)}</button>
    `).join('');
    container.innerHTML = `
        <div class="error-state">
            <div class="empty-icon-box" style="margin: 0 auto 16px;">
                <i data-lucide="alert-circle" width="32" height="32"></i>
            </div>
            <p class="empty-title">${escapeHtml(title)}</p>
            <p class="empty-text">${escapeHtml(message || 'Please try again')}</p>
            <div class="error-actions">${actionButtons}</div>
        </div>
    `;
    safeCreateIcons();
    container.querySelectorAll('[data-error-action]').forEach(btn => {
        const index = parseInt(btn.dataset.errorAction, 10);
        if (Number.isNaN(index) || !actions[index]) return;
        btn.addEventListener('click', actions[index].onClick);
    });
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

function handleInfiniteScroll() {
    if (state.filters.pagination !== 'infinite') return;
    if (state.activeView === 'details' || state.activeView === 'library') return;
    if (state.searchQuery && state.activeView === 'discover') return;
    if (state.isLoadingFeed) return;
    const threshold = 600;
    if (window.innerHeight + window.scrollY < document.body.offsetHeight - threshold) return;

    const maxPages = 20;
    switch (state.activeView) {
        case 'discover': {
            const nextPage = (state.viewPages.discover || 1) + 1;
            if (nextPage > maxPages) return;
            loadDiscover(nextPage, { append: true });
            break;
        }
        case 'popular': {
            const nextPage = (state.viewPages.popular || 1) + 1;
            if (nextPage > maxPages) return;
            loadPopular(nextPage, { append: true });
            break;
        }
        case 'trending': {
            const nextPage = (state.viewPages.trending || 1) + 1;
            if (nextPage > maxPages) return;
            loadTrendingView(nextPage, { append: true });
            break;
        }
        default:
            break;
    }
}

function reloadActiveView() {
    if (state.activeView === 'discover' && state.searchQuery) {
        performSearch();
        return;
    }

    switch (state.activeView) {
        case 'discover':
            loadDiscover(state.viewPages.discover || 1);
            break;
        case 'popular':
            loadPopular(state.viewPages.popular || 1);
            break;
        case 'trending':
            loadTrendingView(state.viewPages.trending || 1);
            break;
        case 'history':
            loadHistory(state.viewPages.history || 1);
            break;
        case 'library':
            renderLibraryFromState();
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
    renderGridSkeleton(els.discoverGrid, 10);
    els.discoverEmpty.classList.add('hidden');

    if (state.filters.source) {
        log(`🔍 Searching ${state.filters.source} for: ${query}`);
    } else {
        log(`🔍 Searching Jikan for: ${query}`);
    }

    try {
        saveSearchHistory(query);
        hideSearchSuggestions();
        clearLiveSuggestions();
        const results = await API.search(query, 20, state.filters);
        const filtered = applyFiltersToList(results);
        if (filtered.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
        } else {
            renderMangaGrid(filtered, els.discoverGrid, els.discoverEmpty);
        }
        log(`✅ Found ${results.length} results`);
    } catch (error) {
        log(`❌ Search error: ${error.message}`);
        renderErrorState(els.discoverGrid, 'Search failed', error.message, [
            { label: 'Retry', onClick: () => searchManga(query) },
            { label: 'Sources', onClick: showSourceStatus }
        ]);
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

function handleShareTarget() {
    const params = new URLSearchParams(window.location.search);
    const sharedUrl = params.get('url') || '';
    const sharedTitle = params.get('title') || params.get('text') || '';
    if (!sharedUrl && !sharedTitle) return;

    if (sharedUrl) {
        state.searchMode = 'url';
        els.searchModeIcon.setAttribute('data-lucide', 'link');
        els.searchInput.placeholder = 'Paste manga URL (18 sources supported)...';
        els.searchInput.value = sharedUrl;
        state.searchQuery = sharedUrl;
        detectUrl(sharedUrl);
    } else if (sharedTitle) {
        state.searchMode = 'title';
        els.searchModeIcon.setAttribute('data-lucide', 'search');
        els.searchInput.value = sharedTitle;
        state.searchQuery = sharedTitle;
        searchManga(sharedTitle);
    }
    safeCreateIcons();
    window.history.replaceState({}, document.title, window.location.pathname);
}

async function loadPopular(page = 1, { append = false } = {}) {
    if (!append) {
        renderGridSkeleton(els.discoverGrid, 12);
        els.discoverEmpty.classList.add('hidden');
    }
    updateDiscoverSubtitle(`// MOST POPULAR // PAGE ${page}`);

    log('Loading popular manga from Jikan (MyAnimeList)...');

    if (state.isLoadingFeed) return [];
    state.isLoadingFeed = true;

    try {
        if (!navigator.onLine && !append && (state.feedCache.popular || []).length) {
            const cached = applyFiltersToList(state.feedCache.popular);
            renderMangaGrid(cached, els.discoverGrid, els.discoverEmpty);
            renderDiscoverPagination('popular', page);
            showToast('Offline mode: showing cached popular');
            return cached;
        }
        state.viewPages.popular = page;
        const limit = state.filters.dataSaver ? 16 : 24;
        const results = await API.getPopular(page, limit);
        const combined = append ? [...(state.feedCache.popular || []), ...results] : results;
        state.feedCache.popular = combined;
        saveFeedCache();

        const filtered = applyFiltersToList(combined);
        if (!filtered || filtered.length === 0) {
            log('No results returned from API');
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return [];
        }

        log(`✅ Loaded ${results.length} popular manga (page ${page})`);
        renderMangaGrid(filtered, els.discoverGrid, els.discoverEmpty);
        prefetchCoverImages(filtered);
        renderRecommendations();
        renderDiscoverPagination('popular', page);
        return filtered;
    } catch (error) {
        log(`❌ ERROR loading popular: ${error.message}`);
        if (!append) {
            renderErrorState(els.discoverGrid, 'Popular feed unavailable', error.message, [
                { label: 'Retry', onClick: () => loadPopular(page) },
                { label: 'Sources', onClick: showSourceStatus }
            ]);
        }
    } finally {
        state.isLoadingFeed = false;
    }
    return [];
}

async function loadDiscover(page = 1, { append = false } = {}) {
    if (!append) {
        renderGridSkeleton(els.discoverGrid, 12);
        els.discoverEmpty.classList.add('hidden');
    }
    log('Loading discover feed (hidden gems - lesser-known quality manga)...');

    if (state.isLoadingFeed) return [];
    state.isLoadingFeed = true;

    try {
        if (!navigator.onLine && !append && (state.feedCache.discover || []).length) {
            const cached = applyFiltersToList(state.feedCache.discover);
            renderMangaGrid(cached, els.discoverGrid, els.discoverEmpty);
            renderDiscoverPagination('discover', page);
            showToast('Offline mode: showing cached discover');
            return cached;
        }
        // Rotate page every 10 minutes for variety, unless user paginates manually
        const timeBucket = Math.floor(Date.now() / (10 * 60 * 1000));
        const autoPage = (timeBucket % 5) + 1;
        const chosenPage = state.filters.pagination === 'infinite' || append ? page : (page || autoPage);
        state.viewPages.discover = chosenPage;
        updateDiscoverSubtitle(`// HIDDEN GEMS // PAGE ${chosenPage}`);

        const limit = state.filters.dataSaver ? 16 : 20;
        const results = await API.getDiscover(chosenPage, limit);
        const combined = append ? [...(state.feedCache.discover || []), ...results] : results;
        state.feedCache.discover = combined;
        saveFeedCache();

        const filtered = applyFiltersToList(combined);
        if (!filtered || filtered.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return [];
        }

        renderMangaGrid(filtered, els.discoverGrid, els.discoverEmpty);
        prefetchCoverImages(filtered);
        renderRecommendations();
        log(`✅ Loaded ${results.length} hidden gems`);
        renderDiscoverPagination('discover', chosenPage);
        return filtered;
    } catch (error) {
        log(`❌ ERROR loading discover: ${error.message}`);
        if (!append) {
            renderErrorState(els.discoverGrid, 'Discover feed unavailable', error.message, [
                { label: 'Retry', onClick: () => loadDiscover(page) },
                { label: 'Sources', onClick: showSourceStatus }
            ]);
        }
    } finally {
        state.isLoadingFeed = false;
    }
    return [];
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
        if (!navigator.onLine) {
            const cached = await loadCachedHistory();
            if (cached) {
                state.history = cached;
                renderHistorySummary(cached);
                renderHistoryTimeline(cached);
                showToast('Offline mode: showing cached history');
                return;
            }
        }
        const results = await API.getHistory(50);
        state.history = results;
        renderHistorySummary(results);
        saveAutoBackup();
        saveCachedHistory();
        if (!results || results.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            els.discoverEmpty.querySelector('.empty-title').textContent = 'No History Yet';
            els.discoverEmpty.querySelector('.empty-text').textContent = 'Start reading to see items here';
            return;
        }
        renderHistoryTimeline(results);
        log(`✅ Loaded ${results.length} history items`);
    } catch (error) {
        log(`❌ ERROR loading history: ${error.message}`);
        renderErrorState(els.discoverGrid, 'History unavailable', error.message, [
            { label: 'Retry', onClick: () => loadHistory() }
        ]);
    }
}

function renderHistoryTimeline(items) {
    els.discoverGrid.classList.remove('hidden');
    els.discoverGrid.innerHTML = '';
    const grouped = items.reduce((acc, item) => {
        const date = item.viewed_at ? new Date(item.viewed_at).toLocaleDateString() : 'Unknown';
        if (!acc[date]) acc[date] = [];
        acc[date].push(item);
        return acc;
    }, {});

    const sortedDates = Object.keys(grouped).sort((a, b) => new Date(b) - new Date(a));
    sortedDates.forEach(date => {
        const wrapper = document.createElement('div');
        wrapper.className = 'history-group';
        wrapper.innerHTML = `<div class="history-date">${escapeHtml(date)}</div><div class="manga-grid"></div>`;
        const grid = wrapper.querySelector('.manga-grid');
        const emptyStub = document.createElement('div');
        emptyStub.classList.add('hidden');
        renderMangaGrid(grouped[date], grid, emptyStub);
        els.discoverGrid.appendChild(wrapper);
    });
}

function renderHistorySummary(items) {
    if (els.historyTools) {
        els.historyTools.classList.remove('hidden');
    }
    if (els.historyCalendar) {
        els.historyCalendar.classList.remove('hidden');
    }
    renderHistoryOnThisDay(items);
    renderHistoryCalendar(items);
}

function renderHistoryOnThisDay(items) {
    if (!els.historyOnThisDay) return;
    const today = new Date();
    const month = today.getMonth();
    const date = today.getDate();
    const matches = (items || []).filter(entry => {
        const parsed = Date.parse(entry.viewed_at || entry.last_viewed_at || '');
        if (Number.isNaN(parsed)) return false;
        const d = new Date(parsed);
        return d.getMonth() === month && d.getDate() === date && d.getFullYear() !== today.getFullYear();
    }).slice(0, 3);
    if (!matches.length) {
        els.historyOnThisDay.textContent = 'On this day: No past reads yet.';
        return;
    }
    els.historyOnThisDay.innerHTML = `
        <div class="history-on-title">On this day</div>
        <div class="history-on-list">
            ${matches.map(entry => `<span>${escapeHtml(entry.title || 'Unknown')}</span>`).join('')}
        </div>
    `;
}

async function trackHistory(entry) {
    if (!entry) return;
    if (!navigator.onLine) {
        state.history = [entry, ...(state.history || []).filter(item => item.key !== entry.key)];
        saveCachedHistory();
        queueOfflineAction({ type: 'history', payload: entry });
        return;
    }
    await API.addHistory(entry);
}

function renderHistoryCalendar(items) {
    if (!els.historyCalendar) return;
    const days = [];
    const today = new Date();
    for (let i = 29; i >= 0; i -= 1) {
        const date = new Date(today);
        date.setDate(today.getDate() - i);
        days.push(date);
    }
    const historyDates = new Set((items || []).map(entry => {
        const parsed = Date.parse(entry.viewed_at || entry.last_viewed_at || entry.last_read_at || '');
        return Number.isNaN(parsed) ? null : new Date(parsed).toDateString();
    }).filter(Boolean));

    els.historyCalendar.innerHTML = `
        <div class="calendar-header">Reading Activity</div>
        <div class="calendar-grid">
            ${days.map(date => {
                const key = date.toDateString();
                return `<div class="calendar-day ${historyDates.has(key) ? 'active' : ''}" title="${escapeHtml(key)}"></div>`;
            }).join('')}
        </div>
    `;
}

function exportHistoryCsv() {
    const rows = [['title', 'source', 'viewed_at']];
    (state.history || []).forEach(entry => {
        rows.push([
            entry.title || '',
            entry.source || '',
            entry.viewed_at || entry.last_viewed_at || ''
        ]);
    });
    const csv = rows.map(row => row.map(cell => `"${String(cell).replace(/\"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `manganegus-history-${Date.now()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast('History exported');
}

async function loadTrendingView(page = 1, { append = false } = {}) {
    if (!append) {
        renderGridSkeleton(els.discoverGrid, 12);
        els.discoverEmpty.classList.add('hidden');
    }
    updateDiscoverSubtitle(`// TRENDING // PAGE ${page}`);
    state.viewPages.trending = page;

    log(`Loading trending page ${page}...`);

    if (state.isLoadingFeed) return [];
    state.isLoadingFeed = true;

    try {
        if (!navigator.onLine && !append && (state.feedCache.trending || []).length) {
            const cached = applyFiltersToList(state.feedCache.trending);
            renderMangaGrid(cached, els.discoverGrid, els.discoverEmpty);
            renderDiscoverPagination('trending', page);
            showToast('Offline mode: showing cached trending');
            return cached;
        }
        const limit = state.filters.dataSaver ? 16 : 24;
        const results = await API.getTrending(page, limit);
        const combined = append ? [...(state.feedCache.trending || []), ...results] : results;
        state.feedCache.trending = combined;
        saveFeedCache();

        const filtered = applyFiltersToList(combined);
        if (!filtered || filtered.length === 0) {
            els.discoverGrid.classList.add('hidden');
            els.discoverEmpty.classList.remove('hidden');
            return [];
        }
        renderMangaGrid(filtered, els.discoverGrid, els.discoverEmpty);
        prefetchCoverImages(filtered);
        renderRecommendations();
        renderDiscoverPagination('trending', page);
        log(`✅ Loaded ${results.length} trending manga (page ${page})`);
        return filtered;
    } catch (error) {
        log(`❌ ERROR loading trending: ${error.message}`);
        if (!append) {
            renderErrorState(els.discoverGrid, 'Trending feed unavailable', error.message, [
                { label: 'Retry', onClick: () => loadTrendingView(page) },
                { label: 'Sources', onClick: showSourceStatus }
            ]);
        }
    } finally {
        state.isLoadingFeed = false;
    }
    return [];
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
        const key = mostRecent.key || (mostRecent.source && (mostRecent.manga_id || mostRecent.id)
            ? getLibraryKey(mostRecent.manga_id || mostRecent.id, mostRecent.source)
            : '');
        const pageTotal = getPageTotal(key);
        if (pageTotal) {
            progressBits.push(`Page ${mostRecent.last_page}/${pageTotal}`);
        } else {
            progressBits.push(`Page ${mostRecent.last_page}`);
        }
    }
    if (mostRecent.total_chapters) {
        progressBits.push(`${mostRecent.total_chapters} total`);
    }
    els.continueProgress.textContent = progressBits.join(' | ');
    els.continueReading.classList.remove('hidden');
}

function renderRecommendations() {
    if (!els.recommendationsSection || !els.recommendationsGrid) return;
    if (!state.library.length) {
        els.recommendationsSection.classList.add('hidden');
        els.recommendationsGrid.innerHTML = '';
        return;
    }

    const tagWeights = {};
    state.library.forEach(item => {
        const tags = item.genres || item.tags || [];
        if (!Array.isArray(tags)) return;
        tags.forEach(tag => {
            const key = String(tag).toLowerCase();
            tagWeights[key] = (tagWeights[key] || 0) + 1;
        });
    });
    const weightedTags = Object.entries(tagWeights)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([tag]) => tag);

    const pool = [
        ...(state.feedCache.discover || []),
        ...(state.feedCache.popular || []),
        ...(state.feedCache.trending || [])
    ];

    const libraryKeys = new Set(state.library.map(item => item.key));
    const scored = [];
    pool.forEach(item => {
        const mangaId = item.mal_id || item.id || item.manga_id;
        const sourceId = item.source || item.source_id || (item.mal_id ? 'jikan' : '');
        const key = mangaId && sourceId ? getLibraryKey(mangaId, sourceId) : '';
        if (!mangaId || !sourceId || libraryKeys.has(key) || isHiddenManga(mangaId, sourceId)) return;
        const tags = (item.genres || item.tags || []).map(tag => String(tag).toLowerCase());
        const score = weightedTags.reduce((sum, tag) => sum + (tags.includes(tag) ? 1 : 0), 0);
        if (score > 0) scored.push({ item, score });
    });
    scored.sort((a, b) => b.score - a.score);
    const results = scored.slice(0, 12).map(entry => entry.item);

    if (!results.length) {
        els.recommendationsSection.classList.add('hidden');
        els.recommendationsGrid.innerHTML = '';
        return;
    }

    const last = state.library.find(item => item.last_read_at) || state.library[0];
    if (els.recommendationsSubtitle) {
        els.recommendationsSubtitle.textContent = last?.title ? `Because you read ${last.title}` : 'Based on your library';
    }
    const emptyStub = document.createElement('div');
    emptyStub.classList.add('hidden');
    renderMangaGrid(results, els.recommendationsGrid, emptyStub);
    els.recommendationsSection.classList.remove('hidden');
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
    state.currentChapterId = entry.last_chapter_id || null;

    await ensureReaderChapters();

    const startPage = entry.last_page ? Math.max(0, Number(entry.last_page) - 1) : 0;
    const rawChapter = entry.last_chapter ? String(entry.last_chapter) : '';
    const chapterLabel = rawChapter
        ? (rawChapter.toLowerCase().includes('chapter') ? rawChapter : `Chapter ${rawChapter}`)
        : 'Chapter';
    await openReader(entry.last_chapter_id, chapterLabel, startPage, entry.last_chapter, entry.total_chapters);
}

function applyLibrarySmartFilter(items) {
    if (!state.smartFilter) return items;
    const now = Date.now();
    switch (state.smartFilter) {
        case 'unread_updates':
            return items.filter(item => {
                const total = parseFloat(item.total_chapters || 0);
                const last = parseFloat(item.last_chapter || 0);
                return !Number.isNaN(total) && !Number.isNaN(last) && total > last;
            });
        case 'completed_unfinished':
            return items.filter(item => {
                const total = parseFloat(item.total_chapters || 0);
                const last = parseFloat(item.last_chapter || 0);
                return item.status === 'completed' && !Number.isNaN(total) && !Number.isNaN(last) && total > last;
            });
        case 'abandoned':
            return items.filter(item => {
                if (item.status !== 'plan_to_read') return false;
                const addedAt = Date.parse(item.added_at || '');
                if (Number.isNaN(addedAt)) return false;
                return (now - addedAt) > 30 * 24 * 60 * 60 * 1000;
            });
        default:
            return items;
    }
}

function sortLibraryItems(items) {
    const sort = state.librarySort || 'recent';
    const sorted = [...items];
    sorted.sort((a, b) => {
        switch (sort) {
            case 'title_asc':
                return String(a.title || '').localeCompare(String(b.title || ''));
            case 'title_desc':
                return String(b.title || '').localeCompare(String(a.title || ''));
            case 'last_read': {
                const aTime = Date.parse(a.last_read_at || '') || 0;
                const bTime = Date.parse(b.last_read_at || '') || 0;
                return bTime - aTime;
            }
            case 'rating_desc': {
                const aRating = a.rating?.average || a.score || 0;
                const bRating = b.rating?.average || b.score || 0;
                return bRating - aRating;
            }
            case 'rating_asc': {
                const aRating = a.rating?.average || a.score || 0;
                const bRating = b.rating?.average || b.score || 0;
                return aRating - bRating;
            }
            case 'recent':
            default: {
                const aTime = Date.parse(a.added_at || '') || 0;
                const bTime = Date.parse(b.added_at || '') || 0;
                return bTime - aTime;
            }
        }
    });
    return sorted;
}

async function renderLibraryFromState() {
    // Show loading if library is large
    if (state.library.length > 500) {
        els.libraryGrid.innerHTML = `
            <div class="loading-state">
                <div class="spinner"></div>
                <span class="loading-text">Filtering library...</span>
            </div>
        `;
    }

    try {
        const filteredLibrary = await runFilterTask('filterLibrary', {
            library: state.library,
            filter: state.activeFilter,
            smartFilter: state.smartFilter,
            collectionFilter: state.collectionFilter,
            sort: state.librarySort || 'recent'
        });

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
            last_read_at: item.last_read_at,
            added_at: item.added_at
        }));

        els.libraryEmpty.classList.add('hidden');
        els.libraryGrid.classList.remove('hidden');
        renderMangaGrid(mangaItems, els.libraryGrid, els.libraryEmpty);
        
    } catch (error) {
        console.error('Library filtering failed:', error);
        els.libraryGrid.innerHTML = `<div class="error-message">Failed to load library: ${error.message}</div>`;
    }
}

function populateCollectionFilterOptions() {
    if (!els.libraryCollection) return;
    const collections = new Set();
    state.library.forEach(entry => {
        getCollectionsForEntry(entry).forEach(tag => {
            if (tag) collections.add(tag.toLowerCase());
        });
    });
    const options = Array.from(collections).sort();
    els.libraryCollection.innerHTML = `
        <option value="">All</option>
        ${options.map(tag => `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`).join('')}
    `;
    if (state.collectionFilter) {
        els.libraryCollection.value = state.collectionFilter;
    }
}

async function checkFavoritesForUpdates({ silent = false } = {}) {
    if (!state.autoDownloadFavorites || state.filters.dataSaver) return;
    const now = Date.now();
    if (now - state.lastAutoDownloadCheck < 30 * 60 * 1000) return;
    state.lastAutoDownloadCheck = now;

    const favorites = Array.from(state.favoriteManga);
    if (!favorites.length) return;

    const entries = favorites
        .map(key => state.library.find(item => item.key === key))
        .filter(Boolean)
        .slice(0, 5);

    if (!entries.length) return;

    let queuedCount = 0;
    for (const entry of entries) {
        try {
            const response = await API.getChapters(entry.manga_id, entry.source, 1, entry.title, entry.mal_id, { silent: true });
            const chapters = response?.chapters || [];
            const total = response?.total || chapters.length;
            const lastRead = parseFloat(entry.last_chapter || 0);
            const diff = Number.isNaN(lastRead) ? 0 : Math.max(0, total - lastRead);
            if (diff <= 0 || chapters.length === 0) continue;

            const toQueue = chapters.slice(0, Math.min(diff, 3)).map(ch => ({
                id: ch.id,
                chapter: ch.chapter || '0',
                title: ch.title
            }));

            if (!toQueue.length) continue;
            await API.downloadChapters(entry.manga_id, toQueue, entry.source, entry.title, false);
            queuedCount += toQueue.length;
            entry.total_chapters = total;
        } catch (error) {
            log(`Auto-download check failed for ${entry?.title}: ${error.message}`);
        }
    }

    if (queuedCount > 0 && !silent) {
        showToast(`Queued ${queuedCount} new chapters`);
        fetchDownloadQueue();
    }
}

function scheduleAutoDownloadChecks() {
    if (state.autoDownloadTimer) {
        clearInterval(state.autoDownloadTimer);
        state.autoDownloadTimer = null;
    }
    if (!state.autoDownloadFavorites || state.filters.dataSaver) return;
    state.autoDownloadTimer = setInterval(() => {
        void checkFavoritesForUpdates({ silent: true });
    }, 30 * 60 * 1000);
}

function calculateStats() {
    const libraryCount = state.library.length;
    const chaptersRead = state.library.reduce((sum, item) => {
        const val = parseFloat(item.last_chapter || 0);
        return sum + (Number.isNaN(val) ? 0 : val);
    }, 0);
    const pagesRead = state.library.reduce((sum, item) => {
        const val = parseFloat(item.last_page || 0);
        return sum + (Number.isNaN(val) ? 0 : val);
    }, 0);
    const lastReadTimes = state.library.map(item => Date.parse(item.last_read_at || '') || 0);
    const latestRead = Math.max(0, ...lastReadTimes);
    const lastReadLabel = latestRead ? new Date(latestRead).toLocaleDateString() : '-';
    const genreCounts = {};
    state.library.forEach(item => {
        const tags = item.genres || item.tags || [];
        if (!Array.isArray(tags)) return;
        tags.forEach(tag => {
            const key = String(tag);
            genreCounts[key] = (genreCounts[key] || 0) + 1;
        });
    });
    const topGenre = Object.entries(genreCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || '-';

    const historyDates = (state.history || [])
        .map(entry => entry.viewed_at || entry.last_viewed_at || entry.last_read_at || '')
        .map(dateStr => {
            const parsed = Date.parse(dateStr);
            return Number.isNaN(parsed) ? null : new Date(parsed).toDateString();
        })
        .filter(Boolean);
    const statDays = Object.keys(state.readingStats.daily || {});
    const uniqueDays = Array.from(new Set([...historyDates, ...statDays])).sort((a, b) => new Date(b) - new Date(a));
    let streak = 0;
    if (uniqueDays.length) {
        const today = new Date().toDateString();
        let cursor = new Date(today);
        while (uniqueDays.includes(cursor.toDateString())) {
            streak += 1;
            cursor.setDate(cursor.getDate() - 1);
        }
    }

    const timeMinutes = state.readingStats.totalMinutes || Math.round((pagesRead || 0) * 0.5);
    const timeLabel = timeMinutes ? `${timeMinutes} min` : '-';
    const avgPageMb = state.filters.dataSaver ? 0.35 : 0.6;
    const dataUsageMb = pagesRead ? (pagesRead * avgPageMb) : 0;
    const dataUsageLabel = dataUsageMb ? `${dataUsageMb.toFixed(1)} MB` : '-';
    return {
        libraryCount,
        chaptersRead: Math.round(chaptersRead),
        pagesRead: Math.round(pagesRead),
        lastReadLabel,
        streak,
        topGenre,
        timeLabel,
        dataUsageLabel,
        genreCounts
    };
}

function updateStatsUI() {
    if (!els.statsGrid) return;
    const stats = calculateStats();
    els.statsGrid.querySelector('[data-stat="library"]').textContent = stats.libraryCount;
    els.statsGrid.querySelector('[data-stat="chapters"]').textContent = stats.chaptersRead;
    els.statsGrid.querySelector('[data-stat="pages"]').textContent = stats.pagesRead;
    els.statsGrid.querySelector('[data-stat="last-read"]').textContent = stats.lastReadLabel;
    const streakEl = els.statsGrid.querySelector('[data-stat="streak"]');
    if (streakEl) streakEl.textContent = stats.streak;
    const topGenreEl = els.statsGrid.querySelector('[data-stat="top-genre"]');
    if (topGenreEl) topGenreEl.textContent = stats.topGenre;
    const timeEl = els.statsGrid.querySelector('[data-stat="time"]');
    if (timeEl) timeEl.textContent = stats.timeLabel;
    const storageEl = els.statsGrid.querySelector('[data-stat="storage"]');
    if (storageEl && navigator.storage?.estimate) {
        navigator.storage.estimate().then(({ usage, quota }) => {
            if (!usage || !quota) {
                storageEl.textContent = '-';
                return;
            }
            const usedMb = (usage / 1024 / 1024).toFixed(1);
            const quotaMb = (quota / 1024 / 1024).toFixed(0);
            storageEl.textContent = `${usedMb} / ${quotaMb} MB`;
        }).catch(() => {
            storageEl.textContent = '-';
        });
    }
    const dataUsageEl = els.statsGrid.querySelector('[data-stat="data-usage"]');
    if (dataUsageEl) dataUsageEl.textContent = stats.dataUsageLabel || '-';
    renderReadingCalendar();
    renderGenreBreakdown(stats.genreCounts || {});
}

function renderReadingCalendar() {
    if (!els.readingCalendar) return;
    const days = [];
    const today = new Date();
    for (let i = 27; i >= 0; i -= 1) {
        const date = new Date(today);
        date.setDate(today.getDate() - i);
        days.push(date);
    }
    const historyDates = new Set((state.history || []).map(entry => {
        const parsed = Date.parse(entry.viewed_at || entry.last_viewed_at || entry.last_read_at || '');
        return Number.isNaN(parsed) ? null : new Date(parsed).toDateString();
    }).filter(Boolean));
    const dailyStats = state.readingStats.daily || {};

    els.readingCalendar.innerHTML = `
        <div class="calendar-header">Reading Streak (last 28 days)</div>
        <div class="calendar-grid">
            ${days.map(date => {
                const key = date.toDateString();
                const hasRead = historyDates.has(key) || dailyStats[key];
                const minutes = dailyStats[key]?.minutes || 0;
                return `<div class="calendar-day ${hasRead ? 'active' : ''}" title="${escapeHtml(key)}${minutes ? ` · ${minutes} min` : ''}"></div>`;
            }).join('')}
        </div>
    `;
}

function renderGenreBreakdown(genreCounts) {
    if (!els.genreBreakdown) return;
    const entries = Object.entries(genreCounts || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);
    if (!entries.length) {
        els.genreBreakdown.innerHTML = '<p class="genre-empty">No genre data yet.</p>';
        return;
    }
    const max = entries[0][1] || 1;
    els.genreBreakdown.innerHTML = `
        <div class="genre-header">Favorite Genres</div>
        <div class="genre-list">
            ${entries.map(([genre, count]) => `
                <div class="genre-row">
                    <span>${escapeHtml(genre)}</span>
                    <span class="genre-bar"><span style="width: ${(count / max) * 100}%"></span></span>
                </div>
            `).join('')}
        </div>
    `;
}

async function handleExportLibrary() {
    try {
        const data = await API.exportLibrary();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `manganegus-library-${Date.now()}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        showToast('Library exported');
    } catch (error) {
        showToast('Export failed');
        log(`❌ Export failed: ${error.message}`);
    }
}

async function handleImportLibrary(file) {
    if (!file) return;
    try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        const entries = Array.isArray(parsed)
            ? parsed
            : (parsed.entries || parsed.manga || parsed.mangas || parsed.library || parsed.items || parsed);
        const normalized = normalizeImportEntries(entries);
        const resolved = await resolveImportEntries(normalized);
        if (!resolved.entries.length) {
            showToast('No valid entries found');
            return;
        }
        await API.importLibrary(resolved.entries);
        if (resolved.skipped > 0) {
            showToast(`Imported ${resolved.entries.length}, skipped ${resolved.skipped}`);
        } else {
            showToast('Library imported');
        }
        await loadLibrary();
    } catch (error) {
        log(`❌ Import failed: ${error.message}`);
        showToast('Import failed');
    }
}

const STATUS_IMPORT_MAP = {
    1: 'reading',
    2: 'completed',
    3: 'on_hold',
    4: 'dropped',
    5: 'plan_to_read'
};

function normalizeImportStatus(status) {
    if (typeof status === 'number') {
        return STATUS_IMPORT_MAP[status] || 'reading';
    }
    if (typeof status === 'string') {
        const value = status.trim().toLowerCase();
        if (!value) return 'reading';
        if (value.includes('plan')) return 'plan_to_read';
        if (value.includes('hold') || value.includes('pause')) return 'on_hold';
        if (value.includes('drop')) return 'dropped';
        if (value.includes('complete')) return 'completed';
        if (value.includes('read')) return 'reading';
    }
    return 'reading';
}

function normalizeImportEntries(entries) {
    if (!Array.isArray(entries)) return [];
    return entries.map(entry => {
        if (!entry || typeof entry !== 'object') return null;
        const raw = entry.manga || entry;
        let source = raw.source || raw.source_id || raw.provider || raw.site || '';
        let mangaId = raw.manga_id || raw.id || raw.mangaId || raw.series_id || '';
        const title = raw.title || raw.name || raw.manga_title || raw.series_title || '';
        const status = normalizeImportStatus(raw.status || raw.reading_status || raw.state || raw.readingStatus || raw.reading_state);
        const cover = raw.cover || raw.cover_url || raw.thumbnail || raw.coverUrl || '';
        const url = raw.url || raw.link || raw.manga_url || raw.mangaUrl || '';
        const malId = raw.mal_id || raw.malId || raw.mal || raw.malID || '';
        const lastChapter = raw.last_chapter || raw.last_read_chapter || raw.lastReadChapter || raw.chapter || raw.chapter_read || raw.chapters_read || null;
        const lastPage = raw.last_page || raw.lastReadPage || raw.page || raw.pages_read || null;
        const lastChapterId = raw.last_chapter_id || raw.lastChapterId || null;
        const totalChapters = raw.total_chapters || raw.chapter_count || raw.total || null;

        if (!source && malId) {
            source = 'jikan';
            mangaId = malId;
        }

        const hasLookup = Boolean((source && mangaId && title) || malId || url);
        if (!hasLookup) return null;
        return {
            source,
            manga_id: mangaId,
            title,
            status,
            cover,
            url,
            mal_id: malId,
            last_chapter: lastChapter,
            last_page: lastPage,
            last_chapter_id: lastChapterId,
            total_chapters: totalChapters
        };
    }).filter(Boolean);
}

async function resolveImportEntries(entries) {
    const resolved = [];
    let skipped = 0;
    let detected = 0;
    const detectLimit = 25;

    for (const entry of entries) {
        const source = entry.source;
        const mangaId = entry.manga_id || entry.id;
        const title = entry.title || '';
        if (source && mangaId && title) {
            resolved.push(entry);
            continue;
        }

        if (entry.mal_id) {
            resolved.push({
                source: 'jikan',
                manga_id: entry.mal_id,
                title: title || `MAL ${entry.mal_id}`,
                status: entry.status || 'reading',
                cover: entry.cover || ''
            });
            continue;
        }

        if (!entry.url || !navigator.onLine || detected >= detectLimit) {
            skipped += 1;
            continue;
        }

        try {
            detected += 1;
            const result = await API.detectUrl(entry.url);
            if (result?.source_id && result?.manga_id) {
                resolved.push({
                    source: result.source_id,
                    manga_id: result.manga_id,
                    title: result.title || title || 'Imported Manga',
                    status: entry.status || 'reading',
                    cover: result.cover || entry.cover || ''
                });
            } else {
                skipped += 1;
            }
        } catch {
            skipped += 1;
        }
    }

    return { entries: resolved, skipped };
}

async function handleExportBackup() {
    try {
        const [libraryData, historyData] = await Promise.all([
            API.exportLibrary(),
            API.getHistory(200)
        ]);
        const backup = {
            version: 1,
            exported_at: new Date().toISOString(),
            library: libraryData,
            history: historyData,
            preferences: collectPreferences()
        };
        const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `manganegus-backup-${Date.now()}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        showToast('Backup exported');
    } catch (error) {
        log(`❌ Backup export failed: ${error.message}`);
        showToast('Backup export failed');
    }
}

async function handleImportBackup(file) {
    if (!file) return;
    try {
        const text = await file.text();
        const backup = JSON.parse(text);
        if (backup.preferences) {
            applyPreferences(backup.preferences);
        }
        if (backup.library) {
            const entries = Array.isArray(backup.library)
                ? backup.library
                : Object.entries(backup.library).map(([key, value]) => ({ key, ...value }));
            await API.importLibrary(entries);
        }
        if (Array.isArray(backup.history)) {
            await API.importHistory(backup.history);
        }
        showToast('Backup restored');
        await loadLibrary();
        await loadHistory();
    } catch (error) {
        log(`❌ Backup import failed: ${error.message}`);
        showToast('Backup import failed');
    }
}

function saveAutoBackup() {
    if (!state.autoBackupEnabled) return;
    try {
        const payload = {
            version: 1,
            saved_at: new Date().toISOString(),
            library: state.library,
            history: state.history,
            preferences: collectPreferences()
        };
        localStorage.setItem('manganegus.autoBackupPayload', JSON.stringify(payload));
    } catch {
        // Ignore storage errors
    }
}

function generateCloudSyncId() {
    if (crypto?.randomUUID) {
        return crypto.randomUUID();
    }
    return `sync_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function loadCloudSyncSettings() {
    const savedId = localStorage.getItem('manganegus.cloudSyncId');
    state.cloudSyncId = savedId || generateCloudSyncId();
    const enabled = localStorage.getItem('manganegus.cloudSyncEnabled');
    state.cloudSyncEnabled = enabled === 'on';
    const lastSync = parseInt(localStorage.getItem('manganegus.cloudSyncLastSync') || '0', 10);
    state.cloudSyncLastSync = Number.isNaN(lastSync) ? 0 : lastSync;
    if (!savedId) {
        localStorage.setItem('manganegus.cloudSyncId', state.cloudSyncId);
    }
    if (els.cloudSyncId) {
        els.cloudSyncId.value = state.cloudSyncId;
    }
    if (els.cloudSyncToggle) {
        els.cloudSyncToggle.value = state.cloudSyncEnabled ? 'on' : 'off';
    }
    scheduleCloudSync();
}

function scheduleCloudSync() {
    if (state.cloudSyncTimer) {
        clearInterval(state.cloudSyncTimer);
        state.cloudSyncTimer = null;
    }
    if (!state.cloudSyncEnabled) return;
    state.cloudSyncTimer = setInterval(() => {
        void cloudSyncNow({ silent: true });
    }, 15 * 60 * 1000);
}

function buildCloudPayload() {
    return {
        version: 1,
        saved_at: new Date().toISOString(),
        library: state.library,
        history: state.history,
        preferences: collectPreferences()
    };
}

async function cloudSyncPush({ silent = false } = {}) {
    if (!state.cloudSyncId) return;
    try {
        const payload = buildCloudPayload();
        await API.cloudPush(state.cloudSyncId, payload);
        state.cloudSyncLastSync = Date.now();
        localStorage.setItem('manganegus.cloudSyncLastSync', String(state.cloudSyncLastSync));
        if (!silent) showToast('Cloud sync pushed');
    } catch (error) {
        log(`Cloud push failed: ${error.message}`);
        if (!silent) showToast('Cloud push failed');
    }
}

async function cloudSyncPull({ silent = false } = {}) {
    if (!state.cloudSyncId) return;
    try {
        const response = await API.cloudPull(state.cloudSyncId);
        const payload = response?.payload || response;
        if (!payload) {
            if (!silent) showToast('No cloud data found');
            return;
        }
        if (payload.preferences) {
            applyPreferences(payload.preferences);
        }
        if (payload.library) {
            const entries = Array.isArray(payload.library)
                ? payload.library
                : Object.entries(payload.library).map(([key, value]) => ({ key, ...value }));
            await API.importLibrary(entries);
        }
        if (Array.isArray(payload.history)) {
            await API.importHistory(payload.history);
        }
        state.cloudSyncLastSync = Date.now();
        localStorage.setItem('manganegus.cloudSyncLastSync', String(state.cloudSyncLastSync));
        if (!silent) showToast('Cloud sync pulled');
        await loadLibrary();
        await loadHistory();
    } catch (error) {
        log(`Cloud pull failed: ${error.message}`);
        if (!silent) showToast('Cloud pull failed');
    }
}

async function cloudSyncNow({ silent = false } = {}) {
    if (!state.cloudSyncEnabled) {
        if (!silent) showToast('Cloud sync disabled');
        return;
    }
    await cloudSyncPull({ silent: true });
    await cloudSyncPush({ silent: true });
    if (!silent) showToast('Cloud sync complete');
}

function clearLocalCache() {
    memoryCache.clear();
    clearPersistentCache();
    state.pageTotals = {};
    savePageTotals();
    try {
        localStorage.removeItem(FEED_CACHE_KEY);
        localStorage.removeItem(LIBRARY_CACHE_KEY);
        localStorage.removeItem(HISTORY_CACHE_KEY);
        localStorage.removeItem(OFFLINE_QUEUE_KEY);
    } catch {
        // Ignore
    }
    state.offlineQueue = [];
    showToast('Cache cleared');
}

function collectLocalStoragePrefix(prefix) {
    const data = {};
    try {
        Object.keys(localStorage).forEach((key) => {
            if (key.startsWith(prefix)) {
                data[key] = localStorage.getItem(key);
            }
        });
    } catch {
        // Ignore
    }
    return data;
}

function collectPreferences() {
    return {
        filters: state.filters,
        theme: state.manualTheme || state.theme,
        themeSchedule: state.themeSchedule,
        accentColor: state.accentColor,
        readerMode: state.readerMode,
        readerFitMode: state.readerFitMode,
        readerDirection: state.readerDirection,
        readerBackground: state.readerBackground,
        readerSpread: state.readerSpread,
        readerEnhance: state.readerEnhance,
        prefetchDistance: state.prefetchDistance,
        mergeChapters: state.mergeChapters,
        autoDownloadFavorites: state.autoDownloadFavorites,
        autoBackupEnabled: state.autoBackupEnabled,
        cloudSyncEnabled: state.cloudSyncEnabled,
        favoriteSources: Array.from(state.favoriteSources),
        hiddenSources: Array.from(state.hiddenSources),
        favoriteManga: Array.from(state.favoriteManga),
        hiddenManga: Array.from(state.hiddenManga),
        pageTotals: state.pageTotals,
        readingStats: state.readingStats,
        localNotes: collectLocalStoragePrefix('manganegus.notes:'),
        localCollections: collectLocalStoragePrefix('manganegus.collections:'),
        readerPrefs: collectLocalStoragePrefix('manganegus.readerPrefs:'),
        searchHistory: state.searchHistory
    };
}

function applyPreferences(payload) {
    if (!payload || typeof payload !== 'object') return;
    if (payload.filters) {
        state.filters = { ...state.filters, ...payload.filters };
        saveFilters();
        applyGridDensity();
        updateFilterButtonState();
    }
    if (payload.theme) {
        state.theme = payload.theme;
        state.manualTheme = payload.theme;
        localStorage.setItem('manganegus.theme', payload.theme);
    }
    if (payload.themeSchedule) {
        setThemeSchedule(payload.themeSchedule);
    }
    if (payload.accentColor) {
        setAccentColor(payload.accentColor);
    }
    if (payload.readerMode) state.readerMode = payload.readerMode;
    if (payload.readerFitMode) state.readerFitMode = payload.readerFitMode;
    if (payload.readerDirection) state.readerDirection = payload.readerDirection;
    if (payload.readerBackground) state.readerBackground = payload.readerBackground;
    if (typeof payload.readerSpread === 'boolean') state.readerSpread = payload.readerSpread;
    if (payload.readerEnhance) state.readerEnhance = { ...state.readerEnhance, ...payload.readerEnhance };
    if (payload.prefetchDistance != null) state.prefetchDistance = payload.prefetchDistance;
    if (payload.mergeChapters != null) state.mergeChapters = Boolean(payload.mergeChapters);
    if (payload.autoDownloadFavorites != null) state.autoDownloadFavorites = Boolean(payload.autoDownloadFavorites);
    if (payload.autoBackupEnabled != null) state.autoBackupEnabled = Boolean(payload.autoBackupEnabled);
    if (payload.cloudSyncEnabled != null) {
        state.cloudSyncEnabled = Boolean(payload.cloudSyncEnabled);
        localStorage.setItem('manganegus.cloudSyncEnabled', state.cloudSyncEnabled ? 'on' : 'off');
    }
    if (Array.isArray(payload.favoriteSources)) state.favoriteSources = new Set(payload.favoriteSources);
    if (Array.isArray(payload.hiddenSources)) state.hiddenSources = new Set(payload.hiddenSources);
    if (Array.isArray(payload.favoriteManga)) state.favoriteManga = new Set(payload.favoriteManga);
    if (Array.isArray(payload.hiddenManga)) state.hiddenManga = new Set(payload.hiddenManga);
    if (payload.pageTotals && typeof payload.pageTotals === 'object') state.pageTotals = payload.pageTotals;
    if (payload.readingStats && typeof payload.readingStats === 'object') {
        state.readingStats = {
            totalMinutes: payload.readingStats.totalMinutes || 0,
            daily: payload.readingStats.daily || {}
        };
    }
    if (Array.isArray(payload.searchHistory)) state.searchHistory = payload.searchHistory;

    try {
        Object.entries(payload.localNotes || {}).forEach(([key, value]) => localStorage.setItem(key, value));
        Object.entries(payload.localCollections || {}).forEach(([key, value]) => localStorage.setItem(key, value));
        Object.entries(payload.readerPrefs || {}).forEach(([key, value]) => localStorage.setItem(key, value));
    } catch {
        // Ignore
    }

    if (els.autoBackupToggle) {
        els.autoBackupToggle.value = state.autoBackupEnabled ? 'on' : 'off';
    }
    if (els.cloudSyncToggle) {
        els.cloudSyncToggle.value = state.cloudSyncEnabled ? 'on' : 'off';
    }
    applyThemeSchedule();
    applyReaderMode();
    applyReaderFitMode();
    applyReaderDirection();
    applyReaderBackground();
    applyReaderSpread();
    applyReaderEnhancements();
    applyDataSaverMode();
    scheduleCloudSync();
    renderSources();
    renderLibraryFromState();
    saveHiddenManga();
    savePageTotals();
    saveReadingStats();
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
    if (DEBUG_MODE) {
        console.log('[DEBUG] loadLibrary called');
    }

    hidePagination();
    renderGridSkeleton(els.libraryGrid, 10);
    els.libraryEmpty.classList.add('hidden');

    log('📚 Loading library...');

    try {
        if (!navigator.onLine) {
            const cached = await loadCachedLibrary();
            if (cached) {
                state.library = cached;
                renderLibraryFromState();
                populateCollectionFilterOptions();
                renderContinueReading();
                renderRecommendations();
                renderNav();
                showToast('Offline mode: showing cached library');
                return;
            }
        }
        const library = await API.getLibrary();
        state.library = library;
        state.library.forEach(entry => {
            if (entry.last_page_total) {
                setPageTotal(entry.key, entry.last_page_total);
            }
        });
        renderLibraryFromState();
        populateCollectionFilterOptions();
        renderContinueReading();
        renderRecommendations();
        saveAutoBackup();
        saveCachedLibrary();
        void checkFavoritesForUpdates({ silent: true });

        renderNav(); // Update library count in nav
        log(`✅ Loaded ${library.length} library items`);

        if (DEBUG_MODE) {
            console.log(`[DEBUG] loadLibrary complete. Loaded ${library.length} items`);
            console.log(`[DEBUG] First 3 items:`, library.slice(0, 3));
        }
    } catch (error) {
        log(`❌ Library loading error: ${error.message}`);
        if (DEBUG_MODE) {
            console.error('[DEBUG] loadLibrary error:', error);
        }
        renderErrorState(els.libraryGrid, 'Library unavailable', error.message, [
            { label: 'Retry', onClick: () => loadLibrary() }
        ]);
    }
}

async function showRandomManga() {
    const view = state.activeView;
    if (!['discover', 'popular', 'trending'].includes(view)) {
        showToast('Random works in Discover, Popular, or Trending');
        return;
    }

    let feed = state.feedCache[view] || [];
    if (!feed.length) {
        if (view === 'discover') {
            feed = await loadDiscover(state.viewPages.discover || 1);
        } else if (view === 'popular') {
            feed = await loadPopular(state.viewPages.popular || 1);
        } else {
            feed = await loadTrendingView(state.viewPages.trending || 1);
        }
    }

    const filtered = applyFiltersToList(feed);
    if (!filtered || filtered.length === 0) {
        showToast('No manga matches current filters');
        return;
    }

    if (!feed || feed.length === 0) {
        showToast('No manga available yet');
        return;
    }

    const pick = filtered[Math.floor(Math.random() * filtered.length)];
    const mangaId = pick.mal_id || pick.id || pick.manga_id;
    if (!mangaId) {
        showToast('Random pick missing ID');
        return;
    }
    const source = pick.mal_id ? 'jikan' : (pick.source || state.currentSource || 'jikan');
    const title = pick.title || pick.name || 'Random Pick';
    showToast(`Random pick: ${title}`);
    openMangaDetails(mangaId, source, title, pick);
}

function isInLibrary(mangaId, source) {
    const key = `${source}:${mangaId}`;
    return state.library.some(item => item.key === key);
}

function getLibraryKey(mangaId, source) {
    return `${source}:${mangaId}`;
}

function upsertLocalLibraryEntry({ mangaId, source, title, cover, status }) {
    if (!mangaId || !source) return null;
    const key = getLibraryKey(mangaId, source);
    const now = new Date().toISOString();
    const existing = state.library.find(item => item.key === key);
    const payload = {
        key,
        manga_id: mangaId,
        id: mangaId,
        source,
        title: title || existing?.title || 'Unknown',
        cover: cover || existing?.cover || '',
        status: status || existing?.status || 'reading',
        added_at: existing?.added_at || now,
        last_read_at: existing?.last_read_at || null
    };
    if (existing) {
        Object.assign(existing, payload);
    } else {
        state.library.unshift(payload);
    }
    saveCachedLibrary();
    return key;
}

function loadFavoriteManga() {
    try {
        const raw = localStorage.getItem('manganegus.favoriteManga');
        const list = raw ? JSON.parse(raw) : [];
        state.favoriteManga = new Set(Array.isArray(list) ? list : []);
    } catch {
        state.favoriteManga = new Set();
    }
}

function saveFavoriteManga() {
    try {
        localStorage.setItem('manganegus.favoriteManga', JSON.stringify(Array.from(state.favoriteManga)));
    } catch {
        // Ignore
    }
}

function isFavoriteManga(mangaId, source) {
    if (!mangaId || !source) return false;
    const key = getLibraryKey(mangaId, source);
    return state.favoriteManga.has(key);
}

function toggleFavoriteManga(mangaId, source) {
    if (!mangaId || !source) return false;
    const key = getLibraryKey(mangaId, source);
    if (state.favoriteManga.has(key)) {
        state.favoriteManga.delete(key);
    } else {
        state.favoriteManga.add(key);
    }
    saveFavoriteManga();
    return state.favoriteManga.has(key);
}

function loadHiddenManga() {
    try {
        const raw = localStorage.getItem('manganegus.hiddenManga');
        const list = raw ? JSON.parse(raw) : [];
        state.hiddenManga = new Set(Array.isArray(list) ? list : []);
    } catch {
        state.hiddenManga = new Set();
    }
}

function saveHiddenManga() {
    try {
        localStorage.setItem('manganegus.hiddenManga', JSON.stringify(Array.from(state.hiddenManga)));
    } catch {
        // Ignore
    }
}

function isHiddenManga(mangaId, source) {
    if (!mangaId || !source) return false;
    return state.hiddenManga.has(getLibraryKey(mangaId, source));
}

function hideManga(mangaId, source) {
    if (!mangaId || !source) return;
    state.hiddenManga.add(getLibraryKey(mangaId, source));
    saveHiddenManga();
}

function loadPageTotals() {
    try {
        const raw = localStorage.getItem('manganegus.pageTotals');
        state.pageTotals = raw ? JSON.parse(raw) : {};
    } catch {
        state.pageTotals = {};
    }
}

function savePageTotals() {
    try {
        localStorage.setItem('manganegus.pageTotals', JSON.stringify(state.pageTotals));
    } catch {
        // Ignore
    }
}

function setPageTotal(key, total) {
    if (!key || !total) return;
    state.pageTotals[key] = total;
    savePageTotals();
}

function getPageTotal(key) {
    if (!key) return null;
    return state.pageTotals[key] || null;
}

function loadReadingStats() {
    try {
        const raw = localStorage.getItem('manganegus.readingStats');
        if (raw) {
            const parsed = JSON.parse(raw);
            state.readingStats = {
                totalMinutes: parsed.totalMinutes || 0,
                daily: parsed.daily || {}
            };
        }
    } catch {
        state.readingStats = { totalMinutes: 0, daily: {} };
    }
}

function saveReadingStats() {
    try {
        localStorage.setItem('manganegus.readingStats', JSON.stringify(state.readingStats));
    } catch {
        // Ignore
    }
}

function recordReadingSession(minutes, pages = 0) {
    const mins = Math.max(0, Math.round(minutes || 0));
    if (!mins && !pages) return;
    state.readingStats.totalMinutes += mins;
    const dayKey = new Date().toDateString();
    if (!state.readingStats.daily[dayKey]) {
        state.readingStats.daily[dayKey] = { minutes: 0, pages: 0 };
    }
    state.readingStats.daily[dayKey].minutes += mins;
    state.readingStats.daily[dayKey].pages += pages;
    saveReadingStats();
}

async function addToLibrary(mangaId, source, title, cover, status) {
    try {
        if (!navigator.onLine) {
            const key = upsertLocalLibraryEntry({ mangaId, source, title, cover, status });
            queueOfflineAction({
                type: 'add_library',
                payload: { id: mangaId, source, title, cover, status }
            });
            showToast('Saved offline - will sync later');
            renderLibraryFromState();
            renderNav();
            if (state.currentManga && state.currentManga.id === mangaId && state.currentManga.source === source) {
                state.currentLibraryKey = key;
                els.addToLibraryBtn.innerHTML = '<i data-lucide="check" width="20"></i> In Library';
                els.addToLibraryBtn.classList.add('secondary');
                safeCreateIcons();
            }
            return;
        }
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

async function updateLibraryStatus(key, status) {
    if (!key) {
        showToast('Missing library key');
        return;
    }
    try {
        if (!navigator.onLine) {
            const entry = state.library.find(item => item.key === key);
            if (entry) {
                entry.status = status;
                saveCachedLibrary();
                renderLibraryFromState();
            }
            queueOfflineAction({ type: 'update_status', payload: { key, status } });
            showToast('Status saved offline');
            return;
        }
        await API.updateStatus(key, status);
        const entry = state.library.find(item => item.key === key);
        if (entry) {
            entry.status = status;
        }
        showToast('Status updated');
        log(`✅ Updated status: ${key} -> ${status}`);
        await loadLibrary();
        renderNav();
    } catch (error) {
        log(`❌ Failed to update status: ${error.message}`);
        showToast('Failed to update status');
    }
}

// ========================================
// Manga Grid Rendering
// ========================================
function getOptimizedCoverUrl(url) {
    if (!url || !state.filters.dataSaver) return url;
    try {
        const host = new URL(url, window.location.origin).hostname;
        if (!COVER_PROXY_HOSTS.has(host)) return url;
    } catch {
        return url;
    }
    return `/api/proxy/image?url=${encodeURIComponent(url)}&format=webp&quality=70&w=220&h=300`;
}

function getCoverProxyUrl(url, { quality = 80, width = 220, height = 300 } = {}) {
    if (!url) return '';
    try {
        const host = new URL(url, window.location.origin).hostname;
        if (!COVER_PROXY_HOSTS.has(host)) return '';
    } catch {
        return '';
    }
    const qualityParam = quality ? `&quality=${quality}` : '';
    const widthParam = width ? `&w=${width}` : '';
    const heightParam = height ? `&h=${height}` : '';
    return `/api/proxy/image?url=${encodeURIComponent(url)}&format=webp${qualityParam}${widthParam}${heightParam}`;
}

function getCoverUrlsForItem(item) {
    const coverCandidates = [
        item.cover_url_large,
        item.cover_url,
        item.cover_url_medium,
        item.cover_url_small,
        item.cover_image_large,
        item.cover_image_medium,
        item.cover_image,
        item.cover
    ].filter(Boolean);
    const rawCoverUrl = state.filters.dataSaver
        ? (coverCandidates[2] || coverCandidates[3] || coverCandidates[0] || PLACEHOLDER_COVER)
        : (coverCandidates[0] || coverCandidates[1] || coverCandidates[2] || PLACEHOLDER_COVER);
    const displayUrl = getOptimizedCoverUrl(rawCoverUrl) || rawCoverUrl;
    return { raw: rawCoverUrl, display: displayUrl };
}

function prefetchCoverImages(items, limit = 8) {
    if (!navigator.onLine || !Array.isArray(items) || items.length === 0) return;
    const max = state.filters.dataSaver ? Math.min(limit, 5) : limit;
    let count = 0;
    for (const item of items) {
        if (count >= max) break;
        const { raw } = getCoverUrlsForItem(item);
        const proxy = getCoverProxyUrl(raw, { quality: state.filters.dataSaver ? 65 : 80 });
        if (!proxy || state.prefetchedCovers.has(proxy)) continue;
        state.prefetchedCovers.add(proxy);
        fetch(proxy, { cache: 'force-cache' }).catch(() => {});
        count += 1;
    }
}

/**
 * Generate HTML for a single manga card.
 * Extracted to enable chunked rendering for large datasets.
 */
function generateCardHtml(item) {
    // For Jikan manga, use mal_id as the ID and 'jikan' as pseudo-source
    const mangaId = item.mal_id || item.id || item.manga_id || `item-${Math.random().toString(36).slice(2)}`;
    const source = item.mal_id ? 'jikan' : (item.source || 'unknown');
    const isLibraryView = state.activeView === 'library';
    const libraryKey = item.key || (source && mangaId ? `${source}:${mangaId}` : '');

    const inLibrary = isInLibrary(mangaId, source);
    const isFavorite = isFavoriteManga(mangaId, source);
    const coverUrl = getCoverUrlsForItem(item).display;
    const status = item.status || 'reading';
    const statusLabel = isLibraryView ? (STATUS_LABELS[status] || 'Reading') : '';
    const statusIconMap = {
        reading: 'eye',
        completed: 'check-circle',
        plan_to_read: 'bookmark',
        on_hold: 'pause-circle',
        dropped: 'x-circle'
    };
    const statusIcon = isLibraryView ? statusIconMap[status] : null;
    let collectionsHtml = '';
    if (isLibraryView) {
        try {
            const stored = localStorage.getItem(getCollectionsStorageKey(mangaId, source));
            const collections = stored ? JSON.parse(stored) : [];
            if (Array.isArray(collections) && collections.length) {
                collectionsHtml = `
                    <div class="collection-tags">
                        ${collections.slice(0, 3).map(tag => `<span class="collection-tag">${escapeHtml(tag)}</span>`).join('')}
                    </div>
                `;
            }
        } catch {
            // Ignore
        }
    }

    // Use actual data from API
    const scoreValue = item.rating?.average ?? item.score;
    const scoreNumber = Number(scoreValue);
    const scoreLabel = Number.isFinite(scoreNumber) ? scoreNumber.toFixed(1) : '-';
    const ratingCount = Number(item.rating?.count);
    const viewsLabel = Number.isFinite(ratingCount) && ratingCount > 0
        ? `${(ratingCount / 1000).toFixed(0)}k`
        : '-';
    const userRating = isLibraryView ? getLocalRating(mangaId, source) : null;
    const author = item.author || 'Unknown Author';
    const tags = item.tags || item.genres || ['Manga'];
    const tag = Array.isArray(tags) ? tags[0] : tags;
    const coverMarkup = coverUrl
        ? `<img src="${PLACEHOLDER_COVER}" data-src="${escapeHtml(coverUrl)}" alt="${escapeHtml(item.title)}" loading="lazy" decoding="async" width="220" height="300" class="card-image lazy-image" onload="if (this.dataset.srcLoaded === '1') { this.classList.add('loaded'); }" onerror="this.src='${PLACEHOLDER_COVER}'; this.onerror=null;" />`
        : '<i data-lucide="book-open" width="48" height="48"></i>';

    let progressHtml = '';
    let notificationHtml = '';
    if (isLibraryView) {
        const notifications = [];
        const addedAt = item.added_at || item.addedAt;
        if (addedAt) {
            const addedMs = Date.parse(addedAt);
            if (!Number.isNaN(addedMs) && (Date.now() - addedMs) < 7 * 24 * 60 * 60 * 1000) {
                notifications.push({ label: 'New', className: 'new' });
            }
        }

        const totalCh = parseFloat(item.total_chapters || item.chapters || 0);
        const lastCh = parseFloat(item.last_chapter || 0);
        if (!Number.isNaN(totalCh) && !Number.isNaN(lastCh) && totalCh > lastCh) {
            const diff = Math.max(0, Math.round(totalCh - lastCh));
            notifications.push({ label: diff > 0 ? `${diff} new` : 'Updated', className: 'updated' });
        }

        if (status === 'completed') {
            notifications.push({ label: 'Completed', className: 'completed' });
        }

        if (notifications.length) {
            notificationHtml = `
                <div class="card-notifications">
                    ${notifications.map(n => `<span class="notification-badge ${n.className}">${escapeHtml(n.label)}</span>`).join('')}
                </div>
            `;
        }
    }
    if (isLibraryView && item.total_chapters && item.last_chapter) {
        const total = parseFloat(item.total_chapters);
        const current = parseFloat(item.last_chapter);
        if (!Number.isNaN(total) && total > 0 && !Number.isNaN(current)) {
            const percent = Math.min(100, Math.max(0, (current / total) * 100));
            const pageTotal = getPageTotal(libraryKey);
            const pageProgress = pageTotal && item.last_page
                ? ` · Page ${escapeHtml(String(item.last_page))}/${escapeHtml(String(pageTotal))}`
                : (item.last_page ? ` · Page ${escapeHtml(String(item.last_page))}` : '');
            progressHtml = `
                <div class="progress-wrap">
                    <div class="progress-bar" style="width: ${percent.toFixed(0)}%"></div>
                    <span class="progress-text">Ch ${escapeHtml(String(item.last_chapter))} / ${escapeHtml(String(item.total_chapters))} · ${percent.toFixed(0)}%${pageProgress}</span>
                </div>
            `;
        }
    }
    const statusHtml = isLibraryView && statusLabel
        ? `<div class="status-row">${statusIcon ? `<i data-lucide="${statusIcon}"></i>` : ''}<span class="status-pill status-${escapeHtml(status)}">${escapeHtml(statusLabel)}</span></div>`
        : '';

    return `
        <div class="card" data-manga-id="${escapeHtml(String(mangaId))}" data-source="${escapeHtml(source)}" data-library-key="${escapeHtml(libraryKey)}">
            ${state.selectionMode && isLibraryView ? `
                <div class="card-selection-overlay">
                    <input type="checkbox" class="card-checkbox" ${state.selectedCards.has(libraryKey) ? 'checked' : ''} />
                </div>
            ` : ''}
            <div class="card-cover">
                ${coverMarkup}
                <div class="card-overlay">
                    <button class="read-btn">Read</button>
                </div>
                <div class="card-badges">
                    <span class="badge-score"><i data-lucide="flame"></i> ${escapeHtml(String(scoreLabel))}</span>
                    ${userRating ? `<span class="badge-user-rating"><i data-lucide="star"></i> ${escapeHtml(String(userRating))}</span>` : ''}
                    ${isLibraryView ? `
                        <button class="favorite-btn ${isFavorite ? 'active' : ''}" data-action="favorite" aria-label="Toggle favorite">
                            <i data-lucide="star" width="16" height="16" ${isFavorite ? 'fill="currentColor"' : 'fill="none"'}></i>
                        </button>
                    ` : ''}
                    ${!isLibraryView ? `
                        <button class="bookmark-btn ${inLibrary ? 'active' : ''}" data-action="bookmark">
                            <i data-lucide="heart" width="16" height="16" fill="${inLibrary ? 'currentColor' : 'none'}"></i>
                        </button>
                    ` : ''}
                    <button class="card-menu-btn"
                            data-action="menu"
                            aria-label="Open menu"
                            aria-haspopup="true"
                            aria-expanded="false">
                        <i data-lucide="more-vertical" width="16" aria-hidden="true"></i>
                    </button>
                </div>
            </div>
            <div class="card-info">
                <div>
                    <h3 class="card-title">${escapeHtml(item.title)}</h3>
                    <p class="card-author">${escapeHtml(author)}</p>
                </div>
                ${statusHtml}
                ${notificationHtml}
                ${collectionsHtml}
                <div class="card-footer">
                    <span class="tag">${escapeHtml(tag)}</span>
                    <span class="views">${escapeHtml(String(viewsLabel))}</span>
                </div>
                ${progressHtml}
            </div>
        </div>
    `;
}

/**
 * Render manga grid - uses chunked rendering for large datasets to avoid blocking UI.
 */
async function renderMangaGrid(manga, gridEl, emptyEl) {
    if (manga.length === 0) {
        gridEl.classList.add('hidden');
        emptyEl.classList.remove('hidden');
        return;
    }

    emptyEl.classList.add('hidden');
    gridEl.classList.remove('hidden');

    // Store manga data for event delegation access
    gridEl._mangaData = manga;

    // Use chunked rendering for large datasets to avoid blocking UI
    if (manga.length >= CHUNKED_RENDER_THRESHOLD) {
        await renderChunked(manga, gridEl, generateCardHtml, {
            onComplete: () => {
                safeCreateIcons();
                setupLazyImages(gridEl);
            }
        });
    } else {
        // Small dataset - use synchronous rendering for immediate feedback
        gridEl.innerHTML = manga.map(item => generateCardHtml(item)).join('');
        safeCreateIcons();
        setupLazyImages(gridEl);
    }
}

function getNotesStorageKey(mangaId, source) {
    return `manganegus.notes:${source}:${mangaId}`;
}

function getCollectionsStorageKey(mangaId, source) {
    return `manganegus.collections:${source}:${mangaId}`;
}

function getLocalRating(mangaId, source) {
    if (!mangaId || !source) return null;
    try {
        const raw = localStorage.getItem(getNotesStorageKey(mangaId, source));
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        const rating = Number(parsed?.rating);
        return Number.isNaN(rating) ? null : rating;
    } catch {
        return null;
    }
}

function getCollectionsForEntry(entry) {
    if (!entry?.source || !(entry.manga_id || entry.id)) return [];
    const key = getCollectionsStorageKey(entry.manga_id || entry.id, entry.source);
    try {
        const raw = localStorage.getItem(key);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function loadNotesForCurrent() {
    if (!state.currentManga || !els.notesInput || !els.ratingInput || !els.ratingValue) return;
    const key = getNotesStorageKey(state.currentManga.id, state.currentManga.source);
    try {
        const raw = localStorage.getItem(key);
        const data = raw ? JSON.parse(raw) : {};
        els.notesInput.value = data.notes || '';
        els.ratingInput.value = data.rating || '';
        els.ratingValue.textContent = data.rating || '-';
        if (els.reviewInput) {
            els.reviewInput.value = data.review || '';
        }
    } catch {
        els.notesInput.value = '';
        els.ratingInput.value = '';
        els.ratingValue.textContent = '-';
        if (els.reviewInput) {
            els.reviewInput.value = '';
        }
    }
    if (els.collectionsInput) {
        const collectionsRaw = localStorage.getItem(getCollectionsStorageKey(state.currentManga.id, state.currentManga.source));
        els.collectionsInput.value = collectionsRaw ? JSON.parse(collectionsRaw).join(', ') : '';
    }
}

function scheduleNotesSave() {
    if (state.notesSaveTimer) {
        clearTimeout(state.notesSaveTimer);
        state.notesSaveTimer = null;
    }
    state.notesSaveTimer = setTimeout(() => {
        state.notesSaveTimer = null;
        saveNotesForCurrent();
    }, 500);
}

function saveNotesForCurrent() {
    if (!state.currentManga || !els.notesInput || !els.ratingInput) return;
    const key = getNotesStorageKey(state.currentManga.id, state.currentManga.source);
    const payload = {
        notes: els.notesInput.value.trim(),
        rating: els.ratingInput.value ? Number(els.ratingInput.value) : null,
        review: els.reviewInput ? els.reviewInput.value.trim() : ''
    };
    localStorage.setItem(key, JSON.stringify(payload));
    if (els.collectionsInput) {
        const collections = parseFilterList(els.collectionsInput.value);
        localStorage.setItem(
            getCollectionsStorageKey(state.currentManga.id, state.currentManga.source),
            JSON.stringify(collections)
        );
        populateCollectionFilterOptions();
    }
    if (state.currentLibraryKey) {
        const entry = state.library.find(item => item.key === state.currentLibraryKey);
        if (entry) {
            entry.user_rating = payload.rating;
        }
        renderLibraryFromState();
    }
    saveAutoBackup();
}

function getSimilarManga(mangaData) {
    const tags = (mangaData?.tags || mangaData?.genres || []).map(t => String(t).toLowerCase());
    if (tags.length === 0) return [];
    const tagSet = new Set(tags);
    const pool = [
        ...(state.feedCache.discover || []),
        ...(state.feedCache.popular || []),
        ...(state.feedCache.trending || [])
    ];
    const seen = new Set();
    const scored = [];
    pool.forEach(item => {
        const id = item.mal_id || item.id || item.manga_id;
        if (!id || id === mangaData?.mal_id || id === mangaData?.id) return;
        if (seen.has(id)) return;
        seen.add(id);
        const itemTags = (item.tags || item.genres || []).map(t => String(t).toLowerCase());
        const score = itemTags.reduce((acc, tag) => acc + (tagSet.has(tag) ? 1 : 0), 0);
        if (score > 0) {
            scored.push({ item, score });
        }
    });
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, 8).map(entry => entry.item);
}

async function renderSimilarManga(mangaData) {
    if (!els.similarGrid) return;
    const emptyStub = document.createElement('div');
    emptyStub.classList.add('hidden');

    // Show loading state
    els.similarGrid.innerHTML = '<p style="padding: 16px; color: var(--text-muted);">Finding similar titles...</p>';

    // First try to get recommendations from Jikan API (best quality)
    const malId = mangaData?.mal_id;
    if (malId) {
        try {
            const recommendations = await API.getRecommendations(malId, 8);
            if (recommendations.length) {
                renderMangaGrid(recommendations, els.similarGrid, emptyStub);
                return;
            }
        } catch (error) {
            log(`Recommendations API failed: ${error.message}`);
        }
    }

    // Fallback: Search by tags/genres
    try {
        const seedTags = (mangaData?.tags || mangaData?.genres || []).slice(0, 2).join(' ');
        const query = seedTags || mangaData?.title || '';
        if (!query) {
            els.similarGrid.innerHTML = '<p style="padding: 16px; color: var(--text-muted);">No similar titles available.</p>';
            return;
        }
        const results = await API.search(query, 12, null);
        const filtered = applyFiltersToList(results).filter(item => {
            const id = item.mal_id || item.id || item.manga_id;
            return id && id !== mangaData?.mal_id && id !== mangaData?.id;
        });
        if (filtered.length) {
            renderMangaGrid(filtered.slice(0, 8), els.similarGrid, emptyStub);
        } else {
            // Final fallback: Use tag matching from cached feeds
            const similar = getSimilarManga(mangaData);
            if (similar.length) {
                renderMangaGrid(similar, els.similarGrid, emptyStub);
            } else {
                els.similarGrid.innerHTML = '<p style="padding: 16px; color: var(--text-muted);">No similar titles found.</p>';
            }
        }
    } catch (error) {
        log(`Similar search failed: ${error.message}`);
        // Try tag matching as last resort
        const similar = getSimilarManga(mangaData);
        if (similar.length) {
            renderMangaGrid(similar, els.similarGrid, emptyStub);
        } else {
            els.similarGrid.innerHTML = '<p style="padding: 16px; color: var(--text-muted);">No similar titles found.</p>';
        }
    }
}

function renderAvailableSources() {
    if (!els.detailsSourcesList || !els.detailsSources) return;
    if (!state.currentMangaSources || state.currentMangaSources.length === 0) {
        els.detailsSources.classList.add('hidden');
        els.detailsSourcesList.innerHTML = '';
        return;
    }

    const currentSource = state.currentManga?.source || '';
    els.detailsSources.classList.remove('hidden');
    els.detailsSourcesList.innerHTML = state.currentMangaSources.map(source => {
        const sourceId = source.source_id || source.id || source.source;
        const mangaId = source.manga_id || source.mangaId || '';
        const isActive = sourceId === currentSource;
        return `
            <button class="source-chip ${isActive ? 'active' : ''}" data-source="${escapeHtml(sourceId)}" data-manga-id="${escapeHtml(mangaId)}" type="button">
                ${escapeHtml(source.source_name || source.name || sourceId)}
            </button>
        `;
    }).join('');
}

async function loadMangaSources() {
    if (!state.currentManga?.title) return;
    try {
        const results = await API.smartSearch(state.currentManga.title, 6);
        const match = Array.isArray(results) ? results[0] : null;
        const sources = match?.sources || [];
        state.currentMangaSources = sources.map(src => ({
            source_id: src.source_id || src.id || src.source,
            source_name: src.source_name || src.name || src.source_id || src.id,
            manga_id: src.manga_id || src.mangaId || src.id,
            chapters: src.chapters || 0
        }));
        renderAvailableSources();
    } catch (error) {
        log(`Source lookup failed: ${error.message}`);
        state.currentMangaSources = [];
        renderAvailableSources();
    }
}

function updateFavoriteButton() {
    if (!els.favoriteBtn || !state.currentManga) return;
    const isFav = isFavoriteManga(state.currentManga.id, state.currentManga.source);
    els.favoriteBtn.classList.toggle('active', isFav);
    els.favoriteBtn.innerHTML = `
        <i data-lucide="star" width="20" ${isFav ? 'fill="currentColor"' : 'fill="none"'}></i>
        ${isFav ? 'Favorited' : 'Favorite'}
    `;
    safeCreateIcons();
}

async function switchMangaSource(sourceId, mangaId) {
    if (!sourceId || !mangaId || !state.currentManga) return;
    state.currentManga.source = sourceId;
    state.currentManga.id = mangaId;
    state.currentChapters = [];
    state.currentChaptersOffset = 0;
    state.currentPage = 1;
    renderAvailableSources();
    await loadChapters(1);
}

// ========================================
// Manga Details
// ========================================
async function openMangaDetails(mangaId, source, title, mangaData = null) {
    if (DEBUG_MODE) {
        console.log(`[DEBUG] openMangaDetails called: ${title} (${source}:${mangaId})`);
    }

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
    state.chapterFilters = { language: '', group: '', translation: '' };
    state.currentPage = 1;
    state.totalChaptersCount = 0;
    state.currentChaptersOffset = 0;
    state.currentMangaSources = [];
    loadNotesForCurrent();
    loadReaderPreferencesForCurrent();

    // Track history (non-blocking)
    try {
        await trackHistory({
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
        els.detailsDescription.textContent = 'No description available.';
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

    // Set cover (avoid stale image when data is missing)
    const coverInfo = getCoverUrlsForItem(mangaData || {});
    els.detailsCoverImg.src = coverInfo.display || PLACEHOLDER_COVER;

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
    updateFavoriteButton();
    renderAvailableSources();
    void renderSimilarManga(mangaData || {});

    // Load chapters
    await loadChapters(1);
    void loadMangaSources();
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
    const cacheKey = `chapters:${payload.id}:${payload.source || payload.mal_id}:${payload.offset}`;
    const cached = getCacheValue(cacheKey);
    if (cached) {
        // CRITICAL: Update source from cached response to ensure reader uses correct source
        if (cached.source_id) {
            state.currentManga.source = cached.source_id;
        }
        if (cached.manga_id) {
            state.currentManga.id = cached.manga_id;
        }
        if (updateState && Array.isArray(cached?.chapters)) {
            state.currentChapters = cached.chapters;
            state.currentPage = page;
            state.currentChaptersOffset = (page - 1) * 100;
            renderChapters();
            renderPagination();
        }
        return cached;
    }
    const response = await API.request('/api/chapters', {
        method: 'POST',
        body: JSON.stringify(payload)
    });

    // CRITICAL: Update source from API response to ensure reader uses correct source
    if (response?.source_id) {
        state.currentManga.source = response.source_id;
    }
    if (response?.manga_id) {
        state.currentManga.id = response.manga_id;
    }

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

    if (response) {
        setCacheValue(cacheKey, response, 60 * 60 * 1000);
    }
    return response;
}

async function fetchReaderChaptersPage(page = 1) {
    const payload = buildChaptersPayload(page);
    if (!payload) return null;
    try {
        const response = await API.request('/api/chapters', {
            method: 'POST',
            body: JSON.stringify(payload),
            silent: true
        });

        if (response?.source_id) {
            state.currentManga.source = response.source_id;
        }
        if (response?.manga_id) {
            state.currentManga.id = response.manga_id;
        }

        if (Array.isArray(response?.chapters)) {
            state.currentChapters = response.chapters;
            state.currentPage = page;
            state.currentChaptersOffset = (page - 1) * 100;
            state.totalChaptersCount = response.total || response.chapters.length;
            state.totalPages = Math.ceil((response.total || 0) / 100) || 1;
        }

        return response;
    } catch (error) {
        log(`Reader chapters sync failed: ${error.message}`);
        return null;
    }
}

async function ensureReaderChapters() {
    if (!state.currentManga?.id) return false;

    if (state.currentChapters.length && state.currentChapterId) {
        const existingIndex = state.currentChapters.findIndex(chapter => chapter.id === state.currentChapterId);
        if (existingIndex >= 0) {
            state.currentChapterIndex = existingIndex;
            return true;
        }
    }

    const response = await fetchReaderChaptersPage(1);
    if (response?.chapters && state.currentChapterId) {
        const pageIndex = response.chapters.findIndex(chapter => chapter.id === state.currentChapterId);
        if (pageIndex >= 0) {
            state.currentChapterIndex = pageIndex;
            return true;
        }
    }

    if (!state.currentManga?.source) return false;

    try {
        const allResponse = await API.getAllChapters(state.currentManga.id, state.currentManga.source, { silent: true });
        const chapters = allResponse?.chapters || [];
        if (!chapters.length) return false;

        state.currentChapters = chapters;
        state.currentChaptersOffset = 0;
        state.currentPage = 1;
        state.totalChaptersCount = allResponse.total || chapters.length;
        state.totalPages = 1;

        const index = state.currentChapterId
            ? chapters.findIndex(chapter => chapter.id === state.currentChapterId)
            : -1;
        if (index >= 0) {
            state.currentChapterIndex = index;
            return true;
        }
    } catch (error) {
        log(`Reader chapters fallback failed: ${error.message}`);
    }

    return false;
}

function normalizeChapterKey(chapter) {
    if (!chapter) return '';
    if (chapter.chapter) return `ch:${String(chapter.chapter).trim()}`;
    if (chapter.title) return `title:${String(chapter.title).trim().toLowerCase()}`;
    return `id:${chapter.id || ''}`;
}

function mergeChapterLists(sourceLists, primarySource) {
    const mergedMap = new Map();
    sourceLists.forEach(({ sourceId, chapters }) => {
        (chapters || []).forEach(chapter => {
            const key = normalizeChapterKey(chapter);
            if (!key) return;
            if (!mergedMap.has(key)) {
                mergedMap.set(key, {
                    ...chapter,
                    source: sourceId,
                    sources: [sourceId]
                });
                return;
            }
            const existing = mergedMap.get(key);
            if (!existing.sources.includes(sourceId)) {
                existing.sources.push(sourceId);
            }
            if (sourceId === primarySource) {
                existing.id = chapter.id;
                existing.chapter = chapter.chapter;
                existing.title = chapter.title || existing.title;
                existing.source = sourceId;
            }
        });
    });
    return Array.from(mergedMap.values());
}

async function loadChaptersMerged(page = 1) {
    if (!state.currentManga?.source || !state.currentManga?.id) return;
    const baseSource = state.currentManga.source;
    const sources = [
        { source_id: baseSource, manga_id: state.currentManga.id },
        ...state.currentMangaSources
    ].filter(src => src.source_id && src.manga_id);

    const uniqueSources = [];
    const seen = new Set();
    sources.forEach(src => {
        if (!seen.has(src.source_id)) {
            seen.add(src.source_id);
            uniqueSources.push(src);
        }
    });

    const limitedSources = uniqueSources.slice(0, 3);
    const lists = [];

    for (const src of limitedSources) {
        try {
            let chaptersData = null;
            try {
                chaptersData = await API.getAllChapters(src.manga_id, src.source_id, { silent: true });
            } catch (error) {
                chaptersData = await API.getChapters(src.manga_id, src.source_id, 1, state.currentManga.title, null, { silent: true });
            }
            const chapters = chaptersData?.chapters || [];
            lists.push({ sourceId: src.source_id, chapters });
        } catch (error) {
            log(`Merge chapters failed for ${src.source_id}: ${error.message}`);
        }
    }

    if (!lists.length) {
        await loadChapters(page);
        return;
    }

    const merged = mergeChapterLists(lists, baseSource);
    const order = inferChapterOrder(lists[0]?.chapters || merged);
    const sorted = merged.sort((a, b) => {
        const aNum = parseFloat(a.chapter || 0);
        const bNum = parseFloat(b.chapter || 0);
        if (!Number.isNaN(aNum) && !Number.isNaN(bNum)) {
            return order === 'desc' ? bNum - aNum : aNum - bNum;
        }
        return String(a.chapter || '').localeCompare(String(b.chapter || '')) * (order === 'desc' ? -1 : 1);
    });

    state.totalChaptersCount = sorted.length;
    state.totalPages = Math.ceil(sorted.length / 100) || 1;
    state.currentPage = page;
    state.currentChaptersOffset = (page - 1) * 100;
    state.currentChapters = sorted.slice(state.currentChaptersOffset, state.currentChaptersOffset + 100);

    populateChapterFilters();
    renderChapters();
    renderPagination();
}

async function loadChapters(page = 1) {
    if (state.mergeChapters) {
        if (!state.currentMangaSources?.length) {
            await loadMangaSources();
        }
        if (state.currentMangaSources?.length) {
            await loadChaptersMerged(page);
            return;
        }
    }
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

        const cacheKey = `chapters:${payload.id}:${payload.source || payload.mal_id}:${payload.offset}`;
        const cached = getCacheValue(cacheKey);
        if (cached?.chapters) {
            // CRITICAL: Update source from cached response to ensure reader uses correct source
            if (cached.source_id) {
                state.currentManga.source = cached.source_id;
                log(`Using cached source: ${cached.source_id}`);
            }
            if (cached.manga_id) {
                state.currentManga.id = cached.manga_id;
            }
            state.currentChapters = cached.chapters || [];
            state.totalChaptersCount = cached.total || state.currentChapters.length;
            state.currentChaptersOffset = (page - 1) * 100;
            state.totalPages = Math.ceil((state.totalChaptersCount || 0) / 100) || 1;
            populateChapterFilters();
            renderChapters();
            renderPagination();
            return;
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

        const entry = state.currentLibraryKey
            ? state.library.find(item => item.key === state.currentLibraryKey)
            : null;
        const ttl = entry?.status === 'completed'
            ? 24 * 60 * 60 * 1000
            : 60 * 60 * 1000;
        setCacheValue(cacheKey, response, ttl);

        populateChapterFilters();
        renderChapters();
        renderPagination();

        log(`✅ Loaded ${state.currentChapters.length} chapters`);
    } catch (error) {
        // Silently ignore aborted requests
        if (error.name === 'AbortError') {
            return;
        }
        log(`❌ Chapters loading error: ${error.message}`);
        els.chaptersList.innerHTML = `
            <div style="padding: 24px; text-align: center;">
                <p style="color: var(--text-muted); margin-bottom: 16px;">Failed to load chapters.</p>
                <button class="control-btn" id="chapters-source-btn">Try another source</button>
            </div>
        `;
        document.getElementById('chapters-source-btn')?.addEventListener('click', showSourceStatus);
    }
}

function renderChapters() {
    const chapters = getFilteredChapters();
    if (chapters.length === 0) {
        const message = state.currentChapters.length ? 'No chapters match filters' : 'No chapters available';
        els.chaptersList.innerHTML = `<p style="padding: 24px; text-align: center; color: var(--text-muted);">${message}</p>`;
        return;
    }

    const currentKey = resolveCurrentLibraryKey();
    const libraryEntry = currentKey
        ? state.library.find(item => item.key === currentKey)
        : null;
    const lastReadId = libraryEntry?.last_chapter_id || null;
    const lastReadNumber = parseFloat(libraryEntry?.last_chapter ?? '');
    const hasReadNumber = Number.isFinite(lastReadNumber);

    els.chaptersList.innerHTML = chapters.map(chapter => {
        const isSelected = state.selectedChapters.has(chapter.id);
        const chapterNum = chapter.chapter || '0';
        const chapterValue = parseFloat(chapterNum);
        const readByNumber = hasReadNumber && Number.isFinite(chapterValue) && chapterValue <= lastReadNumber;
        const isRead = readByNumber || (lastReadId && chapter.id === lastReadId);
        const isCurrent = state.currentChapterId && chapter.id === state.currentChapterId;
        const sources = Array.isArray(chapter.sources) ? chapter.sources : [];
        const sourceLabel = sources.length > 1
            ? `Also on ${sources.map(getSourceDisplayName).join(', ')}`
            : '';
        const official = isOfficialChapter(chapter);
        const tagLabel = official ? 'Official' : 'Fan';
        const readBadge = isRead ? '<span class="chapter-read">Read</span>' : '';
        return `
            <div class="chapter-item ${isSelected ? 'selected' : ''} ${isRead ? 'read' : ''} ${isCurrent ? 'current' : ''}" data-chapter-id="${escapeHtml(chapter.id)}" data-chapter-title="${escapeHtml(chapter.title)}" data-chapter-number="${escapeHtml(String(chapterNum))}">
                <div class="chapter-info">
                    <div class="chapter-checkbox"></div>
                    <div>
                        <span class="chapter-name">${escapeHtml(chapter.title)}</span>
                        ${readBadge}
                        <span class="chapter-tag ${official ? 'official' : ''}">${escapeHtml(tagLabel)}</span>
                        ${sourceLabel ? `<span class="chapter-source-hint">${escapeHtml(sourceLabel)}</span>` : ''}
                    </div>
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

    const limit = getDataSaverDownloadLimit();
    const finalBatch = chaptersToDownload.slice(0, limit);
    if (finalBatch.length > 0) {
        try {
            await API.downloadChapters(
                state.currentManga.id,
                finalBatch,
                state.currentManga.source,
                state.currentManga.title
            );
            const label = finalBatch.length !== chaptersToDownload.length
                ? `Queued ${finalBatch.length} (data saver limit)`
                : `Added ${finalBatch.length} chapter(s) to queue`;
            showToast(label);
            fetchDownloadQueue();
        } catch (error) {
            showToast(`Download failed: ${error.message}`);
        }
    }
}

async function downloadNextChapters(count = 5) {
    if (!state.currentChapters.length) {
        showToast('No chapters available');
        return;
    }

    const maxCount = state.filters.dataSaver ? Math.min(count, 2) : count;
    const order = inferChapterOrder();
    let startIndex = state.currentChapterIndex;
    if (startIndex < 0) {
        startIndex = order === 'desc' ? -1 : 0;
    }

    const chaptersToDownload = [];
    let idx = startIndex + (order === 'desc' ? -1 : 1);
    while (idx >= 0 && idx < state.currentChapters.length && chaptersToDownload.length < maxCount) {
        const chapter = state.currentChapters[idx];
        chaptersToDownload.push({
            id: chapter.id,
            chapter: chapter.chapter || '0',
            title: chapter.title
        });
        idx += order === 'desc' ? -1 : 1;
    }

    if (!chaptersToDownload.length) {
        showToast('No next chapters found');
        return;
    }

    try {
        await API.downloadChapters(
            state.currentManga.id,
            chaptersToDownload,
            state.currentManga.source,
            state.currentManga.title,
            !state.filters.dataSaver
        );
        showToast(`Queued next ${chaptersToDownload.length} chapters`);
        fetchDownloadQueue();
    } catch (error) {
        showToast(`Download failed: ${error.message}`);
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
            chapterNumber,
            !state.filters.dataSaver
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

async function downloadLatestChapter(mangaId, source, title) {
    if (!mangaId || !source) {
        showToast('Missing manga source');
        return;
    }
    try {
        const response = await API.getChapters(mangaId, source, 1, title, null, { silent: true });
        const chapter = response?.chapters?.[0];
        if (!chapter) {
            showToast('No chapters found');
            return;
        }
        await API.downloadChapter(
            mangaId,
            chapter.id,
            source,
            title,
            chapter.title || 'Latest',
            chapter.chapter || '0',
            !state.filters.dataSaver
        );
        showToast('Queued latest chapter');
        fetchDownloadQueue();
    } catch (error) {
        showToast(`Download failed: ${error.message}`);
    }
}

function renderPagination() {
    if (state.totalPages <= 1) {
        els.chaptersPagination.classList.add('hidden');
        return;
    }

    // Cleanup previous event listeners to prevent memory leak
    if (state.paginationController) {
        state.paginationController.abort();
    }
    state.paginationController = new AbortController();
    const { signal } = state.paginationController;

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
    }, { signal });

    document.getElementById('next-chapters-page')?.addEventListener('click', () => {
        if (state.currentPage < state.totalPages) loadChapters(state.currentPage + 1);
    }, { signal });
}

function populateChapterFilters() {
    if (!els.chapterLanguage || !els.chapterGroup) return;
    const languages = new Set();
    const groups = new Set();
    let hasOfficial = false;
    let hasFan = false;

    state.currentChapters.forEach(ch => {
        if (ch.language) {
            languages.add(String(ch.language).toLowerCase());
        }
        if (ch.scanlator) {
            groups.add(String(ch.scanlator));
        }
        if (isOfficialChapter(ch)) {
            hasOfficial = true;
        } else {
            hasFan = true;
        }
    });

    const currentLang = state.chapterFilters.language;
    const currentGroup = state.chapterFilters.group;
    const currentTranslation = state.chapterFilters.translation;

    const sortedLangs = Array.from(languages).sort();
    const sortedGroups = Array.from(groups).sort();

    els.chapterLanguage.innerHTML = `<option value="">All</option>` +
        sortedLangs.map(lang => `<option value="${escapeHtml(lang)}">${escapeHtml(lang.toUpperCase())}</option>`).join('');
    els.chapterGroup.innerHTML = `<option value="">All</option>` +
        sortedGroups.map(group => `<option value="${escapeHtml(group)}">${escapeHtml(group)}</option>`).join('');
    if (els.chapterTranslation) {
        const options = ['<option value="">All</option>'];
        if (hasOfficial) options.push('<option value="official">Official</option>');
        if (hasFan) options.push('<option value="fan">Fan</option>');
        els.chapterTranslation.innerHTML = options.join('');
        if (currentTranslation) els.chapterTranslation.value = currentTranslation;
    }

    if (currentLang) els.chapterLanguage.value = currentLang;
    if (currentGroup) els.chapterGroup.value = currentGroup;
}

function getFilteredChapters() {
    let chapters = [...state.currentChapters];
    const lang = state.chapterFilters.language;
    const group = state.chapterFilters.group;
    const translation = state.chapterFilters.translation;

    if (lang) {
        chapters = chapters.filter(ch => String(ch.language || '').toLowerCase() === lang);
    }
    if (group) {
        chapters = chapters.filter(ch => String(ch.scanlator || '') === group);
    }
    if (translation === 'official') {
        chapters = chapters.filter(ch => isOfficialChapter(ch));
    } else if (translation === 'fan') {
        chapters = chapters.filter(ch => !isOfficialChapter(ch));
    }

    return chapters;
}

function isOfficialChapter(chapter) {
    if (!chapter) return false;
    if (typeof chapter.is_official === 'boolean') return chapter.is_official;
    if (typeof chapter.official === 'boolean') return chapter.official;
    const scanlator = String(chapter.scanlator || chapter.group || '').toLowerCase();
    return scanlator.includes('official') || scanlator.includes('viz') || scanlator.includes('kodansha');
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
    if (!entry) return false;
    Object.assign(entry, data);
    entry.last_read_at = new Date().toISOString();
    state.currentLibraryKey = key;
    renderContinueReading();

    if (state.activeView === 'library') {
        renderLibraryFromState();
    }
    return true;
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
    const pageTotal = state.readerPages.length || null;
    const totalChapters = state.totalChaptersCount || state.currentChapters.length || null;
    const lastReadEntry = {
        id: state.currentManga.id,
        manga_id: state.currentManga.id,
        source: state.currentManga.source,
        title: state.currentManga.title,
        cover: state.currentManga.cover || state.currentManga.data?.cover_url || state.currentManga.data?.cover || PLACEHOLDER_COVER,
        last_chapter: String(chapterValue),
        last_chapter_id: state.currentChapterId,
        last_page: pageValue,
        last_page_total: pageTotal,
        total_chapters: totalChapters,
        last_read_at: new Date().toISOString()
    };

    const key = resolveCurrentLibraryKey();
    if (key && pageTotal) {
        setPageTotal(key, pageTotal);
    }
    if (!key) {
        saveLastRead(lastReadEntry);
        renderContinueReading();
        return;
    }

    try {
        if (!navigator.onLine) {
            const updateData = {
                last_chapter: String(chapterValue),
                last_page: pageValue,
                last_chapter_id: state.currentChapterId,
                total_chapters: totalChapters !== null ? totalChapters : undefined,
                last_page_total: pageTotal || undefined
            };
            updateLocalLibraryProgress(key, updateData);
            queueOfflineAction({
                type: 'update_progress',
                payload: {
                    key,
                    chapter: String(chapterValue),
                    page: pageValue,
                    chapter_id: state.currentChapterId,
                    total_chapters: totalChapters,
                    page_total: pageTotal
                }
            });
            saveAutoBackup();
            showToast('Progress saved offline');
            return;
        }
        await API.updateProgress(
            key,
            String(chapterValue),
            pageValue,
            state.currentChapterId,
            totalChapters,
            pageTotal
        );
        const updateData = {
            last_chapter: String(chapterValue),
            last_page: pageValue,
            last_chapter_id: state.currentChapterId
        };
        if (pageTotal) {
            updateData.last_page_total = pageTotal;
        }
        if (totalChapters !== null) {
            updateData.total_chapters = totalChapters;
        }
        const updated = updateLocalLibraryProgress(key, updateData);
        if (!updated) {
            saveLastRead(lastReadEntry);
            renderContinueReading();
        }
        saveAutoBackup();
    } catch (error) {
        log(`Progress save failed: ${error.message}`);
        saveLastRead(lastReadEntry);
        renderContinueReading();
    }
}

async function markAllRead() {
    const key = resolveCurrentLibraryKey();
    if (!key) {
        showToast('Add to library to track progress');
        return;
    }

    const synced = await ensureReaderChapters();
    if (!synced || !state.currentChapters.length) {
        showToast('No chapters available');
        return;
    }

    const order = inferChapterOrder();
    const lastIndex = order === 'desc' ? 0 : state.currentChapters.length - 1;
    const lastChapter = state.currentChapters[lastIndex];
    const chapterNumber = getChapterNumberForProgress(lastChapter, lastIndex) || lastChapter.chapter || state.currentChapters.length;

    try {
        if (!navigator.onLine) {
            updateLocalLibraryProgress(key, {
                last_chapter: String(chapterNumber),
                last_page: 1,
                last_chapter_id: lastChapter.id
            });
            queueOfflineAction({
                type: 'update_progress',
                payload: {
                    key,
                    chapter: String(chapterNumber),
                    page: 1,
                    chapter_id: lastChapter.id,
                    total_chapters: state.totalChaptersCount || state.currentChapters.length
                }
            });
            queueOfflineAction({ type: 'update_status', payload: { key, status: 'completed' } });
            showToast('Marked read (offline)');
            return;
        }
        await API.updateProgress(
            key,
            String(chapterNumber),
            1,
            lastChapter.id,
            state.totalChaptersCount || state.currentChapters.length
        );
        await API.updateStatus(key, 'completed');
        updateLocalLibraryProgress(key, {
            last_chapter: String(chapterNumber),
            last_page: 1,
            last_chapter_id: lastChapter.id
        });
        showToast('Marked all chapters as read');
        await loadLibrary();
    } catch (error) {
        log(`❌ Mark all read failed: ${error.message}`);
        showToast('Failed to mark as read');
    }
}

function getCompletionChapterFromList(chapters) {
    if (!Array.isArray(chapters) || chapters.length === 0) return null;
    let best = null;
    let bestNum = -Infinity;
    chapters.forEach(ch => {
        const num = parseFloat(ch?.chapter);
        if (!Number.isNaN(num) && num > bestNum) {
            bestNum = num;
            best = ch;
        }
    });
    if (best) {
        return { chapter: best.chapter ?? bestNum, id: best.id };
    }
    const order = inferChapterOrder(chapters);
    const fallback = order === 'desc' ? chapters[0] : chapters[chapters.length - 1];
    return { chapter: fallback?.chapter || chapters.length, id: fallback?.id };
}

async function markLibraryEntryRead(key) {
    const entry = state.library.find(item => item.key === key);
    if (!entry) {
        showToast('Item not found in library');
        return;
    }

    const mangaId = entry.manga_id || entry.id;
    const source = entry.source;
    if (!mangaId || !source) {
        showToast('Missing source info');
        return;
    }

    let totalChapters = entry.total_chapters || null;
    let chapterNumber = entry.last_chapter || null;
    let chapterId = entry.last_chapter_id || null;

    if (!totalChapters || !chapterNumber || !chapterId) {
        try {
            const data = await API.getAllChapters(mangaId, source, { silent: true });
            const chapters = data?.chapters || [];
            if (!totalChapters) {
                totalChapters = data?.total || chapters.length || null;
            }
            const completion = getCompletionChapterFromList(chapters);
            if (completion) {
                if (!chapterNumber) chapterNumber = completion.chapter;
                if (!chapterId) chapterId = completion.id;
            }
        } catch (error) {
            log(`Mark read lookup failed: ${error.message}`);
        }
    }

    if (!chapterNumber && totalChapters) {
        chapterNumber = totalChapters;
    }
    if (!chapterNumber) {
        showToast('Unable to determine last chapter');
        return;
    }

    const progressPayload = {
        last_chapter: String(chapterNumber),
        last_page: 1,
        last_chapter_id: chapterId,
        total_chapters: totalChapters || entry.total_chapters || null
    };

    if (!navigator.onLine) {
        updateLocalLibraryProgress(key, progressPayload);
        const localEntry = state.library.find(item => item.key === key);
        if (localEntry) localEntry.status = 'completed';
        saveCachedLibrary();
        saveAutoBackup();
        queueOfflineAction({
            type: 'update_progress',
            payload: {
                key,
                chapter: String(chapterNumber),
                page: 1,
                chapter_id: chapterId,
                total_chapters: totalChapters || entry.total_chapters
            }
        });
        queueOfflineAction({ type: 'update_status', payload: { key, status: 'completed' } });
        showToast('Marked read (offline)');
        return;
    }

    try {
        await API.updateProgress(
            key,
            String(chapterNumber),
            1,
            chapterId,
            totalChapters || entry.total_chapters || null
        );
        await API.updateStatus(key, 'completed');
        updateLocalLibraryProgress(key, progressPayload);
        const localEntry = state.library.find(item => item.key === key);
        if (localEntry) {
            localEntry.status = 'completed';
        }
        showToast('Marked all chapters as read');
        await loadLibrary();
    } catch (error) {
        log(`❌ Mark read failed: ${error.message}`);
        showToast('Failed to mark as read');
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

function isSpreadPage(index) {
    return state.readerSpreadPages.has(index);
}

function getReaderStep() {
    if (!(state.readerSpread && state.readerMode === 'paged')) return 1;
    return isSpreadPage(state.readerCurrentPage) ? 1 : 2;
}

function getReaderDelta(direction) {
    if (!(state.readerSpread && state.readerMode === 'paged')) {
        const step = 1;
        if (state.readerDirection === 'rtl') {
            return direction === 'next' ? -step : step;
        }
        return direction === 'next' ? step : -step;
    }

    let step = 1;
    if (direction === 'next') {
        step = isSpreadPage(state.readerCurrentPage) ? 1 : 2;
    } else {
        const prevIndex = state.readerCurrentPage - 1;
        step = prevIndex >= 0 && isSpreadPage(prevIndex) ? 1 : 2;
    }

    if (state.readerDirection === 'rtl') {
        return direction === 'next' ? -step : step;
    }
    return direction === 'next' ? step : -step;
}

function moveReader(direction) {
    const delta = getReaderDelta(direction);
    const nextIndex = state.readerCurrentPage + delta;
    if (direction === 'next' && (nextIndex >= state.readerPages.length)) {
        advanceToNextChapter();
        return;
    }
    setReaderPage(nextIndex);
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
    if (state.readerMode === 'paged') return;
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
        els.readerContent.classList.remove('webtoon');
        clearReaderObserver();
    } else {
        els.readerContainer.classList.remove('paged');
        els.readerContent.classList.toggle('webtoon', state.readerMode === 'webtoon');
        setupReaderObserver();
    }

    if (els.readerModeLabel) {
        if (state.readerMode === 'paged') {
            els.readerModeLabel.textContent = 'Paged';
        } else if (state.readerMode === 'webtoon') {
            els.readerModeLabel.textContent = 'Webtoon';
        } else {
            els.readerModeLabel.textContent = 'Strip';
        }
    }

    updateReaderControls({ scroll: true });
    updateReaderTapZones();
}

function updateReaderTapZones() {
    if (!els.readerTapZones) return;
    const isMobile = window.innerWidth <= 900;
    els.readerTapZones.classList.toggle('enabled', isMobile);
}

function handleReaderScroll() {
    if (state.readerMode === 'paged') return;
    // If observer is active, don't use manual scroll detection to avoid layout thrashing
    if (state.readerObserver) return;
    
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
    saveReaderPreferencesForCurrent();
}

function toggleReaderMode() {
    const modes = ['strip', 'webtoon', 'paged'];
    const currentIndex = modes.indexOf(state.readerMode);
    const next = modes[(currentIndex + 1) % modes.length];

    if (DEBUG_MODE) {
        console.log(`[DEBUG] toggleReaderMode: ${state.readerMode} → ${next}`);
    }

    setReaderMode(next);
    showToast(`Reader Mode: ${next === 'strip' ? 'Strip' : next === 'webtoon' ? 'Webtoon' : 'Paged'}`);
}

function toggleReaderImmersive() {
    state.readerImmersive = !state.readerImmersive;
    els.readerContainer.classList.toggle('immersive', state.readerImmersive);
    if (els.readerImmersiveBtn) {
        els.readerImmersiveBtn.classList.toggle('active', state.readerImmersive);
    }
    if (state.readerImmersive) {
        closeSidebar();
    }
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
const READER_DIR_LABELS = {
    ltr: 'Left to Right',
    rtl: 'Right to Left'
};
const READER_BG_LABELS = {
    dark: 'Dark',
    light: 'Light',
    sepia: 'Sepia',
    black: 'Black',
    white: 'White'
};

function setReaderFitMode(mode) {
    if (DEBUG_MODE) {
        console.log(`[DEBUG] setReaderFitMode: ${state.readerFitMode} → ${mode}`);
    }

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
    saveReaderPreferencesForCurrent();
}

function applyReaderFitMode() {
    const modes = ['fit-width', 'fit-height', 'fit-screen', 'fit-original'];
    modes.forEach(m => els.readerContainer.classList.remove(m));
    els.readerContainer.classList.add(state.readerFitMode);
}

function setReaderDirection(direction) {
    if (DEBUG_MODE) {
        console.log(`[DEBUG] setReaderDirection: ${state.readerDirection} → ${direction}`);
    }

    state.readerDirection = direction === 'rtl' ? 'rtl' : 'ltr';
    localStorage.setItem('manganegus.readerDirection', state.readerDirection);
    applyReaderDirection();
    showToast(`Direction: ${READER_DIR_LABELS[state.readerDirection]}`);
    saveReaderPreferencesForCurrent();
}

function applyReaderDirection() {
    if (els.readerContent) {
        els.readerContent.style.direction = state.readerDirection === 'rtl' ? 'rtl' : 'ltr';
    }
    if (els.readerSettingsMenu) {
        els.readerSettingsMenu.querySelectorAll('[data-direction]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.direction === state.readerDirection);
        });
    }
}

function setReaderBackground(bg) {
    if (DEBUG_MODE) {
        console.log(`[DEBUG] setReaderBackground: ${state.readerBackground} → ${bg}`);
    }

    const next = READER_BG_LABELS[bg] ? bg : 'dark';
    state.readerBackground = next;
    localStorage.setItem('manganegus.readerBackground', next);
    applyReaderBackground();
    showToast(`Background: ${READER_BG_LABELS[next]}`);
    saveReaderPreferencesForCurrent();
}

function applyReaderBackground() {
    if (els.readerContainer) {
        els.readerContainer.dataset.readerBg = state.readerBackground;
    }
    if (els.readerSettingsMenu) {
        els.readerSettingsMenu.querySelectorAll('[data-bg]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.bg === state.readerBackground);
        });
    }
}

function toggleReaderSpread() {
    state.readerSpread = !state.readerSpread;
    localStorage.setItem('manganegus.readerSpread', state.readerSpread ? '1' : '0');
    applyReaderSpread();
    showToast(`Spread: ${state.readerSpread ? 'On' : 'Off'}`);
    saveReaderPreferencesForCurrent();
}

function applyReaderSpread() {
    if (els.readerContainer) {
        els.readerContainer.classList.toggle('spread', state.readerSpread);
    }
    if (els.readerSettingsMenu) {
        const btn = els.readerSettingsMenu.querySelector('[data-spread="toggle"]');
        if (btn) {
            btn.classList.toggle('active', state.readerSpread);
        }
    }
    updateReaderControls({ scroll: true });
}

function applyReaderEnhancements() {
    if (!els.readerContent) return;
    const { brightness, contrast, sharpen, crop } = state.readerEnhance;
    els.readerContent.style.setProperty('--reader-brightness', `${(brightness || 100) / 100}`);
    els.readerContent.style.setProperty('--reader-contrast', `${(contrast || 100) / 100}`);
    els.readerContent.style.setProperty('--reader-sharpen', `${sharpen || 0}`);
    els.readerContent.style.setProperty('--reader-crop', `${crop || 0}%`);
}

function setReaderEnhancement(key, value) {
    if (!Object.prototype.hasOwnProperty.call(state.readerEnhance, key)) return;
    state.readerEnhance[key] = value;
    try {
        localStorage.setItem('manganegus.readerEnhance', JSON.stringify(state.readerEnhance));
    } catch {
        // Ignore
    }
    applyReaderEnhancements();
    saveReaderPreferencesForCurrent();
}

function getReaderPrefsKey() {
    if (!state.currentManga?.id || !state.currentManga?.source) return null;
    return `manganegus.readerPrefs:${state.currentManga.source}:${state.currentManga.id}`;
}

function saveReaderPreferencesForCurrent() {
    const key = getReaderPrefsKey();
    if (!key) return;
    const payload = {
        readerMode: state.readerMode,
        readerFitMode: state.readerFitMode,
        readerDirection: state.readerDirection,
        readerBackground: state.readerBackground,
        readerSpread: state.readerSpread,
        readerEnhance: state.readerEnhance
    };
    try {
        localStorage.setItem(key, JSON.stringify(payload));
    } catch {
        // Ignore
    }
}

function loadReaderPreferencesForCurrent() {
    const key = getReaderPrefsKey();
    if (!key) return;
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return;
        const prefs = JSON.parse(raw);
        if (prefs.readerMode) state.readerMode = prefs.readerMode;
        if (prefs.readerFitMode) state.readerFitMode = prefs.readerFitMode;
        if (prefs.readerDirection) state.readerDirection = prefs.readerDirection;
        if (prefs.readerBackground) state.readerBackground = prefs.readerBackground;
        if (typeof prefs.readerSpread === 'boolean') state.readerSpread = prefs.readerSpread;
        if (prefs.readerEnhance) {
            state.readerEnhance = { ...state.readerEnhance, ...prefs.readerEnhance };
        }
        applyReaderMode();
        applyReaderFitMode();
        applyReaderDirection();
        applyReaderBackground();
        applyReaderSpread();
        applyReaderEnhancements();
    } catch {
        // Ignore
    }
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

function setTheme(theme, { manual = true, silent = false } = {}) {
    if (!THEMES.includes(theme)) theme = 'dark';
    state.theme = theme;
    if (manual) {
        state.manualTheme = theme;
        localStorage.setItem('manganegus.theme', theme);
    }
    applyTheme();
    if (!silent) {
        showToast(`Theme: ${THEME_LABELS[theme]}`);
    }
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

function applyAccentColor(color) {
    if (!color) return;
    document.documentElement.style.setProperty('--accent', color);
    document.documentElement.style.setProperty('--accent-hover', color);
    document.documentElement.style.setProperty('--accent-border', `${color}80`);
    document.documentElement.style.setProperty('--accent-glow', `${color}33`);
    document.documentElement.style.setProperty('--accent-light', `${color}1a`);
}

function setAccentColor(color) {
    if (!color) return;
    state.accentColor = color;
    try {
        localStorage.setItem('manganegus.accentColor', color);
    } catch {
        // Ignore
    }
    applyAccentColor(color);
}

function applyThemeSchedule() {
    if (state.themeSchedule === 'off') {
        setTheme(state.manualTheme, { manual: false, silent: true });
        return;
    }
    if (state.themeSchedule === 'system') {
        const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches;
        setTheme(prefersDark ? 'dark' : 'light', { manual: false, silent: true });
        return;
    }
    if (state.themeSchedule === 'night') {
        const hour = new Date().getHours();
        const isNight = hour >= 19 || hour < 7;
        setTheme(isNight ? 'dark' : 'light', { manual: false, silent: true });
    }
}

function setThemeSchedule(schedule) {
    state.themeSchedule = schedule || 'off';
    try {
        localStorage.setItem('manganegus.themeSchedule', state.themeSchedule);
    } catch {
        // Ignore
    }
    applyThemeSchedule();
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
            moveReader('prev');
            break;

        case 'ArrowRight':
        case 'd':
        case 'D':
        case ' ': // Space
            event.preventDefault();
            moveReader('next');
            break;

        case 'ArrowUp':
            event.preventDefault();
            if (state.readerMode === 'strip') {
                els.readerContent.scrollBy({ top: -200, behavior: 'smooth' });
            } else {
                moveReader('prev');
            }
            break;

        case 'ArrowDown':
            event.preventDefault();
            if (state.readerMode === 'strip') {
                els.readerContent.scrollBy({ top: 200, behavior: 'smooth' });
            } else {
                moveReader('next');
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
        case 's':
        case 'S':
            event.preventDefault();
            toggleReaderSpread();
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

    const order = inferChapterOrder();
    const delta = order === 'desc' ? -1 : 1;
    const nextIndex = state.currentChapterIndex + delta;
    if (nextIndex >= 0 && nextIndex < state.currentChapters.length) {
        return state.currentChapters[nextIndex];
    }

    const nextPage = order === 'desc' ? state.currentPage - 1 : state.currentPage + 1;
    if (nextPage >= 1 && nextPage <= state.totalPages) {
        try {
            const response = await fetchChaptersPage(nextPage);
            if (!response?.chapters?.length) return null;
            return order === 'desc'
                ? response.chapters[response.chapters.length - 1]
                : response.chapters[0];
        } catch (error) {
            log(`Prefetch chapter list failed: ${error.message}`);
            return null;
        }
    }

    return null;
}

async function prefetchNextChapter() {
    const distance = getEffectivePrefetchDistance();
    if (distance <= 0) return;
    if (state.prefetchInFlight) return;
    if (!state.currentManga?.source) return;
    if (!state.currentChapters.length || state.currentChapterIndex < 0) {
        const synced = await ensureReaderChapters();
        if (!synced) return;
    }

    const order = inferChapterOrder();
    const delta = order === 'desc' ? -1 : 1;
    const chaptersToPrefetch = [];

    for (let offset = 1; offset <= distance; offset += 1) {
        const idx = state.currentChapterIndex + (delta * offset);
        if (idx < 0 || idx >= state.currentChapters.length) break;
        const chapter = state.currentChapters[idx];
        if (!chapter?.id) continue;
        if (state.prefetchedChapters.has(chapter.id)) continue;
        chaptersToPrefetch.push(chapter);
    }

    if (!chaptersToPrefetch.length) {
        const nextChapter = await resolveNextChapterForPrefetch();
        if (!nextChapter || state.prefetchedChapters.has(nextChapter.id)) return;
        chaptersToPrefetch.push(nextChapter);
    }

    state.prefetchInFlight = true;
    try {
        for (const chapter of chaptersToPrefetch) {
            const pages = await API.getChapterPages(chapter.id, state.currentManga.source);
            state.prefetchedChapters.set(chapter.id, pages);
            if (!state.prefetchedChapterId) {
                state.prefetchedChapterId = chapter.id;
                state.prefetchedChapterTitle = chapter.title;
                state.prefetchedPages = pages;
            }
            log(`Prefetched chapter (${chapter.title || chapter.id})`);
        }
    } catch (error) {
        log(`Prefetch failed: ${error.message}`);
    } finally {
        state.prefetchInFlight = false;
    }
}

async function advanceToNextChapter() {
    if (!state.currentChapters.length || state.currentChapterIndex < 0) {
        const synced = await ensureReaderChapters();
        if (!synced) {
            showToast('No next chapter available');
            return;
        }
    }

    let nextChapter = null;
    let nextIndex = -1;
    const order = inferChapterOrder();
    const delta = order === 'desc' ? -1 : 1;
    const candidateIndex = state.currentChapterIndex + delta;
    if (candidateIndex >= 0 && candidateIndex < state.currentChapters.length) {
        nextChapter = state.currentChapters[candidateIndex];
        nextIndex = candidateIndex;
    } else {
        const nextPage = order === 'desc' ? state.currentPage - 1 : state.currentPage + 1;
        if (nextPage >= 1 && nextPage <= state.totalPages) {
            const response = await fetchChaptersPage(nextPage, { updateState: true });
            if (response?.chapters?.length) {
                nextIndex = order === 'desc' ? response.chapters.length - 1 : 0;
                nextChapter = response.chapters[nextIndex];
            }
        }
    }

    if (!nextChapter) {
        showToast('No next chapter available');
        return;
    }

    const chapterNumber = getChapterNumberForProgress(nextChapter, nextIndex);
    await openReader(nextChapter.id, nextChapter.title || 'Chapter', 0, chapterNumber, state.totalChaptersCount);
}

function handleReaderKeydown(event) {
    if (!els.readerContainer?.classList.contains('active')) return;
    const activeTag = document.activeElement?.tagName;
    if (activeTag && ['INPUT', 'TEXTAREA', 'SELECT'].includes(activeTag)) return;
    if (!state.readerPages.length) return;

    switch (event.key) {
        case 'ArrowLeft':
        case 'ArrowUp':
            event.preventDefault();
            moveReader('prev');
            break;
        case 'ArrowRight':
        case 'ArrowDown':
            event.preventDefault();
            moveReader('next');
            break;
        case ' ':
        case 'Enter':
            event.preventDefault();
            moveReader('next');
            break;
        case 'Escape':
            event.preventDefault();
            closeReader();
            break;
        case 's':
        case 'S':
            event.preventDefault();
            toggleReaderSpread();
            break;
        default:
            if (/^[1-9]$/.test(event.key)) {
                const ratio = parseInt(event.key, 10) / 10;
                const target = Math.floor(state.readerPages.length * ratio) - 1;
                setReaderPage(Math.max(0, target));
            }
            break;
    }
}

function handleReaderTap(event) {
    if (!els.readerContainer.classList.contains('active')) return;
    if (state.readerSwipeConsumed) {
        state.readerSwipeConsumed = false;
        return;
    }
    if (event.target.closest('.reader-controls') || event.target.closest('#close-reader-btn')) return;

    const rect = els.readerContent.getBoundingClientRect();
    if (!rect.width) return;
    const x = event.clientX - rect.left;
    const ratio = x / rect.width;

    if (ratio < 0.33) {
        moveReader('prev');
    } else if (ratio > 0.66) {
        moveReader('next');
    } else {
        toggleReaderImmersive();
    }
}

function handleReaderPointerDown(event) {
    if (event.pointerType !== 'touch') return;
    if (!els.readerContainer.classList.contains('active')) return;
    state.readerTouchStart = {
        x: event.clientX,
        y: event.clientY,
        time: Date.now()
    };
}

function handleReaderPointerMove(event) {
    if (!state.readerTouchStart) return;
    const dx = Math.abs(event.clientX - state.readerTouchStart.x);
    const dy = Math.abs(event.clientY - state.readerTouchStart.y);
    if (dx > 14 || dy > 14) {
        state.readerTouchStart.moved = true;
    }
}

function handleReaderPointerUp(event) {
    if (!state.readerTouchStart) return;
    const { x, y } = state.readerTouchStart;
    state.readerTouchStart = null;

    if (state.readerMode === 'webtoon') return;

    const dx = event.clientX - x;
    const dy = event.clientY - y;
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);

    if (absX < 60 || absX < absY) return;

    state.readerSwipeConsumed = true;
    if (dx < 0) {
        moveReader('next');
    } else {
        moveReader('prev');
    }
}

// ========================================
// Reader
// ========================================
async function openReader(chapterId, chapterTitle, startPage = 0, chapterNumberOverride = null, totalChaptersOverride = null) {
    console.log('[READER DEBUG] openReader called', { chapterId, chapterTitle, source: state.currentManga?.source });

    closeSidebar();
    closeAllMenus();

    // Save scroll position before locking body scroll
    state.readerPreviousScrollY = window.scrollY;

    // IMPORTANT: Show reader container FIRST, then lock body scroll
    // This prevents the scroll lock from interfering with the reader's visibility
    els.readerContainer.classList.add('active');

    // Use requestAnimationFrame to ensure the reader is painted before locking scroll
    await new Promise(resolve => requestAnimationFrame(() => {
        // Now lock body scroll AFTER reader is visible
        document.body.classList.add('reader-active');

        // Scroll the reader content to top (not the window)
        if (els.readerContent) {
            els.readerContent.scrollTop = 0;
        }

        // Also reset window scroll for safety
        window.scrollTo(0, 0);

        resolve();
    }));

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

    if (!state.currentManga?.source || state.currentManga.source === 'jikan') {
        log(`⚠️ Source is '${state.currentManga?.source || 'undefined'}', resolving actual source...`);
        await ensureReaderChapters();
    }
    if (!state.currentManga?.source || state.currentManga.source === 'jikan') {
        showToast('Could not find chapter source - try selecting a different source');
        log(`❌ Failed to resolve source - still '${state.currentManga?.source || 'undefined'}'`);
        document.body.classList.remove('reader-active');
        if (state.readerPreviousScrollY > 0) {
            window.scrollTo(0, state.readerPreviousScrollY);
            state.readerPreviousScrollY = 0;
        }
        return;
    }
    log(`✅ Using source: ${state.currentManga.source}`);

    els.readerTitle.textContent = chapterTitle;
    els.readerContent.innerHTML = `
        <div class="loading-state">
            <div class="spinner"></div>
            <span class="loading-text">Loading pages...</span>
        </div>
    `;
    // Reader container already made active at the start of openReader()
    state.readerCurrentPage = 0;
    state.readerSessionStart = Date.now();
    state.readerSessionPageStart = startPage || 0;

    log(`📖 Opening reader: ${chapterTitle}`);
    console.log('[READER DEBUG] Current manga:', state.currentManga);

    try {
        console.log('[READER DEBUG] Calling API.getChapterPages...');
        let pages = null;
        const prefetched = state.prefetchedChapters?.get(chapterId);
        if (prefetched && Array.isArray(prefetched)) {
            pages = prefetched;
            state.prefetchedChapters.delete(chapterId);
        } else if (state.prefetchedChapterId === chapterId && Array.isArray(state.prefetchedPages)) {
            pages = state.prefetchedPages;
            state.prefetchedChapterId = null;
            state.prefetchedChapterTitle = null;
            state.prefetchedPages = null;
        } else {
            pages = await API.getChapterPages(chapterId, state.currentManga.source);
        }
        console.log('[READER DEBUG] Pages received:', pages, 'Type:', typeof pages, 'IsArray:', Array.isArray(pages));

        state.readerPages = pages;
        state.readerSpreadPages.clear();

        if (pages.length === 0) {
            console.error('[READER DEBUG] No pages returned!');
            els.readerContent.innerHTML = '<p style="padding: 24px; text-align: center; color: var(--text-muted);">No pages available</p>';
            // Remove reader-active and restore scroll to allow sidebar to work
            document.body.classList.remove('reader-active');
            if (state.readerPreviousScrollY > 0) {
                window.scrollTo(0, state.readerPreviousScrollY);
                state.readerPreviousScrollY = 0;
            }
            return;
        }

        console.log('[READER DEBUG] Rendering', pages.length, 'pages');
        state.readerCurrentPage = Math.max(0, Math.min(startPage, pages.length - 1));
        renderReaderPages();
        applyReaderMode();

        // Ensure reader content is scrolled to top after rendering
        requestAnimationFrame(() => {
            if (els.readerContent) {
                els.readerContent.scrollTop = 0;
            }
        });

        log(`✅ Loaded ${pages.length} pages`);
        scheduleProgressSave(true);
        prefetchNextChapter();
    } catch (error) {
        console.error('[READER DEBUG] Error:', error);
        els.readerContent.innerHTML = `<p style="padding: 24px; text-align: center; color: var(--text-muted);">Failed to load pages<br/>${escapeHtml(error.message)}</p>`;
        log(`❌ Reader error: ${error.message}`);
        // Remove reader-active and restore scroll to allow sidebar to work
        document.body.classList.remove('reader-active');
        if (state.readerPreviousScrollY > 0) {
            window.scrollTo(0, state.readerPreviousScrollY);
            state.readerPreviousScrollY = 0;
        }
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

        const optimizeParams = state.filters.dataSaver ? '&format=webp&quality=55' : '&format=webp&quality=85';
        const proxyUrl = referer
            ? `/api/proxy/image?url=${encodeURIComponent(pageUrl)}&referer=${encodeURIComponent(referer)}${optimizeParams}`
            : `/api/proxy/image?url=${encodeURIComponent(pageUrl)}${optimizeParams}`;
        return `<img src="${escapeHtml(proxyUrl)}" alt="Page ${index + 1}" class="reader-page lazy-image" data-page-index="${index}" data-original-url="${escapeHtml(pageUrl)}" loading="lazy" />`;
    }).join('');

    console.log('[READER DEBUG] Generated HTML length:', html.length);
    els.readerContent.innerHTML = html;
    els.readerContent.querySelectorAll('.reader-page').forEach((img) => {
        // Handle successful load
        img.addEventListener('load', () => {
            img.classList.add('loaded');
            const index = Number(img.dataset.pageIndex || 0);
            if (Number.isNaN(index) || !img.naturalWidth || !img.naturalHeight) return;
            const ratio = img.naturalWidth / img.naturalHeight;
            if (ratio > 1.25) {
                state.readerSpreadPages.add(index);
            } else {
                state.readerSpreadPages.delete(index);
            }
        }, { once: true });

        // Handle load errors - show error state and log
        img.addEventListener('error', () => {
            const index = img.dataset.pageIndex || '?';
            const originalUrl = img.dataset.originalUrl || 'unknown';
            console.error(`[READER] Failed to load page ${index}:`, originalUrl);
            img.classList.add('load-error');
            img.alt = `Page ${index} failed to load`;
            img.style.minHeight = '200px';
            img.style.background = 'repeating-linear-gradient(45deg, #1a1a1a, #1a1a1a 10px, #222 10px, #222 20px)';
            log(`⚠️ Page ${index} failed to load`);
        }, { once: true });
    });
    console.log('[READER DEBUG] Rendered', state.readerPages.length, 'page elements');
    setupReaderObserver();
    applyReaderEnhancements();
}

function updateReaderControls(options = {}) {
    const total = state.readerPages.length;
    if (!total) {
        els.readerPageIndicator.textContent = '0 / 0';
        els.prevPageBtn.disabled = true;
        els.nextPageBtn.disabled = true;
        return;
    }
    if (state.readerMode === 'paged' && state.readerSpread) {
        const start = state.readerCurrentPage + 1;
        const showPair = !isSpreadPage(state.readerCurrentPage);
        const end = showPair ? Math.min(total, start + 1) : start;
        els.readerPageIndicator.textContent = showPair ? `${start}-${end} / ${total}` : `${start} / ${total}`;
    } else {
        els.readerPageIndicator.textContent = `${state.readerCurrentPage + 1} / ${total}`;
    }
    els.prevPageBtn.disabled = state.readerCurrentPage === 0;
    els.nextPageBtn.disabled = state.readerCurrentPage >= total - 1;

    // Scroll to current page
    const pages = els.readerContent.querySelectorAll('.reader-page');
    if (state.readerMode === 'paged') {
        const showPair = state.readerSpread && !isSpreadPage(state.readerCurrentPage);
        pages.forEach((page, index) => {
            const isActive = index === state.readerCurrentPage
                || (showPair && index === state.readerCurrentPage + 1);
            page.classList.toggle('active', isActive);
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
    // CRITICAL: Always remove reader-active first to ensure sidebar access is restored
    // even if subsequent operations fail
    els.readerContainer.classList.remove('active');
    els.readerContainer.classList.remove('immersive');
    document.body.classList.remove('reader-active');

    // Restore scroll position to where user was before opening reader
    if (state.readerPreviousScrollY > 0) {
        window.scrollTo(0, state.readerPreviousScrollY);
        state.readerPreviousScrollY = 0;
    }

    try {
        await saveReadingProgress();
        if (state.readerSessionStart) {
            const sessionMs = Date.now() - state.readerSessionStart;
            const pagesRead = Math.max(0, state.readerCurrentPage - state.readerSessionPageStart + 1);
            recordReadingSession(sessionMs / 60000, pagesRead);
            state.readerSessionStart = null;
            state.readerSessionPageStart = 0;
        }
    } catch (error) {
        console.error('[READER] Error saving progress on close:', error);
    }

    clearReaderObserver();
    if (state.progressSaveTimer) {
        clearTimeout(state.progressSaveTimer);
        state.progressSaveTimer = null;
    }
    if (state.readerScrollRaf) {
        cancelAnimationFrame(state.readerScrollRaf);
        state.readerScrollRaf = null;
    }
    state.readerImmersive = false;
    state.readerPages = [];
    state.readerCurrentPage = 0;
    state.readerSpreadPages.clear();
    state.currentChapterId = null;
    state.currentChapterTitle = '';
    state.currentChapterNumber = null;
    state.currentChapterIndex = -1;
}

// ========================================
// Modals
// ========================================
async function bulkUpdateStatus(keys, status) {
    if (!keys || keys.length === 0) {
        showToast('No items selected');
        return;
    }
    try {
        await Promise.all(keys.map(key => API.updateStatus(key, status)));
        keys.forEach(key => {
            const entry = state.library.find(item => item.key === key);
            if (entry) entry.status = status;
        });
        showToast(`Updated ${keys.length} manga`);
        exitSelectionMode();
        await loadLibrary();
        renderNav();
    } catch (error) {
        log(`❌ Bulk status update failed: ${error.message}`);
        showToast('Bulk status update failed');
    }
}

function showLibraryStatusModal(mangaId, source, title, coverUrl, libraryKey = null, bulkKeys = null) {
    if (DEBUG_MODE) {
        console.log(`[DEBUG] showLibraryStatusModal called for ${title}`);
    }

    els.libraryStatusModal.classList.add('active');
    const modalTitle = els.libraryStatusModal.querySelector('.modal-title');
    const modalSubtitle = els.libraryStatusModal.querySelector('.modal-subtitle');
    const isBulk = Array.isArray(bulkKeys) && bulkKeys.length > 0;
    const isUpdate = Boolean(libraryKey);
    if (modalTitle) {
        modalTitle.textContent = isBulk ? 'Update Selected' : (isUpdate ? 'Update Status' : 'Add to Library');
    }
    if (modalSubtitle) {
        modalSubtitle.textContent = isBulk
            ? 'Apply status to selected manga'
            : (isUpdate ? 'Select new status' : 'Select reading status');
    }

    // Remove existing listeners and add new ones
    document.querySelectorAll('.status-option-btn').forEach(btn => {
        const newBtn = btn.cloneNode(true);
        btn.replaceWith(newBtn);

        newBtn.addEventListener('click', async () => {
            const status = newBtn.dataset.status;
            if (isBulk) {
                await bulkUpdateStatus(bulkKeys, status);
            } else if (isUpdate) {
                await updateLibraryStatus(libraryKey, status);
            } else {
                await addToLibrary(mangaId, source, title, coverUrl, status);
            }
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
        offlineBanner: document.getElementById('offline-banner'),

        // Header Search
        searchInput: document.getElementById('search-input'),
        searchModeBtn: document.getElementById('search-mode-btn'),
        searchModeIcon: document.getElementById('search-mode-icon'),
        clearSearchBtn: document.getElementById('clear-search'),
        searchBtn: document.getElementById('search-btn'),
        searchWrapper: document.querySelector('.search-wrapper'),
        searchSuggestions: document.getElementById('search-suggestions'),

        // Navigation
        navList: document.getElementById('nav-list'),
        sourceList: document.getElementById('source-list'),
        sourceStatusBtn: document.getElementById('source-status-btn'),

        // Filters
        filterBtn: document.getElementById('filter-btn'),
        filterModal: document.getElementById('filter-modal'),
        closeFilterModal: document.getElementById('close-filter-modal'),
        filterApply: document.getElementById('filter-apply'),
        filterReset: document.getElementById('filter-reset'),
        filterGenres: document.getElementById('filter-genres'),
        filterExclude: document.getElementById('filter-exclude'),
        filterStatus: document.getElementById('filter-status'),
        filterType: document.getElementById('filter-type'),
        filterDemographics: document.getElementById('filter-demographics'),
        filterYearStart: document.getElementById('filter-year-start'),
        filterYearEnd: document.getElementById('filter-year-end'),
        filterScoreMin: document.getElementById('filter-score-min'),
        filterScoreMax: document.getElementById('filter-score-max'),
        filterSort: document.getElementById('filter-sort'),
        filterOrder: document.getElementById('filter-order'),
        filterDensity: document.getElementById('filter-density'),
        filterMeta: document.getElementById('filter-meta'),
        filterDataSaver: document.getElementById('filter-data-saver'),
        filterSource: document.getElementById('filter-source'),
        filterPagination: document.getElementById('filter-pagination'),

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
        randomBtn: document.getElementById('random-btn'),
        continueReading: document.getElementById('continue-reading'),
        continueBtn: document.getElementById('continue-btn'),
        continueTitle: document.getElementById('continue-title'),
        continueCover: document.getElementById('continue-cover'),
        continueProgress: document.getElementById('continue-progress'),
        recommendationsSection: document.getElementById('recommendations-section'),
        recommendationsGrid: document.getElementById('recommendations-grid'),
        recommendationsSubtitle: document.getElementById('recommendations-subtitle'),
        historyTools: document.getElementById('history-tools'),
        historyCalendar: document.getElementById('history-calendar'),
        historyExportBtn: document.getElementById('history-export-btn'),
        historyOnThisDay: document.getElementById('history-on-this-day'),

        // Library
        libraryGrid: document.getElementById('library-grid'),
        libraryEmpty: document.getElementById('library-empty'),
        libraryCount: document.getElementById('library-count'),
        librarySort: document.getElementById('library-sort'),
        librarySmartFilter: document.getElementById('library-smart-filter'),
        libraryCollection: document.getElementById('library-collection'),

        // Details
        backBtn: document.getElementById('back-btn'),
        detailsCoverImg: document.getElementById('details-cover-img'),
        detailsTitle: document.getElementById('details-title'),
        detailsMeta: document.getElementById('details-meta'),
        detailsDescription: document.getElementById('details-description'),
        addToLibraryBtn: document.getElementById('add-to-library-btn'),
        favoriteBtn: document.getElementById('favorite-btn'),
        markAllReadBtn: document.getElementById('mark-all-read-btn'),
        downloadAllBtn: document.getElementById('download-all-btn'),
        notesInput: document.getElementById('notes-input'),
        ratingInput: document.getElementById('rating-input'),
        ratingValue: document.getElementById('rating-value'),
        reviewInput: document.getElementById('review-input'),
        shareReviewBtn: document.getElementById('share-review-btn'),
        collectionsInput: document.getElementById('collections-input'),
        detailsSources: document.getElementById('details-sources'),
        detailsSourcesList: document.getElementById('details-sources-list'),
        similarGrid: document.getElementById('similar-grid'),
        chaptersList: document.getElementById('chapters-list'),
        chaptersPagination: document.getElementById('chapters-pagination'),
        selectAllChaptersBtn: document.getElementById('select-all-chapters'),
        deselectAllChaptersBtn: document.getElementById('deselect-all-chapters'),
        downloadSelectedBtn: document.getElementById('download-selected-btn'),
        downloadNextBtn: document.getElementById('download-next-btn'),
        downloadNextChaptersBtn: document.getElementById('download-next-chapters-btn'),
        chapterLanguage: document.getElementById('chapter-language'),
        chapterGroup: document.getElementById('chapter-group'),
        chapterTranslation: document.getElementById('chapter-translation'),

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
        readerImmersiveBtn: document.getElementById('reader-immersive-btn'),
        readerSettingsBtn: document.getElementById('reader-settings-btn'),
        readerSettingsMenu: document.getElementById('reader-settings-menu'),
        readerFitLabel: document.getElementById('reader-fit-label'),
        readerTapZones: document.getElementById('reader-tap-zones'),

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
        settingsBtn: document.getElementById('settings-btn'),
        settingsModal: document.getElementById('settings-modal'),
        closeSettingsModal: document.getElementById('close-settings-modal'),
        statsGrid: document.getElementById('stats-grid'),
        readingCalendar: document.getElementById('reading-calendar'),
        genreBreakdown: document.getElementById('genre-breakdown'),
        exportLibraryBtn: document.getElementById('export-library-btn'),
        importLibraryBtn: document.getElementById('import-library-btn'),
        importLibraryInput: document.getElementById('import-library-input'),
        backupExportBtn: document.getElementById('backup-export-btn'),
        backupImportBtn: document.getElementById('backup-import-btn'),
        backupImportInput: document.getElementById('backup-import-input'),
        autoBackupToggle: document.getElementById('auto-backup-toggle'),
        cloudSyncId: document.getElementById('cloud-sync-id'),
        cloudSyncToggle: document.getElementById('cloud-sync-toggle'),
        cloudSyncNow: document.getElementById('cloud-sync-now'),
        cloudSyncPull: document.getElementById('cloud-sync-pull'),
        cloudSyncPush: document.getElementById('cloud-sync-push'),
        copyCloudSync: document.getElementById('copy-cloud-sync'),
        clearCacheBtn: document.getElementById('clear-cache-btn'),
        syncPullBtn: document.getElementById('sync-pull-btn'),
        syncPushBtn: document.getElementById('sync-push-btn'),
        themeSchedule: document.getElementById('theme-schedule'),
        accentColor: document.getElementById('accent-color'),
        readerBrightness: document.getElementById('reader-brightness'),
        readerContrast: document.getElementById('reader-contrast'),
        readerSharpen: document.getElementById('reader-sharpen'),
        readerCrop: document.getElementById('reader-crop'),
        readerPrefetch: document.getElementById('reader-prefetch'),
        mergeChapters: document.getElementById('merge-chapters'),
        autoDownloadFavorites: document.getElementById('auto-download-favorites'),
        installBtn: document.getElementById('install-btn'),

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
        themeIcon: document.getElementById('theme-icon'),

        // Selection Mode
        pausedBadge: document.getElementById('paused-badge'),
        selectionActionBar: document.getElementById('selection-action-bar'),
        selectionCount: document.getElementById('selection-count'),
        btnStatusSelected: document.getElementById('btn-status-selected'),
        btnDeleteSelected: document.getElementById('btn-delete-selected'),
        btnDownloadSelected: document.getElementById('btn-download-selected'),
        btnCancelSelection: document.getElementById('btn-cancel-selection'),
        appTitle: document.querySelector('.app-title'),

        // Confirm Modal
        confirmModal: document.getElementById('confirm-modal'),
        confirmTitle: document.getElementById('confirm-title'),
        confirmMessage: document.getElementById('confirm-message'),
        confirmOkBtn: document.getElementById('confirm-ok'),
        confirmCancelBtn: document.getElementById('confirm-cancel')
    };

    // Expose els in debug mode
    if (DEBUG_MODE) {
        window.DEBUG_ELS = els;
        console.log('[DEBUG] Elements initialized and exposed via window.DEBUG_ELS');
    } else {
        console.log('[DEBUG] Elements initialized');
    }
    console.log('[DEBUG] els.sourceList:', els.sourceList);
    console.log('[DEBUG] els.sidebar:', els.sidebar);
}

// ========================================
// Initialization
// ========================================
// ========================================
// Event Delegation Setup (prevents memory leaks)
// ========================================
function clearLongPress() {
    if (state.longPressTimer) {
        clearTimeout(state.longPressTimer);
        state.longPressTimer = null;
    }
}

function getCardContext(card, gridEl) {
    const mangaId = card.dataset.mangaId;
    const source = card.dataset.source;
    const titleEl = card.querySelector('.card-title');
    const title = titleEl ? titleEl.textContent : '';
    const coverImg = card.querySelector('.card-cover img');
    const coverUrl = coverImg ? coverImg.src : '';
    const allCards = Array.from(gridEl.querySelectorAll('.card'));
    const index = allCards.indexOf(card);
    const mangaData = gridEl._mangaData ? gridEl._mangaData[index] : null;
    return { mangaId, source, title, coverUrl, mangaData };
}

function openCardMenuFromCard(card, gridEl) {
    const menuBtn = card.querySelector('.card-menu-btn');
    if (!menuBtn) return;
    const { mangaId, source, title, coverUrl } = getCardContext(card, gridEl);
    const context = gridEl === els.libraryGrid ? 'library' : 'discovery';
    const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
    let menu = card.querySelector('.card-menu-dropdown');
    if (!menu) {
        menu = createCardMenu(context, mangaId, source, key, title, coverUrl);
        card.appendChild(menu);
    }
    openCardMenu(menuBtn, menu);
}

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
        const favToggle = e.target.closest('[data-action="source-favorite"]');
        if (favToggle) {
            e.stopPropagation();
            toggleFavoriteSource(favToggle.dataset.source);
            return;
        }
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
        const dataGrid = card.closest('.manga-grid') || gridEl;

        // Handle selection mode
        if (state.selectionMode && gridEl === els.libraryGrid) {
            const checkbox = e.target.closest('.card-checkbox');
            const clickedCard = e.target.closest('.card') && !e.target.closest('.card-menu-btn');

            if (checkbox || clickedCard) {
                e.stopPropagation();
                const key = card.dataset.libraryKey;
                toggleCardSelection(key);
                return;
            }
        }

        const mangaId = card.dataset.mangaId;
        const source = card.dataset.source;
        const titleEl = card.querySelector('.card-title');
        const title = titleEl ? titleEl.textContent : '';
        const coverImg = card.querySelector('.card-cover img');
        const coverUrl = coverImg ? coverImg.src : '';

        // Get manga data from stored array
        const allCards = Array.from(dataGrid.querySelectorAll('.card'));
        const index = allCards.indexOf(card);
        const mangaData = dataGrid._mangaData ? dataGrid._mangaData[index] : null;

        // Handle menu button
        const menuBtn = e.target.closest('.card-menu-btn');
        if (menuBtn) {
            e.stopPropagation();

            // Block menu in selection mode
            if (state.selectionMode && gridEl === els.libraryGrid) {
                return; // Prevent menu from opening in selection mode
            }

            const context = gridEl === els.libraryGrid ? 'library' : 'discovery';
            const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
            const titleText = title;
            const coverUrlText = coverUrl;

            // Create or find existing menu
            // Clean up any stray menus first to prevent DOM accumulation
            let menu = card.querySelector('.card-menu-dropdown');
            if (!menu) {
                // Remove any orphaned menu nodes
                card.querySelectorAll('.card-menu-dropdown').forEach(n => n.remove());
                menu = createCardMenu(context, mangaId, source, key, titleText, coverUrlText);
                card.appendChild(menu);
            }

            openCardMenu(menuBtn, menu);
            return;
        }

        // Handle remove button
        const removeBtn = e.target.closest('.remove-btn');
        if (removeBtn) {
            e.stopPropagation();
            const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
            API.removeFromLibrary(key)
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

        const favoriteBtn = e.target.closest('.favorite-btn');
        if (favoriteBtn) {
            e.stopPropagation();
            const nowFav = toggleFavoriteManga(mangaId, source);
            favoriteBtn.classList.toggle('active', nowFav);
            showToast(nowFav ? 'Added to favorites' : 'Removed from favorites');
            safeCreateIcons();
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

    // Similar grid delegation (in manga details panel)
    if (els.similarGrid) {
        els.similarGrid.addEventListener('click', (e) => handleGridClick(els.similarGrid, e));
    }

    function handlePointerDown(gridEl, e) {
        if (e.pointerType !== 'touch') return;
        const card = e.target.closest('.card');
        if (!card) return;
        if (state.selectionMode && gridEl === els.libraryGrid) return;

        state.touchStart = {
            x: e.clientX,
            y: e.clientY,
            card,
            gridEl
        };
        clearLongPress();
        state.longPressTimer = setTimeout(() => {
            openCardMenuFromCard(card, gridEl);
            state.longPressTimer = null;
        }, 500);
    }

    function handlePointerMove(e) {
        if (!state.touchStart) return;
        const dx = Math.abs(e.clientX - state.touchStart.x);
        const dy = Math.abs(e.clientY - state.touchStart.y);
        if (dx > 12 || dy > 12) {
            clearLongPress();
        }
    }

    function handlePointerUp(e) {
        if (!state.touchStart) return;
        const { card, gridEl, x, y } = state.touchStart;
        clearLongPress();

        const dx = e.clientX - x;
        const dy = e.clientY - y;
        const absX = Math.abs(dx);
        const absY = Math.abs(dy);

        if (absX > 60 && absX > absY) {
            const { mangaId, source, title, coverUrl } = getCardContext(card, gridEl);
            if (dx > 0) {
                if (isInLibrary(mangaId, source)) {
                    showToast('Already in library');
                } else {
                    addToLibrary(mangaId, source, title, coverUrl, 'reading');
                }
            } else {
                const key = card.dataset.libraryKey || getLibraryKey(mangaId, source);
                if (isInLibrary(mangaId, source)) {
                    updateLibraryStatus(key, 'completed');
                } else {
                    showToast('Add to library to track status');
                }
            }
        } else if (absY > 80 && absY > absX && dy > 0 && window.scrollY < 120) {
            showToast('Refreshing...');
            reloadActiveView();
        }

        state.touchStart = null;
    }

    [els.discoverGrid, els.libraryGrid].forEach(gridEl => {
        gridEl.addEventListener('pointerdown', (e) => handlePointerDown(gridEl, e));
        gridEl.addEventListener('pointermove', handlePointerMove, { passive: true });
        gridEl.addEventListener('pointerup', handlePointerUp);
        gridEl.addEventListener('pointercancel', handlePointerUp);
    });

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

    if (els.detailsSourcesList) {
        els.detailsSourcesList.addEventListener('click', (e) => {
            const chip = e.target.closest('.source-chip');
            if (!chip) return;
            const sourceId = chip.dataset.source;
            const mangaId = chip.dataset.mangaId;
            switchMangaSource(sourceId, mangaId);
        });
    }

    if (els.sourceStatusGrid) {
        els.sourceStatusGrid.addEventListener('click', (e) => {
            const actionBtn = e.target.closest('[data-action]');
            if (!actionBtn) return;
            const action = actionBtn.dataset.action;
            const sourceId = actionBtn.dataset.source;
            if (!sourceId) return;
            if (action === 'source-favorite') {
                toggleFavoriteSource(sourceId);
                showSourceStatus();
            } else if (action === 'source-hide') {
                toggleHiddenSource(sourceId);
                showSourceStatus();
            }
        });
    }
}

// ==================== Title Cycling ====================

const titles = [
    'Manga Negus',
    'Manga King',
    'マンガキング'  // Japanese: Manga Kingu
];

// Module-level tracking to prevent memory leaks
let titleCycleInterval = null;
let titleCyclingStarted = false;

function updateTitle() {
    if (!els.appTitle) return;  // Early return BEFORE timeout

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
    if (!els.appTitle || titleCyclingStarted) return;
    titleCyclingStarted = true;

    // Clear any existing interval to prevent memory leaks
    if (titleCycleInterval) {
        clearInterval(titleCycleInterval);
    }

    // Auto-cycle every 30 seconds
    titleCycleInterval = setInterval(cycleTitle, 30000);

    // Manual cycle on click
    els.appTitle.addEventListener('click', cycleTitle);

    // Add accessibility for screen readers
    els.appTitle.setAttribute('aria-live', 'polite');
    els.appTitle.setAttribute('role', 'button');
    els.appTitle.setAttribute('tabindex', '0');
    els.appTitle.setAttribute('aria-label', 'Cycle application title');

    // Keyboard support (Enter or Space to cycle)
    els.appTitle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            cycleTitle();
        }
    });
}

// ==================== Card Menu System ====================

function createCardMenu(context, mangaId, source, key, title, coverUrl) {
    const menu = document.createElement('div');
    menu.className = 'card-menu-dropdown';
    menu.style.display = 'none';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', context === 'library' ? 'Library options' : 'Discovery options');

    const items = context === 'library' ? [
        { action: 'status', icon: 'bookmark', label: 'Change Status' },
        { action: 'mark-read', icon: 'check-circle', label: 'Mark All Read' },
        { action: 'favorite', icon: 'star', label: 'Toggle Favorite' },
        { action: 'download-latest', icon: 'download', label: 'Download Latest' },
        { action: 'select-mode', icon: 'check-square', label: 'Select Multiple' },
        { action: 'share', icon: 'share-2', label: 'Share' },
        { action: 'remove', icon: 'trash', label: 'Delete', danger: true }
    ] : [
        { action: 'add-reading', icon: 'play-circle', label: 'Add to Reading' },
        { action: 'add-library', icon: 'heart', label: 'Add to Library' },
        { action: 'favorite', icon: 'star', label: 'Favorite' },
        { action: 'download-latest', icon: 'download', label: 'Download Latest' },
        { action: 'share', icon: 'share-2', label: 'Share' },
        { action: 'not-interested', icon: 'eye-off', label: 'Not Interested' },
        { action: 'queue-download', icon: 'download', label: 'Queue Download' }
    ];

    menu.innerHTML = items.map(item => `
        <button class="menu-item ${item.danger ? 'danger' : ''}"
                data-action="${item.action}"
                role="menuitem"
                tabindex="-1">
            <i data-lucide="${item.icon}" aria-hidden="true"></i>
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

    // Event delegation: single listener on menu (only add if not already present)
    if (!menu.hasAttribute('data-listeners-attached')) {
        menu.addEventListener('click', (e) => {
            const item = e.target.closest('.menu-item');
            if (item) {
                e.stopPropagation();
                const action = item.dataset.action;
                handleMenuAction(action, menu);
            }
        });
        menu.setAttribute('data-listeners-attached', 'true');
    }

    // Keyboard navigation
    if (!menu.hasAttribute('data-keyboard-attached')) {
        menu.addEventListener('keydown', (e) => {
            const items = Array.from(menu.querySelectorAll('.menu-item'));
            const currentIndex = items.indexOf(document.activeElement);

            switch (e.key) {
                case 'Escape':
                    e.preventDefault();
                    closeAllMenus();
                    button.focus(); // Return focus to menu button
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    const nextIndex = (currentIndex + 1) % items.length;
                    items[nextIndex].focus();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    const prevIndex = currentIndex <= 0 ? items.length - 1 : currentIndex - 1;
                    items[prevIndex].focus();
                    break;
                case 'Home':
                    e.preventDefault();
                    items[0].focus();
                    break;
                case 'End':
                    e.preventDefault();
                    items[items.length - 1].focus();
                    break;
            }
        });
        menu.setAttribute('data-keyboard-attached', 'true');
    }

    // Focus first menu item when opened
    const firstItem = menu.querySelector('.menu-item');
    if (firstItem) {
        setTimeout(() => firstItem.focus(), 50); // Small delay for animation
    }

    // Update button aria-expanded
    button.setAttribute('aria-expanded', 'true');
}

function closeAllMenus() {
    // Reset aria-expanded on all menu buttons
    document.querySelectorAll('.card-menu-btn[aria-expanded="true"]').forEach(btn => {
        btn.setAttribute('aria-expanded', 'false');
    });

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

        case 'add-reading':
            if (isInLibrary(mangaId, source)) {
                showToast('Already in library');
            } else {
                await addToLibrary(mangaId, source, title, coverUrl, 'reading');
            }
            break;

        case 'status':
            showLibraryStatusModal(mangaId, source, title, coverUrl, key);
            break;

        case 'favorite': {
            const nowFav = toggleFavoriteManga(mangaId, source);
            showToast(nowFav ? 'Added to favorites' : 'Removed from favorites');
            renderLibraryFromState();
            break;
        }

        case 'mark-read':
            await markLibraryEntryRead(key);
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
        case 'download-latest':
            await downloadLatestChapter(mangaId, source, title);
            break;
        case 'share':
            await shareManga({ mangaId, source, title });
            break;
        case 'not-interested':
            hideManga(mangaId, source);
            showToast('Hidden from recommendations');
            reloadActiveView();
            break;

        default:
            log(`Unknown menu action: ${action}`);
    }
}

async function shareManga({ mangaId, source, title }) {
    const shareText = `${title || 'Manga'} (${source})`;
    const shareUrl = source === 'jikan' && mangaId
        ? `https://myanimelist.net/manga/${mangaId}`
        : '';
    if (navigator.share) {
        try {
            await navigator.share({ title: title || 'Manga', text: shareText, url: shareUrl || location.href });
            showToast('Shared');
            return;
        } catch {
            // User cancelled
            return;
        }
    }
    try {
        await navigator.clipboard.writeText(shareUrl || shareText);
        showToast('Copied to clipboard');
    } catch (error) {
        showToast('Share unavailable');
        log(`Share failed: ${error.message}`);
    }
}

async function shareCurrentReview() {
    if (!state.currentManga) return;
    const key = getNotesStorageKey(state.currentManga.id, state.currentManga.source);
    let reviewText = '';
    let rating = '';
    try {
        const raw = localStorage.getItem(key);
        const parsed = raw ? JSON.parse(raw) : {};
        reviewText = parsed.review || '';
        rating = parsed.rating ? `${parsed.rating}/10` : '';
    } catch {
        // Ignore
    }
    if (!reviewText && !rating) {
        showToast('Add a review or rating first');
        return;
    }
    const title = state.currentManga.title || 'Manga';
    const shareBody = `${title}\nRating: ${rating || '-'}\n${reviewText}`.trim();
    if (navigator.share) {
        try {
            await navigator.share({ title: `${title} Review`, text: shareBody });
            showToast('Review shared');
            return;
        } catch {
            // fallback to clipboard
        }
    }
    try {
        await navigator.clipboard.writeText(shareBody);
        showToast('Review copied');
    } catch (error) {
        showToast('Share unavailable');
        log(`Review share failed: ${error.message}`);
    }
}

async function removeFromLibraryWithConfirm(key, title) {
    const confirmed = confirm(`Remove "${title}" from library?`);
    if (!confirmed) return;

    try {
        if (!navigator.onLine) {
            state.library = state.library.filter(item => item.key !== key);
            saveCachedLibrary();
            renderLibraryFromState();
            queueOfflineAction({ type: 'remove_library', payload: { key } });
            showToast('Removed offline - will sync later');
            return;
        }
        await API.removeFromLibrary(key);
        showToast('Removed from library');
        await loadLibrary();
    } catch (error) {
        log(`❌ Remove failed: ${error.message}`);
        showToast('Failed to remove');
    }
}

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
    if (els.btnStatusSelected) {
        els.btnStatusSelected.disabled = !hasSelection;
    }
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

    const confirmed = await showConfirmModal(
        'Remove from Library',
        `Remove ${count} manga from your library?`,
        'Remove'
    );
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
    const keys = Array.from(state.selectedCards);
    if (keys.length === 0) {
        showToast('No items selected');
        return;
    }

    const entries = keys.map(key => state.library.find(item => item.key === key)).filter(Boolean);
    if (entries.length === 0) {
        showToast('No valid items found');
        return;
    }

    let queuedCount = 0;
    for (const entry of entries) {
        const mangaId = entry.manga_id || entry.id;
        const source = entry.source;
        const title = entry.title;
        const queued = await queueDownloadPassive(mangaId, source, title, { silent: true, skipQueueRefresh: true });
        if (queued) queuedCount += 1;
    }

    if (queuedCount > 0) {
        showToast(`Added ${queuedCount} manga to passive queue`);
        await fetchDownloadQueue();
        renderDownloadQueue();
        exitSelectionMode();
    } else {
        showToast('No downloads queued');
    }
}

async function queueDownloadPassive(mangaId, source, title, options = {}) {
    const { silent = false, skipQueueRefresh = false } = options;
    if (!mangaId || !source) {
        if (!silent) showToast('Missing manga source or ID');
        return false;
    }

    try {
        log(`📋 Loading chapters for passive queue: ${title}`);
        let chaptersData;

        try {
            chaptersData = await API.getAllChapters(mangaId, source, { silent: true });
        } catch (error) {
            chaptersData = await API.getChapters(mangaId, source, 1, title, null, { silent: true });
        }

        const chapters = chaptersData?.chapters || [];
        if (!chapters.length) {
            if (!silent) showToast('No chapters available');
            return false;
        }

        const chaptersPayload = chapters.map(ch => ({
            id: ch.id,
            chapter: ch.chapter || '0',
            title: ch.title
        }));
        const limit = getDataSaverDownloadLimit();
        const finalPayload = chaptersPayload.slice(0, limit);

        await API.downloadChapters(mangaId, finalPayload, source, title, false);

        if (!silent) {
            const label = finalPayload.length !== chaptersPayload.length
                ? `Queued ${finalPayload.length} chapters (data saver)`
                : 'Added to passive queue';
            showToast(label);
        }
        if (!skipQueueRefresh) {
            await fetchDownloadQueue();
            renderDownloadQueue();
        }
        return true;
    } catch (error) {
        log(`❌ Failed to queue download: ${error.message}`);
        if (!silent) showToast('Failed to queue download');
        return false;
    }
}

// Click outside to close menus
document.addEventListener('click', (e) => {
    if (!e.target.closest('.card-menu-btn') && !e.target.closest('.card-menu-dropdown')) {
        closeAllMenus();
    }
});

async function init() {
    // Initialize DOM elements first
    initElements();

    // Initialize IndexedDB storage (async, handles migration from localStorage)
    try {
        await Storage.init();
        log('📦 IndexedDB storage initialized');
    } catch (error) {
        console.warn('[Storage] IndexedDB init failed, using localStorage fallback:', error);
    }

    // Load search history for suggestions
    loadSearchHistory();
    loadLastRead();
    loadFilters();
    loadFeedCache();
    loadSourcePreferences();
    loadFavoriteManga();
    loadHiddenManga();
    loadPageTotals();
    loadReadingStats();
    loadOfflineQueue();
    applyGridDensity();
    updateFilterButtonState();
    applyDataSaverMode();

    if (els.librarySort) {
        const savedSort = localStorage.getItem('manganegus.librarySort');
        if (savedSort) {
            state.librarySort = savedSort;
            els.librarySort.value = savedSort;
        }
    }
    if (els.librarySmartFilter) {
        const savedSmart = localStorage.getItem('manganegus.librarySmartFilter');
        if (savedSmart) {
            state.smartFilter = savedSmart;
            els.librarySmartFilter.value = savedSmart;
        }
    }
    if (els.libraryCollection) {
        const savedCollection = localStorage.getItem('manganegus.libraryCollection');
        if (savedCollection) {
            state.collectionFilter = savedCollection;
        }
    }

    // Setup event delegation (once, prevents memory leaks)
    setupEventDelegation();
    updateOfflineBanner();
    window.addEventListener('online', () => {
        updateOfflineBanner();
        flushOfflineQueue();
        if (state.cloudSyncEnabled) {
            void cloudSyncNow({ silent: true });
        }
    });
    window.addEventListener('offline', updateOfflineBanner);
    registerServiceWorker();
    window.addEventListener('resize', updateReaderTapZones);

    const savedReaderMode = localStorage.getItem('manganegus.readerMode');
    if (savedReaderMode === 'strip' || savedReaderMode === 'paged' || savedReaderMode === 'webtoon') {
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

    const savedDirection = localStorage.getItem('manganegus.readerDirection');
    if (savedDirection === 'rtl' || savedDirection === 'ltr') {
        state.readerDirection = savedDirection;
    }
    applyReaderDirection();

    const savedBackground = localStorage.getItem('manganegus.readerBackground');
    if (savedBackground && READER_BG_LABELS[savedBackground]) {
        state.readerBackground = savedBackground;
    }
    applyReaderBackground();

    const savedSpread = localStorage.getItem('manganegus.readerSpread');
    state.readerSpread = savedSpread === '1';
    applyReaderSpread();

    const savedEnhance = localStorage.getItem('manganegus.readerEnhance');
    if (savedEnhance) {
        try {
            const parsed = JSON.parse(savedEnhance);
            state.readerEnhance = { ...state.readerEnhance, ...parsed };
        } catch {
            // Ignore
        }
    }
    applyReaderEnhancements();

    const savedPrefetch = parseInt(localStorage.getItem('manganegus.prefetchDistance') || '1', 10);
    if (!Number.isNaN(savedPrefetch)) {
        state.prefetchDistance = savedPrefetch;
    }
    const savedMerge = localStorage.getItem('manganegus.mergeChapters');
    if (savedMerge) {
        state.mergeChapters = savedMerge === 'on';
    }
    const savedAutoDownload = localStorage.getItem('manganegus.autoDownloadFavorites');
    if (savedAutoDownload) {
        state.autoDownloadFavorites = savedAutoDownload === 'on';
    }
    scheduleAutoDownloadChecks();

    // Load saved theme
    const savedTheme = localStorage.getItem('manganegus.theme');
    if (savedTheme && THEMES.includes(savedTheme)) {
        state.theme = savedTheme;
        state.manualTheme = savedTheme;
    }
    const savedThemeSchedule = localStorage.getItem('manganegus.themeSchedule');
    if (savedThemeSchedule) {
        state.themeSchedule = savedThemeSchedule;
    }
    const savedAccent = localStorage.getItem('manganegus.accentColor');
    if (savedAccent) {
        state.accentColor = savedAccent;
        applyAccentColor(savedAccent);
    }
    applyThemeSchedule();

    if (els.themeSchedule) {
        els.themeSchedule.value = state.themeSchedule || 'off';
    }
    if (els.accentColor) {
        els.accentColor.value = state.accentColor || '#dc2626';
    }
    if (els.readerBrightness) els.readerBrightness.value = String(state.readerEnhance.brightness || 100);
    if (els.readerContrast) els.readerContrast.value = String(state.readerEnhance.contrast || 100);
    if (els.readerSharpen) els.readerSharpen.value = String(state.readerEnhance.sharpen || 0);
    if (els.readerCrop) els.readerCrop.value = String(state.readerEnhance.crop || 0);
    if (els.readerPrefetch) els.readerPrefetch.value = String(state.prefetchDistance || 1);
    if (els.mergeChapters) els.mergeChapters.value = state.mergeChapters ? 'on' : 'off';
    if (els.autoDownloadFavorites) els.autoDownloadFavorites.value = state.autoDownloadFavorites ? 'on' : 'off';
    loadCloudSyncSettings();

    log('Initializing MangaNegus...');
    console.log('[DEBUG] Init started');

    // Get CSRF token
    await API.getCsrfToken();
    log('CSRF token obtained');

    // Load sources
    state.sources = await API.getSources();
    console.log('[DEBUG] Sources loaded:', state.sources.length);
    if (state.sources.length > 0) {
        const savedSource = localStorage.getItem('manganegus.currentSource') || '';
        const visibleSources = state.sources.filter(source => !state.hiddenSources.has(source.id));
        const fallbackSource = visibleSources[0]?.id || state.sources[0].id;
        if (savedSource && !state.hiddenSources.has(savedSource)) {
            state.currentSource = savedSource;
        } else {
            state.currentSource = fallbackSource;
        }
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

    // Register service worker for PWA/offline caching
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch((error) => {
            log(`Service worker registration failed: ${error.message}`);
        });
    }

    window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault();
        state.deferredInstallPrompt = event;
    });

    // Load initial content
    loadDiscover();
    handleShareTarget();

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

    if (els.randomBtn) {
        els.randomBtn.addEventListener('click', () => {
            showRandomManga();
        });
    }

    if (els.searchWrapper) {
        els.searchWrapper.addEventListener('click', (e) => {
            if (e.target.closest('button')) return;
            if (document.activeElement !== els.searchInput) {
                els.searchInput.focus();
            }
        });
    }

    if (els.searchSuggestions) {
        const handleSuggestionPick = (e) => {
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
        };
        els.searchSuggestions.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            handleSuggestionPick(e);
        });
        els.searchSuggestions.addEventListener('click', handleSuggestionPick);
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

    // Settings Modal
    if (els.settingsBtn && els.settingsModal) {
        els.settingsBtn.addEventListener('click', () => {
            updateStatsUI();
            els.settingsModal.classList.add('active');
        });
    }
    if (els.closeSettingsModal) {
        els.closeSettingsModal.addEventListener('click', () => {
            els.settingsModal.classList.remove('active');
        });
    }
    if (els.settingsModal) {
        els.settingsModal.addEventListener('click', (e) => {
            if (e.target === els.settingsModal) {
                els.settingsModal.classList.remove('active');
            }
        });
    }
    if (els.exportLibraryBtn) {
        els.exportLibraryBtn.addEventListener('click', handleExportLibrary);
    }
    if (els.importLibraryBtn && els.importLibraryInput) {
        els.importLibraryBtn.addEventListener('click', () => {
            els.importLibraryInput.click();
        });
        els.importLibraryInput.addEventListener('change', () => {
            const file = els.importLibraryInput.files?.[0];
            if (file) {
                handleImportLibrary(file);
            }
            els.importLibraryInput.value = '';
        });
    }
    if (els.backupExportBtn) {
        els.backupExportBtn.addEventListener('click', handleExportBackup);
    }
    if (els.backupImportBtn && els.backupImportInput) {
        els.backupImportBtn.addEventListener('click', () => {
            els.backupImportInput.click();
        });
        els.backupImportInput.addEventListener('change', () => {
            const file = els.backupImportInput.files?.[0];
            if (file) {
                handleImportBackup(file);
            }
            els.backupImportInput.value = '';
        });
    }
    if (els.autoBackupToggle) {
        const savedAutoBackup = localStorage.getItem('manganegus.autoBackup');
        if (savedAutoBackup) {
            state.autoBackupEnabled = savedAutoBackup === 'on';
            els.autoBackupToggle.value = state.autoBackupEnabled ? 'on' : 'off';
        }
        els.autoBackupToggle.addEventListener('change', () => {
            state.autoBackupEnabled = els.autoBackupToggle.value === 'on';
            localStorage.setItem('manganegus.autoBackup', state.autoBackupEnabled ? 'on' : 'off');
            showToast(state.autoBackupEnabled ? 'Auto-backup enabled' : 'Auto-backup disabled');
        });
    }
    if (els.clearCacheBtn) {
        els.clearCacheBtn.addEventListener('click', clearLocalCache);
    }
    if (els.syncPullBtn) {
        els.syncPullBtn.addEventListener('click', async () => {
            try {
                const prefs = await API.getPreferences();
                applyPreferences(prefs);
                showToast('Synced from server');
            } catch (error) {
                showToast('Sync failed');
                log(`Sync pull failed: ${error.message}`);
            }
        });
    }
    if (els.syncPushBtn) {
        els.syncPushBtn.addEventListener('click', async () => {
            try {
                await API.savePreferences(collectPreferences());
                showToast('Synced to server');
            } catch (error) {
                showToast('Sync failed');
                log(`Sync push failed: ${error.message}`);
            }
        });
    }
    if (els.themeSchedule) {
        els.themeSchedule.addEventListener('change', () => {
            setThemeSchedule(els.themeSchedule.value);
        });
    }
    if (els.accentColor) {
        els.accentColor.addEventListener('input', () => {
            setAccentColor(els.accentColor.value);
        });
    }
    if (els.readerBrightness) {
        els.readerBrightness.addEventListener('input', () => {
            setReaderEnhancement('brightness', parseInt(els.readerBrightness.value, 10));
        });
    }
    if (els.readerContrast) {
        els.readerContrast.addEventListener('input', () => {
            setReaderEnhancement('contrast', parseInt(els.readerContrast.value, 10));
        });
    }
    if (els.readerSharpen) {
        els.readerSharpen.addEventListener('input', () => {
            setReaderEnhancement('sharpen', parseInt(els.readerSharpen.value, 10));
        });
    }
    if (els.readerCrop) {
        els.readerCrop.addEventListener('input', () => {
            setReaderEnhancement('crop', parseInt(els.readerCrop.value, 10));
        });
    }
    if (els.readerPrefetch) {
        els.readerPrefetch.addEventListener('change', () => {
            const value = parseInt(els.readerPrefetch.value, 10);
            state.prefetchDistance = Number.isNaN(value) ? 1 : value;
            localStorage.setItem('manganegus.prefetchDistance', String(state.prefetchDistance));
        });
    }
    if (els.mergeChapters) {
        els.mergeChapters.addEventListener('change', () => {
            state.mergeChapters = els.mergeChapters.value === 'on';
            localStorage.setItem('manganegus.mergeChapters', state.mergeChapters ? 'on' : 'off');
            if (state.activeView === 'details') {
                loadChapters(1);
            }
        });
    }
    if (els.autoDownloadFavorites) {
        els.autoDownloadFavorites.addEventListener('change', () => {
            state.autoDownloadFavorites = els.autoDownloadFavorites.value === 'on';
            localStorage.setItem('manganegus.autoDownloadFavorites', state.autoDownloadFavorites ? 'on' : 'off');
            scheduleAutoDownloadChecks();
            if (state.autoDownloadFavorites) {
                void checkFavoritesForUpdates();
            }
        });
    }
    if (els.installBtn) {
        els.installBtn.addEventListener('click', async () => {
            if (!state.deferredInstallPrompt) {
                showToast('Install not available');
                return;
            }
            state.deferredInstallPrompt.prompt();
            await state.deferredInstallPrompt.userChoice;
            state.deferredInstallPrompt = null;
        });
    }
    if (els.cloudSyncToggle) {
        els.cloudSyncToggle.addEventListener('change', () => {
            state.cloudSyncEnabled = els.cloudSyncToggle.value === 'on';
            localStorage.setItem('manganegus.cloudSyncEnabled', state.cloudSyncEnabled ? 'on' : 'off');
            scheduleCloudSync();
            if (state.cloudSyncEnabled) {
                void cloudSyncNow();
            }
        });
    }
    if (els.cloudSyncId) {
        els.cloudSyncId.addEventListener('change', () => {
            const value = els.cloudSyncId.value.trim();
            if (!value) return;
            state.cloudSyncId = value;
            localStorage.setItem('manganegus.cloudSyncId', value);
            showToast('Sync key updated');
        });
    }
    if (els.cloudSyncNow) {
        els.cloudSyncNow.addEventListener('click', () => {
            cloudSyncNow();
        });
    }
    if (els.cloudSyncPull) {
        els.cloudSyncPull.addEventListener('click', () => {
            cloudSyncPull();
        });
    }
    if (els.cloudSyncPush) {
        els.cloudSyncPush.addEventListener('click', () => {
            cloudSyncPush();
        });
    }
    if (els.copyCloudSync) {
        els.copyCloudSync.addEventListener('click', async () => {
            if (!state.cloudSyncId) return;
            try {
                await navigator.clipboard.writeText(state.cloudSyncId);
                showToast('Sync key copied');
            } catch (error) {
                log(`Copy sync key failed: ${error.message}`);
                showToast('Unable to copy');
            }
        });
    }

    // Filter Modal
    if (els.filterBtn) {
        els.filterBtn.addEventListener('click', openFilterModal);
    }
    if (els.closeFilterModal) {
        els.closeFilterModal.addEventListener('click', closeFilterModal);
    }
    if (els.filterApply) {
        els.filterApply.addEventListener('click', applyFiltersFromModal);
    }
    if (els.filterReset) {
        els.filterReset.addEventListener('click', () => {
            resetFilters();
            closeFilterModal();
        });
    }
    if (els.filterModal) {
        els.filterModal.addEventListener('click', (e) => {
            if (e.target === els.filterModal) {
                closeFilterModal();
            }
        });
    }

    // Library Filters
    document.querySelectorAll('.control-btn[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.control-btn[data-filter]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.activeFilter = btn.dataset.filter;
            loadLibrary();
        });
    });
    if (els.librarySort) {
        els.librarySort.addEventListener('change', () => {
            state.librarySort = els.librarySort.value || 'recent';
            localStorage.setItem('manganegus.librarySort', state.librarySort);
            renderLibraryFromState();
        });
    }
    if (els.librarySmartFilter) {
        els.librarySmartFilter.addEventListener('change', () => {
            state.smartFilter = els.librarySmartFilter.value || '';
            localStorage.setItem('manganegus.librarySmartFilter', state.smartFilter);
            renderLibraryFromState();
        });
    }
    if (els.libraryCollection) {
        els.libraryCollection.addEventListener('change', () => {
            state.collectionFilter = (els.libraryCollection.value || '').toLowerCase();
            localStorage.setItem('manganegus.libraryCollection', state.collectionFilter);
            renderLibraryFromState();
        });
    }
    if (els.historyExportBtn) {
        els.historyExportBtn.addEventListener('click', exportHistoryCsv);
    }

    // Selection mode handlers
    if (els.btnStatusSelected) {
        els.btnStatusSelected.addEventListener('click', () => {
            const keys = Array.from(state.selectedCards);
            if (keys.length === 0) {
                showToast('No items selected');
                return;
            }
            showLibraryStatusModal(null, null, null, null, null, keys);
        });
    }
    els.btnDeleteSelected.addEventListener('click', deleteSelected);
    els.btnDownloadSelected.addEventListener('click', downloadSelected);
    els.btnCancelSelection.addEventListener('click', exitSelectionMode);

    // Details View
    els.backBtn.addEventListener('click', () => {
        // Go back to the view we came from (discover, trending, popular, library, history)
        setView(state.previousView || 'discover');
    });

    if (els.favoriteBtn) {
        els.favoriteBtn.addEventListener('click', () => {
            if (!state.currentManga) return;
            const nowFav = toggleFavoriteManga(state.currentManga.id, state.currentManga.source);
            updateFavoriteButton();
            showToast(nowFav ? 'Added to favorites' : 'Removed from favorites');
        });
    }

    // Debounce scroll event to reduce performance impact (300ms)
    window.addEventListener('scroll', debounce(handleInfiniteScroll, 300), { passive: true });

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
    if (els.markAllReadBtn) {
        els.markAllReadBtn.addEventListener('click', markAllRead);
    }
    if (els.notesInput) {
        els.notesInput.addEventListener('input', scheduleNotesSave);
    }
    if (els.reviewInput) {
        els.reviewInput.addEventListener('input', scheduleNotesSave);
    }
    if (els.shareReviewBtn) {
        els.shareReviewBtn.addEventListener('click', shareCurrentReview);
    }
    if (els.ratingInput) {
        els.ratingInput.addEventListener('input', () => {
            els.ratingValue.textContent = els.ratingInput.value || '-';
            scheduleNotesSave();
        });
    }
    if (els.collectionsInput) {
        els.collectionsInput.addEventListener('input', scheduleNotesSave);
    }

    els.selectAllChaptersBtn.addEventListener('click', selectAllChapters);
    els.deselectAllChaptersBtn.addEventListener('click', deselectAllChapters);
    els.downloadSelectedBtn.addEventListener('click', downloadSelectedChapters);
    if (els.downloadNextBtn) {
        els.downloadNextBtn.addEventListener('click', () => downloadNextChapters(5));
    }
    if (els.downloadNextChaptersBtn) {
        els.downloadNextChaptersBtn.addEventListener('click', () => downloadNextChapters(5));
    }
    if (els.chapterLanguage) {
        els.chapterLanguage.addEventListener('change', () => {
            state.chapterFilters.language = els.chapterLanguage.value || '';
            renderChapters();
        });
    }
    if (els.chapterGroup) {
        els.chapterGroup.addEventListener('change', () => {
            state.chapterFilters.group = els.chapterGroup.value || '';
            renderChapters();
        });
    }
    if (els.chapterTranslation) {
        els.chapterTranslation.addEventListener('change', () => {
            state.chapterFilters.translation = els.chapterTranslation.value || '';
            renderChapters();
        });
    }

    // Reader
    els.closeReaderBtn.addEventListener('click', closeReader);
    els.prevPageBtn.addEventListener('click', () => {
        moveReader('prev');
    });
    els.nextPageBtn.addEventListener('click', () => {
        moveReader('next');
    });
    if (els.readerTapZones) {
        els.readerTapZones.addEventListener('click', (e) => {
            const zone = e.target.closest('.tap-zone')?.dataset.zone;
            if (!zone) return;
            if (zone === 'menu') {
                toggleReaderImmersive();
            } else {
                moveReader(zone);
            }
        });
    }
    document.addEventListener('keydown', handleReaderKeydown);
    if (els.readerModeBtn) {
        els.readerModeBtn.addEventListener('click', toggleReaderMode);
    }
    if (els.readerImmersiveBtn) {
        els.readerImmersiveBtn.addEventListener('click', toggleReaderImmersive);
    }
    els.readerContent.addEventListener('click', handleReaderTap);
    els.readerContent.addEventListener('pointerdown', handleReaderPointerDown);
    els.readerContent.addEventListener('pointermove', handleReaderPointerMove, { passive: true });
    els.readerContent.addEventListener('pointerup', handleReaderPointerUp);
    els.readerContent.addEventListener('pointercancel', handleReaderPointerUp);
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

        // Direction buttons
        els.readerSettingsMenu.querySelectorAll('[data-direction]').forEach(btn => {
            btn.addEventListener('click', () => {
                const direction = btn.dataset.direction;
                setReaderDirection(direction);
                els.readerSettingsMenu.classList.remove('active');
            });
        });

        // Background buttons
        els.readerSettingsMenu.querySelectorAll('[data-bg]').forEach(btn => {
            btn.addEventListener('click', () => {
                const bg = btn.dataset.bg;
                setReaderBackground(bg);
                els.readerSettingsMenu.classList.remove('active');
            });
        });

        // Spread toggle
        const spreadBtn = els.readerSettingsMenu.querySelector('[data-spread="toggle"]');
        if (spreadBtn) {
            spreadBtn.addEventListener('click', () => {
                toggleReaderSpread();
                els.readerSettingsMenu.classList.remove('active');
            });
        }

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.reader-settings-dropdown')) {
                els.readerSettingsMenu.classList.remove('active');
            }
        });
    }

    // Keyboard navigation for reader
    document.addEventListener('keydown', handleKeyboardNavigation);
    document.addEventListener('fullscreenchange', () => {
        if (document.fullscreenElement) {
            closeSidebar();
        }
    });
    document.addEventListener('webkitfullscreenchange', () => {
        if (document.webkitFullscreenElement) {
            closeSidebar();
        }
    });

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

    // Start title cycling
    startTitleCycling();

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
