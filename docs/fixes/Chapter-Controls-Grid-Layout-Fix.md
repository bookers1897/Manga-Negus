# Chapter Controls Grid Layout Fix

**Related to:** NEG-65 (Manga Info Area UI)
**Status:** Done
**Priority:** High
**Labels:** Frontend, Mobile, CSS

---

## Problem Description

The chapter control buttons (Select All, Deselect All, Download Selected, Download Next 5) were:
- Being cut off on the right side of the screen on mobile
- Not properly aligned in a grid
- Different sizes
- Icons and text not centered

## Root Cause Analysis

1. Parent container `.chapters-header` used flexbox with `align-items: flex-start` which prevented child grid from taking full width
2. Grid used `1fr` instead of `minmax(0, 1fr)` causing overflow
3. Buttons didn't have `min-width: 0` to allow shrinking

## Solution

### 1. Updated HTML Structure

Changed to semantic grid with larger icons:

```html
<!-- BEFORE -->
<div class="chapters-controls">
  <button class="control-btn" id="select-all-chapters">
    <i data-lucide="check-square" width="14"></i>
    Select All
  </button>
  <!-- ... -->
</div>

<!-- AFTER -->
<div class="chapters-controls-grid">
  <button class="chapter-action-btn" id="select-all-chapters">
    <i data-lucide="check-square" width="18"></i>
    <span>Select All</span>
  </button>
  <button class="chapter-action-btn" id="deselect-all-chapters">
    <i data-lucide="square" width="18"></i>
    <span>Deselect All</span>
  </button>
  <button class="chapter-action-btn primary" id="download-selected-btn">
    <i data-lucide="download" width="18"></i>
    <span>Download Selected</span>
  </button>
  <button class="chapter-action-btn" id="download-next-chapters-btn">
    <i data-lucide="fast-forward" width="18"></i>
    <span>Download Next 5</span>
  </button>
</div>
```

### 2. Parent Container - Changed to Grid

```css
/* BEFORE: Flexbox causing width issues */
.chapters-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

/* AFTER: Grid allows full width children */
.chapters-header {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  margin-bottom: 24px;
  width: 100%;
  max-width: 100%;
}
@media (min-width: 768px) {
  .chapters-header {
    grid-template-columns: auto 1fr;
    align-items: center;
  }
  .chapters-controls-grid {
    justify-self: end;
  }
}
```

### 3. 2x2 Button Grid with Overflow Prevention

```css
.chapters-controls-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  margin-top: 16px;
}
```

### 4. Button Styling - Centered Content

```css
.chapter-action-btn {
  display: grid;
  place-items: center;
  place-content: center;
  grid-auto-flow: column;
  gap: 6px;
  padding: 12px 8px;
  min-height: 48px;
  min-width: 0;
  width: 100%;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border-glass);
  border-radius: 8px;
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  overflow: hidden;
  box-sizing: border-box;
}

.chapter-action-btn.primary {
  background: var(--red-primary);
  border-color: var(--red-primary);
}

.chapter-action-btn span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

### 5. Desktop Layout

```css
@media (min-width: 768px) {
  .chapters-controls-grid {
    width: auto;
    grid-template-columns: repeat(4, minmax(0, auto));
    margin-top: 0;
  }
  .chapter-action-btn {
    padding: 10px 16px;
    min-height: 42px;
  }
}
```

## Layout Result

**Mobile (2x2 Grid):**
```
┌─────────────────┬─────────────────┐
│   Select All    │  Deselect All   │
├─────────────────┼─────────────────┤
│Download Selected│ Download Next 5 │
└─────────────────┴─────────────────┘
```

**Desktop (1x4 Row):**
```
┌────────────┬─────────────┬─────────────────┬────────────────┐
│ Select All │ Deselect All│ Download Selected│ Download Next 5│
└────────────┴─────────────┴─────────────────┴────────────────┘
```

## Key Technical Insights

1. **`minmax(0, 1fr)` is critical** - Using just `1fr` has implicit `min-width: auto` that prevents shrinking
2. **Parent containers matter** - Flexbox with `align-items: flex-start` prevents children from taking full width
3. **`min-width: 0` on grid items** - Required to allow items to shrink below content size
4. **`box-sizing: border-box`** - Ensures padding is included in width calculations

## Files Modified

- `templates/index.html` - New button structure with spans
- `static/css/styles.css` - Grid-based layout for header and controls

## Testing

1. Open manga details on mobile
2. Scroll to Chapters section
3. Verify all 4 buttons are visible in 2x2 grid
4. Verify buttons are equal size
5. Verify icons and text are centered
6. Verify no horizontal overflow/cutoff
