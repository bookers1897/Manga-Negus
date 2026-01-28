"""Image validation and processing utilities for image proxy and caching.

Provides:
- Image format validation
- Image optimization
- Safe image processing
- Error handling
"""

import io
from typing import Tuple, Optional
from PIL import Image


def is_valid_image(data: bytes) -> Tuple[bool, str]:
    """Validate that data is actually an image.
    
    Returns:
        Tuple of (is_valid: bool, mime_type: str)
    """
    if not data:
        return False, 'empty'
    
    try:
        # Try to open and verify as image
        img = Image.open(io.BytesIO(data))
        img.verify()  # This raises exception if corrupted
        
        # Get actual format
        format_name = img.format or 'UNKNOWN'
        mime_map = {
            'JPEG': 'image/jpeg',
            'PNG': 'image/png',
            'GIF': 'image/gif',
            'WEBP': 'image/webp',
            'BMP': 'image/bmp',
            'TIFF': 'image/tiff',
            'ICO': 'image/x-icon'
        }
        mime = mime_map.get(format_name, f'image/{format_name.lower()}')
        return True, mime
    
    except Exception as e:
        return False, str(type(e).__name__)


def optimize_image(data: bytes, format: str = 'webp', quality: int = 85) -> Optional[bytes]:
    """Safely convert and optimize image data.
    
    Args:
        data: Raw image bytes
        format: Target format (webp, jpeg, png)
        quality: Quality level 1-100 (ignored for PNG)
    
    Returns:
        Optimized image bytes or None on failure
    """
    if not data:
        return None
    
    try:
        # Validate input
        is_valid, _ = is_valid_image(data)
        if not is_valid:
            return None
        
        img = Image.open(io.BytesIO(data))
        
        # Handle format-specific conversions
        if format.lower() == 'jpeg':
            # JPEG doesn't support transparency
            if img.mode in ('RGBA', 'PA', 'P', 'LA'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                # Handle different transparency modes
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
        
        elif format.lower() == 'webp':
            # WebP handles all formats
            if img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                # Preserve alpha if present
                img = img.convert('RGBA' if 'A' in img.mode or img.mode == 'P' else 'RGB')
        
        elif format.lower() == 'png':
            # PNG supports transparency
            if img.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
                img = img.convert('RGBA')
        
        output = io.BytesIO()
        save_kwargs = {
            'format': format.upper(),
            'optimize': True
        }
        
        # Don't set quality for PNG (not applicable)
        if format.lower() != 'png':
            save_kwargs['quality'] = max(10, min(100, quality))
        
        img.save(output, **save_kwargs)
        result = output.getvalue()
        
        return result if result else None
    
    except Exception as e:
        return None


def get_image_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Get image width and height.
    
    Returns:
        Tuple of (width, height) or None if invalid
    """
    try:
        img = Image.open(io.BytesIO(data))
        return img.size
    except Exception:
        return None


def get_image_format(data: bytes) -> Optional[str]:
    """Get image format (JPEG, PNG, GIF, etc).
    
    Returns:
        Format string or None if invalid
    """
    try:
        img = Image.open(io.BytesIO(data))
        return img.format
    except Exception:
        return None


def is_image_corrupted(data: bytes) -> bool:
    """Check if image data is corrupted.
    
    Returns:
        True if corrupted or invalid
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        return False
    except Exception:
        return True


def can_be_converted_to_webp(data: bytes) -> bool:
    """Check if image can be converted to WebP format.
    
    Returns:
        True if conversion is possible
    """
    if not data:
        return False
    
    try:
        img = Image.open(io.BytesIO(data))
        # Check if format is convertible
        convertible_formats = ('JPEG', 'PNG', 'GIF', 'BMP', 'TIFF')
        return img.format in convertible_formats
    except Exception:
        return False
