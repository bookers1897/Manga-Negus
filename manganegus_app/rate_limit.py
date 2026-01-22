"""
Rate limiting configuration for MangaNegus API.

Uses Flask-Limiter to protect API endpoints from abuse.

Rate Limit Tiers:
- Heavy: /api/search, /api/download (expensive operations)
- Medium: /api/popular, /api/chapters (moderate load)
- Light: /api/library, /api/sources (cheap operations)
- Burst: /api/proxy/image (high volume but cached)
"""

import os
from functools import wraps
from flask import request, jsonify, g, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize limiter (will be attached to app in create_app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
    strategy="fixed-window",
    headers_enabled=True,  # Add X-RateLimit-* headers to responses
)


# ==============================================================================
# RATE LIMIT TIERS
# ==============================================================================

# Heavy operations - expensive scraping/parallel queries
HEAVY_LIMIT = "20 per minute"

# Medium operations - database/API calls
MEDIUM_LIMIT = "60 per minute"

# Light operations - fast reads
LIGHT_LIMIT = "120 per minute"

# Burst operations - high volume with caching (image proxy)
# Increased to 1200/min (20/sec) for smooth manga page and cover loading
BURST_LIMIT = "1200 per minute"

# Download operations - resource intensive
DOWNLOAD_LIMIT = "10 per minute"


# ==============================================================================
# RATE LIMIT DECORATORS
# ==============================================================================

def limit_heavy(f):
    """Apply heavy rate limit to expensive operations like search."""
    return limiter.limit(HEAVY_LIMIT)(f)


def limit_medium(f):
    """Apply medium rate limit to moderate operations."""
    return limiter.limit(MEDIUM_LIMIT)(f)


def limit_light(f):
    """Apply light rate limit to cheap operations."""
    return limiter.limit(LIGHT_LIMIT)(f)


def limit_burst(f):
    """Apply burst rate limit to high-volume cached operations."""
    return limiter.limit(BURST_LIMIT)(f)


def limit_download(f):
    """Apply strict rate limit to download operations."""
    return limiter.limit(DOWNLOAD_LIMIT)(f)


# ==============================================================================
# ERROR HANDLER
# ==============================================================================

def rate_limit_exceeded_handler(e):
    """
    Custom handler for rate limit exceeded errors.

    Returns JSON for API requests, HTML error page for browser navigations.
    This prevents raw JSON from filling the screen when users hit rate limits
    on page loads.
    """
    retry_after = e.retry_after if hasattr(e, 'retry_after') else 60

    # Check if this is an API request (wants JSON) vs page navigation (wants HTML)
    # API requests typically have Accept: application/json or are to /api/ endpoints
    is_api_request = (
        request.path.startswith('/api/') or
        'application/json' in request.headers.get('Accept', '') or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )

    if is_api_request:
        return jsonify({
            "error": "Rate limit exceeded",
            "message": str(e.description),
            "retry_after": retry_after
        }), 429

    # Return a styled HTML error page for browser navigations
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rate Limited - MangaNegus</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #0a0a0a;
            color: #e5e5e5;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
        }}
        .error-container {{
            max-width: 480px;
            text-align: center;
            padding: 40px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .error-icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 24px;
            margin-bottom: 12px;
            color: #dc2626;
        }}
        p {{
            color: #a3a3a3;
            margin-bottom: 24px;
            line-height: 1.6;
        }}
        .retry-info {{
            background: rgba(220, 38, 38, 0.1);
            border: 1px solid rgba(220, 38, 38, 0.3);
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 24px;
        }}
        .retry-info strong {{
            color: #dc2626;
        }}
        .btn {{
            display: inline-block;
            padding: 12px 24px;
            background: #dc2626;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            transition: background 0.2s;
        }}
        .btn:hover {{
            background: #b91c1c;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">⏱️</div>
        <h1>Rate Limited</h1>
        <p>You've made too many requests. Please wait a moment before trying again.</p>
        <div class="retry-info">
            <strong>Retry after:</strong> {retry_after} seconds
        </div>
        <a href="/" class="btn">Go Home</a>
    </div>
</body>
</html>'''

    response = make_response(html, 429)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Retry-After'] = str(retry_after)
    return response


# ==============================================================================
# INITIALIZATION
# ==============================================================================

def init_rate_limiting(app):
    """
    Initialize rate limiting for a Flask app.

    Call this in create_app() after app configuration.
    """
    limiter.init_app(app)

    # Register custom error handler
    app.errorhandler(429)(rate_limit_exceeded_handler)

    # Optionally disable rate limiting in debug mode
    if app.config.get('DISABLE_RATE_LIMITING'):
        limiter.enabled = False

    return limiter
