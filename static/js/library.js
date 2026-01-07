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
        console.log('📚 Library API response:', lib);

        // Ensure lib is an object
        const safeLib = (lib && typeof lib === 'object') ? lib : {};
        console.log('📚 Safe library object:', safeLib);

        // Cache library data in state for "Already Added" checks
        state.libraryData = safeLib;

        let items = Object.entries(safeLib);
        console.log('📚 Library entries:', items.length, items);

        if (filter !== 'all') {
            items = items.filter(([k, m]) => m && m.status === filter);
            console.log('📚 Filtered entries:', items.length);
        }

        // Check if library grid exists
        if (!state.elements.libraryGrid) {
            console.error('❌ Library grid element not found!');
            return;
        }

        // Clear grid safely
        while (state.elements.libraryGrid.firstChild) {
            state.elements.libraryGrid.removeChild(state.elements.libraryGrid.firstChild);
        }

        if (!items.length) {
            console.log('📚 No items to display, showing empty state');
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

        console.log('📚 Rendering', items.length, 'library items...');

        // Build library items using safe DOM methods - NEW PORTRAIT FORMAT
        items.forEach(([key, m], index) => {
            console.log(`📚 Processing item ${index + 1}/${items.length}:`, key, m);

            // Skip if manga data is invalid
            if (!m || !m.title) {
                console.warn('⚠️ Invalid library item:', key, m);
                return;
            }

            try {
                console.log(`📚 Creating card for: ${m.title}`);
                const card = document.createElement('div');
                card.className = 'manga-card glass-panel';
                card.dataset.key = key;
                card.dataset.source = m.source || 'unknown';
                card.dataset.id = m.manga_id || key;

                const cover = document.createElement('img');
                cover.className = 'manga-card-cover';

                // Don't proxy MAL images - use directly
                const coverUrl = m.cover;
                if (coverUrl && coverUrl.includes('myanimelist.net')) {
                    cover.src = coverUrl;
                } else if (coverUrl) {
                    cover.src = proxyImageUrl(coverUrl);
                } else {
                    cover.src = '/static/images/placeholder.svg';
                }

                cover.alt = m.title;
                cover.loading = 'lazy';
                cover.onerror = () => cover.src = '/static/images/placeholder.svg';

                const content = document.createElement('div');
                content.className = 'manga-card-content';

                const title = document.createElement('h3');
                title.className = 'manga-card-title';
                title.textContent = m.title;

                const desc = document.createElement('p');
                desc.className = 'manga-card-desc';
                desc.textContent = m.last_chapter ? `Last read: Ch. ${m.last_chapter}` : 'Not started';

                // Status badge
                const statusBadge = document.createElement('span');
                statusBadge.className = 'status-badge';
                statusBadge.textContent = m.status ? m.status.replace('_', ' ') : 'reading';
                statusBadge.style.cssText = 'display: inline-block; padding: 0.25rem 0.5rem; border-radius: 0.5rem; background: var(--accent-color); color: white; font-size: 0.75rem; font-weight: 600; text-transform: capitalize; margin-bottom: 0.5rem;';

                content.appendChild(statusBadge);
                content.appendChild(title);
                content.appendChild(desc);

                card.appendChild(cover);
                card.appendChild(content);

                // Click handler - will trigger manga details view
                card.addEventListener('click', () => {
                    window.dispatchEvent(new CustomEvent('openManga', {
                        detail: {
                            manga: {
                                id: m.manga_id,
                                source: m.source,
                                title: m.title,
                                cover: m.cover,
                                cover_url: m.cover
                            }
                        }
                    }));
                });

                state.elements.libraryGrid.appendChild(card);
                console.log(`✅ Card appended for: ${m.title}`);
            } catch (itemError) {
                console.error('❌ Failed to render library item:', itemError, m);
                // Skip this item but continue with others
            }
        });

        console.log(`✅ Finished rendering ${items.length} library items`);
    } catch (e) {
        console.error('❌ Failed to load library:', e);
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

        // Reload library data to update "Already Added" states
        await loadLibrary();

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
            icon.className = 'ph-fill ph-check';
            const text = document.createTextNode(' Added');
            buttonElement.appendChild(icon);
            buttonElement.appendChild(text);
            buttonElement.disabled = true;
            buttonElement.style.opacity = '0.6';
            buttonElement.style.cursor = 'not-allowed';
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

export function isInLibrary(manga) {
    if (!state.libraryData) return false;

    const mangaId = manga.id || manga.mal_id || manga.manga_id;
    const source = manga.source || 'jikan';
    const key = `${source}:${mangaId}`;

    return key in state.libraryData;
}

export function updateButtonState(button, manga) {
    if (!button) return;

    if (isInLibrary(manga)) {
        // Clear button content
        while (button.firstChild) {
            button.removeChild(button.firstChild);
        }

        const icon = document.createElement('i');
        icon.className = 'ph-fill ph-check';
        const text = document.createTextNode(' Added');

        button.appendChild(icon);
        button.appendChild(text);
        button.disabled = true;
        button.style.opacity = '0.6';
        button.style.cursor = 'not-allowed';
    }
}
