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
from flask import request, jsonify, g
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
HEAVY_LIMIT = "10 per minute"

# Medium operations - database/API calls
MEDIUM_LIMIT = "30 per minute"

# Light operations - fast reads
LIGHT_LIMIT = "60 per minute"

# Burst operations - high volume with caching (image proxy)
BURST_LIMIT = "120 per minute"

# Download operations - resource intensive
DOWNLOAD_LIMIT = "5 per minute"


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
    """Custom handler for rate limit exceeded errors."""
    return jsonify({
        "error": "Rate limit exceeded",
        "message": str(e.description),
        "retry_after": e.retry_after if hasattr(e, 'retry_after') else 60
    }), 429


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
