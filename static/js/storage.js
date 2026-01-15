/**
 * IndexedDB Storage Module for MangaNegus
 *
 * Replaces localStorage for large datasets (library, feed cache, history)
 * to avoid blocking the main thread during serialization.
 *
 * Features:
 * - Async read/write operations
 * - Automatic migration from localStorage
 * - Fallback to localStorage for unsupported browsers
 * - Versioned database schema
 *
 * Usage:
 *   await Storage.init();
 *   await Storage.setLibrary(libraryArray);
 *   const library = await Storage.getLibrary();
 */

const DB_NAME = 'manganegus_db';
const DB_VERSION = 1;

// Store names
const STORES = {
    LIBRARY: 'library',
    FEED_CACHE: 'feedCache',
    HISTORY: 'history',
    SETTINGS: 'settings'
};

// LocalStorage keys for migration
const LS_KEYS = {
    LIBRARY: 'manganegus.libraryCache',
    FEED_CACHE: 'manganegus.feedCache',
    HISTORY: 'manganegus.historyCache'
};

class IndexedDBStorage {
    constructor() {
        this._db = null;
        this._isSupported = this._checkSupport();
        this._initPromise = null;
    }

    _checkSupport() {
        return typeof indexedDB !== 'undefined';
    }

    /**
     * Initialize the database connection.
     * Call this once at app startup.
     */
    async init() {
        if (this._initPromise) {
            return this._initPromise;
        }

        this._initPromise = this._doInit();
        return this._initPromise;
    }

    async _doInit() {
        if (!this._isSupported) {
            console.warn('[Storage] IndexedDB not supported, using localStorage fallback');
            return false;
        }

        try {
            this._db = await this._openDatabase();
            console.log('[Storage] IndexedDB initialized successfully');

            // Migrate from localStorage if needed
            await this._migrateFromLocalStorage();

            return true;
        } catch (error) {
            console.error('[Storage] IndexedDB init failed:', error);
            this._isSupported = false;
            return false;
        }
    }

    _openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => {
                reject(new Error(`Failed to open database: ${request.error}`));
            };

