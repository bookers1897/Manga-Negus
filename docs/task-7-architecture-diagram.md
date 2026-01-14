# Task 7: Multi-Select Mode - Architecture Diagram

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Library Grid (Normal Mode)                  │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        │  │
│  │  │ Card 1 │  │ Card 2 │  │ Card 3 │  │ Card 4 │        │  │
│  │  │  [⋮]   │  │  [⋮]   │  │  [⋮]   │  │  [⋮]   │        │  │
│  │  └────────┘  └────────┘  └────────┘  └────────┘        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│                          ↓ Click "⋮" → "Select Multiple"       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Library Grid (Selection Mode)                  │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        │  │
│  │  │[✓]Card1│  │[ ]Card2│  │[✓]Card3│  │[ ]Card4│        │  │
│  │  │  [⋮]   │  │  [⋮]   │  │  [⋮]   │  │  [⋮]   │        │  │
│  │  └────────┘  └────────┘  └────────┘  └────────┘        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            Selection Action Bar (Bottom)                 │  │
│  │  "2 selected"  [Delete Selected]  [Queue]  [Cancel]     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
User Action                State Update              UI Update
───────────               ──────────────             ─────────

Click "Select
Multiple"
    │
    ├──> enterSelectionMode()
    │         │
    │         ├──> state.selectionMode = true
    │         │
    │         ├──> document.body.classList.add('selection-mode')
    │         │
    │         ├──> renderLibraryFromState()     ──> Checkboxes appear
    │         │
    │         └──> els.selectionActionBar.show() ──> Action bar slides up
    │
    │
Click Card 1
    │
    ├──> handleGridClick()
    │         │
    │         ├──> toggleCardSelection('source:id1')
    │         │         │
    │         │         ├──> state.selectedCards.add('source:id1')
    │         │         │
    │         │         ├──> updateSelectionCount()
    │         │         │         │
    │         │         │         └──> els.selectionCount.textContent = "1 selected"
    │         │         │
    │         │         └──> updateCheckboxStates() ──> Checkbox 1 checked
    │         │
    │
Click Card 3
    │
    ├──> handleGridClick()
    │         │
    │         ├──> toggleCardSelection('source:id3')
    │         │         │
    │         │         ├──> state.selectedCards.add('source:id3')
    │         │         │
    │         │         ├──> updateSelectionCount()
    │         │         │         │
    │         │         │         └──> els.selectionCount.textContent = "2 selected"
    │         │         │
    │         │         └──> updateCheckboxStates() ──> Checkbox 3 checked
    │         │
    │
Click "Delete
Selected"
    │
    ├──> deleteSelected()
    │         │
    │         ├──> Show confirm dialog          ──> "Remove 2 manga?"
    │         │
    │         ├──> Promise.all([
    │         │       API.removeFromLibrary('source:id1'),
    │         │       API.removeFromLibrary('source:id3')
    │         │     ])
    │         │
    │         ├──> showToast()                  ──> "Removed 2 manga"
    │         │
    │         ├──> exitSelectionMode()
    │         │         │
    │         │         ├──> state.selectionMode = false
    │         │         │
    │         │         ├──> state.selectedCards.clear()
    │         │         │
    │         │         └──> renderLibraryFromState() ──> Checkboxes disappear
    │         │
    │         └──> loadLibrary()                ──> Library refreshes
```

## State Management

```javascript
// Initial State
state = {
    selectionMode: false,
    selectedCards: new Set()
}

// After Entering Selection Mode
state = {
    selectionMode: true,
    selectedCards: new Set()
}

// After Selecting 2 Cards
state = {
    selectionMode: true,
    selectedCards: new Set([
        'weebcentral-v2:123',
        'mangadex:abc-def-ghi'
    ])
}

