// Web Worker for Heavy Filtering Computations
// Offloads filtering logic from main thread to prevent UI freezing

// Helper: Get collections for entry (replicated from main.js logic)
function getCollectionsForEntry(entry) {
    const tags = [];
    if (entry.status) tags.push(entry.status);
    if (entry.source) tags.push(entry.source);
    // Add custom collections if present in metadata (future proofing)
    return tags;
}

self.onmessage = function(e) {
    const { id, type } = e.data;
    
    try {
        let result = [];
        
        if (type === 'filterLibrary') {
            result = processLibraryFilter(e.data);
        } else {
            // Default to generic list filtering
            result = processListFilter(e.data);
        }
        
        self.postMessage({ id, result });
    } catch (err) {
        self.postMessage({ id, error: err.message });
    }
};

function processLibraryFilter({ library, filter, smartFilter, collectionFilter, sort }) {
    if (!library || !Array.isArray(library)) return [];
    
    // 1. Status Filter
    let filtered = filter === 'all' 
        ? library 
        : library.filter(item => item.status === filter);
        
    // 2. Smart Filter
    if (smartFilter) {
        const now = Date.now();
        switch (smartFilter) {
            case 'unread_updates':
                filtered = filtered.filter(item => {
                    const total = parseFloat(item.total_chapters || 0);
                    const last = parseFloat(item.last_chapter || 0);
                    return !Number.isNaN(total) && !Number.isNaN(last) && total > last;
                });
                break;
            case 'completed_unfinished':
                filtered = filtered.filter(item => {
                    const total = parseFloat(item.total_chapters || 0);
                    const last = parseFloat(item.last_chapter || 0);
                    return item.status === 'completed' && !Number.isNaN(total) && !Number.isNaN(last) && total > last;
                });
                break;
            case 'abandoned':
                filtered = filtered.filter(item => {
                    if (item.status !== 'plan_to_read') return false;
                    const addedAt = Date.parse(item.added_at || '');
                    if (Number.isNaN(addedAt)) return false;
                    return (now - addedAt) > 30 * 24 * 60 * 60 * 1000;
                });
                break;
        }
    }
    
    // 3. Collection Filter
    if (collectionFilter) {
        filtered = filtered.filter(item => {
            const collections = getCollectionsForEntry(item).map(tag => tag.toLowerCase());
            return collections.includes(collectionFilter);
        });
    }
    
    // 4. Sort
    filtered.sort((a, b) => {
        switch (sort) {
            case 'title_asc':
                return String(a.title || '').localeCompare(String(b.title || ''));
            case 'title_desc':
                return String(b.title || '').localeCompare(String(a.title || ''));
            case 'last_read': {
                const aTime = Date.parse(a.last_read_at || '') || 0;
                const bTime = Date.parse(b.last_read_at || '') || 0;
                return bTime - aTime;
            }
            case 'rating_desc': {
                const aRating = a.rating?.average || a.score || 0;
                const bRating = b.rating?.average || b.score || 0;
                return bRating - aRating;
            }
            case 'rating_asc': {
                const aRating = a.rating?.average || a.score || 0;
                const bRating = b.rating?.average || b.score || 0;
                return aRating - bRating;
            }
            case 'recent':
            default: {
                const aTime = Date.parse(a.added_at || '') || 0;
                const bTime = Date.parse(b.added_at || '') || 0;
                return bTime - aTime;
            }
        }
    });
    
    return filtered;
}

function processListFilter({ list, filters, hiddenManga }) {
    if (!list || !Array.isArray(list)) return [];

    const f = filters || {};
    const hiddenSet = new Set(hiddenManga || []);
    let results = [...list];

    // Helper: Is Hidden
    const isHidden = (id, src) => hiddenSet.has(`${src}:${id}`);

    // 1. Filter Hidden & Source
    results = results.filter(item => {
        const id = item.mal_id || item.id || item.manga_id;
        const src = item.source || item.source_id || (item.mal_id ? 'jikan' : '');
        if (id && src && isHidden(id, src)) return false;
        if (f.source && src !== f.source) return false;
        return true;
    });

    // 2. Filter Genres (Include/Exclude)
    if (f.genres?.length || f.exclude?.length || f.demographics?.length) {
        results = results.filter(item => {
            const tags = (item.genres || item.tags || []).map(t => String(t).toLowerCase());
            if (f.genres?.length && !f.genres.every(t => tags.includes(t))) return false;
            if (f.exclude?.length && f.exclude.some(t => tags.includes(t))) return false;
            if (f.demographics?.length && !f.demographics.every(t => tags.includes(t))) return false;
            return true;
        });
    }

    // 3. Filter Metadata (Status, Type, Year, Score)
    if (f.status) results = results.filter(i => (i.status || '').toLowerCase().includes(f.status));
    if (f.type) results = results.filter(i => (i.type || '').toLowerCase().includes(f.type));
    if (f.yearStart) results = results.filter(i => Number(i.year || 0) >= Number(f.yearStart));
    if (f.yearEnd) results = results.filter(i => Number(i.year || 0) <= Number(f.yearEnd));
    if (f.scoreMin) results = results.filter(i => Number(i.rating?.average || i.score || 0) >= Number(f.scoreMin));
    if (f.scoreMax) results = results.filter(i => Number(i.rating?.average || i.score || 0) <= Number(f.scoreMax));

    // 4. Sort
    const key = f.sort || 'popularity';
    const ord = f.order === 'asc' ? 1 : -1;
    results.sort((a, b) => {
        const getVal = (obj, k) => {
            if (k === 'score') return obj.rating?.average || obj.score || 0;
            if (k === 'year') return obj.year || 0;
            if (k === 'chapters') return obj.chapters || 0;
            if (k === 'title') return String(obj.title || '');
            return obj.popularity || obj.rank || obj.rating?.count || 0;
        };
        const valA = getVal(a, key);
        const valB = getVal(b, key);
        if (key === 'title') return valA.localeCompare(valB) * ord;
        return (valA - valB) * ord;
    });

    return results;
}
