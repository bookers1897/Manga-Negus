const els = {
    backBtn: document.getElementById('reader-back-btn'),
    topbar: document.querySelector('.reader-topbar'),
    mangaTitle: document.getElementById('reader-manga-title'),
    chapterTitle: document.getElementById('reader-chapter-title'),
    prevBtn: document.getElementById('reader-prev-btn'),
    nextBtn: document.getElementById('reader-next-btn'),
    pageIndicator: document.getElementById('reader-page-indicator'),
    pages: document.getElementById('reader-pages'),
    loading: document.getElementById('reader-loading'),
    settings: document.getElementById('reader-settings'),
    settingsClose: document.getElementById('reader-settings-close'),
    settingsToggle: document.getElementById('reader-settings-toggle'),
    spreadToggle: document.getElementById('reader-spread-toggle')
};

const state = {
    chapterId: '',
    source: '',
    mangaId: '',
    mangaTitle: '',
    chapterName: '',
    chapterNumber: null,
    totalChapters: null,
    libraryKey: '',
    cover: '',
    mangaType: '',
    mangaTags: [],
    pages: [],
    currentPage: 0,
    startPage: 0,
    readerMode: 'strip',
    readerFit: 'fit-width',
    readerDirection: 'ltr',
    readerBackground: 'dark',
    readerSpread: false,
    spreadPages: new Set(),
    readerObserver: null,
    progressTimer: null,
    csrfToken: null,
    dataSaver: false,
    prefetchDistance: 1,
    chapterList: [],
    chapterIndex: -1,
    sessionStart: Date.now(),
    sessionStartPage: 0,
    settingsOpen: false,
    controlsVisible: true,
    controlsTimer: null,
    renderGeneration: 0,
    initialScrollDone: false,
    isNavigating: false,
    virtualEnabled: false,
    virtualStart: 0,
    virtualEnd: -1,
    virtualHeights: [],
    virtualAvgHeight: 0,
    virtualNodes: new Map(),
    virtualTopSpacer: null,
    virtualBottomSpacer: null,
    virtualContainer: null,
    virtualScrollRaf: null,
    virtualGap: 20,
    // Prefetch state
    prefetchedUrls: new Set(),
    prefetchQueue: [],
    prefetchInProgress: false,
    nextChapterPrefetched: false,
    nextChapterPages: null
};

function inferContentProfile() {
    const type = state.mangaType || '';
    const tags = new Set(state.mangaTags || []);
    const isWebtoon = type.includes('webtoon')
        || type.includes('manhwa')
        || type.includes('manhua')
        || tags.has('webtoon')
        || tags.has('long strip')
        || tags.has('vertical');
    return {
        isWebtoon,
        defaultMode: isWebtoon ? 'webtoon' : 'strip',
        defaultDirection: isWebtoon ? 'ltr' : 'rtl',
        defaultFit: isWebtoon ? 'fit-width' : 'fit-height'
    };
}

function getPrefetchAhead() {
    if (state.dataSaver) return 0;
    const distance = Math.max(0, state.prefetchDistance || 1);
    if (distance === 0) return 0;
    if (distance === 1) return 5;
    if (distance === 2) return 8;
    return 12;
}

function getNextChapterPrefetchCount() {
    if (state.dataSaver) return 1;
    const distance = Math.max(0, state.prefetchDistance || 1);
    if (distance <= 1) return 3;
    if (distance === 2) return 5;
    return 8;
}

