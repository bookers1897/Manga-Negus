"""
Authentication API Blueprint

Provides user registration, login, logout, and profile management.
Uses session-based authentication with PBKDF2-SHA256 password hashing.

OAuth-ready: password_hash is nullable for future OAuth-only users.
"""
from flask import Blueprint, jsonify, request, g, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError
from manganegus_app.database import get_db_session
from manganegus_app.models import User
from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect, regenerate_csrf_token
from manganegus_app.rate_limit import limiter
from manganegus_app.routes.validators import validate_fields
import functools
import re
import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth_api', __name__, url_prefix='/api/auth')
login_manager = LoginManager()

# Constants
MIN_PASSWORD_LENGTH = 8
MAX_EMAIL_LENGTH = 255
MAX_DISPLAY_NAME_LENGTH = 100
AUTH_RATE_LIMIT = "5 per minute"
AUTH_REGISTER_LIMIT = "3 per hour"

# Email regex pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.environ.get('ADMIN_EMAILS', 'bookers1897@gmail.com').split(',')
    if email.strip()
}

@login_manager.user_loader
def load_user(user_id):
    """Flask-Login user loader."""
    try:
        with get_db_session() as db:
            return db.query(User).get(str(user_id))
    except Exception as e:
        log(f"User load error: {e}")
        return None

def init_login_manager(app):
    """Initialize Flask-Login with the app."""
    login_manager.init_app(app)
    # Disable default redirect for API-first design
    login_manager.login_view = None 

    @app.before_request
    def set_current_user():
        g.current_user = current_user

def is_admin_user(user):
    """Return True if a user is an admin via flag or allowed email list."""
    if not user:
        return False
    # Check if user object has is_admin attribute (it should from User model)
    if hasattr(user, 'is_admin') and user.is_admin:
        return True
    if hasattr(user, 'email') and user.email and user.email.lower() in ADMIN_EMAILS:
        return True
    return False

def admin_required(f):
    @functools.wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not is_admin_user(current_user):
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def optional_login(f):
    """
    Decorator that populates g.current_user if authenticated, but doesn't require it.
    Useful for endpoints that work for both anonymous and authenticated users.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # g.current_user is already set by set_current_user in before_request
        # This decorator just documents that auth is optional
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get the currently logged-in user from session (Legacy helper)."""
    return current_user if current_user.is_authenticated else None

def user_to_dict(user):
    """Convert User model to safe dictionary (no password hash)."""
    if not user:
        return None
    return user.to_dict()

@auth_bp.route('/register', methods=['POST'])
@limiter.limit(AUTH_REGISTER_LIMIT)
@csrf_protect
def register():
    """Register a new user."""
    data = request.get_json(silent=True) or {}
    
    # Validate required fields
    error = validate_fields(data, [
        ('email', str, MAX_EMAIL_LENGTH),
        ('password', str, 128),
    ])
    if error:
        return jsonify({'error': error}), 400

    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    display_name = (data.get('display_name') or '').strip()

    # Validate email format
    if not EMAIL_PATTERN.match(email):
        return jsonify({'error': 'Invalid email format'}), 400
    
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters'}), 400

    try:
        with get_db_session() as db:
            # Check if this is the first user (make admin)
            user_count = db.query(User).count()
            is_first = user_count == 0
            
            # Check if email exists
            if db.query(User).filter_by(email=email).first():
                return jsonify({'error': 'Email already registered'}), 409

            new_user = User(
                email=email,
                display_name=display_name or email.split('@')[0],
                is_admin=is_first or email in ADMIN_EMAILS
            )
            new_user.set_password(password)
            db.add(new_user)
            db.commit()
            
            # Auto-login after registration
            login_user(new_user)
            regenerate_csrf_token()
            
            log(f"New user registered: {email} (Admin: {new_user.is_admin})")
            return jsonify({
                'status': 'ok',
                'user': new_user.to_dict(),
                'message': 'Registration successful'
            })

    except IntegrityError:
        return jsonify({'error': 'Email already registered'}), 409
    except Exception as e:
        log(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@auth_bp.route('/login', methods=['POST'])
@limiter.limit(AUTH_RATE_LIMIT)
@csrf_protect
def login():
    """Login user."""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    remember = data.get('remember', False)

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    try:
        with get_db_session() as db:
            user = db.query(User).filter_by(email=email).first()
            
            if user and user.check_password(password):
                login_user(user, remember=remember)
                user.last_login = datetime.now(timezone.utc)
                db.commit()
                regenerate_csrf_token()
                log(f"User logged in: {email}")
                return jsonify({
                    'status': 'ok',
                    'user': user.to_dict()
                })
            
            return jsonify({'error': 'Invalid credentials'}), 401

    except Exception as e:
        log(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@auth_bp.route('/logout', methods=['POST'])
@login_required
@csrf_protect
def logout():
    """Logout current user."""
    logout_user()
    return jsonify({'status': 'ok', 'message': 'Logged out'})

@auth_bp.route('/me')
def me():
    """Get current user info."""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': current_user.to_dict()
        })
    return jsonify({'authenticated': False})

@auth_bp.route('/update', methods=['POST'])
@login_required
@csrf_protect
def update_profile():
    """Update user profile."""
    data = request.get_json(silent=True) or {}
    display_name = data.get('display_name')
    avatar_url = data.get('avatar_url')
    preferences = data.get('preferences')
    new_password = data.get('new_password')
    current_password = data.get('current_password')

    try:
        with get_db_session() as db:
            # Need to re-fetch user within session to update
            user = db.query(User).get(current_user.id)

            if display_name is not None:
                user.display_name = str(display_name).strip()[:MAX_DISPLAY_NAME_LENGTH]

            # Update avatar URL (validate it's a safe URL)
            if avatar_url is not None:
                avatar_url = str(avatar_url).strip()
                if avatar_url:
                    # Only allow http/https URLs
                    if avatar_url.startswith(('http://', 'https://')):
                        user.avatar_url = avatar_url[:500]  # Limit length
                    else:
                        return jsonify({'error': 'Invalid avatar URL (must be http/https)'}), 400
                else:
                    user.avatar_url = None  # Allow clearing the avatar

            if isinstance(preferences, dict):
                # Merge preferences
                current_prefs = dict(user.preferences or {})
                current_prefs.update(preferences)
                user.preferences = current_prefs

            if new_password:
                if not current_password:
                    return jsonify({'error': 'Current password required'}), 400
                if not user.check_password(current_password):
                    return jsonify({'error': 'Incorrect current password'}), 400
                if len(new_password) < MIN_PASSWORD_LENGTH:
                    return jsonify({'error': f'Password too short (min {MIN_PASSWORD_LENGTH})'}), 400
                user.set_password(new_password)

            db.commit()
            return jsonify({'status': 'ok', 'user': user.to_dict()})
    except Exception as e:
        log(f"Profile update failed: {e}")
        return jsonify({'error': 'Update failed'}), 500

@auth_bp.route('/sessions', methods=['GET'])
@login_required
def get_sessions():
    """Get active sessions (stub)."""
    # Parse user agent for device info
    ua = request.user_agent
    device = 'Desktop'
    if ua.platform:
        if 'iphone' in ua.platform.lower() or 'android' in ua.platform.lower():
            device = 'Mobile'
        elif 'ipad' in ua.platform.lower():
            device = 'Tablet'

    # In a real implementation, we'd query a sessions table
    return jsonify({
        'sessions': [{
            'id': 'current',
            'is_current': True,
            'ip': request.remote_addr,
            'device': device,
            'browser': ua.browser or 'Unknown',
            'created_at': datetime.now(timezone.utc).isoformat()
        }]
    })