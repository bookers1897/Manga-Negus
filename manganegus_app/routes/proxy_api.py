"""Image proxy API with format conversion and timeout protection.

Provides image proxying with:
- Format conversion (WebP, JPEG, PNG)
- Quality optimization
- Timeout protection
- CORS handling
- Rate limiting
- Proper error handling
"""

from flask import Blueprint, request, jsonify, Response
from manganegus_app.rate_limit import limit_heavy
from manganegus_app.log import log
import requests
from urllib.parse import unquote
from io import BytesIO
import time
from typing import Optional, Tuple

proxy_bp = Blueprint('proxy_api', __name__, url_prefix='/api/proxy')

# Session with proper headers for image proxying
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# Content type whitelist for security
ALLOWED_IMAGE_TYPES = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'image/gif',
    'image/bmp',
    'image/tiff',
    'image/x-icon'
}


def _validate_image_url(url: str) -> Tuple[bool, str]:
    """Validate image URL is safe to proxy."""
    if not url:
        return False, 'Empty URL'
    
    if not url.startswith(('http://', 'https://')):
        return False, 'Invalid URL scheme'
    
    # Check for localhost/private IPs (security)
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        
        # Block private IP ranges
        if hostname.startswith(('127.', '192.168.', '10.', '172.')):
            return False, 'Private IP not allowed'
        
        if hostname in ('localhost', '0.0.0.0'):
            return False, 'Localhost not allowed'
    except Exception:
        return False, 'Invalid URL'
    
    return True, ''


def _validate_image_content(response: requests.Response) -> Tuple[bool, str]:
    """Validate response is actually an image."""
    content_type = response.headers.get('content-type', '').lower()
    
    # Extract base type (remove charset, etc)
    base_type = content_type.split(';')[0].strip()
    
    if not base_type.startswith('image/'):
        return False, f'Not an image: {base_type}'
    
    if base_type not in ALLOWED_IMAGE_TYPES and not base_type.startswith('image/'):
        return False, f'Unsupported image type: {base_type}'
    
    return True, ''


def _convert_image_format(data: bytes, output_format: str, quality: int) -> Optional[bytes]:
    """Convert image to target format with optimization.
    
    Returns:
        Converted image bytes or None on failure
    """
    try:
        from PIL import Image
        
        img = Image.open(BytesIO(data))
        
        # Handle format-specific conversions
        if output_format == 'jpeg':
            # JPEG doesn't support transparency
            if img.mode in ('RGBA', 'PA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
        
        elif output_format == 'webp':
            # WebP can handle all formats
            if img.mode not in ('RGB', 'RGBA', 'L'):
                img = img.convert('RGBA' if 'A' in img.mode else 'RGB')
        
        elif output_format == 'png':
            # PNG supports transparency
            if img.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
                img = img.convert('RGBA')
        
        output = BytesIO()
        save_kwargs = {
            'format': output_format.upper(),
            'optimize': True
        }
        
        if output_format != 'png':
            save_kwargs['quality'] = quality
        
        img.save(output, **save_kwargs)
        return output.getvalue()
    
    except Exception as e:
        log(f'❌ Image conversion failed: {e}')
        return None


@proxy_bp.route('/image', methods=['GET'])
@limit_heavy  # Rate limit to prevent abuse
def proxy_image():
    """Proxy image requests with format conversion and timeout protection.
    
    Query Parameters:
        - url (required): Original image URL
        - referer (optional): Source referer header
        - format (optional): Output format (webp/jpeg/png, default: original)
        - quality (optional): Output quality 1-100 (default: 85, ignored for PNG)
        - timeout (optional): Fetch timeout in seconds (default: 10, max: 20)
    
    Returns:
        Image data with appropriate content-type and cache headers
    """
    
    # Parse parameters
    image_url = request.args.get('url', '').strip()
    referer = request.args.get('referer', '').strip()
    output_format = request.args.get('format', '').lower() or None
    
    try:
        quality = int(request.args.get('quality', '85'))
        timeout = int(request.args.get('timeout', '10'))
    except ValueError:
        return jsonify({'error': 'Invalid quality or timeout parameter'}), 400
    
    # Validate inputs
    is_valid, error = _validate_image_url(image_url)
    if not is_valid:
        log(f'🚫 Invalid URL in proxy: {error}')
        return jsonify({'error': f'Invalid URL: {error}'}), 400
    
    # Validate format
    if output_format and output_format not in ['webp', 'jpeg', 'jpg', 'png']:
        return jsonify({'error': 'Invalid format (webp/jpeg/png)'}), 400
    
    # Clamp values to safe ranges
    quality = max(10, min(100, quality))  # 10-100
    timeout = max(5, min(20, timeout))    # 5-20 seconds
    
    # Normalize JPEG alias
    if output_format == 'jpg':
        output_format = 'jpeg'
    
    try:
        # Fetch image with timeout
        headers = {'User-Agent': session.headers.get('User-Agent')}
        if referer:
            headers['Referer'] = referer
        
        log(f'🖼️ Proxying image: {image_url[:60]}... (timeout={timeout}s, format={output_format})')
        
        response = session.get(
            image_url,
            headers=headers,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
            verify=True  # SSL verification
        )
        response.raise_for_status()
        
        # Validate response is actually an image
        is_image, error = _validate_image_content(response)
        if not is_image:
            log(f'⚠️ {error}')
            return jsonify({'error': error}), 400
        
        # Read image data
        image_data = response.content
        if not image_data:
            log(f'⚠️ Empty image response from {image_url[:60]}')
            return jsonify({'error': 'Empty image response'}), 400
        
        # Get original content type
        original_content_type = response.headers.get('content-type', 'image/jpeg').lower()
        original_content_type = original_content_type.split(';')[0].strip()
        
        # Convert format if requested
        if output_format and output_format not in original_content_type:
            converted = _convert_image_format(image_data, output_format, quality)
            if converted:
                image_data = converted
                original_content_type = f'image/{output_format}'
                log(f'✅ Converted to {output_format} (quality={quality}, size={len(image_data)} bytes)')
            else:
                log(f'⚠️ Conversion to {output_format} failed, serving original')
        
        # Return image with proper cache headers
        return Response(
            image_data,
            mimetype=original_content_type,
            headers={
                'Cache-Control': 'public, max-age=2592000, immutable',  # 30 days
                'Content-Length': len(image_data),
                'X-Content-Type-Options': 'nosniff',
                'Access-Control-Allow-Origin': '*'  # Allow CORS
            }
        )
        
    except requests.Timeout:
        log(f'⏱️ Image proxy timeout: {image_url[:60]}... (>{timeout}s)')
        return jsonify({'error': f'Image fetch timeout (>{timeout}s)'}), 504
    
    except requests.ConnectionError as e:
        log(f'❌ Connection error: {str(e)[:100]}')
        return jsonify({'error': 'Failed to connect to source'}), 502
    
    except Exception as e:
        log(f'❌ Proxy error: {str(e)[:100]}')
        return jsonify({'error': str(e)[:100]}), 500
