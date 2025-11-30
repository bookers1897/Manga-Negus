"""
================================================================================
MangaNegus v2.1 - Backend Server
================================================================================
A Flask-based manga downloader and library manager for iOS Code App.
Connects to MangaDex API for searching, fetching chapters, and downloading.

Author: bookers1897
GitHub: https://github.com/bookers1897/Manga-Negus
================================================================================
"""

import os
import json
import time
import shutil
import zipfile
import threading
import queue
import requests
from flask import Flask, render_template, jsonify, request, send_from_directory

# =============================================================================
# CONFIGURATION
# =============================================================================

# Get the directory where this script is located
# This ensures all file paths are relative to the project root
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize Flask application
# Flask will look for templates in /templates and static files in /static
app = Flask(__name__)

# Thread-safe queue for logging messages
# Messages are added here and polled by the frontend for real-time updates
msg_queue = queue.Queue()

# Directory where downloaded manga chapters (.cbz files) are stored
DOWNLOAD_DIR = os.path.join(BASE_DIR, "static", "downloads")

# JSON file that stores the user's manga library (saved manga and reading status)
LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")

# MangaDex API base URL - all API calls go through this endpoint
BASE_URL = "https://api.mangadex.org"

# Create downloads directory if it doesn't exist
# This prevents errors when trying to save downloaded chapters
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


# =============================================================================
# LOGGING UTILITY
# =============================================================================

def log(msg):
    """
    Log a message to both the console and the message queue.
    
    The message queue is polled by the frontend to display real-time
    progress updates in the console panel.
    
    Args:
        msg (str): The message to log
    """
    print(msg)  # Print to server console for debugging
    timestamp = time.strftime("[%H:%M:%S]")  # Add timestamp for context
    msg_queue.put(f"{timestamp} {msg}")  # Add to queue for frontend


# =============================================================================
# MANGA LOGIC CLASS
# =============================================================================

