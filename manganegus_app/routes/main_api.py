from flask import Blueprint, jsonify, request, Response, render_template
from manganegus_app.log import log, msg_queue
import requests
import queue
import ipaddress

main_bp = Blueprint('main_api', __name__)

def is_safe_url(url: str, allowed_domains: list) -> tuple[bool, str]:
    """
    Validate URL for SSRF protection.

    Args:
        url: URL to validate
        allowed_domains: List of allowed domain names

    Returns:
        (is_valid, error_message)
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)

        # Only allow http/https schemes
        if parsed.scheme not in ('http', 'https'):
            return False, f'Scheme {parsed.scheme} not allowed'

        hostname = parsed.hostname
        if not hostname:
            return False, 'Missing hostname'

        # Resolve hostname and block private/loopback/link-local/reserved IPs for ALL hosts
        try:
            import socket
            ip_str = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False, f'Access to private IP ranges not allowed'
        except (socket.gaierror, ValueError):
            # Resolution failed; continue to domain whitelist check
            pass

        # Check domain whitelist
        if hostname not in allowed_domains:
            return False, f'Domain {hostname} not in whitelist'

        return True, ''

    except Exception as e:
        return False, f'Invalid URL: {str(e)}'

@main_bp.route('/')
def index():
    """Serve main page."""
    return render_template('index.html')

@main_bp.route('/modern')
def modern_preview():
    """Serve modern editorial design preview."""
    return render_template('index-modern.html')

@main_bp.route('/sidebar')
def sidebar_preview():
    """Serve sidebar navigation with original glassmorphism design."""
    return render_template('index-sidebar.html')

@main_bp.route('/redesign')
def redesign():
    """Serve new redesign interface (alias for /)."""
    return render_template('index.html')

@main_bp.route('/legacy')
def legacy():
    """Serve legacy glassmorphism UI."""
    return render_template('legacy_v3.0/index.html')

@main_bp.route('/api/proxy/image')
def proxy_image():
    """
    Proxy external images to avoid CORS issues.
    SECURITY: Protected against SSRF with domain whitelist and private IP blocking.
    Usage: /api/proxy/image?url=https://uploads.mangadex.org/covers/...
    """
    url = request.args.get('url', '')
    referer = request.args.get('referer', '')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Validate URL is from allowed domains (SSRF protection)
    allowed_domains = [
        # MangaDex
        'uploads.mangadex.org',
        'mangadex.org',

        # WeebCentral V2 CDNs
        'official.lowee.us',
        'temp.compsci88.com',
        'planeptune.us',
        'www.planeptune.us',
        'weebcentral.com',
        'www.weebcentral.com',

        # MangaNato / MangaKakalot
        'cover.nep.li',
        'avt.mkklcdnv6temp.com',
        'mangakakalot.com',
        'chapmanganato.com',
        'v1.mkklcdnv6tempv5.com',
        'v2.mkklcdnv6tempv5.com',

        # MangaSee / Manga4Life
        'official-ongoing-1.ivalice.us',
        'official-ongoing-2.ivalice.us',
        'official-complete-1.ivalice.us',
        'official-complete-2.ivalice.us',
        'temp.compsci88.com',

        # MangaFire
        'mangafire.to',
        'cdn.mangafire.to',

        # AsuraScans
        'asurascans.com',
        'cdn.asurascans.com',

        # Other sources
        'fanfox.net',
        'mangahere.cc',
        's1.mbcdnv1.xyz',
        's1.mbcdnv2.xyz',
        's1.mbcdnv3.xyz',
        's1.mbcdnv4.xyz',
        's1.mbcdnv5.xyz',

        # Common manga CDNs
        'manga4life.com',
        'official-ongoing.ivalice.us',
        'official-complete.ivalice.us',
    ]

    # SECURITY: Validate URL to prevent SSRF attacks
    is_valid, error_msg = is_safe_url(url, allowed_domains)
    if not is_valid:
        log(f"🚨 SSRF attempt blocked: {url} - {error_msg}")
        return jsonify({'error': f'Security: {error_msg}'}), 403

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': referer or url,
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
