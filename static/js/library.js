/**
 * Library Management Module
 * Handles user's manga library operations
 */

import api from './api.js';
import state from './state.js';
import { proxyImageUrl } from './utils.js';

export async function loadLibrary(filter = 'all') {
    try {
        const lib = await api.getLibrary();

        // Ensure lib is an object
        const safeLib = (lib && typeof lib === 'object') ? lib : {};

        let items = Object.entries(safeLib);
        if (filter !== 'all') {
            items = items.filter(([k, m]) => m && m.status === filter);
        }

        // Clear grid safely
        while (state.elements.libraryGrid.firstChild) {
            state.elements.libraryGrid.removeChild(state.elements.libraryGrid.firstChild);
        }

        if (!items.length) {
            const emptyState = document.createElement('div');
            emptyState.className = 'empty-state';

            const icon = document.createElement('i');
            icon.className = 'ph ph-books';

            const text = document.createElement('p');
            text.textContent = 'Empty';

            emptyState.appendChild(icon);
            emptyState.appendChild(text);
            state.elements.libraryGrid.appendChild(emptyState);
            return;
        }

        // Build library items using safe DOM methods
        items.forEach(([key, m]) => {
            // Skip if manga data is invalid
            if (!m || !m.title) {
                console.warn('Invalid library item:', key, m);
                return;
            }

            try {
                const item = document.createElement('div');
                item.className = 'library-item glass-panel';
                item.dataset.key = key;
                item.dataset.source = m.source || 'unknown';
                item.dataset.id = m.manga_id || key;
                item.dataset.title = m.title;

            const cover = document.createElement('img');
            cover.className = 'library-item-cover';
            cover.src = proxyImageUrl(m.cover);
            cover.alt = m.title;
            cover.loading = 'lazy';
            cover.onerror = () => cover.src = '/static/images/placeholder.svg';

            const info = document.createElement('div');
            info.className = 'library-item-info';

            const title = document.createElement('h3');
            title.className = 'library-item-title';
            title.textContent = m.title;

            const progress = document.createElement('p');
            progress.className = 'library-item-progress';
            progress.textContent = m.last_chapter ? `Ch. ${m.last_chapter}` : 'Not started';

            info.appendChild(title);
            info.appendChild(progress);
            item.appendChild(cover);
            item.appendChild(info);

            // Click handler - will trigger manga details view
            item.addEventListener('click', () => {
                window.dispatchEvent(new CustomEvent('openManga', {
                    detail: {
                        manga: {
                            id: m.manga_id,
                            source: m.source,
                            title: m.title,
                            cover: m.cover
                        }
                    }
                }));
            });

            state.elements.libraryGrid.appendChild(item);
            } catch (itemError) {
                console.error('Failed to render library item:', itemError, m);
                // Skip this item but continue with others
            }
        });
    } catch (e) {
        console.error('Failed to load library:', e);
    }
}

export async function addToLibrary(manga, buttonElement = null, status = null) {
    // If no status provided, show modal to select status
    if (!status) {
        showStatusSelectionModal(manga, buttonElement);
        return;
    }

    try {
        await api.addToLibrary(manga, status);

        // Log success
        window.dispatchEvent(new CustomEvent('log', {
            detail: { message: `📚 Added: ${manga.title}` }
        }));

        // Visual feedback on button
        if (buttonElement) {
            // Clear and rebuild button content safely
            while (buttonElement.firstChild) {
                buttonElement.removeChild(buttonElement.firstChild);
            }
            const icon = document.createElement('i');
            icon.className = 'ph-fill ph-check-circle';
            buttonElement.appendChild(icon);
            buttonElement.disabled = true;
            buttonElement.style.opacity = '0.6';
            buttonElement.style.cursor = 'not-allowed';
        }

        // Reload library if we're on library view
        if (state.activeView === 'library') {
            await loadLibrary();
        }
    } catch (e) {
        console.error('Failed to add:', e);
        // Show error feedback on button
        if (buttonElement) {
            while (buttonElement.firstChild) {
                buttonElement.removeChild(buttonElement.firstChild);
            }
            const icon = document.createElement('i');
            icon.className = 'ph-fill ph-x-circle';
            buttonElement.appendChild(icon);

            setTimeout(() => {
                while (buttonElement.firstChild) {
                    buttonElement.removeChild(buttonElement.firstChild);
                }
                const plusIcon = document.createElement('i');
                plusIcon.className = 'ph ph-plus';
                buttonElement.appendChild(plusIcon);
            }, 2000);
        }
    }
}

function showStatusSelectionModal(manga, buttonElement) {
    const overlay = document.getElementById('library-status-modal-overlay');
    const modal = document.getElementById('library-status-modal');

    if (!overlay || !modal) {
        console.error('Status modal not found');
        return;
    }

    // Store manga and button in modal for later use
    modal._pendingManga = manga;
    modal._pendingButton = buttonElement;

    // Show modal
    overlay.classList.add('active');
}

export function initializeStatusModal() {
    const overlay = document.getElementById('library-status-modal-overlay');
    const modal = document.getElementById('library-status-modal');
    const closeBtn = document.getElementById('close-library-status-modal');
    const statusButtons = document.querySelectorAll('.status-option-btn');

    if (!overlay || !modal) return;

    // Close modal handlers
    const closeModal = () => {
        overlay.classList.remove('active');
        modal._pendingManga = null;
        modal._pendingButton = null;
    };

    closeBtn?.addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    // Status selection handlers
    statusButtons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const status = btn.dataset.status;
            const manga = modal._pendingManga;
            const buttonElement = modal._pendingButton;

            if (!manga) {
                console.error('No manga data in modal');
                return;
            }

            closeModal();

            // Call addToLibrary with selected status
            await addToLibrary(manga, buttonElement, status);
        });
    });
}
