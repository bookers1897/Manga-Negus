import os
import json
import time
import shutil
import zipfile
import threading
import queue
import requests
from flask import Flask, render_template, jsonify, request

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
msg_queue = queue.Queue()

DOWNLOAD_DIR = os.path.join(BASE_DIR, "static", "downloads")
LIBRARY_FILE = os.path.join(BASE_DIR, "library.json")
BASE_URL = "https://api.mangadex.org"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def log(msg):
    print(msg)
    timestamp = time.strftime("[%H:%M:%S]")
    msg_queue.put(f"{timestamp} {msg}")

class MangaLogic:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
        })

    def load_library(self):
        if not os.path.exists(LIBRARY_FILE): return {}
        try:
            with open(LIBRARY_FILE, 'r') as f:
                data = json.load(f)
                for k, v in data.items():
                    if 'status' not in v: v['status'] = 'reading'
                return data
        except: return {}

    def save_to_library(self, manga_id, title, status='reading'):
        db = self.load_library()
        current_status = db.get(manga_id, {}).get('status', status)
        db[manga_id] = { "title": title, "status": status if status else current_status }
        with open(LIBRARY_FILE, 'w') as f: json.dump(db, f, indent=4)
        log(f"📚 Updated Library: {title}")

    def update_status(self, manga_id, status):
        db = self.load_library()
        if manga_id in db:
            db[manga_id]['status'] = status
            with open(LIBRARY_FILE, 'w') as f: json.dump(db, f, indent=4)

    def remove_from_library(self, manga_id):
        db = self.load_library()
        if manga_id in db:
            del db[manga_id]
            with open(LIBRARY_FILE, 'w') as f: json.dump(db, f, indent=4)
            log(f"🗑 Removed from Library")

    def get_popular(self):
        try:
            params = {
                "limit": 10,
                "includes[]": ["cover_art"],
                "order[followedCount]": "desc",
                "contentRating[]": ["safe", "suggestive", "erotica"],
                "availableTranslatedLanguage[]": ["en"]
            }
            r = self.session.get(f"{BASE_URL}/manga", params=params, timeout=10)
            if r.status_code == 200: return r.json()["data"]
            return []
        except Exception as e:
            log(f"❌ Error fetching popular: {e}")
            return []

    def search(self, query):
        log(f"🔍 Searching: {query}")
        try:
            params = {
                "title": query, "limit": 10,
                "contentRating[]": ["safe", "suggestive", "erotica"]
            }
            r = self.session.get(f"{BASE_URL}/manga", params=params, timeout=10)
            if r.status_code == 200: return r.json()["data"]
            return []
        except Exception as e:
            log(f"❌ Search Error: {e}")
            return []

    def get_chapters(self, manga_id, offset=0, limit=100):
        """
        Fetch chapters with pagination support.
        Returns: { chapters: [], total: int, hasMore: bool }
        """
        log(f"📖 Fetching chapters (offset: {offset})...")
        chapters = []
        current_offset = offset
        fetched_total = 0
        total_available = 0
        
        # Fetch up to 'limit' unique chapters
        while fetched_total < limit:
            try:
                params = {
                    "manga": manga_id, 
                    "translatedLanguage[]": ["en"],
                    "limit": 100,  # API max per request
                    "offset": current_offset, 
                    "order[chapter]": "asc"
                }
                r = self.session.get(f"{BASE_URL}/chapter", params=params, timeout=10)
                if r.status_code != 200: 
                    break
                
                data = r.json()
                total_available = data.get("total", 0)
                fetched = data.get("data", [])
                
                if not fetched:
                    break
                    
                chapters.extend(fetched)
                current_offset += len(fetched)
                fetched_total = len(chapters)
                
                # If we got fewer than requested, we've hit the end
                if len(fetched) < 100:
                    break
                    
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                log(f"❌ Chapter fetch error: {e}")
                break
        
        # Deduplicate by chapter number
        unique = {}
        for ch in chapters:
            num = ch["attributes"].get("chapter")
            if num and num not in unique: 
                unique[num] = ch
        
        sorted_chapters = sorted(unique.values(), key=lambda x: float(x["attributes"]["chapter"] or 0))
        
        # For pagination: check if there's more after what we've fetched
        has_more = current_offset < total_available
        
        return {
            "chapters": sorted_chapters[:limit],
            "total": len(unique),
            "hasMore": has_more,
            "nextOffset": current_offset
        }

    def get_all_chapters(self, manga_id):
        """
        Fetch ALL chapters for a manga (used for downloads).
        This fetches everything without pagination limits.
        """
        log("📖 Fetching all chapters...")
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
                r = self.session.get(f"{BASE_URL}/chapter", params=params, timeout=10)
                if r.status_code != 200: 
                    break
                
                data = r.json()
                fetched = data.get("data", [])
                chapters.extend(fetched)
                
                if len(fetched) < limit: 
                    break
                offset += limit
                time.sleep(0.1)
            except: 
                break
        
        unique = {}
        for ch in chapters:
            num = ch["attributes"].get("chapter")
            if num and num not in unique: 
                unique[num] = ch
        
        return sorted(unique.values(), key=lambda x: float(x["attributes"]["chapter"] or 0))

    def download_worker(self, chapters, title):
        safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()
        series_dir = os.path.join(DOWNLOAD_DIR, safe_title)
        if not os.path.exists(series_dir): os.makedirs(series_dir)

        log(f"🚀 Batch Download: {len(chapters)} chapters")
        
        for ch in chapters:
            ch_num = ch["attributes"]["chapter"]
            ch_id = ch["id"]
            
            try:
                r = self.session.get(f"{BASE_URL}/at-home/server/{ch_id}", timeout=15)
                if r.status_code != 200:
                    log(f"⚠️ Metadata fail Ch {ch_num}")
                    continue

                data = r.json()
                base_host = data["baseUrl"]
                hash_code = data["chapter"]["hash"]
                filenames = data["chapter"]["data"]

                chapter_folder = f"{safe_title} - Ch{ch_num}"
                save_folder = os.path.join(series_dir, chapter_folder)
                if not os.path.exists(save_folder): os.makedirs(save_folder)

                log(f"⬇️ Ch {ch_num} ({len(filenames)} pages)...")
                for i, filename in enumerate(filenames):
                    img_url = f"{base_host}/data/{hash_code}/{filename}"
                    success = False
                    for _ in range(3):
                        try:
                            res = self.session.get(img_url, timeout=10)
                            if res.status_code == 200:
                                with open(os.path.join(save_folder, f"{i:03d}.jpg"), 'wb') as f:
                                    f.write(res.content)
                                success = True
                                break
                        except: time.sleep(1)
                    if not success: log(f"   ⚠️ Failed page {i}")

                cbz_path = os.path.join(series_dir, f"{chapter_folder}.cbz")
                with zipfile.ZipFile(cbz_path, 'w') as zf:
                    for root, _, files in os.walk(save_folder):
                        for file in files:
                            zf.write(os.path.join(root, file), arcname=file)
                
                shutil.rmtree(save_folder)
                log(f"✅ Finished: {os.path.basename(cbz_path)}")
                time.sleep(0.5)

            except Exception as e:
                log(f"❌ Error Ch {ch_num}: {e}")
        
        log("✨ All downloads completed.")