// ========================================
// Prefetcher - Preload pages ahead for smooth reading
// ========================================
const Prefetcher = {
    // When to trigger chapter prefetch (percentage of current chapter)
    CHAPTER_PREFETCH_THRESHOLD: 0.8,
    // IndexedDB for image caching
    DB_NAME: 'manganegus-reader-cache',
    DB_STORE: 'images',
    db: null,

    /**
     * Initialize IndexedDB for image caching
     */
    async initDB() {
        if (this.db) return;
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.DB_NAME, 1);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(this.DB_STORE)) {
                    const store = db.createObjectStore(this.DB_STORE, { keyPath: 'url' });
                    store.createIndex('timestamp', 'timestamp');
                }
            };
        });
    },

    /**
     * Get cached image from IndexedDB
     */
    async getCached(url) {
        if (!this.db) return null;
        return new Promise((resolve) => {
            try {
                const tx = this.db.transaction(this.DB_STORE, 'readonly');
                const store = tx.objectStore(this.DB_STORE);
                const request = store.get(url);
                request.onsuccess = () => resolve(request.result?.blob || null);
                request.onerror = () => resolve(null);
            } catch {
                resolve(null);
            }
        });
    },

    /**
     * Cache image in IndexedDB
     */
    async cacheImage(url, blob) {
        if (!this.db) return;
        try {
            const tx = this.db.transaction(this.DB_STORE, 'readwrite');
            const store = tx.objectStore(this.DB_STORE);
            store.put({
                url,
                blob,
                timestamp: Date.now()
            });
        } catch (e) {
            console.warn('[Prefetcher] Failed to cache image:', e);
        }
    },

    /**
     * Clean up old cached images (older than 7 days)
     */
    async cleanup() {
        if (!this.db) return;
        const sevenDaysAgo = Date.now() - (7 * 24 * 60 * 60 * 1000);
        try {
            const tx = this.db.transaction(this.DB_STORE, 'readwrite');
            const store = tx.objectStore(this.DB_STORE);
            const index = store.index('timestamp');
            const range = IDBKeyRange.upperBound(sevenDaysAgo);
            const request = index.openCursor(range);
            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor) {
                    store.delete(cursor.primaryKey);
                    cursor.continue();
                }
            };
        } catch (e) {
            console.warn('[Prefetcher] Cleanup failed:', e);
        }
    },

    /**
     * Prefetch a single image by URL
     */
    async prefetchImage(url, referer = null) {
        if (state.prefetchedUrls.has(url)) return;
        state.prefetchedUrls.add(url);

        try {
            // Check cache first
            const cached = await this.getCached(url);
            if (cached) return;

            // Build proxy URL to avoid CORS and use rate limiting
            const page = referer ? { url, referer } : url;
            const proxyUrl = buildProxyUrl(page);

            // Use low priority for prefetch requests
            const response = await fetch(proxyUrl, {
                priority: 'low'
            });

            if (response.ok) {
                const blob = await response.blob();
                // Cache using original URL as key for consistency
                await this.cacheImage(url, blob);
            }
        } catch (e) {
            // Silent fail for prefetch
            console.debug('[Prefetcher] Failed to prefetch:', url);
        }
    },

    /**
     * Prefetch pages ahead of current page
     */
    prefetchPagesAhead(currentIndex, pages) {
        if (!pages || !pages.length) return;
        const ahead = getPrefetchAhead();
        if (!ahead) return;
        const endIndex = Math.min(currentIndex + ahead, pages.length - 1);

        for (let i = currentIndex + 1; i <= endIndex; i++) {
            const page = pages[i];
            if (page) {
                const url = typeof page === 'string' ? page : page.url;
                const referer = typeof page === 'object' ? page.referer : null;
                if (url) {
                    // Use setTimeout to not block the main thread
                    setTimeout(() => this.prefetchImage(url, referer), (i - currentIndex) * 50);
                }
            }
        }
    },

    /**
     * Check if we should prefetch the next chapter
     */
    shouldPrefetchNextChapter(currentIndex, totalPages) {
        if (state.nextChapterPrefetched) return false;
        if (totalPages === 0) return false;
        const progress = (currentIndex + 1) / totalPages;
        return progress >= this.CHAPTER_PREFETCH_THRESHOLD;
    },

    /**
     * Prefetch next chapter's first few pages
     */
    async prefetchNextChapter() {
        if (state.nextChapterPrefetched) return;
        if (state.chapterList.length === 0) return;

        const order = inferChapterOrder(state.chapterList);
        const delta = order === 'desc' ? -1 : 1;
        const nextIndex = state.chapterIndex + delta;

        if (nextIndex < 0 || nextIndex >= state.chapterList.length) return;

        const nextChapter = state.chapterList[nextIndex];
        if (!nextChapter) return;

        state.nextChapterPrefetched = true;
        console.log('[Prefetcher] Prefetching next chapter:', nextChapter.id);

        try {
            // Fetch next chapter's pages
            const response = await apiRequest('/api/chapter_pages', {
                method: 'POST',
                body: JSON.stringify({
                    chapter_id: nextChapter.id,
                    source: state.source
                })
            });

            const pages = response?.pages_data || response?.pages || [];
            state.nextChapterPages = pages;

            const count = Math.min(getNextChapterPrefetchCount(), pages.length);
            for (let i = 0; i < count; i++) {
                const page = pages[i];
                const url = typeof page === 'string' ? page : page.url;
                const referer = typeof page === 'object' ? page.referer : null;
                if (url) {
                    this.prefetchImage(url, referer);
                }
            }
        } catch (e) {
            console.debug('[Prefetcher] Failed to prefetch next chapter:', e);
            state.nextChapterPrefetched = false;
        }
    },

    /**
     * Called when page changes - triggers appropriate prefetching
     */
    onPageChange(currentIndex, pages) {
        // Prefetch pages ahead
        this.prefetchPagesAhead(currentIndex, pages);

        // Check if we should prefetch next chapter
        if (this.shouldPrefetchNextChapter(currentIndex, pages.length)) {
            this.prefetchNextChapter();
        }
    }
};

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function parseParams() {
    const params = new URLSearchParams(window.location.search);
    state.chapterId = params.get('chapter_id') || '';
    state.source = params.get('source') || '';
    state.mangaId = params.get('manga_id') || '';
    state.mangaTitle = params.get('manga_title') || 'Manga';
    state.chapterName = params.get('chapter_title') || 'Chapter';
    state.cover = params.get('cover') || '';
    state.libraryKey = params.get('library_key') || '';
    state.mangaType = (params.get('manga_type') || '').toLowerCase();
    const rawTags = params.get('manga_tags') || '';
    state.mangaTags = rawTags
        ? rawTags.split(',').map(tag => tag.trim().toLowerCase()).filter(Boolean)
        : [];
    state.startPage = parseInt(params.get('start_page') || '0', 10);
    state.chapterNumber = params.get('chapter_number');
    if (state.chapterNumber !== null) {
        const num = parseFloat(state.chapterNumber);
        state.chapterNumber = Number.isNaN(num) ? state.chapterNumber : num;
    }
    const total = parseInt(params.get('total_chapters') || '', 10);
    state.totalChapters = Number.isNaN(total) ? null : total;
}

