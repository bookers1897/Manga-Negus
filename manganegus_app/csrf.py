import secrets
import hmac
from functools import wraps
from flask import request, session, jsonify
from manganegus_app.log import log

def csrf_protect(f):
    """Decorator to require CSRF token on POST requests.

    Uses constant-time comparison to prevent timing attacks.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.headers.get('X-CSRF-Token') or (request.json or {}).get('_csrf_token')
            stored_token = session.get('csrf_token', '')

            # Both tokens must exist and match (constant-time comparison)
            if not token or not stored_token:
                log(f"⚠️ CSRF: Missing token (provided={bool(token)}, stored={bool(stored_token)})")
                return jsonify({'error': 'Invalid or missing CSRF token'}), 403

            if not hmac.compare_digest(token, stored_token):
                log("⚠️ CSRF: Token mismatch detected")
                return jsonify({'error': 'Invalid or missing CSRF token'}), 403

        return f(*args, **kwargs)
    return decorated_function

def ensure_csrf_token():
    """Generate CSRF token for the session if not present."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)

def regenerate_csrf_token():
    """Force regeneration of CSRF token (call after sensitive actions)."""
    session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def get_csrf_token():
    """Return the CSRF token for the current session."""
    ensure_csrf_token()
    return jsonify({'csrf_token': session.get('csrf_token', '')})