# --- ROUTES ---
logic = MangaLogic()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/library')
def get_library(): return jsonify(logic.load_library())

@app.route('/api/popular')
def get_popular(): return jsonify(logic.get_popular())

@app.route('/api/search', methods=['POST'])
def search(): return jsonify(logic.search(request.json['query']))

@app.route('/api/save', methods=['POST'])
def save():
    d = request.json
    logic.save_to_library(d['id'], d['title'], d.get('status', 'reading'))
    return jsonify({'status': 'ok'})

@app.route('/api/update_status', methods=['POST'])
def update_status_route():
    d = request.json
    logic.update_status(d['id'], d['status'])
    return jsonify({'status': 'ok'})

@app.route('/api/delete', methods=['POST'])
def delete():
    logic.remove_from_library(request.json['id'])
    return jsonify({'status': 'ok'})

@app.route('/api/chapters', methods=['POST'])
def chapters():
    d = request.json
    offset = d.get('offset', 0)
    limit = d.get('limit', 100)
    return jsonify(logic.get_chapters(d['id'], offset, limit))

@app.route('/api/all_chapters', methods=['POST'])
def all_chapters():
    """Get all chapters for download purposes"""
    return jsonify(logic.get_all_chapters(request.json['id']))

@app.route('/api/download', methods=['POST'])
def download():
    d = request.json
    t = threading.Thread(target=logic.download_worker, args=(d['chapters'], d['title']))
    t.start()
    return jsonify({'status': 'started'})

@app.route('/api/logs')
def logs():
    l = []
    while not msg_queue.empty(): l.append(msg_queue.get())
    return jsonify({'logs': l})

if __name__ == '__main__':
    print("Server running on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