function loadReaderPreferences() {
    let userPrefs = null;
    try {
        const rawPrefs = localStorage.getItem('userPreferences');
        if (rawPrefs) {
            userPrefs = JSON.parse(rawPrefs);
        }
    } catch {
        userPrefs = null;
    }

    const modePref = localStorage.getItem('manganegus.readerMode');
    const fitPref = localStorage.getItem('manganegus.readerFitMode');
    const directionPref = localStorage.getItem('manganegus.readerDirection');
    const backgroundPref = localStorage.getItem('manganegus.readerBackground');
    const spreadPref = localStorage.getItem('manganegus.readerSpread');

    if (modePref && ['strip', 'paged', 'webtoon'].includes(modePref)) {
        state.readerMode = modePref;
    } else if (userPrefs?.defaultReaderMode && ['strip', 'paged', 'webtoon'].includes(userPrefs.defaultReaderMode)) {
        state.readerMode = userPrefs.defaultReaderMode;
    }

    if (fitPref && ['fit-width', 'fit-height', 'fit-screen', 'fit-original'].includes(fitPref)) {
        state.readerFit = fitPref;
    } else if (userPrefs?.imageFit && ['fit-width', 'fit-height', 'fit-screen', 'fit-original'].includes(userPrefs.imageFit)) {
        state.readerFit = userPrefs.imageFit;
    }

    if (directionPref && (directionPref === 'rtl' || directionPref === 'ltr')) {
        state.readerDirection = directionPref;
    } else if (userPrefs?.readingDirection && (userPrefs.readingDirection === 'rtl' || userPrefs.readingDirection === 'ltr')) {
        state.readerDirection = userPrefs.readingDirection;
    }

    if (backgroundPref && ['dark', 'light', 'sepia', 'black', 'white'].includes(backgroundPref)) {
        state.readerBackground = backgroundPref;
    }
    state.readerSpread = spreadPref === '1';

    const savedPrefetch = parseInt(localStorage.getItem('manganegus.prefetchDistance') || '1', 10);
    if (!Number.isNaN(savedPrefetch)) {
        state.prefetchDistance = savedPrefetch;
    }

    try {
        const raw = localStorage.getItem('manganegus.filters');
        if (raw) {
            const parsed = JSON.parse(raw);
            state.dataSaver = !!parsed.dataSaver;
        }
    } catch {
        state.dataSaver = false;
    }

    const hasModePref = Boolean(modePref || userPrefs?.defaultReaderMode);
    const hasFitPref = Boolean(fitPref || userPrefs?.imageFit);
    const hasDirectionPref = Boolean(directionPref || userPrefs?.readingDirection);

    const contentProfile = inferContentProfile();
    if (!hasModePref && contentProfile.defaultMode) {
        state.readerMode = contentProfile.defaultMode;
    }
    if (!hasFitPref && contentProfile.defaultFit) {
        state.readerFit = contentProfile.defaultFit;
    }
    if (!hasDirectionPref && contentProfile.defaultDirection) {
        state.readerDirection = contentProfile.defaultDirection;
    }
}

function applySettings() {
    document.body.dataset.readerMode = state.readerMode;
    document.body.dataset.readerFit = state.readerFit;
    document.body.dataset.readerBg = state.readerBackground;
    document.body.dataset.readerDirection = state.readerDirection;
    updateSettingsUI();
}

function isMobileView() {
    return window.innerWidth <= 960;
}

function updateLayoutMetrics() {
    document.documentElement.style.setProperty('--reader-vh', `${window.innerHeight}px`);
    if (els.topbar) {
        document.documentElement.style.setProperty('--reader-topbar-height', `${els.topbar.offsetHeight}px`);
    }
}

function scheduleControlsHide() {
    if (state.controlsTimer) {
        clearTimeout(state.controlsTimer);
        state.controlsTimer = null;
    }
    if (!isMobileView() || state.settingsOpen) return;
    state.controlsTimer = setTimeout(() => {
        setControlsVisible(false);
    }, 2600);
}

function setControlsVisible(visible, { persist = false } = {}) {
    state.controlsVisible = visible;
    document.body.classList.toggle('controls-hidden', !visible);
    if (visible) {
        if (!persist) {
            scheduleControlsHide();
        }
    } else if (state.controlsTimer) {
        clearTimeout(state.controlsTimer);
        state.controlsTimer = null;
    }
}

function syncControlsForViewport() {
    if (isMobileView()) {
        setControlsVisible(false, { persist: true });
    } else {
        setControlsVisible(true, { persist: true });
    }
}

function updateSettingsUI() {
    document.querySelectorAll('.settings-options').forEach(group => {
        const setting = group.dataset.setting;
        let value = '';
        if (setting === 'mode') value = state.readerMode;
        if (setting === 'fit') value = state.readerFit;
        if (setting === 'direction') value = state.readerDirection;
        if (setting === 'background') value = state.readerBackground;
        group.querySelectorAll('button[data-value]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.value === value);
        });
    });
    if (els.spreadToggle) {
        els.spreadToggle.checked = state.readerSpread;
    }
}

function setReaderMode(mode) {
    if (!['strip', 'paged', 'webtoon'].includes(mode)) return;
    state.readerMode = mode;
    localStorage.setItem('manganegus.readerMode', mode);
    applySettings();
    if (state.pages.length) {
        void renderPages();
        return;
    }
    updatePageVisibility({ scroll: true });
    setupReaderObserver();
}

function setReaderFit(mode) {
    if (!['fit-width', 'fit-height', 'fit-screen', 'fit-original'].includes(mode)) return;
    state.readerFit = mode;
    localStorage.setItem('manganegus.readerFitMode', mode);
    applySettings();
}

function setReaderDirection(direction) {
    state.readerDirection = direction === 'rtl' ? 'rtl' : 'ltr';
    localStorage.setItem('manganegus.readerDirection', state.readerDirection);
    applySettings();
}

function setReaderBackground(bg) {
    if (!['dark', 'light', 'sepia', 'black', 'white'].includes(bg)) return;
    state.readerBackground = bg;
    localStorage.setItem('manganegus.readerBackground', bg);
    applySettings();
}

function setReaderSpread(enabled) {
    state.readerSpread = !!enabled;
    localStorage.setItem('manganegus.readerSpread', state.readerSpread ? '1' : '0');
    if (state.readerMode === 'paged') {
        renderPagedWindow(state.currentPage);
    }
    updatePageVisibility({ scroll: true });
    updateSettingsUI();
}

