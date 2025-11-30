# 👑 MangaNegus v2.1

A native manga downloader, library manager, and **in-app reader** for iOS Code App. Run a local Python server to search MangaDex, track reading progress, read chapters online, and bulk-download as .cbz files.

![MangaNegus](https://img.shields.io/badge/version-2.1-red)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![Flask](https://img.shields.io/badge/flask-3.0-green)

**Author:** [@bookers1897](https://github.com/bookers1897)  
**Repository:** [github.com/bookers1897/Manga-Negus](https://github.com/bookers1897/Manga-Negus)

---

## ✨ What's New in v2.1

### 🐛 Bug Fixes
- **Fixed:** Start/End chapter inputs no longer overflow on mobile devices (iPhone)
- **Fixed:** Console panel now slides smoothly with proper cubic-bezier animation
- **Fixed:** Improved API error handling - chapters should load more reliably now
- **Fixed:** Added retry logic for failed requests (rate limiting, timeouts)

### 🎨 UI/UX Improvements
- **Hamburger Navigation:** Slide-out menu for cleaner mobile experience
- **Manga Cover Art:** Covers now display in search results and library
- **Animated Background:** Subtle ambient gradient animation
- **Footer with Socials:** GitHub link and author credit
- **iOS Liquid Glass Design:** Refined glassmorphism throughout

### 📖 New Features
- **In-App Manga Reader:** Read chapters directly in the browser!
  - Stream from MangaDex (no download required)
  - Read downloaded CBZ files (coming soon)
  - HD/SD quality toggle (data saver mode)
  - Chapter navigation (prev/next)
- **Reading Progress Tracking:** Saves your last read chapter
- **Downloaded Chapter Indicators:** See which chapters you already have

### 🛠️ Code Quality
- **Separated CSS:** Styles moved to `static/css/styles.css`
- **Comprehensive Comments:** Every function documented with purpose and parameters
- **Improved Efficiency:** Better API error handling, reduced redundant calls

---

## 📁 Project Structure

```
manga-negus/
├── app.py                      # Flask backend server (fully commented)
├── library.json                # User's saved manga library
├── templates/
│   └── index.html              # Main UI template
└── static/
    ├── css/
    │   └── styles.css          # All styles (fully commented)
    ├── images/
    │   └── sharingan.png       # App logo (add your own!)
    └── downloads/              # Downloaded .cbz files
```

---

## 🚀 Installation

### Prerequisites
- **iOS Code App** ([App Store](https://apps.apple.com/us/app/code-app/id1512938504))
- Python 3.8+

### Setup Steps

1. **Clone or download** the project into Code App:
   ```bash
   git clone https://github.com/bookers1897/Manga-Negus.git
   cd Manga-Negus
   ```

2. **Install dependencies** (iOS-compatible versions):
   ```bash
   pip install markupsafe==2.1.3
   pip install werkzeug==3.0.1
   pip install flask==3.0.0
   pip install requests
   pip install charset-normalizer
   ```

3. **Add your logo** (optional):
   - Place `sharingan.png` in `static/images/`
   - Or use any PNG image and rename it

4. **Run the server:**
   ```bash
   python app.py
   ```

5. **Open in Safari:**
   ```
   http://127.0.0.1:5000
   ```

---

## 📱 Features

### 🔍 Search & Discovery
- Search MangaDex's entire library
- Browse trending/popular manga
- Cover art displayed for all results

### 📚 Library Management
- **Currently Reading** - Manga you're actively reading
- **Want to Read** - Your planned reading list
- **Completed** - Finished manga
- Reading progress tracking (last chapter read)

### 📖 In-App Reader
- **Stream chapters** directly from MangaDex
- **HD/SD toggle** for slower connections
- **Chapter navigation** (previous/next)
- Progress automatically saved

### ⬇️ Downloads
- Download individual chapters
- Batch download by range (Ch. 1-50)
- Select multiple chapters manually
- Auto-packaged as .cbz files

### 🎛️ Console
- Real-time download progress
- System logs and errors
- Resizable panel

---

## 🎨 Customization

### Changing the Logo
Replace `static/images/sharingan.png` with any PNG image.

### Changing the App Name
Edit line in `templates/index.html`:
```html
<h1 class="app-title">漫画キング</h1>
```

### Changing the Accent Color
Edit `static/css/styles.css`:
```css
:root {
    --accent-color: #ff453a;        /* Primary accent */
    --accent-glow: rgba(255, 69, 58, 0.4);  /* Glow effect */
}
```

### Adding Anime Background
In `templates/index.html`, find the `anime-bg` div and add:
```javascript
document.getElementById('anime-bg').style.backgroundImage = 'url(/static/images/your-anime.png)';
```

---

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/library` | GET | Get user's library |
| `/api/save` | POST | Add manga to library |
| `/api/delete` | POST | Remove from library |
| `/api/update_status` | POST | Update reading status |
| `/api/update_progress` | POST | Save last read chapter |
| `/api/popular` | GET | Get trending manga |
| `/api/search` | POST | Search by title |
| `/api/chapters` | POST | Get chapters (paginated) |
| `/api/all_chapters` | POST | Get all chapters |
| `/api/chapter_pages` | POST | Get page URLs for reader |
| `/api/download` | POST | Start chapter download |
| `/api/logs` | GET | Get console messages |

---

## 🗺️ Roadmap (Future Features)

- [ ] **Offline CBZ Reader** - Read downloaded files in-app
- [ ] **Search Filters** - Genre, status, year
- [ ] **Pull-to-Refresh** - Native mobile feel
- [ ] **Chapter Read Markers** - Visual indicators
- [ ] **Night Shift Mode** - Warm tones for nighttime reading
- [ ] **Swipe Gestures** - Swipe between pages/chapters
- [ ] **Image Preloading** - Smoother reading experience
- [ ] **Settings Page** - Customize reader behavior

---

## 🤝 Contributing

Contributions welcome! Feel free to:
- Report bugs via GitHub Issues
- Submit feature requests
- Create pull requests

---

## 📄 License

MIT License - feel free to use and modify!

---

## 🙏 Acknowledgments

- [MangaDex](https://mangadex.org/) for the API
- [Phosphor Icons](https://phosphoricons.com/) for the icon set
- [Tailwind CSS](https://tailwindcss.com/) for utility classes

---

**Made with ❤️ by [@bookers1897](https://github.com/bookers1897)**
