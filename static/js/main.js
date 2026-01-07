/**
 * Main Application Coordinator
 * Initializes all modules and binds event handlers
 */

import api from './api.js';
import state from './state.js';
import * as sources from './sources.js';
import * as search from './search.js';
import * as library from './library.js';
import * as chapters from './chapters.js';
import * as reader from './reader.js';
import * as ui from './ui.js';

class MangaNegusApp {
    async init() {
        // Initialize API
        await api.fetchCsrfToken();

        // Cache DOM elements
        state.cacheElements();

        // Bind all event listeners
        this.bindEvents();

        // Initialize modals
        library.initializeStatusModal();

        // Load sources and popular manga
        await sources.loadSources();
        search.loadPopular();

        // Start log polling
        ui.startLogPolling();
    }

    bindEvents() {
        // === Navigation ===
        state.elements.menuBtn.addEventListener('click', () => ui.toggleMenu(true));
        state.elements.closeMenuBtn.addEventListener('click', () => ui.toggleMenu(false));
        state.elements.menuOverlay.addEventListener('click', () => ui.toggleMenu(false));
        state.elements.libraryBtn.addEventListener('click', () => {
            ui.showView('library');
            library.loadLibrary();
        });
        state.elements.backBtn.addEventListener('click', () => {
            ui.showView(state.previousView || 'search');
        });

        // Menu items
        document.querySelectorAll('.menu-item[data-view]').forEach(btn => {
            btn.addEventListener('click', () => {
                const view = btn.dataset.view;
                ui.showView(view);
                ui.toggleMenu(false);

                if (view === 'library') {
                    library.loadLibrary();
                }
            });
        });

        // === Source Management ===
        state.elements.sourceSelect.addEventListener('change', async e => {
            await sources.setActiveSource(e.target.value);
            search.loadPopular();
        });
        state.elements.sourceStatusBtn.addEventListener('click', () => sources.showSourceStatus());
        state.elements.closeSourceModal.addEventListener('click', () => sources.hideSourceStatus());
        state.elements.sourceModalOverlay.addEventListener('click', e => {
            if (e.target === state.elements.sourceModalOverlay) {
                sources.hideSourceStatus();
            }
        });

        // === Search ===
        state.elements.searchBtn.addEventListener('click', () => search.search());
        state.elements.searchInput.addEventListener('keypress', e => {
            if (e.key === 'Enter') search.search();
        });

        // URL Detection
        state.elements.detectUrlBtn.addEventListener('click', () => search.detectAndOpenFromURL());
        state.elements.urlInput.addEventListener('keypress', e => {
            if (e.key === 'Enter') search.detectAndOpenFromURL();
        });

        // === Library Filters ===
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                library.loadLibrary(btn.dataset.filter);
            });
        });

        // === Chapters ===
        state.elements.selectAllBtn.addEventListener('click', () => chapters.selectAllChapters());
        state.elements.clearSelectionBtn.addEventListener('click', () => chapters.clearSelection());
        state.elements.loadMoreBtn.addEventListener('click', () => chapters.loadMoreChapters());
        state.elements.downloadSelectedBtn.addEventListener('click', () => chapters.downloadSelected());

        // === Console ===
        state.elements.consoleToggle.addEventListener('click', () => ui.toggleConsole());

        // === Reader ===
        state.elements.readerCloseBtn.addEventListener('click', () => reader.closeReader());

        // === Custom Events (Cross-Module Communication) ===

        // Open manga details
        window.addEventListener('openManga', e => {
            const { manga } = e.detail;
            chapters.showMangaDetails(manga);
        });

        // Add to library
        window.addEventListener('addToLibrary', e => {
            const { manga, button } = e.detail;
            library.addToLibrary(manga, button);
        });

        // Open reader
        window.addEventListener('openReader', e => {
            const { chapterId, chapterNum } = e.detail;
            reader.openReader(chapterId, chapterNum);
        });

        // Log message
        window.addEventListener('log', e => {
            const { message } = e.detail;
            ui.log(message);
        });

        // Show view
        window.addEventListener('showView', e => {
            const { view } = e.detail;
            ui.showView(view);
        });

        // Load library
        window.addEventListener('loadLibrary', () => {
            library.loadLibrary();
        });
    }
}

// Initialize app on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    const app = new MangaNegusApp();
    app.init();
});
