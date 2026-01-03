/**
 * UI Management Module
 * Handles views, logging, console, and menu operations
 */

import api from './api.js';
import state from './state.js';

// === View Management ===

export function showView(view) {
    state.previousView = state.currentView;
    state.currentView = view;

    // Remove active class from all views
    document.querySelectorAll('.view-panel').forEach(v => v.classList.remove('active'));

    // Add active to target view
    const targetView = document.getElementById(`${view}-view`);
    if (targetView) {
        targetView.classList.add('active');
    }
}

export function toggleMenu(show) {
    state.elements.hamburgerMenu.classList.toggle('active', show);
    state.elements.menuOverlay.classList.toggle('active', show);
}

export function toggleConsole() {
    state.elements.consolePanel.classList.toggle('active');
    state.elements.consoleToggle.classList.toggle('active');
}

// === Logging ===

export function log(message) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.textContent = message;
    state.elements.consoleContent.appendChild(entry);
    state.elements.consoleContent.scrollTop = state.elements.consoleContent.scrollHeight;
}

export function startLogPolling() {
    setInterval(async () => {
        try {
            const data = await api.getLogs();
            data.logs.forEach(msg => log(msg));
        } catch (e) {
            // Silently fail - don't spam console
        }
    }, 1000);
}

// === Initial View Load ===

export function handleInitialView(view) {
    if (view === 'library') {
        // Library will be loaded when switching to it
        window.dispatchEvent(new CustomEvent('loadLibrary'));
    }
}
