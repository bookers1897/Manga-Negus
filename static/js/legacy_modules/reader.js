/**
 * Manga Reader Module
 * Handles fullscreen chapter reading
 */

import api from './api.js';
import state from './state.js';
import { sanitizeUrl } from './utils.js';

let currentChapterId = null;

export async function openReader(chapterId, chapterNum) {
    currentChapterId = chapterId;
    state.elements.readerContainer.classList.add('active');
    state.elements.readerTitle.textContent = `Chapter ${chapterNum}`;

    updateNavigationButtons();

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
    currentChapterId = null;
}

function updateNavigationButtons() {
    if (!state.chapters.length || !currentChapterId) return;
    
    const currentIndex = state.chapters.findIndex(ch => ch.id === currentChapterId);
    if (currentIndex === -1) return;

    // Assuming Descending Order (Newest First in Array)
    // Next (1 -> 2) implies moving to a LOWER index (newer chapter)
    // Prev (2 -> 1) implies moving to a HIGHER index (older chapter)
    
    const nextBtn = state.elements.nextChapterBtn;
    const prevBtn = state.elements.prevChapterBtn;

    if (nextBtn) {
        // "Next" button -> Go to Newer Chapter (Index - 1)
        if (currentIndex > 0) {
            nextBtn.disabled = false;
            nextBtn.onclick = () => {
                const nextCh = state.chapters[currentIndex - 1];
                openReader(nextCh.id, nextCh.chapter);
            };
        } else {
            nextBtn.disabled = true;
            nextBtn.onclick = null;
        }
    }

    if (prevBtn) {
        // "Prev" button -> Go to Older Chapter (Index + 1)
        if (currentIndex < state.chapters.length - 1) {
            prevBtn.disabled = false;
            prevBtn.onclick = () => {
                const prevCh = state.chapters[currentIndex + 1];
                openReader(prevCh.id, prevCh.chapter);
            };
        } else {
            prevBtn.disabled = true;
            prevBtn.onclick = null;
        }
    }
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
