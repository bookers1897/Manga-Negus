/**
 * Virtual Scroll Module for MangaNegus
 *
 * Renders only visible items in a large list, recycling DOM nodes
 * as the user scrolls. This prevents memory issues with large libraries.
 *
 * Features:
 * - Only renders visible items + buffer
 * - Recycles DOM nodes instead of creating/destroying
 * - Supports variable height items
 * - Smooth scroll with momentum
 * - ResizeObserver for responsive grids
 *
 * Usage:
 *   const vs = new VirtualScroll({
 *       container: document.getElementById('library-grid'),
 *       itemHeight: 320,
 *       itemWidth: 200,
 *       buffer: 2,
 *       renderItem: (item, element) => { ... }
 *   });
 *   vs.setItems(libraryArray);
 */

export class VirtualScroll {
    constructor(options) {
        this.container = options.container;
        this.itemHeight = options.itemHeight || 320;
        this.itemWidth = options.itemWidth || 200;
        this.gap = options.gap || 16;
        this.buffer = options.buffer || 2; // Extra rows above/below viewport
        this.renderItem = options.renderItem;
        this.onItemClick = options.onItemClick;

        this.items = [];
        this.visibleNodes = new Map(); // index -> DOM node
        this.nodePool = []; // Recycled nodes
        this.columns = 1;
        this.scrollTop = 0;
        this.containerHeight = 0;

        this._scrollRAF = null;
        this._resizeObserver = null;
        this._scrollHandler = null;

        this._init();
    }

    _init() {
        // Create scroll container structure
        this.container.style.position = 'relative';
        this.container.style.overflow = 'auto';

        // Spacer element to create scroll height
        this.spacer = document.createElement('div');
        this.spacer.style.position = 'absolute';
        this.spacer.style.top = '0';
        this.spacer.style.left = '0';
        this.spacer.style.width = '100%';
        this.spacer.style.pointerEvents = 'none';
        this.container.appendChild(this.spacer);

        // Content container for visible items
        this.content = document.createElement('div');
        this.content.className = 'virtual-scroll-content';
        this.content.style.position = 'relative';
        this.content.style.width = '100%';
        this.container.appendChild(this.content);

        // Bind scroll handler with throttling
        this._scrollHandler = this._onScroll.bind(this);
        this.container.addEventListener('scroll', this._scrollHandler, { passive: true });

        // Watch for container resize
        this._resizeObserver = new ResizeObserver(entries => {
            for (const entry of entries) {
                this._onResize(entry.contentRect.width, entry.contentRect.height);
            }
        });
        this._resizeObserver.observe(this.container);

        // Initial layout
        this._calculateLayout();
    }

    /**
     * Set the items to display.
     */
    setItems(items) {
        this.items = items || [];
        this._calculateLayout();
        this._render();
    }

    /**
     * Update a single item at index.
     */
    updateItem(index, item) {
        if (index >= 0 && index < this.items.length) {
            this.items[index] = item;
            const node = this.visibleNodes.get(index);
            if (node) {
                this.renderItem(item, node, index);
            }
        }
    }

    /**
     * Scroll to a specific item index.
     */
    scrollToIndex(index) {
        const row = Math.floor(index / this.columns);
        const targetY = row * (this.itemHeight + this.gap);
        this.container.scrollTop = targetY;
    }

    /**
     * Refresh the display (after filter/sort).
     */
    refresh() {
        this._calculateLayout();
        this._render();
    }

