/**
 * Chapter Management Module
 * Handles chapter loading, selection, and downloads
 */

import api from './api.js';
import state from './state.js';

export async function showMangaDetails(mangaId, sourceId, title = '') {
    // Reset and set current manga
    state.resetMangaState();
    state.currentManga = { id: mangaId, source: sourceId, title: title };

    // Switch to details view
    window.dispatchEvent(new CustomEvent('showView', {
        detail: { view: 'details' }
    }));

    // Show loading states
    showTitleCardLoading();
    showChaptersLoading();

    await loadChapters();
}

export async function loadChapters() {
    try {
        const data = await api.getChapters(
            state.currentManga.id,
            state.currentManga.source,
            state.chapterOffset,
            100
        );

        let newChapters = null;

        if (state.chapterOffset === 0) {
            state.chapters = data.chapters;
            // newChapters remains null to trigger full render
        } else {
            newChapters = data.chapters;
            state.chapters = [...state.chapters, ...data.chapters];
        }

        state.hasMoreChapters = data.hasMore;
        state.chapterOffset = data.nextOffset;

        renderTitleCard();
        renderChapters(newChapters);

        state.elements.loadMoreContainer.style.display = state.hasMoreChapters ? 'block' : 'none';
    } catch (e) {
        console.error('Failed to load chapters:', e);
        showChaptersError(e.message || 'Failed to load chapters');
    }
}

export async function loadMoreChapters() {
    state.elements.loadMoreBtn.disabled = true;

    // Clear and rebuild button content
    while (state.elements.loadMoreBtn.firstChild) {
        state.elements.loadMoreBtn.removeChild(state.elements.loadMoreBtn.firstChild);
    }
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    state.elements.loadMoreBtn.appendChild(spinner);
    state.elements.loadMoreBtn.appendChild(document.createTextNode(' Loading...'));

    await loadChapters();

    state.elements.loadMoreBtn.disabled = false;
    while (state.elements.loadMoreBtn.firstChild) {
        state.elements.loadMoreBtn.removeChild(state.elements.loadMoreBtn.firstChild);
    }
    const icon = document.createElement('i');
    icon.className = 'ph ph-plus-circle';
    state.elements.loadMoreBtn.appendChild(icon);
    state.elements.loadMoreBtn.appendChild(document.createTextNode(' Load More'));
}

function renderTitleCard() {
    // Clear existing content
    while (state.elements.titleCard.firstChild) {
        state.elements.titleCard.removeChild(state.elements.titleCard.firstChild);
    }

    // Create title header
    const titleHeader = document.createElement('div');
    titleHeader.className = 'title-card-header';

    const titleElement = document.createElement('h2');
    titleElement.className = 'manga-title';
    titleElement.textContent = state.currentManga.title || `${state.currentManga.source} / ${state.currentManga.id.substring(0,8)}...`;

    titleHeader.appendChild(titleElement);
    state.elements.titleCard.appendChild(titleHeader);

    // Create quick download panel
    const quickDownload = document.createElement('div');
    quickDownload.className = 'quick-download glass-panel';

    const header = document.createElement('div');
    header.className = 'quick-download-header';

    const label = document.createElement('span');
    label.className = 'quick-download-label';
    label.textContent = 'Quick Download';
    header.appendChild(label);

    const inputRow = document.createElement('div');
    inputRow.className = 'download-input-row';

    const inputGroup = document.createElement('div');
    inputGroup.className = 'input-group';

    const startInput = document.createElement('input');
    startInput.type = 'number';
    startInput.className = 'glass-input chapter-input';
    startInput.id = 'start-chapter';
    startInput.placeholder = 'Start';
    startInput.min = '1';

    const arrow = document.createElement('span');
    arrow.className = 'input-arrow';
    arrow.textContent = '→';

    const endInput = document.createElement('input');
    endInput.type = 'number';
    endInput.className = 'glass-input chapter-input';
    endInput.id = 'end-chapter';
    endInput.placeholder = 'End';
    endInput.min = '1';

    inputGroup.appendChild(startInput);
    inputGroup.appendChild(arrow);
    inputGroup.appendChild(endInput);

    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'glass-btn download-btn dl-btn';
    downloadBtn.id = 'quick-download-btn';
    const dlIcon = document.createElement('i');
    dlIcon.className = 'ph ph-download';
    downloadBtn.appendChild(dlIcon);

    downloadBtn.addEventListener('click', () => {
        const start = parseFloat(startInput.value);
        const end = parseFloat(endInput.value);
        downloadRange(start, end);
    });

    inputRow.appendChild(inputGroup);
    inputRow.appendChild(downloadBtn);

    quickDownload.appendChild(header);
    quickDownload.appendChild(inputRow);

    state.elements.titleCard.appendChild(quickDownload);

    // Update chapter count
    state.elements.chapterCount.textContent = `(${state.chapters.length})`;
}

