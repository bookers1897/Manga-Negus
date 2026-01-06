/**
 * Source Management Module
 * Handles source selection, status, and health monitoring
 */

import api from './api.js';
import state from './state.js';
import { escapeHtml } from './utils.js';

export async function loadSources() {
    try {
        state.sources = await api.getSources();

        // Build options using safe DOM methods
        state.elements.sourceSelect.innerHTML = '';
        state.sources.forEach(s => {
            const option = document.createElement('option');
            option.value = s.id;
            option.textContent = `${s.icon} ${s.name}`;
            if (s.is_active) option.selected = true;
            state.elements.sourceSelect.appendChild(option);
        });

        const active = state.sources.find(s => s.is_active);
        if (active) state.activeSource = active.id;

    } catch (e) {
        console.error('Failed to load sources:', e);
        state.elements.sourceSelect.innerHTML = '';
        const option = document.createElement('option');
        option.textContent = 'Error loading sources';
        state.elements.sourceSelect.appendChild(option);
    }
}

export async function setActiveSource(sourceId) {
    try {
        await api.setActiveSource(sourceId);
        state.activeSource = sourceId;
    } catch (e) {
        console.error('Failed to set source:', e);
    }
}

export async function showSourceStatus() {
    try {
        const data = await api.getSourceHealth();

        // Clear and rebuild using safe DOM methods
        state.elements.sourceStatusContent.innerHTML = '';

        data.sources.forEach(s => {
            const item = document.createElement('div');
            item.className = `source-status-item ${s.is_available ? 'available' : 'unavailable'}`;

            const info = document.createElement('div');
            info.className = 'source-info';

            const name = document.createElement('span');
            name.className = 'source-name';
            name.textContent = `${s.icon} ${s.name}`;

            const badge = document.createElement('span');
            badge.className = `source-status-badge ${s.status}`;
            badge.textContent = s.status;

            info.appendChild(name);
            info.appendChild(badge);
            item.appendChild(info);

            if (!s.is_available) {
                const resetBtn = document.createElement('button');
                resetBtn.className = 'glass-btn reset-btn';
                resetBtn.dataset.sourceId = s.id;

                const icon = document.createElement('i');
                icon.className = 'ph ph-arrow-counter-clockwise';
                resetBtn.appendChild(icon);
                resetBtn.appendChild(document.createTextNode(' Reset'));

                resetBtn.addEventListener('click', () => resetSource(s.id));
                item.appendChild(resetBtn);
            }

            state.elements.sourceStatusContent.appendChild(item);
        });

        state.elements.sourceModalOverlay.classList.add('active');
    } catch (e) {
        console.error('Failed to load source status:', e);
    }
}

export function hideSourceStatus() {
    state.elements.sourceModalOverlay.classList.remove('active');
}

export async function resetSource(sourceId) {
    await api.resetSource(sourceId);
    showSourceStatus();
}
