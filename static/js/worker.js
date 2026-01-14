// Web Worker for Heavy Filtering Computations
// Offloads filtering logic from main thread to prevent UI freezing

self.onmessage = function(e) {
    const { list, filters, hiddenManga, searchQuery } = e.data;
    if (!list || !Array.isArray(list)) {
        self.postMessage([]);
        return;
    }

    const f = filters;
    const hiddenSet = new Set(hiddenManga || []);
    let results = [...list];

    // Helper: Is Hidden
    const isHidden = (id, src) => hiddenSet.has(`${src}:${id}`);

    // 1. Filter Hidden & Source
    results = results.filter(item => {
        const id = item.mal_id || item.id || item.manga_id;
        const src = item.source || item.source_id || (item.mal_id ? 'jikan' : '');
        if (id && src && isHidden(id, src)) return false;
        if (f.source && searchQuery && src !== f.source) return false;
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

    self.postMessage(results);
};
