from flask import Blueprint, jsonify, request, Response, render_template
from manganegus_app.log import log, msg_queue
import requests
import queue
import ipaddress

main_bp = Blueprint('main_api', __name__)

def is_safe_url(url: str, allowed_domains: list) -> tuple[bool, str]:
    """
    Validate URL for SSRF protection with DNS rebinding prevention.

    Args:
        url: URL to validate
        allowed_domains: List of allowed domain names

    Returns:
        (is_valid, error_message)
    """
    try:
        from urllib.parse import urlparse
        import socket
        parsed = urlparse(url)

        # Only allow http/https schemes
        if parsed.scheme not in ('http', 'https'):
            return False, f'Scheme {parsed.scheme} not allowed'

        hostname = parsed.hostname
        if not hostname:
            return False, 'Missing hostname'

        # Check domain whitelist FIRST (before DNS resolution)
        if hostname not in allowed_domains:
            return False, f'Domain {hostname} not in whitelist'

        # DNS rebinding protection: Resolve hostname and block private IPs
        # This is done AFTER whitelist check to prevent unnecessary DNS queries
        try:
            # Get ALL IP addresses for the hostname (not just first one)
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for info in addr_info:
                ip_str = info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    # Block private, loopback, link-local, reserved, multicast IPs
                    if (ip.is_private or ip.is_loopback or ip.is_link_local or
                        ip.is_reserved or ip.is_multicast):
                        return False, f'Access to private/reserved IP ranges not allowed ({ip_str})'
                except ValueError:
                    continue
        except (socket.gaierror, OSError) as e:
            return False, f'DNS resolution failed: {str(e)}'

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

        # MyAnimeList CDN (Jikan covers)
        'cdn.myanimelist.net',

        # WeebCentral V2 CDNs
        'official.lowee.us',
        'temp.compsci88.com',
        'hot.planeptune.us',
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
        img_bytes = resp.content

        fmt = (request.args.get('format') or '').lower().strip()
        quality = request.args.get('quality')
        width = request.args.get('w')
        height = request.args.get('h')

        try:
            from io import BytesIO
            from PIL import Image

            if fmt or width or height:
                image = Image.open(BytesIO(img_bytes))
                if width or height:
                    try:
                        w = int(width) if width else None
                        h = int(height) if height else None
                    except ValueError:
                        w = h = None
                    if w or h:
                        image.thumbnail((w or image.width, h or image.height), Image.LANCZOS)

                out = BytesIO()
                save_format = fmt.upper() if fmt else image.format or 'JPEG'
                save_kwargs = {}
                if quality:
                    try:
                        save_kwargs['quality'] = max(20, min(95, int(quality)))
                    except ValueError:
                        pass
                if save_format == 'WEBP':
                    save_kwargs.setdefault('method', 6)
                image.save(out, format=save_format, optimize=True, **save_kwargs)
                img_bytes = out.getvalue()
                content_type = f"image/{save_format.lower()}"
        except ImportError:
            # Pillow not installed; skip optimization
            pass

        return Response(
            img_bytes,
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
