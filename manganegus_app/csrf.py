from functools import wraps
from flask import request, session, jsonify

def csrf_protect(f):
    """Decorator to require CSRF token on POST requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.headers.get('X-CSRF-Token') or (request.json or {}).get('_csrf_token')
            if not token or token != session.get('csrf_token'):
                return jsonify({'error': 'Invalid or missing CSRF token'}), 403
        return f(*args, **kwargs)
    return decorated_function

def ensure_csrf_token():
    """Generate CSRF token for the session if not present."""
    if 'csrf_token' not in session:
        import secrets
        session['csrf_token'] = secrets.token_hex(32)

def get_csrf_token():
    """Return the CSRF token for the current session."""
    return jsonify({'csrf_token': session.get('csrf_token', '')})