async function apiRequest(endpoint, options = {}) {
    const MAX_RETRIES = 3;
    let rateLimitAttempt = 0;

    const headers = {
        ...(options.headers || {})
    };
    if (options.method === 'POST' && state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    if (options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    while (true) {
        const response = await fetch(endpoint, {
            ...options,
            headers
        });

        // Handle rate limiting with silent retry (consistent with main.js)
        if (response.status === 429) {
            if (rateLimitAttempt >= MAX_RETRIES) {
                console.warn(`[Reader] Rate limit exceeded after ${MAX_RETRIES} retries: ${endpoint}`);
                throw new Error('Rate limit exceeded. Please wait a moment and try again.');
            }
            const retryAfter = parseInt(response.headers.get('Retry-After')) || 60;
            const delay = Math.min(retryAfter * 1000 * (0.5 + Math.random()), 120000);
            console.log(`[Reader] Rate limited, retrying in ${Math.round(delay / 1000)}s`);
            await new Promise(r => setTimeout(r, delay));
            rateLimitAttempt++;
            continue;
        }

        const contentType = response.headers.get('content-type') || '';
        const isJson = contentType.includes('application/json');
        const data = isJson ? await response.json() : null;
        if (!response.ok) {
            const message = data?.error || data?.message || `HTTP ${response.status}: ${response.statusText}`;
            throw new Error(message);
        }
        return data;
    }
}

async function ensureCsrfToken() {
    if (state.csrfToken) return state.csrfToken;
    const data = await apiRequest('/api/csrf-token');
    state.csrfToken = data?.csrf_token || null;
    return state.csrfToken;
}

async function getChapterPages() {
    await ensureCsrfToken();
    const data = await apiRequest('/api/chapter_pages', {
        method: 'POST',
        body: JSON.stringify({
            chapter_id: state.chapterId,
            source: state.source
        })
    });
    return data?.pages_data || data?.pages || [];
}

async function getAllChapters() {
    if (!state.mangaId || !state.source) return null;
    await ensureCsrfToken();
    const data = await apiRequest('/api/all_chapters', {
        method: 'POST',
        body: JSON.stringify({
            id: state.mangaId,
            source: state.source
        })
    });
    return data;
}

function buildProxyUrl(page) {
    const pageUrl = typeof page === 'string' ? page : page.url;
    const referer = typeof page === 'object'
        ? (page.referer || page.headers?.Referer || page.headers?.referer || '')
        : '';
    const optimizeParams = state.dataSaver ? '&format=webp&quality=55' : '&format=webp&quality=85';
    const base = `/api/proxy/image?url=${encodeURIComponent(pageUrl)}`;
    if (referer) {
        return `${base}&referer=${encodeURIComponent(referer)}${optimizeParams}`;
    }
    return `${base}${optimizeParams}`;
}

function showLoading(show) {
    if (!els.loading) return;
    els.loading.classList.toggle('hidden', !show);
}

function showError(message) {
    if (!els.pages) return;
    els.pages.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'loading-state';
    const text = document.createElement('span');
    text.textContent = message;
    wrapper.appendChild(text);
    els.pages.appendChild(wrapper);
}

const VIRTUAL_MIN_BUFFER = 10;
const VIRTUAL_MAX_BUFFER = 30;

function getPageGap() {
    return state.readerMode === 'webtoon' ? 12 : 20;
}

function estimateAverageHeight() {
    const width = els.pages?.clientWidth || window.innerWidth;
    const ratio = state.readerMode === 'webtoon' ? 1.4 : 1.25;
    return Math.max(360, Math.round(width * ratio)) + state.virtualGap;
}

function resetVirtualState() {
    state.virtualEnabled = false;
    state.virtualStart = 0;
    state.virtualEnd = -1;
    state.virtualHeights = [];
    state.virtualAvgHeight = 0;
    state.virtualNodes = new Map();
    state.virtualTopSpacer = null;
    state.virtualBottomSpacer = null;
    state.virtualContainer = null;
    state.virtualScrollRaf = null;
}

function getVirtualBuffer() {
    const viewport = els.pages?.clientHeight || window.innerHeight;
    const visible = Math.ceil(viewport / Math.max(1, state.virtualAvgHeight));
    return Math.min(VIRTUAL_MAX_BUFFER, Math.max(VIRTUAL_MIN_BUFFER, visible + 2));
}

function getEstimatedHeight(index) {
    return state.virtualHeights[index] || state.virtualAvgHeight;
}

function calculateHeightRange(start, end) {
    let total = 0;
    for (let i = start; i < end; i += 1) {
        total += getEstimatedHeight(i);
    }
    return total;
}

function updateVirtualAverage() {
    const known = state.virtualHeights.filter(height => height > 0);
    if (!known.length) return;
    const sum = known.reduce((acc, height) => acc + height, 0);
    state.virtualAvgHeight = Math.max(300, Math.round(sum / known.length));
}

function updateVirtualSpacers() {
    if (!state.virtualTopSpacer || !state.virtualBottomSpacer) return;
    const total = state.pages.length;
    const topHeight = calculateHeightRange(0, state.virtualStart);
    const bottomHeight = calculateHeightRange(state.virtualEnd + 1, total);
    state.virtualTopSpacer.style.height = `${topHeight}px`;
    state.virtualBottomSpacer.style.height = `${bottomHeight}px`;
}

function ensureVirtualElements() {
    if (state.virtualTopSpacer && state.virtualBottomSpacer && state.virtualContainer) return;
    const top = document.createElement('div');
    top.className = 'reader-spacer';
    const container = document.createElement('div');
    container.className = 'reader-window';
    const bottom = document.createElement('div');
    bottom.className = 'reader-spacer';
    els.pages.append(top, container, bottom);
    state.virtualTopSpacer = top;
    state.virtualContainer = container;
    state.virtualBottomSpacer = bottom;
}

function getPageNode(index) {
    let node = state.virtualNodes.get(index);
    if (node) return node;
    const page = state.pages[index];
    node = document.createElement('img');
    node.className = 'reader-page';
    node.dataset.pageIndex = String(index);
    const pageUrl = typeof page === 'string' ? page : page.url;
    const isPriority = index === state.currentPage || index === state.currentPage + 1;
    node.loading = isPriority ? 'eager' : 'lazy';
    node.fetchPriority = isPriority ? 'high' : 'low';
    node.decoding = 'async';
    node.alt = `Page ${index + 1}`;
    const proxyUrl = buildProxyUrl(page);
    node.dataset.proxySrc = proxyUrl;
    let srcAssigned = false;
    const assignSrc = (src, isBlob = false) => {
        if (srcAssigned) return;
        srcAssigned = true;
        node.src = src;
        if (isBlob) {
            node.dataset.blobUrl = src;
        }
    };
    if (pageUrl) {
        Prefetcher.getCached(pageUrl).then(blob => {
            if (!blob) return;
            const blobUrl = URL.createObjectURL(blob);
            assignSrc(blobUrl, true);
        });
    }
    setTimeout(() => {
        if (!srcAssigned) assignSrc(proxyUrl);
    }, 60);
    node.addEventListener('load', () => {
        node.classList.add('loaded');
        const blobUrl = node.dataset.blobUrl;
        if (blobUrl) {
            URL.revokeObjectURL(blobUrl);
            delete node.dataset.blobUrl;
        }
        if (!node.naturalWidth || !node.naturalHeight) return;
        const ratio = node.naturalWidth / node.naturalHeight;
        if (ratio > 1.25) {
            state.spreadPages.add(index);
        } else {
            state.spreadPages.delete(index);
        }
        const measured = Math.round(node.getBoundingClientRect().height) + state.virtualGap;
        if (measured > 0) {
            state.virtualHeights[index] = measured;
            updateVirtualAverage();
            if (state.virtualEnabled) {
                updateVirtualSpacers();
            }
            if (state.readerMode === 'paged' && state.readerSpread) {
                updatePageVisibility({ scroll: false, behavior: 'auto' });
            }
        }
    }, { once: true });
    node.addEventListener('error', () => {
        const retryCount = parseInt(node.dataset.retryCount || '0', 10);
        const maxRetries = 2;

        if (retryCount < maxRetries) {
            // Auto-retry with exponential backoff
            node.dataset.retryCount = String(retryCount + 1);
            const delay = 500 * Math.pow(2, retryCount); // 500ms, 1000ms
            setTimeout(() => {
                node.classList.remove('load-error');
                if (node.dataset.proxySrc) {
                    node.src = node.dataset.proxySrc + '&retry=' + (retryCount + 1) + '&t=' + Date.now();
                }
            }, delay);
        } else {
            // Max retries exhausted - show tap-to-retry
            node.classList.add('load-error');
            node.alt = `Page ${index + 1} failed - tap to retry`;
            node.style.cursor = 'pointer';
            node.style.minHeight = '200px';
            node.onclick = () => {
                node.classList.remove('load-error');
                node.style.cursor = '';
                node.dataset.retryCount = '0';
                node.onclick = null;
                if (node.dataset.proxySrc) {
                    node.src = node.dataset.proxySrc + '&force=' + Date.now();
                }
            };
        }
    });
    state.virtualNodes.set(index, node);
    return node;
}

function renderVirtualWindow(startIndex, endIndex) {
    const total = state.pages.length;
    if (!total) return;
    const start = clamp(startIndex, 0, total - 1);
    const end = clamp(endIndex, 0, total - 1);
    if (start > end) return;
    if (state.virtualStart === start && state.virtualEnd === end) return;
    state.virtualStart = start;
    state.virtualEnd = end;
    updateVirtualSpacers();
    const fragment = document.createDocumentFragment();
    for (let i = start; i <= end; i += 1) {
        fragment.appendChild(getPageNode(i));
    }
    if (state.virtualContainer) {
        state.virtualContainer.replaceChildren(fragment);
    }
    setupReaderObserver();
}

function updateVirtualWindowForIndex(index) {
    if (!state.virtualEnabled) return;
    const total = state.pages.length;
    if (!total) return;
    const buffer = getVirtualBuffer();
    const start = clamp(index - buffer, 0, total - 1);
    const end = clamp(index + buffer, 0, total - 1);
    renderVirtualWindow(start, end);
}

function renderPagedWindow(index) {
    const total = state.pages.length;
    if (!total) return;
    const buffer = state.readerSpread ? 3 : 2;
    const start = clamp(index - buffer, 0, total - 1);
    const end = clamp(index + buffer, 0, total - 1);
    if (state.virtualStart === start && state.virtualEnd === end) return;
    state.virtualStart = start;
    state.virtualEnd = end;
    const fragment = document.createDocumentFragment();
    for (let i = start; i <= end; i += 1) {
        fragment.appendChild(getPageNode(i));
    }
    els.pages.replaceChildren(fragment);
    setupReaderObserver();
}

function handleVirtualScroll() {
    if (!state.virtualEnabled || state.readerMode === 'paged') return;
    if (state.virtualScrollRaf) return;
    state.virtualScrollRaf = requestAnimationFrame(() => {
        state.virtualScrollRaf = null;
        const scrollTop = els.pages.scrollTop;
        const estimatedIndex = Math.floor(scrollTop / Math.max(1, state.virtualAvgHeight));
        updateVirtualWindowForIndex(clamp(estimatedIndex, 0, state.pages.length - 1));
    });
}

async function renderPages() {
    if (!els.pages) return;
    state.renderGeneration += 1;
    state.initialScrollDone = false;
    clearReaderObserver();
    resetVirtualState();
    els.pages.innerHTML = '';
    state.spreadPages.clear();

    const total = state.pages.length;
    state.currentPage = clamp(state.startPage, 0, Math.max(0, total - 1));
    state.sessionStartPage = state.currentPage;
    updatePageIndicator();

    state.virtualGap = getPageGap();
    state.virtualHeights = new Array(total).fill(0);
    state.virtualAvgHeight = estimateAverageHeight();

    if (state.readerMode === 'paged') {
        els.pages.style.gap = '';
        renderPagedWindow(state.currentPage);
        showLoading(false);
        updatePageVisibility({ scroll: false, behavior: 'auto' });
        scheduleProgressSave(true);
        return;
    }

    // For shorter chapters (< 60 pages), render all pages without virtual scrolling
    // This is more reliable and most manga chapters have 15-40 pages
    const VIRTUAL_THRESHOLD = 60;
    if (total <= VIRTUAL_THRESHOLD) {
        state.virtualEnabled = false;
        els.pages.style.gap = `${state.virtualGap}px`;
        const fragment = document.createDocumentFragment();
        for (let i = 0; i < total; i++) {
            fragment.appendChild(getPageNode(i));
        }
        els.pages.appendChild(fragment);
        showLoading(false);
        setupReaderObserver();
        updatePageVisibility({ scroll: true, behavior: 'auto' });
        state.initialScrollDone = true;
        scheduleProgressSave(true);
        return;
    }

    // For longer chapters, use virtual scrolling
    state.virtualEnabled = true;
    els.pages.style.gap = '0px';
    ensureVirtualElements();
    updateVirtualWindowForIndex(state.currentPage);
    showLoading(false);
    updatePageVisibility({ scroll: true, behavior: 'auto' });
    state.initialScrollDone = true;
    scheduleProgressSave(true);
}

function updatePageIndicator() {
    if (!els.pageIndicator) return;
    const total = state.pages.length;
    if (!total) {
        els.pageIndicator.textContent = '0 / 0';
        return;
    }
    if (state.readerMode === 'paged' && state.readerSpread) {
        const start = state.currentPage + 1;
        const showPair = !isSpreadPage(state.currentPage);
        const end = showPair ? Math.min(total, start + 1) : start;
        els.pageIndicator.textContent = showPair ? `${start}-${end} / ${total}` : `${start} / ${total}`;
    } else {
        els.pageIndicator.textContent = `${state.currentPage + 1} / ${total}`;
    }
    if (els.prevBtn) {
        els.prevBtn.disabled = state.currentPage === 0;
    }
    if (els.nextBtn) {
        els.nextBtn.disabled = state.currentPage >= total - 1;
    }
}

function updatePageVisibility(options = {}) {
    if (!els.pages) return;
    const pages = els.pages.querySelectorAll('.reader-page');
    const behavior = options.behavior || (state.readerMode === 'paged' ? 'auto' : 'smooth');

    // Find the current page element by data-page-index (fixes paged mode bug)
    let currentPageEl = null;

    if (state.readerMode === 'paged') {
        const showPair = state.readerSpread && !isSpreadPage(state.currentPage);
        pages.forEach((page) => {
            // Use data-page-index instead of DOM index for correct page identification
            const pageIndex = parseInt(page.dataset.pageIndex, 10);
            const isActive = pageIndex === state.currentPage
                || (showPair && pageIndex === state.currentPage + 1);
            page.classList.toggle('is-hidden', !isActive);
            page.classList.toggle('is-active', isActive);
            if (pageIndex === state.currentPage) {
                currentPageEl = page;
            }
        });
        if (options.scroll !== false && currentPageEl) {
            currentPageEl.scrollIntoView({ behavior, block: 'center' });
        }
    } else {
        pages.forEach((page) => {
            const pageIndex = parseInt(page.dataset.pageIndex, 10);
            page.classList.toggle('is-hidden', false);
            page.classList.toggle('is-active', pageIndex === state.currentPage);
            if (pageIndex === state.currentPage) {
                currentPageEl = page;
            }
        });
        if (options.scroll !== false && currentPageEl) {
            currentPageEl.scrollIntoView({
                behavior,
                block: state.readerMode === 'webtoon' ? 'start' : 'center'
            });
        }
    }
    updatePageIndicator();
}

function isSpreadPage(index) {
    return state.spreadPages.has(index);
}

function getReaderDelta(direction) {
    if (!(state.readerSpread && state.readerMode === 'paged')) {
        const step = 1;
        return direction === 'next' ? step : -step;
    }

    let step = 1;
    if (direction === 'next') {
        step = isSpreadPage(state.currentPage) ? 1 : 2;
    } else {
        const prevIndex = state.currentPage - 1;
        step = prevIndex >= 0 && isSpreadPage(prevIndex) ? 1 : 2;
    }

    return direction === 'next' ? step : -step;
}

function setReaderPage(index, options = {}) {
    const total = state.pages.length;
    if (!total) return;
    const clamped = clamp(index, 0, total - 1);
    if (clamped === state.currentPage && !options.force) return;
    state.currentPage = clamped;
    if (state.readerMode === 'paged') {
        renderPagedWindow(state.currentPage);
    } else {
        updateVirtualWindowForIndex(state.currentPage);
    }
    updatePageVisibility({ scroll: options.scroll !== false, behavior: options.behavior });
    scheduleProgressSave();

    // Trigger prefetching for pages ahead and next chapter
    Prefetcher.onPageChange(state.currentPage, state.pages);
}

function moveReader(direction, options = {}) {
    const total = state.pages.length;
    if (!total) return;
    const delta = getReaderDelta(direction);
    const nextIndex = state.currentPage + delta;
    if (direction === 'next' && nextIndex >= total) {
        void advanceChapter('next');
        return;
    }
    if (direction === 'prev' && nextIndex < 0) {
        void advanceChapter('prev');
        return;
    }
    setReaderPage(nextIndex, { behavior: options.behavior });
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
    const pages = els.pages.querySelectorAll('.reader-page');
    if (pages.length === 0) return;

    state.readerObserver = new IntersectionObserver((entries) => {
        const visible = entries
            .filter(entry => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (!visible.length) return;
        const index = Number(visible[0].target.dataset.pageIndex || 0);
        if (!Number.isNaN(index)) {
            setReaderPage(index, { scroll: false });
        }
    }, {
        root: els.pages,
        threshold: [0.6]
    });

    pages.forEach(page => state.readerObserver.observe(page));
}

function handleReaderTap(event) {
    if (event.target.closest('.reader-settings') || event.target.closest('.reader-topbar')) return;
    if (event.target.closest('#reader-settings-toggle')) return;
    const rect = els.pages.getBoundingClientRect();
    if (!rect.width) return;
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const ratio = x / rect.width;
    const yRatio = rect.height ? (y / rect.height) : 0;
    const isTopZone = yRatio <= 0.18;
    const isCenterZone = ratio >= 0.33 && ratio <= 0.66;
    if (isTopZone || isCenterZone) {
        setControlsVisible(!state.controlsVisible);
        return;
    }
    const isRtl = state.readerDirection === 'rtl';
    if (state.readerMode === 'webtoon') return;
    if (ratio < 0.33) {
        moveReader(isRtl ? 'next' : 'prev');
    } else if (ratio > 0.66) {
        moveReader(isRtl ? 'prev' : 'next');
    }
}

function handleKeydown(event) {
    if (event.target.matches('input, textarea, select')) return;
    if (event.target.closest('#reader-settings')) return;
    if (state.settingsOpen && window.innerWidth <= 960) return;
    switch (event.key) {
        case 'ArrowLeft':
        case 'ArrowUp':
            event.preventDefault();
            if (event.key === 'ArrowLeft') {
                moveReader(state.readerDirection === 'rtl' ? 'next' : 'prev', { behavior: 'auto' });
            } else {
                moveReader('prev', { behavior: 'auto' });
            }
            break;
        case 'ArrowRight':
        case 'ArrowDown':
        case ' ':
        case 'Enter':
            event.preventDefault();
            if (event.key === 'ArrowRight') {
                moveReader(state.readerDirection === 'rtl' ? 'prev' : 'next', { behavior: 'auto' });
            } else {
                moveReader('next', { behavior: 'auto' });
            }
            break;
        case 'Escape':
            event.preventDefault();
            goBack();
            break;
        case 's':
        case 'S':
            event.preventDefault();
            setReaderSpread(!state.readerSpread);
            break;
        default:
            break;
    }
}

function inferChapterOrder(chapters) {
    if (!chapters || chapters.length < 2) return 'desc';
    const first = parseFloat(chapters[0]?.chapter);
    const last = parseFloat(chapters[chapters.length - 1]?.chapter);
    if (!Number.isNaN(first) && !Number.isNaN(last)) {
        if (first > last) return 'desc';
        if (first < last) return 'asc';
    }
    return 'desc';
}

function getChapterNumber(chapter, index, total, order) {
    const parsed = parseFloat(chapter?.chapter);
    if (!Number.isNaN(parsed)) {
        return parsed;
    }
    if (!total) return null;
    if (order === 'desc') {
        return Math.max(1, total - index);
    }
    return index + 1;
}

async function ensureChapterList() {
    if (state.chapterList.length) return true;
    try {
        const data = await getAllChapters();
        const chapters = data?.chapters || [];
        if (!chapters.length) return false;
        state.chapterList = chapters;
        state.totalChapters = data.total || state.totalChapters || chapters.length;
        state.chapterIndex = chapters.findIndex(chapter => chapter.id === state.chapterId);
        return state.chapterIndex >= 0;
    } catch (error) {
        console.warn('[Reader] Failed to load chapter list:', error);
        return false;
    }
}

async function advanceChapter(direction) {
    if (state.isNavigating) return;
    state.isNavigating = true;
    try {
        const ready = await ensureChapterList();
        if (!ready) return;
        const order = inferChapterOrder(state.chapterList);
        const delta = order === 'desc' ? -1 : 1;
        const targetIndex = direction === 'next'
            ? state.chapterIndex + delta
            : state.chapterIndex - delta;
        if (targetIndex < 0 || targetIndex >= state.chapterList.length) return;
        const chapter = state.chapterList[targetIndex];
        const nextNumber = getChapterNumber(chapter, targetIndex, state.totalChapters, order);
        const params = new URLSearchParams();
        params.set('chapter_id', chapter.id);
        params.set('source', state.source);
        if (state.mangaId) params.set('manga_id', state.mangaId);
        if (state.mangaTitle) params.set('manga_title', state.mangaTitle);
        if (chapter.title) params.set('chapter_title', chapter.title);
        if (state.cover) params.set('cover', state.cover);
        if (state.libraryKey) params.set('library_key', state.libraryKey);
        if (nextNumber !== null && nextNumber !== undefined) {
            params.set('chapter_number', String(nextNumber));
        }
        if (state.totalChapters) params.set('total_chapters', String(state.totalChapters));
        params.set('start_page', '0');
        window.location.assign(`/reader?${params.toString()}`);
    } finally {
        state.isNavigating = false;
    }
}

function scheduleProgressSave(immediate = false) {
    if (state.progressTimer) {
        clearTimeout(state.progressTimer);
        state.progressTimer = null;
    }
    if (immediate) {
        void saveReadingProgress();
        return;
    }
    state.progressTimer = setTimeout(() => {
        state.progressTimer = null;
        void saveReadingProgress();
    }, 1200);
}

function buildLastReadEntry() {
    const pageValue = state.currentPage + 1;
    return {
        id: state.mangaId,
        manga_id: state.mangaId,
        source: state.source,
        title: state.mangaTitle,
        cover: state.cover,
        last_chapter: String(state.chapterNumber || state.chapterName || '0'),
        last_chapter_id: state.chapterId,
        last_page: pageValue,
        last_page_total: state.pages.length || null,
        total_chapters: state.totalChapters,
        last_read_at: new Date().toISOString()
    };
}

function saveLastRead(entry) {
    try {
        localStorage.setItem('manganegus.lastRead', JSON.stringify(entry));
    } catch {
        // Ignore storage errors
    }
}

async function saveReadingProgress() {
    if (!state.chapterId) return;
    const pageValue = state.currentPage + 1;
    const pageTotal = state.pages.length || null;
    const chapterValue = state.chapterNumber || state.chapterName || '';

    if (!state.libraryKey) {
        saveLastRead(buildLastReadEntry());
        return;
    }

    try {
        await ensureCsrfToken();
        await apiRequest('/api/library/update_progress', {
            method: 'POST',
            body: JSON.stringify({
                key: state.libraryKey,
                chapter: String(chapterValue),
                page: pageValue,
                chapter_id: state.chapterId,
                total_chapters: state.totalChapters,
                page_total: pageTotal
            })
        });
        saveLastRead(buildLastReadEntry());
    } catch (error) {
        console.warn('[Reader] Progress save failed:', error);
        saveLastRead(buildLastReadEntry());
    }
}

function recordReadingSession() {
    const elapsed = Date.now() - state.sessionStart;
    const minutes = Math.max(0, Math.round(elapsed / 60000));
    const pagesRead = Math.max(0, state.currentPage - state.sessionStartPage + 1);
    if (!minutes && !pagesRead) return;
    try {
        const raw = localStorage.getItem('manganegus.readingStats');
        const parsed = raw ? JSON.parse(raw) : { totalMinutes: 0, daily: {} };
        parsed.totalMinutes = (parsed.totalMinutes || 0) + minutes;
        const dayKey = new Date().toDateString();
        if (!parsed.daily[dayKey]) {
            parsed.daily[dayKey] = { minutes: 0, pages: 0 };
        }
        parsed.daily[dayKey].minutes += minutes;
        parsed.daily[dayKey].pages += pagesRead;
        localStorage.setItem('manganegus.readingStats', JSON.stringify(parsed));
    } catch {
        // Ignore storage errors
    }
}

function goBack() {
    if (window.history.length > 1) {
        window.history.back();
    } else {
        window.location.assign('/');
    }
}

function setSettingsOpen(open) {
    state.settingsOpen = open;
    if (els.settings) {
        els.settings.classList.toggle('open', open);
    }
    document.body.classList.toggle('settings-collapsed', !open);
    if (open) {
        setControlsVisible(true, { persist: true });
    } else if (isMobileView()) {
        scheduleControlsHide();
    }
}

function bindEvents() {
    if (els.backBtn) {
        els.backBtn.addEventListener('click', goBack);
    }
    if (els.prevBtn) {
        els.prevBtn.addEventListener('click', () => moveReader('prev'));
    }
    if (els.nextBtn) {
        els.nextBtn.addEventListener('click', () => moveReader('next'));
    }
    if (els.pages) {
        els.pages.addEventListener('click', handleReaderTap);
        els.pages.addEventListener('scroll', handleVirtualScroll, { passive: true });
    }
    if (els.settingsToggle) {
        els.settingsToggle.addEventListener('click', () => setSettingsOpen(!state.settingsOpen));
    }
    if (els.settingsClose) {
        els.settingsClose.addEventListener('click', () => setSettingsOpen(false));
    }
    if (els.spreadToggle) {
        els.spreadToggle.addEventListener('change', () => setReaderSpread(els.spreadToggle.checked));
    }

    document.querySelectorAll('.settings-options').forEach(group => {
        group.addEventListener('click', (event) => {
            const btn = event.target.closest('button[data-value]');
            if (!btn) return;
            const setting = group.dataset.setting;
            const value = btn.dataset.value;
            if (setting === 'mode') setReaderMode(value);
            if (setting === 'fit') setReaderFit(value);
            if (setting === 'direction') setReaderDirection(value);
            if (setting === 'background') setReaderBackground(value);
        });
    });

    document.addEventListener('keydown', handleKeydown);
    document.addEventListener('click', (event) => {
        if (!state.settingsOpen) return;
        if (window.innerWidth > 960) return;
        if (event.target.closest('#reader-settings') || event.target.closest('#reader-settings-toggle')) return;
        setSettingsOpen(false);
    });

    window.addEventListener('resize', () => {
        updateLayoutMetrics();
        syncControlsForViewport();
    });

    window.addEventListener('beforeunload', () => {
        void saveReadingProgress();
        recordReadingSession();
    });
}

async function init() {
    parseParams();
    loadReaderPreferences();
    updateLayoutMetrics();
    applySettings();
    state.settingsOpen = window.innerWidth > 960;
    setSettingsOpen(state.settingsOpen);
    syncControlsForViewport();

    if (els.mangaTitle) els.mangaTitle.textContent = state.mangaTitle || 'Manga';
    if (els.chapterTitle) els.chapterTitle.textContent = state.chapterName || 'Chapter';
    if (state.chapterName) {
        document.title = state.mangaTitle ? `${state.chapterName} • ${state.mangaTitle}` : state.chapterName;
    }
    requestAnimationFrame(updateLayoutMetrics);
    bindEvents();

    // Initialize prefetcher IndexedDB cache
    try {
        await Prefetcher.initDB();
        // Run cleanup in background (don't await)
        Prefetcher.cleanup();
    } catch (e) {
        console.warn('[Reader] Failed to init prefetch cache:', e);
    }

    if (!state.chapterId) {
        showError('Missing chapter ID. Please go back and select a chapter.');
        return;
    }
    if (!state.source) {
        showError('Missing source. Please go back and select this manga from a source.');
        return;
    }
    // Reject jikan pseudo-source which is metadata-only (MyAnimeList)
    if (state.source === 'jikan') {
        showError('This manga was found via MyAnimeList metadata. Please search for it from a manga source to read chapters.');
        return;
    }

    showLoading(true);
    try {
        state.pages = await getChapterPages();
        if (!state.pages.length) {
            showError('No pages available for this chapter.');
            return;
        }
        await renderPages();

        // Start prefetching pages ahead after initial render
        Prefetcher.onPageChange(state.currentPage, state.pages);

        // Pre-fetch chapter list for next chapter prefetching
        ensureChapterList();
    } catch (error) {
        console.error('[Reader] Failed to load pages:', error);
        showError(`Failed to load pages: ${error.message}`);
    } finally {
        showLoading(false);
    }

    if (window.lucide && window.lucide.createIcons) {
        window.lucide.createIcons();
    }
}

init();
