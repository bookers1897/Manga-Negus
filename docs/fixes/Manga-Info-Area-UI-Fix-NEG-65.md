# Manga Info Area UI Fix - NEG-65

**Linear Issue:** [NEG-65](https://linear.app/negus-domain/issue/NEG-65/manga-info-area-ui-needs-fixing)
**Status:** Done
**Priority:** High
**Labels:** Urgent, Mobile, CSS, HTML, JavaScript, Frontend

---

## Problem Description

When clicking on a manga to view details on mobile (iPhone 17 Pro), the layout of buttons and inputs was broken:
- Add to Library, Favorite, Mark All Read, Download buttons were stacked and overlapping
- Rating slider, Notes, Review, Share Review, Collections inputs were cluttered
- Buttons were different sizes and not aligned
- Layout looked messy and unprofessional on mobile

## Elements Removed (Per User Request)

1. Favorites Button
2. Notes Area/Input
3. Share Review Button
4. Collections Input
5. Download Next 5 / Download All buttons (already exist in chapters section)
6. Rating Slider (replaced with 5-star rating, then removed entirely for simplicity)
7. Review Textarea

## Solution

### 1. Simplified HTML Structure

Removed clutter and kept only essential elements:

```html
<!-- BEFORE: Cluttered with many inputs -->
<div class="details-actions">
  <button id="add-to-library-btn">Add to Library</button>
  <button id="favorite-btn">Favorite</button>
  <button id="mark-all-read-btn">Mark All Read</button>
  <button id="download-next-btn">Download Next 5</button>
  <button id="download-all-btn">Download All</button>
</div>
<div class="details-notes">
  <textarea id="notes-input"></textarea>
  <input type="range" id="rating-input" />
  <textarea id="review-input"></textarea>
  <button id="share-review-btn">Share Review</button>
  <input id="collections-input" />
</div>

<!-- AFTER: Clean and focused -->
<div class="details-actions">
  <button class="action-btn" id="add-to-library-btn">
    <i data-lucide="heart" width="18"></i>
    Add to Library
  </button>
  <button class="action-btn secondary" id="mark-all-read-btn">
    <i data-lucide="check-circle" width="18"></i>
    Mark All Read
  </button>
</div>
```

### 2. CSS Grid Layout for Buttons

Changed from broken flexbox to proper CSS Grid:

```css
/* BEFORE: Flexbox causing overlap */
.details-actions {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

/* AFTER: CSS Grid with equal columns */
.details-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
  max-width: 100%;
  margin-top: 8px;
}
.details-actions .action-btn {
  display: grid;
  place-items: center;
  place-content: center;
  grid-auto-flow: column;
  gap: 8px;
  padding: 12px 16px;
  font-size: 14px;
  min-width: 0;
  width: 100%;
}
```

### 3. Mobile-First Details Card

Restructured the entire details header for mobile:

```css
.details-card {
  background: var(--bg-card);
  border: 1px solid var(--border-glass);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

/* Cover centered on mobile */
.details-cover {
  width: 140px;
  height: 200px;
  margin: 0 auto;
  border-radius: 6px;
}

/* Title and info centered */
.details-info {
  text-align: center;
}
.details-title {
  font-size: 18px;
  font-weight: 700;
}
```

### 4. Expandable Description

Added truncation with "Show more" functionality:

```css
.details-desc {
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.details-desc.expanded {
  display: block;
  -webkit-line-clamp: unset;
}
.details-expand-btn {
  background: none;
  border: none;
  color: var(--red-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
```

### 5. JavaScript Updates

Updated element references and expand functionality:

```javascript
// Element references updated
els.expandDescBtn = document.getElementById('expand-desc-btn');

// Expand/collapse handler
if (els.expandDescBtn) {
  els.expandDescBtn.addEventListener('click', () => {
    const isExpanded = els.detailsDescription.classList.contains('expanded');
    els.detailsDescription.classList.toggle('expanded', !isExpanded);
    els.expandDescBtn.textContent = isExpanded ? 'Show more' : 'Show less';
  });
}

// Reset on new manga load
els.detailsDescription.classList.remove('expanded');
if (els.expandDescBtn) {
  els.expandDescBtn.textContent = 'Show more';
}
```

### 6. Desktop Responsive Styles

Side-by-side layout on larger screens:

```css
@media (min-width: 768px) {
  .details-card {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 24px;
    text-align: left;
  }
  .details-cover {
    width: 180px;
    height: 260px;
    margin: 0;
  }
  .details-actions {
    grid-template-columns: repeat(2, auto);
    justify-content: start;
    width: auto;
  }
}
```

## Files Modified

- `templates/index.html` - Removed clutter, simplified structure
- `static/css/styles.css` - New grid-based layout, mobile-first styles
- `static/js/main.js` - Updated element references, expand functionality

## Testing

1. Open manga details on mobile device
2. Verify cover image is centered at top
3. Verify title and meta are centered below cover
4. Verify description truncates with "Show more" button
5. Verify both buttons are side-by-side, equal size
6. Verify proper spacing from chapters section below

## Before/After

**Before:** Buttons overlapping, inputs cluttered, messy layout
**After:** Clean 2-button row, centered content, expandable description