            request.onsuccess = () => {
                resolve(request.result);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Create object stores
                if (!db.objectStoreNames.contains(STORES.LIBRARY)) {
                    db.createObjectStore(STORES.LIBRARY, { keyPath: 'key' });
                }

                if (!db.objectStoreNames.contains(STORES.FEED_CACHE)) {
                    db.createObjectStore(STORES.FEED_CACHE, { keyPath: 'view' });
                }

                if (!db.objectStoreNames.contains(STORES.HISTORY)) {
                    db.createObjectStore(STORES.HISTORY, { keyPath: 'key' });
                }

                if (!db.objectStoreNames.contains(STORES.SETTINGS)) {
                    db.createObjectStore(STORES.SETTINGS, { keyPath: 'key' });
                }

                console.log('[Storage] Database schema created');
            };
        });
    }

    /**
     * Migrate data from localStorage to IndexedDB.
     * This is a one-time operation on first run.
     */
    async _migrateFromLocalStorage() {
        const migrationKey = 'manganegus.idb_migrated';
        if (localStorage.getItem(migrationKey) === 'true') {
            return; // Already migrated
        }

        console.log('[Storage] Starting migration from localStorage...');

        try {
            // Migrate library
            const libraryRaw = localStorage.getItem(LS_KEYS.LIBRARY);
            if (libraryRaw) {
                const library = JSON.parse(libraryRaw);
                if (Array.isArray(library) && library.length > 0) {
                    await this.setLibrary(library);
                    console.log(`[Storage] Migrated ${library.length} library entries`);
                }
            }

            // Migrate feed cache
            const feedRaw = localStorage.getItem(LS_KEYS.FEED_CACHE);
            if (feedRaw) {
                const feedCache = JSON.parse(feedRaw);
                if (feedCache && typeof feedCache === 'object') {
                    await this.setFeedCache(feedCache);
                    console.log('[Storage] Migrated feed cache');
                }
            }

            // Migrate history
            const historyRaw = localStorage.getItem(LS_KEYS.HISTORY);
            if (historyRaw) {
                const history = JSON.parse(historyRaw);
                if (Array.isArray(history) && history.length > 0) {
                    await this.setHistory(history);
                    console.log(`[Storage] Migrated ${history.length} history entries`);
                }
            }

            // Mark migration as complete
            localStorage.setItem(migrationKey, 'true');
            console.log('[Storage] Migration complete');

        } catch (error) {
            console.error('[Storage] Migration failed:', error);
        }
    }

    // =========================================================================
    // LIBRARY OPERATIONS
    // =========================================================================

    /**
     * Get the entire library as an array.
     */
    async getLibrary() {
        if (!this._isSupported || !this._db) {
            return this._getFromLocalStorage(LS_KEYS.LIBRARY, []);
        }

        try {
            return await this._getAllFromStore(STORES.LIBRARY);
        } catch (error) {
            console.error('[Storage] getLibrary failed:', error);
            return this._getFromLocalStorage(LS_KEYS.LIBRARY, []);
        }
    }

    /**
     * Save the entire library (array of entries).
     */
    async setLibrary(library) {
        if (!this._isSupported || !this._db) {
            this._setToLocalStorage(LS_KEYS.LIBRARY, library);
            return;
        }

        try {
            await this._clearStore(STORES.LIBRARY);
            await this._putMany(STORES.LIBRARY, library);
        } catch (error) {
            console.error('[Storage] setLibrary failed:', error);
            this._setToLocalStorage(LS_KEYS.LIBRARY, library);
        }
    }

    /**
     * Add or update a single library entry.
     */
    async putLibraryEntry(entry) {
        if (!entry.key) {
            throw new Error('Library entry must have a key');
        }

        if (!this._isSupported || !this._db) {
            const library = this._getFromLocalStorage(LS_KEYS.LIBRARY, []);
            const index = library.findIndex(e => e.key === entry.key);
            if (index >= 0) {
                library[index] = entry;
            } else {
                library.push(entry);
            }
            this._setToLocalStorage(LS_KEYS.LIBRARY, library);
            return;
        }

        try {
            await this._put(STORES.LIBRARY, entry);
        } catch (error) {
            console.error('[Storage] putLibraryEntry failed:', error);
        }
    }

    /**
     * Remove a library entry by key.
     */
    async removeLibraryEntry(key) {
        if (!this._isSupported || !this._db) {
            const library = this._getFromLocalStorage(LS_KEYS.LIBRARY, []);
            const filtered = library.filter(e => e.key !== key);
            this._setToLocalStorage(LS_KEYS.LIBRARY, filtered);
            return;
        }

        try {
            await this._delete(STORES.LIBRARY, key);
        } catch (error) {
            console.error('[Storage] removeLibraryEntry failed:', error);
        }
    }

    // =========================================================================
    // FEED CACHE OPERATIONS
    // =========================================================================

    async getFeedCache() {
        if (!this._isSupported || !this._db) {
            return this._getFromLocalStorage(LS_KEYS.FEED_CACHE, {
                discover: [],
                popular: [],
                trending: []
            });
        }

        try {
            const entries = await this._getAllFromStore(STORES.FEED_CACHE);
            const cache = { discover: [], popular: [], trending: [] };
            for (const entry of entries) {
                cache[entry.view] = entry.data || [];
            }
            return cache;
        } catch (error) {
            console.error('[Storage] getFeedCache failed:', error);
            return { discover: [], popular: [], trending: [] };
        }
    }

    async setFeedCache(feedCache) {
        if (!this._isSupported || !this._db) {
            this._setToLocalStorage(LS_KEYS.FEED_CACHE, feedCache);
            return;
        }

        try {
            const entries = Object.entries(feedCache).map(([view, data]) => ({
                view,
                data,
                timestamp: Date.now()
            }));
            await this._clearStore(STORES.FEED_CACHE);
            await this._putMany(STORES.FEED_CACHE, entries);
        } catch (error) {
            console.error('[Storage] setFeedCache failed:', error);
            this._setToLocalStorage(LS_KEYS.FEED_CACHE, feedCache);
        }
    }

    // =========================================================================
    // HISTORY OPERATIONS
    // =========================================================================

    async getHistory() {
        if (!this._isSupported || !this._db) {
            return this._getFromLocalStorage(LS_KEYS.HISTORY, []);
        }

        try {
            return await this._getAllFromStore(STORES.HISTORY);
        } catch (error) {
            console.error('[Storage] getHistory failed:', error);
            return this._getFromLocalStorage(LS_KEYS.HISTORY, []);
        }
    }

    async setHistory(history) {
        if (!this._isSupported || !this._db) {
            this._setToLocalStorage(LS_KEYS.HISTORY, history);
            return;
        }

        try {
            await this._clearStore(STORES.HISTORY);
            // Ensure each entry has a key
            const entries = history.map(entry => ({
                key: entry.key || `${entry.source}:${entry.id}`,
                ...entry
            }));
            await this._putMany(STORES.HISTORY, entries);
        } catch (error) {
            console.error('[Storage] setHistory failed:', error);
            this._setToLocalStorage(LS_KEYS.HISTORY, history);
        }
    }

    // =========================================================================
    // LOW-LEVEL DATABASE OPERATIONS
    // =========================================================================

    _getAllFromStore(storeName) {
        return new Promise((resolve, reject) => {
            const transaction = this._db.transaction(storeName, 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();

            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    }

    _put(storeName, data) {
        return new Promise((resolve, reject) => {
            const transaction = this._db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.put(data);

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    _putMany(storeName, items) {
        return new Promise((resolve, reject) => {
            const transaction = this._db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);

            for (const item of items) {
                store.put(item);
            }

            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
        });
    }

    _delete(storeName, key) {
        return new Promise((resolve, reject) => {
            const transaction = this._db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.delete(key);

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    _clearStore(storeName) {
        return new Promise((resolve, reject) => {
            const transaction = this._db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.clear();

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    // =========================================================================
    // LOCALSTORAGE FALLBACK
    // =========================================================================

    _getFromLocalStorage(key, defaultValue) {
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : defaultValue;
        } catch {
            return defaultValue;
        }
    }

    _setToLocalStorage(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.error('[Storage] localStorage write failed:', error);
        }
    }

    // =========================================================================
    // UTILITIES
    // =========================================================================

    /**
     * Get storage statistics.
     */
    async getStats() {
        if (!this._isSupported || !this._db) {
            return {
                type: 'localStorage',
                libraryCount: this._getFromLocalStorage(LS_KEYS.LIBRARY, []).length,
                historyCount: this._getFromLocalStorage(LS_KEYS.HISTORY, []).length
            };
        }

        const library = await this.getLibrary();
        const history = await this.getHistory();

        return {
            type: 'IndexedDB',
            libraryCount: library.length,
            historyCount: history.length,
            dbName: DB_NAME,
            dbVersion: DB_VERSION
        };
    }

    /**
     * Clear all stored data (for testing/reset).
     */
    async clear() {
        if (this._isSupported && this._db) {
            await this._clearStore(STORES.LIBRARY);
            await this._clearStore(STORES.FEED_CACHE);
            await this._clearStore(STORES.HISTORY);
        }

        localStorage.removeItem(LS_KEYS.LIBRARY);
        localStorage.removeItem(LS_KEYS.FEED_CACHE);
        localStorage.removeItem(LS_KEYS.HISTORY);
    }
}

// Export singleton instance
export const Storage = new IndexedDBStorage();
export default Storage;