class MangaLogic:
    """
    Core class handling all manga-related operations.
    
    This class manages:
    - API communication with MangaDex
    - Local library storage (JSON file)
    - Chapter fetching with pagination
    - Background downloading of chapters
    - Cover art retrieval
    """
    
    def __init__(self):
        """
        Initialize the MangaLogic instance.
        
        Creates a persistent requests session with appropriate headers
        to avoid being blocked by MangaDex's anti-bot measures.
        """
        self.session = requests.Session()
        
        # Set a realistic User-Agent header
        # MangaDex may block requests without proper headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
        })
        
        # Cache for cover art URLs to reduce API calls
        # Key: manga_id, Value: cover_url
        self.cover_cache = {}

    # =========================================================================
    # LIBRARY MANAGEMENT
    # =========================================================================
    
    def load_library(self):
        """
        Load the user's manga library from the JSON file.
        
        Returns:
            dict: Dictionary of saved manga with their metadata.
                  Keys are manga IDs, values contain title, status, and cover.
                  Returns empty dict if file doesn't exist or is corrupted.
        """
        if not os.path.exists(LIBRARY_FILE):
            return {}
        
        try:
            with open(LIBRARY_FILE, 'r') as f:
                data = json.load(f)
                
                # Ensure all entries have required fields (backwards compatibility)
                for manga_id, manga_data in data.items():
                    if 'status' not in manga_data:
                        manga_data['status'] = 'reading'
                    if 'cover' not in manga_data:
                        manga_data['cover'] = None
                    if 'last_chapter' not in manga_data:
                        manga_data['last_chapter'] = None
                        
                return data
        except (json.JSONDecodeError, IOError):
            # Return empty library if file is corrupted
            return {}

    def save_to_library(self, manga_id, title, status='reading', cover=None):
        """
        Save or update a manga in the user's library.
        
        Args:
            manga_id (str): MangaDex manga UUID
            title (str): Display title of the manga
            status (str): Reading status ('reading', 'plan_to_read', 'completed')
            cover (str): URL to the manga's cover art (optional)
        """
        db = self.load_library()
        
        # Preserve existing status if not explicitly provided
        current_status = db.get(manga_id, {}).get('status', status)
        current_cover = db.get(manga_id, {}).get('cover', cover)
        current_last_chapter = db.get(manga_id, {}).get('last_chapter', None)
        
        db[manga_id] = {
            "title": title,
            "status": status if status else current_status,
            "cover": cover if cover else current_cover,
            "last_chapter": current_last_chapter
        }
        
        # Write updated library to disk
        with open(LIBRARY_FILE, 'w') as f:
            json.dump(db, f, indent=4)
            
        log(f"📚 Updated Library: {title}")

    def update_status(self, manga_id, status):
        """
        Update only the reading status of a manga in the library.
        
        Args:
            manga_id (str): MangaDex manga UUID
            status (str): New reading status
        """
        db = self.load_library()
        
        if manga_id in db:
            db[manga_id]['status'] = status
            with open(LIBRARY_FILE, 'w') as f:
                json.dump(db, f, indent=4)

    def update_last_chapter(self, manga_id, chapter_num):
        """
        Update the last read chapter for reading progress tracking.
        
        Args:
            manga_id (str): MangaDex manga UUID
            chapter_num (str): Chapter number that was last read
        """
        db = self.load_library()
        
        if manga_id in db:
            db[manga_id]['last_chapter'] = chapter_num
            with open(LIBRARY_FILE, 'w') as f:
                json.dump(db, f, indent=4)
            log(f"📖 Progress saved: Chapter {chapter_num}")

    def remove_from_library(self, manga_id):
        """
        Remove a manga from the user's library.
        
        Args:
            manga_id (str): MangaDex manga UUID to remove
        """
        db = self.load_library()
        
        if manga_id in db:
            del db[manga_id]
            with open(LIBRARY_FILE, 'w') as f:
                json.dump(db, f, indent=4)
            log(f"🗑 Removed from Library")

    # =========================================================================
    # COVER ART
    # =========================================================================
    
    def get_cover_url(self, manga_id, cover_filename):
        """
        Construct the full URL for a manga's cover art.
        
        MangaDex stores cover art separately and requires constructing
        the URL from the manga ID and cover filename.
        
        Args:
            manga_id (str): MangaDex manga UUID
            cover_filename (str): Filename of the cover image
            
        Returns:
            str: Full URL to the cover image (256px thumbnail)
        """
        if not cover_filename:
            return None
            
        # Use 256px thumbnail for faster loading
        return f"https://uploads.mangadex.org/covers/{manga_id}/{cover_filename}.256.jpg"

    def extract_cover_from_manga(self, manga_data):
        """
        Extract cover art URL from manga API response data.
        
        MangaDex includes cover art in the 'relationships' array
        when requested with includes[]=cover_art parameter.
        
        Args:
            manga_data (dict): Manga object from MangaDex API
            
        Returns:
            str: Cover art URL or None if not found
        """
        manga_id = manga_data.get('id')
        relationships = manga_data.get('relationships', [])
        
        # Find the cover_art relationship
        for rel in relationships:
            if rel.get('type') == 'cover_art':
                cover_filename = rel.get('attributes', {}).get('fileName')
                if cover_filename:
                    return self.get_cover_url(manga_id, cover_filename)
                    
        return None

    # =========================================================================
    # SEARCH & DISCOVERY
    # =========================================================================
    
    def get_popular(self):
        """
        Fetch the most popular manga from MangaDex.
        
        Popularity is determined by follower count. Results are filtered
        to only include manga with English translations available.
        
        Returns:
            list: List of manga objects with cover art included
        """
        try:
            params = {
                "limit": 15,  # Number of results to fetch
                "includes[]": ["cover_art"],  # Include cover art in response
                "order[followedCount]": "desc",  # Sort by popularity
                "contentRating[]": ["safe", "suggestive", "erotica"],
                "availableTranslatedLanguage[]": ["en"]  # English only
            }
            
            response = self.session.get(
                f"{BASE_URL}/manga",
                params=params,
                timeout=15  # Increased timeout for reliability
            )
            
            if response.status_code == 200:
                return response.json()["data"]
            else:
                log(f"⚠️ Popular fetch failed: HTTP {response.status_code}")
                return []
                
        except requests.exceptions.Timeout:
            log("❌ Timeout fetching popular manga")
            return []
        except Exception as e:
            log(f"❌ Error fetching popular: {e}")
            return []

    def search(self, query):
        """
        Search for manga by title.
        
        Args:
            query (str): Search term to look for
            
        Returns:
            list: List of matching manga objects with cover art
        """
        log(f"🔍 Searching: {query}")
        
        try:
            params = {
                "title": query,
                "limit": 15,
                "includes[]": ["cover_art"],  # Include cover art
                "contentRating[]": ["safe", "suggestive", "erotica"],
                "order[relevance]": "desc"  # Most relevant first
            }
            
            response = self.session.get(
                f"{BASE_URL}/manga",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                results = response.json()["data"]
                log(f"✅ Found {len(results)} results")
                return results
            else:
                log(f"⚠️ Search failed: HTTP {response.status_code}")
                return []
                
        except requests.exceptions.Timeout:
            log("❌ Search timeout - try again")
            return []
        except Exception as e:
            log(f"❌ Search Error: {e}")
            return []

    # =========================================================================
    # CHAPTER FETCHING
    # =========================================================================
    
    def get_chapters(self, manga_id, offset=0, limit=100):
        """
        Fetch chapters for a manga with pagination support.
        
        This method handles MangaDex's pagination and deduplicates
        chapters (since multiple scanlation groups may translate the same chapter).
        
        Args:
            manga_id (str): MangaDex manga UUID
            offset (int): Starting position for pagination
            limit (int): Maximum number of unique chapters to return
            
        Returns:
            dict: {
                'chapters': List of chapter objects,
                'total': Total unique chapters fetched,
                'hasMore': Boolean indicating if more chapters exist,
                'nextOffset': Offset to use for next page
            }
        """
        log(f"📖 Fetching chapters (offset: {offset})...")
        
        chapters = []
        current_offset = offset
        fetched_total = 0
        total_available = 0
        max_retries = 3
        
        # Fetch chapters in batches until we have enough unique ones
        while fetched_total < limit:
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    params = {
                        "manga": manga_id,
                        "translatedLanguage[]": ["en"],  # English only
                        "limit": 100,  # MangaDex API max per request
                        "offset": current_offset,
                        "order[chapter]": "asc",  # Oldest first
                        "includes[]": ["scanlation_group"]  # Include group info
                    }
                    
                    response = self.session.get(
                        f"{BASE_URL}/chapter",
                        params=params,
                        timeout=20
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        total_available = data.get("total", 0)
                        fetched = data.get("data", [])
                        
                        if not fetched:
                            # No more chapters available
                            success = True
                            break
                        
                        chapters.extend(fetched)
                        current_offset += len(fetched)
                        fetched_total = len(chapters)
                        success = True
                        
                        # If we got fewer than requested, we've reached the end
                        if len(fetched) < 100:
                            break
                            
                    elif response.status_code == 429:
                        # Rate limited - wait and retry
                        log("⏳ Rate limited, waiting...")
                        time.sleep(2)
                        retry_count += 1
                    else:
                        log(f"⚠️ Chapter fetch failed: HTTP {response.status_code}")
                        retry_count += 1
                        
                except requests.exceptions.Timeout:
                    log("⏳ Timeout, retrying...")
                    retry_count += 1
                except Exception as e:
                    log(f"❌ Chapter fetch error: {e}")
                    retry_count += 1
            
            if not success:
                break
                
            # Small delay to avoid rate limiting
            time.sleep(0.2)
        
        # Deduplicate chapters by chapter number
        # Multiple groups may translate the same chapter - we only want one
        unique = {}
        for ch in chapters:
            num = ch["attributes"].get("chapter")
            if num and num not in unique:
                unique[num] = ch
        
        # Sort by chapter number (numerically)
        sorted_chapters = sorted(
            unique.values(),
            key=lambda x: float(x["attributes"]["chapter"] or 0)
        )
        
        # Determine if more chapters are available
        has_more = current_offset < total_available
        
        log(f"✅ Loaded {len(sorted_chapters)} unique chapters")
        
        return {
            "chapters": sorted_chapters[:limit],
            "total": len(unique),
            "hasMore": has_more,
            "nextOffset": current_offset
        }

    def get_all_chapters(self, manga_id):
        """
        Fetch ALL chapters for a manga (used for downloads).
        
        Unlike get_chapters(), this fetches everything without pagination
        limits. Used when downloading a range of chapters.
        
        Args:
            manga_id (str): MangaDex manga UUID
            
        Returns:
            list: Complete list of unique chapter objects, sorted by number
        """
        log("📖 Fetching all chapters for download...")
        
        chapters = []
        offset = 0
        limit = 100
        
        while True:
            try:
                params = {
                    "manga": manga_id,
                    "translatedLanguage[]": ["en"],
                    "limit": limit,
                    "offset": offset,
                    "order[chapter]": "asc"
                }
                
                response = self.session.get(
                    f"{BASE_URL}/chapter",
                    params=params,
                    timeout=20
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                fetched = data.get("data", [])
                chapters.extend(fetched)
                
                # Check if we've fetched all available chapters
                if len(fetched) < limit:
                    break
                    
                offset += limit
                time.sleep(0.2)  # Rate limiting
                
            except Exception as e:
                log(f"❌ Error fetching all chapters: {e}")
                break
        
        # Deduplicate by chapter number
        unique = {}
        for ch in chapters:
            num = ch["attributes"].get("chapter")
            if num and num not in unique:
                unique[num] = ch
        
        return sorted(
            unique.values(),
            key=lambda x: float(x["attributes"]["chapter"] or 0)
        )

    # =========================================================================
    # READER - PAGE FETCHING
    # =========================================================================
    
    def get_chapter_pages(self, chapter_id):
        """
        Fetch the image URLs for a specific chapter (for streaming reader).
        
        MangaDex requires fetching page URLs from their at-home API,
        which provides CDN links for the actual images.
        
        Args:
            chapter_id (str): MangaDex chapter UUID
            
        Returns:
            dict: {
                'pages': List of full image URLs,
                'pages_datasaver': List of compressed image URLs,
                'chapter_info': Chapter metadata
            }
        """
        log(f"📄 Fetching pages for chapter {chapter_id}...")
        
        try:
            # First, get the CDN server and image filenames
            response = self.session.get(
                f"{BASE_URL}/at-home/server/{chapter_id}",
                timeout=15
            )
            
            if response.status_code != 200:
                log(f"⚠️ Failed to get chapter pages: HTTP {response.status_code}")
                return None
            
            data = response.json()
            base_url = data["baseUrl"]
            chapter_hash = data["chapter"]["hash"]
            
            # Full quality images
            pages = [
                f"{base_url}/data/{chapter_hash}/{filename}"
                for filename in data["chapter"]["data"]
            ]
            
            # Data saver (compressed) images
            pages_datasaver = [
                f"{base_url}/data-saver/{chapter_hash}/{filename}"
                for filename in data["chapter"]["dataSaver"]
            ]
            
            log(f"✅ Found {len(pages)} pages")
            
            return {
                "pages": pages,
                "pages_datasaver": pages_datasaver
            }
            
        except Exception as e:
            log(f"❌ Error fetching chapter pages: {e}")
            return None

    # =========================================================================
    # DOWNLOADING
    # =========================================================================
    
    def download_worker(self, chapters, title):
        """
        Background worker that downloads chapters as CBZ files.
        
        This runs in a separate thread to avoid blocking the UI.
        Each chapter is downloaded as individual images, then packaged
        into a CBZ (Comic Book ZIP) file for use with reader apps.
        
        Args:
            chapters (list): List of chapter objects to download
            title (str): Manga title (used for folder/file naming)
        """
        # Sanitize title for filesystem use
        safe_title = "".join(
            c for c in title if c.isalnum() or c in (' ', '-', '_')
        ).strip()
        
        # Create series directory
        series_dir = os.path.join(DOWNLOAD_DIR, safe_title)
        if not os.path.exists(series_dir):
            os.makedirs(series_dir)

        log(f"🚀 Starting download: {len(chapters)} chapters")
        
        for ch in chapters:
            ch_num = ch["attributes"]["chapter"]
            ch_id = ch["id"]
            
            try:
                # Get CDN info for this chapter
                response = self.session.get(
                    f"{BASE_URL}/at-home/server/{ch_id}",
                    timeout=15
                )
                
                if response.status_code != 200:
                    log(f"⚠️ Metadata fail Ch {ch_num}")
                    continue

                data = response.json()
                base_host = data["baseUrl"]
                hash_code = data["chapter"]["hash"]
                filenames = data["chapter"]["data"]

                # Create temporary folder for chapter images
                chapter_folder = f"{safe_title} - Ch{ch_num}"
                save_folder = os.path.join(series_dir, chapter_folder)
                if not os.path.exists(save_folder):
                    os.makedirs(save_folder)

                log(f"⬇️ Ch {ch_num} ({len(filenames)} pages)...")
                
                # Download each page
                for i, filename in enumerate(filenames):
                    img_url = f"{base_host}/data/{hash_code}/{filename}"
                    success = False
                    
                    # Retry logic for failed downloads
                    for attempt in range(3):
                        try:
                            res = self.session.get(img_url, timeout=15)
                            if res.status_code == 200:
                                # Save with zero-padded index for proper ordering
                                with open(os.path.join(save_folder, f"{i:03d}.jpg"), 'wb') as f:
                                    f.write(res.content)
                                success = True
                                break
                        except:
                            time.sleep(1)
                            
                    if not success:
                        log(f"   ⚠️ Failed page {i}")

                # Package into CBZ file
                cbz_path = os.path.join(series_dir, f"{chapter_folder}.cbz")
                with zipfile.ZipFile(cbz_path, 'w') as zf:
                    for root, _, files in os.walk(save_folder):
                        for file in sorted(files):  # Sort for proper order
                            zf.write(
                                os.path.join(root, file),
                                arcname=file
                            )
                
                # Clean up temporary folder
                shutil.rmtree(save_folder)
                log(f"✅ Finished: Ch {ch_num}")
                
                # Small delay between chapters to avoid rate limiting
                time.sleep(0.5)

            except Exception as e:
                log(f"❌ Error Ch {ch_num}: {e}")
        
        log("✨ All downloads completed!")

    def get_downloaded_chapters(self, title):
        """
        Get list of already downloaded chapters for a manga.
        
        Scans the downloads directory for CBZ files matching the manga title.
        
        Args:
            title (str): Manga title to search for
            
        Returns:
            list: List of chapter numbers that have been downloaded
        """
        safe_title = "".join(
            c for c in title if c.isalnum() or c in (' ', '-', '_')
        ).strip()
        
        series_dir = os.path.join(DOWNLOAD_DIR, safe_title)
        
        if not os.path.exists(series_dir):
            return []
        
        downloaded = []
        for filename in os.listdir(series_dir):
            if filename.endswith('.cbz'):
                # Extract chapter number from filename
                # Format: "Title - Ch123.cbz"
                try:
                    ch_part = filename.rsplit(' - Ch', 1)[-1]
                    ch_num = ch_part.replace('.cbz', '')
                    downloaded.append(ch_num)
                except:
                    pass
        
        return downloaded


# =============================================================================
# FLASK ROUTES
# =============================================================================

# Initialize the manga logic handler
logic = MangaLogic()


@app.route('/')
def index():
    """
    Serve the main application page.
    
    Returns:
        str: Rendered HTML template
    """
    return render_template('index.html')


# -----------------------------------------------------------------------------
# Library Endpoints
# -----------------------------------------------------------------------------

@app.route('/api/library')
def get_library():
    """
    Get the user's complete manga library.
    
    Returns:
        JSON: Dictionary of saved manga
    """
    return jsonify(logic.load_library())


@app.route('/api/save', methods=['POST'])
def save():
    """
    Save a manga to the library.
    
    Expected JSON body:
        - id: Manga UUID
        - title: Manga title
        - status: Reading status (optional)
        - cover: Cover URL (optional)
    
    Returns:
        JSON: Success status
    """
    data = request.json
    logic.save_to_library(
        data['id'],
        data['title'],
        data.get('status', 'reading'),
        data.get('cover')
    )
    return jsonify({'status': 'ok'})


@app.route('/api/update_status', methods=['POST'])
def update_status_route():
    """
    Update the reading status of a manga.
    
    Expected JSON body:
        - id: Manga UUID
        - status: New reading status
    
    Returns:
        JSON: Success status
    """
    data = request.json
    logic.update_status(data['id'], data['status'])
    return jsonify({'status': 'ok'})


@app.route('/api/update_progress', methods=['POST'])
def update_progress():
    """
    Update the last read chapter for a manga.
    
    Expected JSON body:
        - id: Manga UUID
        - chapter: Last read chapter number
    
    Returns:
        JSON: Success status
    """
    data = request.json
    logic.update_last_chapter(data['id'], data['chapter'])
    return jsonify({'status': 'ok'})


@app.route('/api/delete', methods=['POST'])
def delete():
    """
    Remove a manga from the library.
    
    Expected JSON body:
        - id: Manga UUID
    
    Returns:
        JSON: Success status
    """
    logic.remove_from_library(request.json['id'])
    return jsonify({'status': 'ok'})


# -----------------------------------------------------------------------------
# Search & Discovery Endpoints
# -----------------------------------------------------------------------------

@app.route('/api/popular')
def get_popular():
    """
    Get popular manga for the home page.
    
    Returns:
        JSON: List of popular manga with cover art
    """
    return jsonify(logic.get_popular())


@app.route('/api/search', methods=['POST'])
def search():
    """
    Search for manga by title.
    
    Expected JSON body:
        - query: Search term
    
    Returns:
        JSON: List of matching manga
    """
    return jsonify(logic.search(request.json['query']))


# -----------------------------------------------------------------------------
# Chapter Endpoints
# -----------------------------------------------------------------------------

@app.route('/api/chapters', methods=['POST'])
def chapters():
    """
    Get chapters for a manga with pagination.
    
    Expected JSON body:
        - id: Manga UUID
        - offset: Starting position (optional, default 0)
        - limit: Max chapters to return (optional, default 100)
    
    Returns:
        JSON: Chapter list with pagination info
    """
    data = request.json
    offset = data.get('offset', 0)
    limit = data.get('limit', 100)
    return jsonify(logic.get_chapters(data['id'], offset, limit))


@app.route('/api/all_chapters', methods=['POST'])
def all_chapters():
    """
    Get all chapters for a manga (used for downloads).
    
    Expected JSON body:
        - id: Manga UUID
    
    Returns:
        JSON: Complete list of chapters
    """
    return jsonify(logic.get_all_chapters(request.json['id']))


# -----------------------------------------------------------------------------
# Reader Endpoints
# -----------------------------------------------------------------------------

@app.route('/api/chapter_pages', methods=['POST'])
def chapter_pages():
    """
    Get page image URLs for a chapter (streaming reader).
    
    Expected JSON body:
        - chapter_id: Chapter UUID
    
    Returns:
        JSON: List of page URLs
    """
    data = request.json
    pages = logic.get_chapter_pages(data['chapter_id'])
    
    if pages:
        return jsonify(pages)
    else:
        return jsonify({'error': 'Failed to fetch pages'}), 500


@app.route('/api/downloaded_chapters', methods=['POST'])
def downloaded_chapters():
    """
    Get list of downloaded chapters for a manga.
    
    Expected JSON body:
        - title: Manga title
    
    Returns:
        JSON: List of downloaded chapter numbers
    """
    data = request.json
    chapters = logic.get_downloaded_chapters(data['title'])
    return jsonify({'chapters': chapters})


# -----------------------------------------------------------------------------
# Download Endpoints
# -----------------------------------------------------------------------------

@app.route('/api/download', methods=['POST'])
def download():
    """
    Start downloading chapters in the background.
    
    Expected JSON body:
        - chapters: List of chapter objects to download
        - title: Manga title
    
    Returns:
        JSON: Success status (download runs in background thread)
    """
    data = request.json
    
    # Run download in separate thread to avoid blocking
    thread = threading.Thread(
        target=logic.download_worker,
        args=(data['chapters'], data['title'])
    )
    thread.start()
    
    return jsonify({'status': 'started'})


@app.route('/downloads/<path:filename>')
def serve_download(filename):
    """
    Serve downloaded CBZ files.
    
    Args:
        filename: Path to the file within downloads directory
    
    Returns:
        File: The requested CBZ file
    """
    return send_from_directory(DOWNLOAD_DIR, filename)


# -----------------------------------------------------------------------------
# Logging Endpoint
# -----------------------------------------------------------------------------

@app.route('/api/logs')
def logs():
    """
    Get pending log messages for the console.
    
    This is polled by the frontend to display real-time progress.
    Messages are removed from the queue once retrieved.
    
    Returns:
        JSON: List of log messages
    """
    messages = []
    while not msg_queue.empty():
        messages.append(msg_queue.get())
    return jsonify({'logs': messages})


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  MangaNegus v2.1")
    print("  Server running on http://127.0.0.1:5000")
    print("=" * 60)
    
    # Run Flask development server
    # - host='0.0.0.0' allows access from other devices on network
    # - debug=True enables auto-reload and detailed errors
    # - use_reloader=False prevents double-initialization issues
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )
