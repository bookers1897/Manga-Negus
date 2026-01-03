/**
 * Manga Reader Module
 * Handles fullscreen chapter reading
 */

import api from './api.js';
import state from './state.js';
import { sanitizeUrl } from './utils.js';

export async function openReader(chapterId, chapterNum) {
    state.elements.readerContainer.classList.add('active');
    state.elements.readerTitle.textContent = `Chapter ${chapterNum}`;

    // Show loading state
    showReaderLoading();

    try {
        const resp = await api.getChapterPages(chapterId, state.currentManga.source);

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Failed to load pages');
        }

        const data = await resp.json();

        if (!data.pages?.length) {
            showReaderEmpty();
            return;
        }

        renderPages(data.pages);
    } catch (e) {
        console.error('Failed to load reader:', e);
        showReaderError(e.message || 'Failed to load chapter');
    }
}

export function closeReader() {
    state.elements.readerContainer.classList.remove('active');
}

function renderPages(pages) {
    // Clear content
    while (state.elements.readerContent.firstChild) {
        state.elements.readerContent.removeChild(state.elements.readerContent.firstChild);
    }

    pages.forEach((url, i) => {
        const img = document.createElement('img');
        img.className = 'reader-page';
        img.src = sanitizeUrl(url);
        img.alt = `Page ${i + 1}`;
        img.loading = 'lazy';

        state.elements.readerContent.appendChild(img);
    });
}

function showReaderLoading() {
    while (state.elements.readerContent.firstChild) {
        state.elements.readerContent.removeChild(state.elements.readerContent.firstChild);
    }

    const loading = document.createElement('div');
    loading.className = 'loading-state';

    const spinner = document.createElement('div');
    spinner.className = 'spinner';

    loading.appendChild(spinner);
    state.elements.readerContent.appendChild(loading);
}

function showReaderEmpty() {
    while (state.elements.readerContent.firstChild) {
        state.elements.readerContent.removeChild(state.elements.readerContent.firstChild);
    }

    const emptyState = document.createElement('div');
    emptyState.className = 'empty-state';

    const text = document.createElement('p');
    text.textContent = 'No pages found for this chapter';

    emptyState.appendChild(text);
    state.elements.readerContent.appendChild(emptyState);
}

function showReaderError(message) {
    while (state.elements.readerContent.firstChild) {
        state.elements.readerContent.removeChild(state.elements.readerContent.firstChild);
    }

    const errorState = document.createElement('div');
    errorState.className = 'empty-state';

    const text = document.createElement('p');
    text.textContent = message;

    errorState.appendChild(text);
    state.elements.readerContent.appendChild(errorState);
}
