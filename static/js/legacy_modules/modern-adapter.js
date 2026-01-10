/**
 * Modern Design Adapter
 * Bridges new editorial design with existing functionality
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => {
    // Map new navigation buttons to view switching
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active from all nav items
            navItems.forEach(ni => ni.classList.remove('active'));
            // Add active to clicked item
            item.classList.add('active');

            // Get view name and trigger existing view switching
            const view = item.dataset.view;
            if (view) {
                window.dispatchEvent(new CustomEvent('showView', {
                    detail: { view }
                }));
            }

            // Close mobile menu if open
            if (window.innerWidth <= 768) {
                document.getElementById('sidebar')?.classList.remove('active');
                document.getElementById('sidebar-overlay')?.classList.remove('active');
            }
        });
    });

    // Map filter buttons
    const filterBtns = document.querySelectorAll('.filter-btn-new');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(fb => fb.classList.remove('active'));
            btn.classList.add('active');

            const filter = btn.dataset.filter;
            // Trigger library reload with filter
            import('./library.js').then(lib => {
                lib.loadLibrary(filter);
            });
        });
    });

    // Enhance manga cards with new styling
    const observeCards = () => {
        const resultsGrid = document.getElementById('results-grid');
        const libraryGrid = document.getElementById('library-grid');

        const applyNewCardStyles = (grid) => {
            if (!grid) return;

            const cards = grid.querySelectorAll('.manga-card');
            cards.forEach(card => {
                // Add new class if not already present
                if (!card.classList.contains('manga-card-new')) {
                    card.classList.add('manga-card-new');
                }

                // Update cover class
                const cover = card.querySelector('.manga-card-cover');
                if (cover && !cover.classList.contains('manga-cover-new')) {
                    cover.classList.add('manga-cover-new');
                }

                // Update title class
                const title = card.querySelector('.manga-card-title');
                if (title && !title.classList.contains('manga-title-new')) {
                    title.classList.add('manga-title-new');
                }

                // Update button classes
                const buttons = card.querySelectorAll('.add-btn, .glass-btn');
                buttons.forEach(btn => {
                    if (!btn.classList.contains('add-btn-new')) {
                        btn.classList.add('add-btn-new');
                    }
                });

                // Update rating
                const rating = card.querySelector('.manga-card-rating');
                if (rating && !rating.classList.contains('manga-rating-new')) {
                    rating.classList.add('manga-rating-new');
                }
            });
        };

        // Initial application
        applyNewCardStyles(resultsGrid);
        applyNewCardStyles(libraryGrid);

        // Watch for new cards being added
        const observer = new MutationObserver(() => {
            applyNewCardStyles(resultsGrid);
            applyNewCardStyles(libraryGrid);
        });

        if (resultsGrid) {
            observer.observe(resultsGrid, { childList: true, subtree: true });
        }
        if (libraryGrid) {
            observer.observe(libraryGrid, { childList: true, subtree: true });
        }
    };

    // Start observing after a short delay to let main.js initialize
    setTimeout(observeCards, 500);

    // Update trending count when results load
    const updateTrendingCount = () => {
        const resultsGrid = document.getElementById('results-grid');
        const counter = document.getElementById('trending-count');
        if (resultsGrid && counter) {
            const cards = resultsGrid.querySelectorAll('.manga-card');
            if (cards.length > 0) {
                counter.textContent = cards.length;
            }
        }
    };

    // Watch for results being loaded
    const resultsObserver = new MutationObserver(updateTrendingCount);
    const resultsGrid = document.getElementById('results-grid');
    if (resultsGrid) {
        resultsObserver.observe(resultsGrid, { childList: true });
    }
});