    /**
     * Destroy and clean up.
     */
    destroy() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
        }
        if (this._scrollHandler) {
            this.container.removeEventListener('scroll', this._scrollHandler);
        }
        if (this._scrollRAF) {
            cancelAnimationFrame(this._scrollRAF);
        }
        this.content.innerHTML = '';
        this.spacer.remove();
        this.visibleNodes.clear();
        this.nodePool = [];
    }

    _calculateLayout() {
        const containerWidth = this.container.clientWidth;
        this.containerHeight = this.container.clientHeight;

        // Calculate number of columns
        this.columns = Math.max(1, Math.floor((containerWidth + this.gap) / (this.itemWidth + this.gap)));

        // Calculate total height
        const rowCount = Math.ceil(this.items.length / this.columns);
        const totalHeight = rowCount * (this.itemHeight + this.gap) - this.gap;

        this.spacer.style.height = `${Math.max(totalHeight, 0)}px`;
    }

    _onScroll() {
        // Throttle with RAF
        if (this._scrollRAF) return;

        this._scrollRAF = requestAnimationFrame(() => {
            this._scrollRAF = null;
            this.scrollTop = this.container.scrollTop;
            this._render();
        });
    }

    _onResize(width, height) {
        this.containerHeight = height;
        this._calculateLayout();
        this._render();
    }

    _render() {
        const rowHeight = this.itemHeight + this.gap;

        // Calculate visible range
        const firstVisibleRow = Math.floor(this.scrollTop / rowHeight);
        const lastVisibleRow = Math.ceil((this.scrollTop + this.containerHeight) / rowHeight);

        // Add buffer
        const startRow = Math.max(0, firstVisibleRow - this.buffer);
        const endRow = Math.min(
            Math.ceil(this.items.length / this.columns),
            lastVisibleRow + this.buffer
        );

        const startIndex = startRow * this.columns;
        const endIndex = Math.min(endRow * this.columns, this.items.length);

        // Track which indices should be visible
        const shouldBeVisible = new Set();
        for (let i = startIndex; i < endIndex; i++) {
            shouldBeVisible.add(i);
        }

        // Remove nodes that are no longer visible
        for (const [index, node] of this.visibleNodes) {
            if (!shouldBeVisible.has(index)) {
                this.visibleNodes.delete(index);
                node.style.display = 'none';
                this.nodePool.push(node);
            }
        }

        // Add/update visible nodes
        for (let i = startIndex; i < endIndex; i++) {
            const item = this.items[i];
            if (!item) continue;

            let node = this.visibleNodes.get(i);

            if (!node) {
                // Get from pool or create new
                node = this.nodePool.pop() || this._createNode();
                node.style.display = '';
                this.visibleNodes.set(i, node);
            }

            // Position the node
            const row = Math.floor(i / this.columns);
            const col = i % this.columns;
            const x = col * (this.itemWidth + this.gap);
            const y = row * rowHeight;

            node.style.transform = `translate(${x}px, ${y}px)`;
            node.dataset.index = i;

            // Render content
            this.renderItem(item, node, i);
        }
    }

    _createNode() {
        const node = document.createElement('div');
        node.className = 'virtual-scroll-item';
        node.style.position = 'absolute';
        node.style.width = `${this.itemWidth}px`;
        node.style.height = `${this.itemHeight}px`;
        node.style.top = '0';
        node.style.left = '0';
        node.style.willChange = 'transform';

        // Click handler
        if (this.onItemClick) {
            node.addEventListener('click', (e) => {
                const index = parseInt(node.dataset.index, 10);
                if (!isNaN(index) && this.items[index]) {
                    this.onItemClick(this.items[index], index, e);
                }
            });
        }

        this.content.appendChild(node);
        return node;
    }
}

/**
 * Helper to create a virtual scroll grid for manga cards.
 */
export function createMangaGrid(container, options = {}) {
    const {
        itemHeight = 320,
        itemWidth = 200,
        gap = 16,
        buffer = 2,
        onCardClick,
        onCardMenu,
        renderCard // Function to render card HTML
    } = options;

    const vs = new VirtualScroll({
        container,
        itemHeight,
        itemWidth,
        gap,
        buffer,
        renderItem: (manga, node, index) => {
            // If renderCard is provided, use it
            if (renderCard) {
                node.innerHTML = renderCard(manga, index);
            } else {
                // Default simple render
                node.innerHTML = `
                    <div class="manga-card" data-index="${index}">
                        <img src="${manga.cover_url || ''}" alt="${manga.title || ''}" loading="lazy" />
                        <div class="card-title">${manga.title || 'Unknown'}</div>
                    </div>
                `;
            }

            // Rebind icons if using Lucide
            if (window.lucide) {
                window.lucide.createIcons({ nodes: [node] });
            }
        },
        onItemClick: onCardClick
    });

    return vs;
}

export default VirtualScroll;