// After Deletion/Exit
state = {
    selectionMode: false,
    selectedCards: new Set()
}
```

## Function Call Graph

```
User Interaction
    │
    ├─> Card Menu Click
    │       │
    │       └─> Menu Item: "Select Multiple"
    │               │
    │               └─> enterSelectionMode()
    │                       ├─> state.selectionMode = true
    │                       ├─> state.selectedCards.clear()
    │                       ├─> body.classList.add('selection-mode')
    │                       ├─> renderLibraryFromState()
    │                       │       └─> renderMangaGrid()
    │                       │               └─> Conditional checkbox render
    │                       ├─> els.selectionActionBar.show()
    │                       └─> updateSelectionCount()
    │                               └─> Enable/disable buttons
    │
    ├─> Card Click (in selection mode)
    │       │
    │       └─> handleGridClick()
    │               │
    │               └─> toggleCardSelection(key)
    │                       ├─> Set.add() or Set.delete()
    │                       ├─> updateSelectionCount()
    │                       │       └─> Update count text
    │                       │       └─> Enable/disable buttons
    │                       └─> updateCheckboxStates()
    │                               └─> Sync all checkbox states
    │
    ├─> Delete Selected Click
    │       │
    │       └─> deleteSelected()
    │               ├─> Get Array.from(selectedCards)
    │               ├─> Show confirm() dialog
    │               ├─> Promise.all([API calls])
    │               ├─> showToast()
    │               ├─> exitSelectionMode()
    │               │       ├─> state.selectionMode = false
    │               │       ├─> state.selectedCards.clear()
    │               │       ├─> body.classList.remove('selection-mode')
    │               │       ├─> els.selectionActionBar.hide()
    │               │       └─> renderLibraryFromState()
    │               └─> loadLibrary()
    │
    └─> Cancel Click
            │
            └─> exitSelectionMode()
                    ├─> state.selectionMode = false
                    ├─> state.selectedCards.clear()
                    ├─> body.classList.remove('selection-mode')
                    ├─> els.selectionActionBar.hide()
                    └─> renderLibraryFromState()
```

## Event Flow

```
┌─────────────────────────────────────────────────────────┐
│                    Document Body                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Library Grid Container               │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │          Card (event delegation)            │  │  │
│  │  │  ┌───────────────────────────────────────┐  │  │  │
│  │  │  │     Card Selection Overlay           │  │  │  │
│  │  │  │  ┌─────────────────────────────────┐  │  │  │  │
│  │  │  │  │   Checkbox Input (click)        │  │  │  │  │
│  │  │  │  │   ├─> e.stopPropagation()       │  │  │  │  │
│  │  │  │  │   └─> toggleCardSelection()     │  │  │  │  │
│  │  │  │  └─────────────────────────────────┘  │  │  │  │
│  │  │  └───────────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────────┐  │  │  │
│  │  │  │     Card Cover (click anywhere)      │  │  │  │  │
│  │  │  │   ├─> if (selectionMode)             │  │  │  │  │
│  │  │  │   │   └─> toggleCardSelection()      │  │  │  │  │
│  │  │  │   └─> else                           │  │  │  │  │
│  │  │  │       └─> openMangaDetails()         │  │  │  │  │
│  │  │  └───────────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────────┐  │  │  │
│  │  │  │     Card Menu Button (⋮)             │  │  │  │  │
│  │  │  │   ├─> if (!selectionMode)            │  │  │  │  │
│  │  │  │   │   └─> openCardMenu()             │  │  │  │  │
│  │  │  │   └─> else                           │  │  │  │  │
│  │  │  │       └─> (blocked, selection toggle)│  │  │  │  │
│  │  │  └───────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │          Selection Action Bar (fixed bottom)      │  │
│  │  [Delete Selected] ──> deleteSelected()           │  │
│  │  [Queue Selected]  ──> downloadSelected()         │  │
│  │  [Cancel]          ──> exitSelectionMode()        │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## CSS Class Cascade

```
Normal Mode:
<body>
    <div class="card">
        <div class="card-cover">...</div>
        <div class="card-info">...</div>
    </div>

Selection Mode:
<body class="selection-mode">  ← Added class triggers CSS changes
    <div class="card">
        <div class="card-selection-overlay">  ← Conditionally rendered
            <input type="checkbox" class="card-checkbox" />
        </div>
        <div class="card-cover">...</div>
        <div class="card-info">...</div>
    </div>

    <div class="selection-action-bar">  ← Shown (not .hidden)
        <span class="selection-count">2 selected</span>
        <button class="btn-delete-selected">Delete</button>
        <button class="btn-download-selected">Queue</button>
        <button class="btn-cancel-selection">Cancel</button>
    </div>
```

