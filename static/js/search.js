/**
 * Search & Discovery Module
 * Handles manga search and trending/popular listings
 */

import api from './api.js';
import state from './state.js';
import { proxyImageUrl } from './utils.js';

export async function loadPopular() {
    showLoadingState(state.elements.resultsGrid);

    try {
        const resp = await api.getPopular();
        if (resp.error) {
            throw new Error(resp.error);
        }
        renderResults(resp);
    } catch (e) {
        showErrorState(state.elements.resultsGrid, 'Failed to load');
    }
}

export async function search() {
    const query = state.elements.searchInput.value.trim();
    if (!query || state.isLoading) return;

    state.setLoading(true);
    showLoadingState(state.elements.resultsGrid);

    try {
        const resp = await api.search(query, state.activeSource);
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Search failed');
        }
        const results = await resp.json();
        renderResults(results);
    } catch (e) {
        showErrorState(state.elements.resultsGrid, e.message || 'Search failed');
    } finally {
        state.setLoading(false);
    }
}

export async function detectAndOpenFromURL() {
    const url = state.elements.urlInput.value.trim();
    if (!url || state.isLoading) return;

    state.setLoading(true);

    // Log detection attempt
    window.dispatchEvent(new CustomEvent('log', {
        detail: { message: '🔍 Detecting source from URL...' }
    }));

    try {
        const resp = await api.detectUrl(url);
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'URL detection failed');
        }

        const data = await resp.json();

        window.dispatchEvent(new CustomEvent('log', {
            detail: { message: `✅ Detected: ${data.source_name}` }
        }));

        // Clear URL input
        state.elements.urlInput.value = '';

        // Trigger manga details open
        window.dispatchEvent(new CustomEvent('openManga', {
            detail: { id: data.manga_id, source: data.source_id, title: data.title || '' }
        }));
    } catch (e) {
        window.dispatchEvent(new CustomEvent('log', {
            detail: { message: `❌ ${e.message || 'URL detection failed'}` }
        }));
    } finally {
        state.setLoading(false);
    }
}

function renderResults(results) {
    // Clear grid safely
    while (state.elements.resultsGrid.firstChild) {
        state.elements.resultsGrid.removeChild(state.elements.resultsGrid.firstChild);
    }

    if (!results.length) {
        showEmptyState(state.elements.resultsGrid, 'No results');
        return;
    }

    results.forEach(m => {
        const card = createMangaCard(m);
        state.elements.resultsGrid.appendChild(card);
    });
}

function createMangaCard(manga) {
    const card = document.createElement('div');
    card.className = 'manga-card glass-panel';
    card.dataset.id = manga.id;
    card.dataset.source = manga.source;

    const cover = document.createElement('img');
    cover.className = 'manga-card-cover';
    cover.src = proxyImageUrl(manga.cover);
    cover.alt = manga.title;
    cover.loading = 'lazy';
    cover.onerror = () => cover.src = '/static/images/placeholder.svg';

    const content = document.createElement('div');
    content.className = 'manga-card-content';

    const title = document.createElement('h3');
    title.className = 'manga-card-title';
    title.textContent = manga.title;

    const desc = document.createElement('p');
    desc.className = 'manga-card-desc';
    desc.textContent = manga.author || manga.source;

    const footer = document.createElement('div');
    footer.className = 'manga-card-footer';

    const label = document.createElement('span');
    label.className = 'manga-card-label';
    label.textContent = manga.source;

    const addBtn = document.createElement('button');
    addBtn.className = 'glass-btn add-btn';
    const icon = document.createElement('i');
    icon.className = 'ph ph-plus';
    addBtn.appendChild(icon);

    footer.appendChild(label);
    footer.appendChild(addBtn);

    content.appendChild(title);
    content.appendChild(desc);
    content.appendChild(footer);

    card.appendChild(cover);
    card.appendChild(content);

    // Event listeners
    card.addEventListener('click', e => {
        if (!e.target.closest('.add-btn')) {
            window.dispatchEvent(new CustomEvent('openManga', {
                detail: { id: manga.id, source: manga.source, title: manga.title }
            }));
        }
    });

    addBtn.addEventListener('click', e => {
        e.stopPropagation();
        window.dispatchEvent(new CustomEvent('addToLibrary', {
            detail: { manga, button: addBtn }
        }));
    });

    return card;
}

function showLoadingState(container) {
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }

    const loadingState = document.createElement('div');
    loadingState.className = 'loading-state';

    const spinner = document.createElement('div');
    spinner.className = 'spinner';

    loadingState.appendChild(spinner);
    container.appendChild(loadingState);
}

function showEmptyState(container, message) {
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }

    const emptyState = document.createElement('div');
    emptyState.className = 'empty-state';

    const icon = document.createElement('i');
    icon.className = 'ph ph-magnifying-glass';

    const text = document.createElement('p');
    text.textContent = message;

    emptyState.appendChild(icon);
    emptyState.appendChild(text);
    container.appendChild(emptyState);
}

function showErrorState(container, message) {
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }

    const errorState = document.createElement('div');
    errorState.className = 'empty-state';

    const icon = document.createElement('i');
    icon.className = 'ph ph-warning';

    const text = document.createElement('p');
    text.textContent = message;

    errorState.appendChild(icon);
    errorState.appendChild(text);
    container.appendChild(errorState);
}
