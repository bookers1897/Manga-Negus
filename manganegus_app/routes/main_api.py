from flask import Blueprint, jsonify, request, Response, render_template
from manganegus_app.log import log, msg_queue
import requests
import queue

main_bp = Blueprint('main_api', __name__)

@main_bp.route('/')
def index():
    """Serve main page."""
    return render_template('index.html')

@main_bp.route('/api/proxy/image')
def proxy_image():
    """
    Proxy external images to avoid CORS issues.
    Usage: /api/proxy/image?url=https://uploads.mangadex.org/covers/...
    """
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Validate URL is from allowed domains
    allowed_domains = [
        'uploads.mangadex.org',
        'mangadex.org',
        'cover.nep.li',
        'avt.mkklcdnv6temp.com',
        'mangakakalot.com',
        'chapmanganato.com',
        'fanfox.net',
        'mangahere.cc',
        'mangafire.to',
        's1.mbcdnv1.xyz',
        's1.mbcdnv2.xyz',
        's1.mbcdnv3.xyz',
    ]

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname not in allowed_domains and parsed.hostname != 'localhost':
            return jsonify({'error': f'Image proxying from {parsed.hostname} is not allowed'}), 403
    except Exception:
        return jsonify({'error': 'Invalid URL provided for proxying'}), 400

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': url,
        }
        resp = requests.get(url, headers=headers, timeout=10, stream=True)
        if resp.status_code != 200:
            return jsonify({'error': 'Failed to fetch image'}), resp.status_code
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        return Response(
            resp.content,
            mimetype=content_type,
            headers={
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*'
            }
        )
    except requests.RequestException as e:
        log(f"⚠️ Image proxy error: {e}")
        return jsonify({'error': 'Failed to fetch image'}), 500

@main_bp.route('/api/logs')
def get_logs():
    """Get pending log messages."""
    messages = []
    while not msg_queue.empty():
        try:
            messages.append(msg_queue.get_nowait())
        except queue.Empty:
            break
    return jsonify({'logs': messages})