## API Integration

```
┌──────────────────────────────────────────────────────┐
│              JavaScript (Frontend)                   │
├──────────────────────────────────────────────────────┤
│                                                      │
│  deleteSelected()                                    │
│      │                                               │
│      ├─> keys = ['weebcentral-v2:123', ...]         │
│      │                                               │
│      ├─> Promise.all([                              │
│      │     API.removeFromLibrary('weebcentral-v2:123'),
│      │     API.removeFromLibrary('mangadex:abc'),    │
│      │   ])                                          │
│      │                                               │
│      ↓                                               │
├──────────────────────────────────────────────────────┤
│                    API Module                        │
├──────────────────────────────────────────────────────┤
│                                                      │
│  API.removeFromLibrary(key)                          │
│      │                                               │
│      ├─> DELETE /api/library/delete                 │
│      │    Headers: X-CSRF-Token                     │
│      │    Body: { library_key: "source:id" }       │
│      │                                               │
│      ↓                                               │
├──────────────────────────────────────────────────────┤
│               Flask Backend                          │
├──────────────────────────────────────────────────────┤
│                                                      │
│  @library_bp.route('/library/delete', methods=['DELETE'])
│      │                                               │
│      ├─> Parse library_key                          │
│      │                                               │
│      ├─> session.query(Manga)                       │
│      │      .filter(source_id=source,               │
│      │              source_manga_id=manga_id)       │
│      │      .delete()                               │
│      │                                               │
│      ├─> session.commit()                           │
│      │                                               │
│      ↓                                               │
├──────────────────────────────────────────────────────┤
│             PostgreSQL Database                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│  DELETE FROM manga                                   │
│  WHERE source_id = 'weebcentral-v2'                  │
│    AND source_manga_id = '123';                      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

## Performance Characteristics

```
Operation                  Complexity    Notes
────────────────────────  ───────────   ─────────────────────
Add to selection          O(1)          Set.add()
Remove from selection     O(1)          Set.delete()
Check if selected         O(1)          Set.has()
Get selection count       O(1)          Set.size
Toggle selection          O(1)          Combined ops
Update checkbox states    O(n)          n = number of cards
Delete selected           O(n)          Parallel API calls
Re-render library         O(n)          Re-create DOM
```

## Memory Management

```
Before Selection Mode:
└─> state.selectedCards = new Set()  [size: 0]

During Selection (2 cards):
└─> state.selectedCards = new Set([  [size: 2]
      'weebcentral-v2:123',          [~30 bytes]
      'mangadex:abc-def-ghi'         [~30 bytes]
    ])
    Total: ~60 bytes + Set overhead

After Exit:
└─> state.selectedCards.clear()      [size: 0]
    └─> Garbage collector reclaims memory
```

## Error Handling Flowchart

```
deleteSelected()
    │
    ├─> selectedCards.size === 0?
    │   └─> YES: showToast("No items selected")
    │           └─> return (exit early)
    │
    ├─> Show confirm() dialog
    │   │
    │   ├─> User clicks "Cancel"?
    │   │   └─> YES: return (no deletions)
    │   │
    │   └─> User clicks "OK"
    │       │
    │       ├─> try {
    │       │     Promise.all([API calls])
    │       │     │
    │       │     ├─> All succeed?
    │       │     │   └─> YES: showToast("Removed N manga")
    │       │     │           exitSelectionMode()
    │       │     │           loadLibrary()
    │       │     │
    │       │     └─> Any fail?
    │       │         └─> YES: throw error
    │       │   }
    │       │
    │       └─> catch (error) {
    │             log("❌ Bulk delete failed")
    │             showToast("Some deletions failed")
    │           }
```

## Conclusion

This architecture provides a robust, performant multi-select system with:

- ✅ Clean separation of concerns
- ✅ Efficient data structures (Set for O(1) operations)
- ✅ Event delegation for performance
- ✅ Proper error handling
- ✅ User feedback at every step
- ✅ Graceful degradation
- ✅ Memory cleanup on exit
