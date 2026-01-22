/**
 * Search & Discovery Module
 * Handles manga search and trending/popular listings
 */

import api from './api.js';
import state from './state.js';
import { proxyImageUrl } from './utils.js';
import { updateButtonState } from './library.js';

export async function loadPopular() {
    showLoadingState(state.elements.resultsGrid);

    try {
        const resp = await api.getPopular();
        if (resp.error) {
            throw new Error(resp.error);
        }
        // Ensure we have an array
        const results = Array.isArray(resp) ? resp : [];
        renderResults(results);
    } catch (e) {
        console.error('Failed to load popular:', e);
        showErrorState(state.elements.resultsGrid, 'Failed to load popular manga');
    }
}

export async function search() {
    const query = state.elements.searchInput.value.trim();
    if (!query || state.isLoading) return;

    state.setLoading(true);
    showLoadingState(state.elements.resultsGrid);

    try {
        // Use smart search for metadata-enriched results
        const resp = await api.smartSearch(query, state.activeSource);
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

        // Trigger manga details open with minimal manga object
        window.dispatchEvent(new CustomEvent('openManga', {
            detail: {
                manga: {
                    id: data.manga_id,
                    source: data.source_id,
                    title: data.title || ''
                }
            }
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

    // Ensure results is an array
    const safeResults = Array.isArray(results) ? results : [];

    if (!safeResults.length) {
        showEmptyState(state.elements.resultsGrid, 'No results');
        return;
    }

    safeResults.forEach(m => {
        try {
            const card = createMangaCard(m);
            state.elements.resultsGrid.appendChild(card);
        } catch (e) {
            console.error('Failed to render manga card:', e, m);
            // Skip this card but continue with others
        }
    });
}

function createMangaCard(manga) {
    // Ensure manga object exists
    if (!manga) {
        throw new Error('Manga object is required');
    }

    const card = document.createElement('div');
    card.className = 'manga-card glass-panel';
    card.dataset.id = manga.id || manga.mal_id || 'unknown';
    card.dataset.source = manga.source || 'jikan';

    const cover = document.createElement('img');
    cover.className = 'manga-card-cover';

    // Prioritize high-quality metadata covers if available
    // This fixes the issue where MangaDex placeholders are used instead of AniList covers
    const coverUrl = manga.cover_image_large 
                  || manga.cover_image 
                  || manga.cover_image_medium 
                  || manga.cover_url 
                  || manga.cover;

    // Jikan images don't need proxying - use directly from MAL CDN
    if (coverUrl && coverUrl.includes('myanimelist.net')) {
        cover.src = coverUrl;  // Direct URL for Jikan/MAL images
    } else if (coverUrl) {
        // Pass the referer (manga url or source id) to allow hotlinking
        const referer = manga.url || manga.source || '';
        cover.src = proxyImageUrl(coverUrl, referer);
    } else {
        cover.src = '/static/images/placeholder.svg';
    }

    cover.alt = manga.title || 'Manga cover';
    cover.loading = 'lazy';
    cover.onerror = () => cover.src = '/static/images/placeholder.svg';

    const content = document.createElement('div');
    content.className = 'manga-card-content';

    const title = document.createElement('h3');
    title.className = 'manga-card-title';
    title.textContent = manga.title || 'Unknown Title';

    // Show rating if available (Jikan manga)
    if (manga.rating && typeof manga.rating.average === 'number') {
        const ratingDiv = document.createElement('div');
        ratingDiv.className = 'manga-card-rating';

        const star = document.createElement('i');
        star.className = 'ph-fill ph-star';
        star.style.color = '#ffd700';

        const score = document.createElement('span');
        score.textContent = manga.rating.average.toFixed(1);

        ratingDiv.appendChild(star);
        ratingDiv.appendChild(score);
        content.appendChild(ratingDiv);
    }

    const desc = document.createElement('p');
    desc.className = 'manga-card-desc';
    desc.textContent = manga.author || manga.source || 'MyAnimeList';

    const addBtn = document.createElement('button');
    addBtn.className = 'glass-btn add-btn';
    const icon = document.createElement('i');
    icon.className = 'ph ph-plus';
    addBtn.appendChild(icon);

    content.appendChild(title);
    content.appendChild(desc);
    content.appendChild(addBtn);

    card.appendChild(cover);
    card.appendChild(content);

    // Check if already in library and update button state
    updateButtonState(addBtn, manga);

    // Event listeners
    card.addEventListener('click', e => {
        if (!e.target.closest('.add-btn')) {
            window.dispatchEvent(new CustomEvent('openManga', {
                detail: { manga: manga }  // Pass full manga object with all metadata
            }));
        }
    });

    addBtn.addEventListener('click', e => {
        e.stopPropagation();
        // Ensure manga has source property for Jikan manga
        if (!manga.source && manga.mal_id) {
            manga.source = 'jikan';
        }
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
