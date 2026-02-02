# Manga Grid Compact View Fix - NEG-66

**Linear Issue:** [NEG-66](https://linear.app/negus-domain/issue/NEG-66/frontend-mobile-ui-compatibility-issues-manga-grid-compact-view)
**Status:** Done
**Priority:** High
**Labels:** Frontend, Mobile, CSS, HTML

---

## Problem Description

The manga grid compact view showed 3 manga card columns, but the 3rd column on the right was being cut off on mobile devices (tested on iPhone 14 Plus). When users switched to compact view in the settings, the rightmost column would overflow beyond the screen edge.

## Root Cause Analysis

The grid was using `1fr` for column sizing which has an implicit `min-width: auto`. This prevents columns from shrinking below their content size, causing overflow when there isn't enough space.

```css
/* PROBLEMATIC CODE */
.manga-grid {
  grid-template-columns: repeat(var(--grid-cols), 1fr);
}
```

Additionally:
- Cards didn't have `min-width: 0` to allow shrinking
- Card covers used fixed heights instead of responsive aspect ratios
- Card content (title, info) couldn't shrink with the card

## Solution

### 1. Fixed Grid Column Sizing

Changed from `1fr` to `minmax(0, 1fr)` to allow columns to shrink below content size:

```css
/* FIXED CODE */
.manga-grid {
  --grid-cols: 2;
  display: grid;
  grid-template-columns: repeat(var(--grid-cols), minmax(0, 1fr));
  gap: 12px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
```

### 2. Updated Card Structure

Changed card from flexbox to grid and added `min-width: 0`:

```css
/* BEFORE */
.card {
  display: flex;
  flex-direction: column;
}

/* AFTER */
.card {
  display: grid;
  grid-template-rows: auto 1fr;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}
```

### 3. Responsive Card Cover

Changed from fixed height to aspect ratio:

```css
/* BEFORE */
.card-cover {
  height: 180px;
}
.density-compact .card-cover {
  height: 150px;
}

/* AFTER */
.card-cover {
  aspect-ratio: 2/3;
  min-width: 0;
  width: 100%;
}
.density-compact .card-cover {
  aspect-ratio: 2/3;
}
```

### 4. Card Info Section

Updated to use grid and allow shrinking:

```css
/* BEFORE */
.card-info {
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* AFTER */
.card-info {
  padding: 12px;
  display: grid;
  grid-template-rows: auto;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}
```

### 5. Card Title

Added shrinking capability:

```css
.card-title {
  font-size: 14px;
  min-width: 0;
  word-break: break-word;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

### 6. Compact Density Specific Styles

Added scaling styles for compact view:

```css
.density-compact .card-info {
  padding: 8px;
  gap: 4px;
}
.density-compact .card-title {
  font-size: 12px;
  -webkit-line-clamp: 2;
}
.density-compact .card-author,
.density-compact .card-meta {
  font-size: 10px;
}
.density-compact .card-footer {
  padding-top: 6px;
  font-size: 10px;
}
```

## Key Technical Insight

The critical fix was understanding that CSS Grid's `1fr` unit has an implicit minimum of `auto` (content size). Using `minmax(0, 1fr)` explicitly sets the minimum to 0, allowing columns to shrink as needed.

From CSS-Tricks research:
> "When you use `1fr`, you're really saying `minmax(auto, 1fr)`. The `auto` means the column can't shrink smaller than its content. Using `minmax(0, 1fr)` allows the column to shrink to 0."

## Files Modified

- `static/css/styles.css` - Grid system, card styles, density-specific styles

## Testing

1. Navigate to the site on a mobile device (iPhone 14 Plus or similar)
2. Go to Settings > Grid Density > Compact
3. Verify all 3 columns are visible without horizontal scrolling
4. Verify card content scales proportionally with card size
