/**
 * API Communication Layer
 * Centralized backend communication with CSRF protection
 */

class API {
    constructor() {
        this.csrfToken = null;
    }

    /**
     * Fetch CSRF token from server
     */
    async fetchCsrfToken() {
        try {
            const resp = await fetch('/api/csrf-token');
            const data = await resp.json();
            this.csrfToken = data.csrf_token;
        } catch (e) {
            console.error('Failed to fetch CSRF token:', e);
        }
    }

    /**
     * Make POST request with CSRF token
     * @param {string} url - API endpoint
     * @param {Object} data - Request data
     * @returns {Promise<Response>} - Fetch response
     */
    async post(url, data = {}) {
        const doPost = () => fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken
            },
            body: JSON.stringify(data)
        });

        const resp = await doPost();
        if (resp.status === 403) {
            await this.fetchCsrfToken();
            return doPost();
        }
        return resp;
    }

    /**
     * Make GET request
     * @param {string} url - API endpoint
     * @returns {Promise<Response>} - Fetch response
     */
    async get(url) {
        return fetch(url);
    }

    // === Source APIs ===

    async getSources() {
        const resp = await this.get('/api/sources');
        return resp.json();
    }

    async setActiveSource(sourceId) {
        return this.post('/api/sources/active', { source_id: sourceId });
    }

    async getSourceHealth() {
        const resp = await this.get('/api/sources/health');
        return resp.json();
    }

    async resetSource(sourceId) {
        return this.post(`/api/sources/${sourceId}/reset`, {});
    }

    // === Search & Discovery APIs ===

    async getPopular() {
        const resp = await this.get('/api/popular');
        return resp.json();
    }

    async search(query, sourceId) {
        return this.post('/api/search', { query, source_id: sourceId });
    }

    async smartSearch(query, sourceId) {
        return this.post('/api/search/smart', { query, source_id: sourceId });
    }

    async detectUrl(url) {
        return this.post('/api/detect_url', { url });
    }

    // === Library APIs ===

    async getLibrary() {
        const resp = await this.get('/api/library');
        return resp.json();
    }

    async addToLibrary(manga, status = 'reading') {
        return this.post('/api/library/save', {
            id: manga.id || manga.mal_id || manga.manga_id,  // Handle Jikan (mal_id) and sources (id/manga_id)
            title: manga.title,
            source: manga.source || 'jikan',  // Default to 'jikan' for Jikan manga
            cover: manga.cover_url || manga.cover,  // Handle both properties
            status: status
        });
    }

    async updateStatus(key, status) {
        return this.post('/api/library/update_status', { key, status });
    }

    async updateProgress(key, chapter) {
        return this.post('/api/library/update_progress', { key, chapter });
    }

    async deleteFromLibrary(key) {
        return this.post('/api/library/delete', { key });
    }

    // === Chapter APIs ===

    async getChapters(mangaId, source, offset = 0, limit = 100, title = null, malId = null) {
        const resp = await this.post('/api/chapters', {
            id: mangaId,
            source,
            offset,
            limit,
            title,
            mal_id: malId
        });
        return resp.json();
    }

    async getAllChapters(mangaId, source) {
        const resp = await this.post('/api/all_chapters', {
            id: mangaId,
            source
        });
        return resp.json();
    }

    async getChapterPages(chapterId, source) {
        return this.post('/api/chapter_pages', {
            chapter_id: chapterId,
            source
        });
    }

    // === Download APIs ===

    async downloadChapters(chapters, title, source, mangaId) {
        return this.post('/api/download', {
            chapters,
            title,
            source,
            manga_id: mangaId
        });
    }

    async getDownloadedChapters(mangaId, source) {
        const title = `manga_${String(mangaId).substring(0, 8)}`;
        const resp = await this.post('/api/downloaded_chapters', { title });
        return resp.json();
    }

    // === Logging API ===

    async getLogs() {
        const resp = await this.get('/api/logs');
        return resp.json();
    }
}

// Export singleton instance
export default new API();