function renderChapters(newItemsOnly = null) {
    if (!newItemsOnly) {
        // Full render - Clear grid
        while (state.elements.chapterGrid.firstChild) {
            state.elements.chapterGrid.removeChild(state.elements.chapterGrid.firstChild);
        }

        if (!state.chapters.length) {
            const emptyState = document.createElement('div');
            emptyState.className = 'empty-state';

            const icon = document.createElement('i');
            icon.className = 'ph ph-book-open';

            const text = document.createElement('p');
            text.textContent = 'No chapters';

            emptyState.appendChild(icon);
            emptyState.appendChild(text);
            state.elements.chapterGrid.appendChild(emptyState);
            return;
        }

        state.chapters.forEach(ch => {
            const item = createChapterItem(ch);
            state.elements.chapterGrid.appendChild(item);
        });
    } else {
        // Append new items only
        newItemsOnly.forEach(ch => {
            const item = createChapterItem(ch);
            state.elements.chapterGrid.appendChild(item);
        });
    }
}

function createChapterItem(chapter) {
    const item = document.createElement('div');
    item.className = `chapter-item glass-panel${state.selectedChapters.has(chapter.id) ? ' selected' : ''}`;
    item.dataset.id = chapter.id;
    item.dataset.chapter = chapter.chapter;

    const checkbox = document.createElement('div');
    checkbox.className = 'chapter-checkbox';
    const checkIcon = document.createElement('i');
    checkIcon.className = 'ph ph-check';
    checkbox.appendChild(checkIcon);

    const chNum = document.createElement('span');
    chNum.className = 'chapter-num';
    chNum.textContent = `Ch. ${chapter.chapter}`;

    item.appendChild(checkbox);
    item.appendChild(chNum);

    if (chapter.title) {
        const chTitle = document.createElement('span');
        chTitle.className = 'chapter-title';
        chTitle.textContent = chapter.title;
        item.appendChild(chTitle);
    }

    // Event listeners
    item.addEventListener('click', () => toggleChapter(chapter.id));
    item.addEventListener('dblclick', () => {
        window.dispatchEvent(new CustomEvent('openReader', {
            detail: { chapterId: chapter.id, chapterNum: chapter.chapter }
        }));
    });

    return item;
}

function toggleChapter(id) {
    state.toggleChapterSelection(id);
    const item = state.elements.chapterGrid.querySelector(`[data-id="${id}"]`);
    if (item) {
        item.classList.toggle('selected');
    }
    updateFloatingBar();
}

export function selectAllChapters() {
    state.selectAllChapters();
    state.elements.chapterGrid.querySelectorAll('.chapter-item').forEach(el => {
        el.classList.add('selected');
    });
    updateFloatingBar();
}

export function clearSelection() {
    state.clearChapterSelection();
    state.elements.chapterGrid.querySelectorAll('.chapter-item').forEach(el => {
        el.classList.remove('selected');
    });
    updateFloatingBar();
}

function updateFloatingBar() {
    const count = state.selectedChapters.size;
    state.elements.selectionCount.textContent = count;
    state.elements.floatingBar.classList.toggle('active', count > 0);
}

export async function downloadSelected() {
    if (!state.selectedChapters.size) return;
    const toDownload = state.getSelectedChapters();
    await startDownload(toDownload);
    clearSelection();
}

export async function downloadRange(start, end) {
    if (!start || !end) {
        window.dispatchEvent(new CustomEvent('log', {
            detail: { message: '⚠️ Enter start and end chapters' }
        }));
        return;
    }

    const toDownload = state.chapters.filter(ch => {
        const num = parseFloat(ch.chapter);
        return num >= start && num <= end;
    });

    if (!toDownload.length) {
        window.dispatchEvent(new CustomEvent('log', {
            detail: { message: '⚠️ No chapters in range' }
        }));
        return;
    }

    await startDownload(toDownload);
}

async function startDownload(chapters) {
    try {
        const title = state.currentManga.title || `manga_${state.currentManga.id.substring(0,8)}`;
        await api.downloadChapters(
            chapters,
            title,
            state.currentManga.source,
            state.currentManga.id
        );
    } catch (e) {
        window.dispatchEvent(new CustomEvent('log', {
            detail: { message: '❌ Download failed' }
        }));
    }
}

function showTitleCardLoading() {
    while (state.elements.titleCard.firstChild) {
        state.elements.titleCard.removeChild(state.elements.titleCard.firstChild);
    }
    const loading = document.createElement('div');
    loading.className = 'loading-state';
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    loading.appendChild(spinner);
    state.elements.titleCard.appendChild(loading);
}

function showChaptersLoading() {
    while (state.elements.chapterGrid.firstChild) {
        state.elements.chapterGrid.removeChild(state.elements.chapterGrid.firstChild);
    }
    const loading = document.createElement('div');
    loading.className = 'loading-state';
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    loading.appendChild(spinner);
    state.elements.chapterGrid.appendChild(loading);
}

function showChaptersError(message) {
    while (state.elements.chapterGrid.firstChild) {
        state.elements.chapterGrid.removeChild(state.elements.chapterGrid.firstChild);
    }
    const errorState = document.createElement('div');
    errorState.className = 'empty-state';

    const icon = document.createElement('i');
    icon.className = 'ph ph-warning';

    const text = document.createElement('p');
    text.textContent = message;

    errorState.appendChild(icon);
    errorState.appendChild(text);
    state.elements.chapterGrid.appendChild(errorState);
}
