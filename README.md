# 漫画キング (Manga King)

A native manga downloader and library manager for iOS Code App. Run a local Python server to search MangaDex, track reading progress, and bulk-download chapters as .cbz files directly to your device storage.

## 🆕 Updates in This Version

### UI/UX Improvements
- **iOS Liquid Glass Design** - Completely revamped UI with modern glassmorphism inspired by iOS design language
- **Compact Header** - Reduced padding, smaller logo, more efficient use of screen space
- **Japanese Title** - Header now shows "漫画キング" (Manga King)
- **Square Navigation Buttons** - Replaced oval buttons with rounded squares (9x9 with rounded-xl)
- **Inline Navigation** - Search and Library buttons are now in the header (no more hamburger menu needed)
- **Toggle Console** - Console is now hidden by default with a floating toggle button in the bottom-right corner
- **Better Spacing** - Reduced padding throughout the entire app for a tighter, more modern feel

### Chapter Loading Fixes
- **Pagination Support** - Large manga (Naruto, One Piece, etc.) now load in batches of 100 chapters
- **Load More Button** - Easily load additional chapters when available
- **Grid Layout** - Chapters now display in a responsive grid (2-4+ columns depending on screen width) instead of a single column
- **Full Download Support** - When downloading a range, the app fetches ALL chapters even if they're not displayed yet

### Bug Fixes
- **Logo Path Fixed** - Uses proper Flask syntax: `{{ url_for('static', filename='images/sharingan.png') }}`
- **Fallback Icon** - Shows a styled eye icon if the logo image fails to load

## 📁 Project Structure

```
manga-negus/
├── app.py                          # Flask backend
├── library.json                    # Your saved manga library
├── templates/
│   └── index.html                  # Main UI
└── static/
    ├── images/
    │   └── sharingan.png          # ⚠️ YOU NEED TO ADD THIS
    └── downloads/                  # Downloaded .cbz files appear here
```

## ⚠️ IMPORTANT: Logo Setup

The logo won't appear until you place `sharingan.png` in the correct location:

1. Create the folder: `static/images/`
2. Copy your `sharingan.png` file into `static/images/`

The full path should be: `manga-negus/static/images/sharingan.png`

## 🚀 Installation

1. Open **Code App** on your iOS device
2. Create a folder named `manga-negus`
3. Copy all project files into the folder
4. Install dependencies:

```bash
pip install markupsafe==2.1.3
pip install werkzeug==3.0.1
pip install flask==3.0.0
pip install requests
pip install charset-normalizer
```

5. Run the server:

```bash
python app.py
```

6. Open Safari and go to: `http://127.0.0.1:5000`

## ✨ Features

- **🔍 MangaDex Search** - Search the entire MangaDex library
- **📚 Library Management** - Organize into Reading, Want to Read, and Completed
- **⬇️ Batch Downloads** - Download chapters individually, by range, or select multiple
- **📂 CBZ Export** - Automatically packages chapters into .cbz files
- **🎛️ Live Console** - Toggle-able log panel to monitor download progress
- **🌙 Dark/Light Theme** - iOS-style theme switcher

## 🎨 Customization

### Changing the Logo
Replace `static/images/sharingan.png` with any PNG image you like.

### Changing the App Name
Edit line 100 in `templates/index.html`:
```html
<h1 class="text-lg font-bold tracking-tight">漫画キング</h1>
```

### Changing the Accent Color
In the CSS variables (`:root` section), modify:
```css
--accent-color: #ff453a;  /* Change this hex value */
--accent-glow: rgba(255, 69, 58, 0.4);  /* Match the RGB values */
```
