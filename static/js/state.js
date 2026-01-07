/**
 * Application State Management
 * Centralized reactive state container
 */

class AppState {
    constructor() {
        // View state
        this.currentView = 'search';
        this.previousView = 'search';
        this.isLoading = false;

        // Source state
        this.sources = [];
        this.activeSource = null;

        // Manga state
        this.currentManga = null;  // {id, source, title}
        this.chapters = [];
        this.chapterOffset = 0;
        this.hasMoreChapters = false;

        // Selection state
        this.selectedChapters = new Set();

        // DOM elements cache
        this.elements = {};

        // Subscribers for reactive updates
        this.subscribers = {};
    }

    /**
     * Cache DOM elements for quick access
     */
    cacheElements() {
        this.elements = {
            // Views
            searchView: document.getElementById('search-view'),
            libraryView: document.getElementById('library-view'),
            detailsView: document.getElementById('details-view'),

            // Header
            menuBtn: document.getElementById('menu-btn'),
            libraryBtn: document.getElementById('library-btn'),

            // Source selector
            sourceSelect: document.getElementById('source-select'),
            sourceStatusBtn: document.getElementById('source-status-btn'),

            // Search
            searchInput: document.getElementById('search-input'),
            searchBtn: document.getElementById('search-btn'),
            urlInput: document.getElementById('url-input'),
            detectUrlBtn: document.getElementById('detect-url-btn'),
            resultsGrid: document.getElementById('results-grid'),

            // Library
            libraryGrid: document.getElementById('library-grid'),

            // Details
            backBtn: document.getElementById('back-btn'),
            titleCard: document.getElementById('title-card'),
            chapterGrid: document.getElementById('chapter-grid'),
            chapterCount: document.getElementById('chapter-count'),
            selectAllBtn: document.getElementById('select-all-btn'),
            clearSelectionBtn: document.getElementById('clear-selection-btn'),
            loadMoreBtn: document.getElementById('load-more-btn'),
            loadMoreContainer: document.getElementById('load-more-container'),

            // Manga metadata elements
            mangaBanner: document.getElementById('manga-banner'),
            mangaCover: document.getElementById('manga-cover'),
            mangaTitle: document.getElementById('manga-title'),
            mangaStatus: document.getElementById('manga-status'),
            mangaType: document.getElementById('manga-type'),
            mangaYear: document.getElementById('manga-year'),
            mangaRatingSection: document.getElementById('manga-rating-section'),
            mangaRatingAvg: document.getElementById('manga-rating-avg'),
            mangaRatingCount: document.getElementById('manga-rating-count'),
            mangaSynopsis: document.getElementById('manga-synopsis'),
            mangaAuthorItem: document.getElementById('manga-author-item'),
            mangaAuthor: document.getElementById('manga-author'),
            mangaArtistItem: document.getElementById('manga-artist-item'),
            mangaArtist: document.getElementById('manga-artist'),
            mangaChaptersItem: document.getElementById('manga-chapters-item'),
            mangaChaptersCount: document.getElementById('manga-chapters-count'),
            mangaVolumesItem: document.getElementById('manga-volumes-item'),
            mangaVolumesCount: document.getElementById('manga-volumes-count'),
            mangaGenres: document.getElementById('manga-genres'),
            mangaTags: document.getElementById('manga-tags'),
            addLibraryBtn: document.getElementById('add-library-btn'),

            // Floating bar
            floatingBar: document.getElementById('floating-bar'),
            selectionCount: document.getElementById('selection-count'),
            downloadSelectedBtn: document.getElementById('download-selected-btn'),

            // Console
            consoleToggle: document.getElementById('console-toggle'),
            consolePanel: document.getElementById('console-panel'),
            consoleContent: document.getElementById('console-content'),

            // Menu
            menuOverlay: document.getElementById('menu-overlay'),
            hamburgerMenu: document.getElementById('hamburger-menu'),
            closeMenuBtn: document.getElementById('close-menu-btn'),

            // Reader
            readerContainer: document.getElementById('reader-container'),
            readerContent: document.getElementById('reader-content'),
            readerTitle: document.getElementById('reader-title'),
            readerCloseBtn: document.getElementById('reader-close-btn'),
            prevChapterBtn: document.getElementById('prev-chapter-btn'),
            nextChapterBtn: document.getElementById('next-chapter-btn'),

            // Source modal
            sourceModalOverlay: document.getElementById('source-modal-overlay'),
            sourceStatusContent: document.getElementById('source-status-content'),
            closeSourceModal: document.getElementById('close-source-modal')
        };
    }

    /**
     * Subscribe to state changes
     * @param {string} key - State key to watch
     * @param {Function} callback - Function to call on change
     */
    subscribe(key, callback) {
        if (!this.subscribers[key]) {
            this.subscribers[key] = [];
        }
        this.subscribers[key].push(callback);
    }

    /**
     * Notify subscribers of state change
     * @param {string} key - State key that changed
     */
    notify(key) {
        if (this.subscribers[key]) {
            this.subscribers[key].forEach(callback => callback(this[key]));
        }
    }

    /**
     * Set state with notification
     * @param {string} key - State key
     * @param {any} value - New value
     */
    set(key, value) {
        this[key] = value;
        this.notify(key);
    }

    /**
     * Set loading state and disable/enable buttons
     * @param {boolean} loading - Loading state
     */
    setLoading(loading) {
        this.isLoading = loading;

        const buttons = [
            this.elements.searchBtn,
            this.elements.selectAllBtn,
            this.elements.clearSelectionBtn,
            this.elements.downloadSelectedBtn,
            this.elements.loadMoreBtn
        ];

        buttons.forEach(btn => {
            if (btn) btn.disabled = loading;
        });

        if (this.elements.searchInput) {
            this.elements.searchInput.disabled = loading;
        }
    }

    /**
     * Reset manga-related state
     */
    resetMangaState() {
        this.currentManga = null;
        this.chapters = [];
        this.chapterOffset = 0;
        this.hasMoreChapters = false;
        this.selectedChapters.clear();
    }

    /**
     * Toggle chapter selection
     * @param {string} id - Chapter ID
     */
    toggleChapterSelection(id) {
        if (this.selectedChapters.has(id)) {
            this.selectedChapters.delete(id);
        } else {
            this.selectedChapters.add(id);
        }
        this.notify('selectedChapters');
    }

    /**
     * Select all chapters
     */
    selectAllChapters() {
        this.chapters.forEach(ch => this.selectedChapters.add(ch.id));
        this.notify('selectedChapters');
    }

    /**
     * Clear chapter selection
     */
    clearChapterSelection() {
        this.selectedChapters.clear();
        this.notify('selectedChapters');
    }

    /**
     * Get selected chapters
     * @returns {Array} - Array of selected chapter objects
     */
    getSelectedChapters() {
        return this.chapters.filter(ch => this.selectedChapters.has(ch.id));
    }
}

// Export singleton instance
export default new AppState();
