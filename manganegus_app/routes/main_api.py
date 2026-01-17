from flask import Blueprint, jsonify, request, Response, render_template
from manganegus_app.log import log, msg_queue
from manganegus_app.rate_limit import limit_burst, limit_light
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
        # Support exact matches and wildcard suffix patterns (e.g., *.mangadex.network)
        domain_allowed = False
        for allowed in allowed_domains:
            if allowed.startswith('*.'):
                # Wildcard pattern: *.example.com matches sub.example.com
                suffix = allowed[1:]  # Remove the * to get .example.com
                if hostname.endswith(suffix) or hostname == allowed[2:]:
                    domain_allowed = True
                    break
            elif hostname == allowed:
                domain_allowed = True
                break

        if not domain_allowed:
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

@main_bp.route('/reader')
def reader():
    """Serve standalone reader page."""
    return render_template('reader.html')

@main_bp.route('/legacy')
def legacy():
    """Serve legacy glassmorphism UI."""
    return render_template('legacy_v3.0/index.html')

@main_bp.route('/api/proxy/image')
@limit_burst
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
    # Comprehensive whitelist covering ALL source connectors
    allowed_domains = [
        # MangaDex (including dynamic CDN subdomains)
        'uploads.mangadex.org',
        'mangadex.org',
        'api.mangadex.org',
        '*.mangadex.network',  # CDN for chapter images (dynamic subdomains)

        # ComicK
        'api.comick.io',
        'comick.io',
        'meo.comick.pictures',  # ComicK image CDN (CRITICAL)
        '*.comick.pictures',    # Wildcard for ComicK CDN variants

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
        'scans.lastation.us',    # Added to fix blank images
        '*.lastation.us',        # Wildcard for Lastation CDNs

        # MangaNato / MangaKakalot (all variants and mirrors)
        'cover.nep.li',
        'avt.mkklcdnv6temp.com',
        'mangakakalot.com',
        'mangakakalot.gg',      # Updated domain (Jan 2026)
        'chapmanganato.com',
        'chapmanganato.to',     # Mirror domain
        'manganato.com',
        'v1.mkklcdnv6tempv5.com',
        'v2.mkklcdnv6tempv5.com',
        '*.mkklcdnv6tempv5.com', # Wildcard for CDN variants

        # MangaSee / Manga4Life
        'official-ongoing-1.ivalice.us',
        'official-ongoing-2.ivalice.us',
        'official-complete-1.ivalice.us',
        'official-complete-2.ivalice.us',
        'official-ongoing.ivalice.us',
        'official-complete.ivalice.us',
        '*.ivalice.us',         # Wildcard for all ivalice CDNs
        'manga4life.com',

        # MangaFire
        'mangafire.to',
        'cdn.mangafire.to',
        '*.mangafire.to',       # Wildcard for MangaFire CDNs

        # AsuraScans
        'asurascans.com',
        'cdn.asurascans.com',
        '*.asurascans.com',     # Wildcard for AsuraScans CDNs

        # FlameScans
        'flamescans.org',
        '*.flamescans.org',

        # ReaperScans
        'reaperscans.com',
        '*.reaperscans.com',

        # TCB Scans
        'tcbscans.me',
        '*.tcbscans.me',

        # MangaReader
        'mangareader.to',
        '*.mangareader.to',

        # MangaPark
        'mangapark.net',
        '*.mangapark.net',

        # MangaBuddy
        'mangabuddy.com',
        '*.mangabuddy.com',

        # MangaFreak
        'mangafreak.net',
        '*.mangafreak.net',

        # MangaKatana
        'mangakatana.com',
        '*.mangakatana.com',

        # ComicX
        'comicx.to',
        '*.comicx.to',

        # MangaHere / Fanfox
        'mangahere.cc',
        'www.mangahere.cc',
        'fanfox.net',
        '*.fanfox.net',

        # Anna's Archive and Shadow Libraries
        'annas-archive.org',
        '*.annas-archive.org',
        'libgen.rs',
        'libgen.st',
        'libgen.is',
        'libgen.lc',

        # IPFS Gateway (used by LibGen mirrors)
        'cloudflare-ipfs.com',
        '*.cloudflare-ipfs.com',

        # MangaBuddy CDN variants
        's1.mbcdnv1.xyz',
        's1.mbcdnv2.xyz',
        's1.mbcdnv3.xyz',
        's1.mbcdnv4.xyz',
        's1.mbcdnv5.xyz',
        '*.mbcdnv1.xyz',
        '*.mbcdnv2.xyz',
        '*.mbcdnv3.xyz',
        '*.mbcdnv4.xyz',
        '*.mbcdnv5.xyz',

        # Imgur (for gallery-dl sources)
        'i.imgur.com',
        'imgur.com',
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

        img_bytes = resp.content

        fmt = (request.args.get('format') or '').lower().strip()
        quality = request.args.get('quality')
        width = request.args.get('w')
        height = request.args.get('h')

        try:
            from io import BytesIO
            from PIL import Image

            # Always open with Pillow to detect actual format (servers often lie about Content-Type)
            image = Image.open(BytesIO(img_bytes))
            actual_format = image.format or 'JPEG'

            # Determine output format
            save_format = fmt.upper() if fmt else actual_format

            # Check if we need to process the image
            needs_processing = fmt or width or height or quality

            if needs_processing:
                if width or height:
                    try:
                        w = int(width) if width else None
                        h = int(height) if height else None
                    except ValueError:
                        w = h = None
                    if w or h:
                        image.thumbnail((w or image.width, h or image.height), Image.LANCZOS)

                out = BytesIO()
                save_kwargs = {}
                if quality:
                    try:
                        save_kwargs['quality'] = max(20, min(95, int(quality)))
                    except ValueError:
                        pass
                if save_format == 'WEBP':
                    save_kwargs.setdefault('method', 6)
                # Convert RGBA to RGB for JPEG format
                if save_format == 'JPEG' and image.mode in ('RGBA', 'P'):
                    image = image.convert('RGB')
                image.save(out, format=save_format, optimize=True, **save_kwargs)
                img_bytes = out.getvalue()

            content_type = f"image/{save_format.lower()}"
        except ImportError:
            # Pillow not installed; use server's Content-Type
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
        except Exception as e:
            # If Pillow fails to process, return original with detected or server Content-Type
            log(f"⚠️ Image processing error: {e}")
            content_type = resp.headers.get('Content-Type', 'image/jpeg')

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
