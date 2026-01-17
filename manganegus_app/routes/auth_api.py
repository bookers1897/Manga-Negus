"""
Authentication API Blueprint

Provides user registration, login, logout, and profile management.
Uses session-based authentication with PBKDF2-SHA256 password hashing.

OAuth-ready: password_hash is nullable for future OAuth-only users.
"""
from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import re
import uuid

from manganegus_app.log import log
from manganegus_app.csrf import csrf_protect
from manganegus_app.models import User
from manganegus_app.database import get_db_session
from .validators import validate_fields

auth_bp = Blueprint('auth_api', __name__, url_prefix='/api/auth')

# Constants
MIN_PASSWORD_LENGTH = 8
MAX_EMAIL_LENGTH = 255
MAX_DISPLAY_NAME_LENGTH = 100

# Email regex pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def get_current_user():
    """Get the currently logged-in user from session.

    Returns:
        User object if logged in, None otherwise
    """
    user_id = session.get('user_id')
    if not user_id:
        return None

    try:
        with get_db_session() as db:
            user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            if user:
                # Detach from session so it can be used after context closes
                db.expunge(user)
            return user
    except Exception:
        return None


def user_to_dict(user):
    """Convert User model to safe dictionary (no password hash)."""
    if not user:
        return None
    return {
        'id': str(user.id),
        'email': user.email,
        'display_name': user.display_name,
        'avatar_url': user.avatar_url,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'is_admin': user.is_admin,
        'oauth_provider': user.oauth_provider,  # Shows if OAuth-connected
    }


@auth_bp.route('/register', methods=['POST'])
@csrf_protect
def register():
    """Register a new user account.

    Request JSON:
        - email: string (required, unique, valid email format)
        - password: string (required, min 8 characters)
        - display_name: string (optional)

    Returns:
        - 201: User created successfully, auto-logged in
        - 400: Validation error
        - 409: Email already registered
    """
    data = request.get_json(silent=True) or {}

    # Validate required fields
    error = validate_fields(data, [
        ('email', str, MAX_EMAIL_LENGTH),
        ('password', str, 128),
    ])
    if error:
        return jsonify({'error': error}), 400

    email = data['email'].strip().lower()
    password = data['password']
    display_name = data.get('display_name', '').strip()[:MAX_DISPLAY_NAME_LENGTH] or None

    # Validate email format
    if not EMAIL_PATTERN.match(email):
        return jsonify({'error': 'Invalid email format'}), 400

    # Validate password length
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters'}), 400

    try:
        with get_db_session() as db:
            # Check if email already exists
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                return jsonify({'error': 'Email already registered'}), 409

            # Create new user
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
                display_name=display_name,
                created_at=datetime.now(timezone.utc),
                is_active=True,
                is_admin=False,
            )
            db.add(user)
            db.flush()  # Get user.id before commit

            # Auto-login after registration
            session['user_id'] = str(user.id)
            session.permanent = True  # Use permanent session (configurable expiry)

            # Create user dict before commit closes session
            user_data = user_to_dict(user)

            log(f"✅ New user registered: {email}")
            return jsonify({
                'status': 'ok',
                'message': 'Registration successful',
                'user': user_data
            }), 201

    except Exception as e:
        log(f"❌ Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500


@auth_bp.route('/login', methods=['POST'])
@csrf_protect
def login():
    """Login with email and password.

    Request JSON:
        - email: string (required)
        - password: string (required)
        - remember: boolean (optional, extends session)

    Returns:
        - 200: Login successful
        - 400: Validation error
        - 401: Invalid credentials
    """
    data = request.get_json(silent=True) or {}

    # Validate required fields
    error = validate_fields(data, [
        ('email', str, MAX_EMAIL_LENGTH),
        ('password', str, 128),
    ])
    if error:
        return jsonify({'error': error}), 400

    email = data['email'].strip().lower()
    password = data['password']
    remember = data.get('remember', False)

    try:
        with get_db_session() as db:
            # Find user by email
            user = db.query(User).filter(User.email == email).first()

            if not user:
                return jsonify({'error': 'Invalid email or password'}), 401

            if not user.is_active:
                return jsonify({'error': 'Account is deactivated'}), 401

            # Check if user has a password (might be OAuth-only)
            if not user.password_hash:
                return jsonify({'error': 'This account uses social login. Please login with your social provider.'}), 401

            # Verify password
            if not check_password_hash(user.password_hash, password):
                return jsonify({'error': 'Invalid email or password'}), 401

            # Update last login
            user.last_login = datetime.now(timezone.utc)

            # Set session
            session['user_id'] = str(user.id)
            session.permanent = remember  # Extended session if remember=True

            # Create user dict before session closes
            user_data = user_to_dict(user)

            log(f"✅ User logged in: {email}")
            return jsonify({
                'status': 'ok',
                'message': 'Login successful',
                'user': user_data
            })

    except Exception as e:
        log(f"❌ Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500


@auth_bp.route('/logout', methods=['POST'])
@csrf_protect
def logout():
    """Logout current user.

    Clears the session while preserving CSRF token.

    Returns:
        - 200: Logout successful
    """
    user_id = session.get('user_id')
    if user_id:
        log(f"✅ User logged out: {user_id}")

    # Clear user from session but keep CSRF token
    session.pop('user_id', None)

    return jsonify({
        'status': 'ok',
        'message': 'Logged out successfully'
    })


@auth_bp.route('/me', methods=['GET'])
def get_me():
    """Get current user info.

    Returns:
        - 200: User info if logged in
        - 200: null if not logged in (graceful handling)
    """
    user = get_current_user()
    return jsonify(user_to_dict(user))


@auth_bp.route('/update', methods=['POST'])
@csrf_protect
def update_profile():
    """Update current user's profile.

    Request JSON (all optional):
        - display_name: string
        - avatar_url: string
        - current_password: string (required if changing password)
        - new_password: string

    Returns:
        - 200: Profile updated
        - 400: Validation error
        - 401: Not logged in
    """
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json(silent=True) or {}
    user_id = user.id  # Save user id before entering new session

    try:
        with get_db_session() as db:
            # Get fresh user from this session
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 401

            # Update display name if provided
            if 'display_name' in data:
                display_name = data['display_name']
                if display_name is not None:
                    display_name = str(display_name).strip()[:MAX_DISPLAY_NAME_LENGTH] or None
                user.display_name = display_name

            # Update avatar URL if provided
            if 'avatar_url' in data:
                avatar_url = data['avatar_url']
                if avatar_url is not None:
                    avatar_url = str(avatar_url).strip()[:1000] or None
                user.avatar_url = avatar_url

            # Change password if requested
            if 'new_password' in data:
                new_password = data['new_password']
                current_password = data.get('current_password')

                # Require current password for password change
                if not current_password:
                    return jsonify({'error': 'Current password required to change password'}), 400

                # Verify current password
                if not user.password_hash or not check_password_hash(user.password_hash, current_password):
                    return jsonify({'error': 'Current password is incorrect'}), 400

                # Validate new password
                if len(new_password) < MIN_PASSWORD_LENGTH:
                    return jsonify({'error': f'New password must be at least {MIN_PASSWORD_LENGTH} characters'}), 400

                user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                log(f"✅ User changed password: {user.email}")

            # Create user dict before session closes
            user_data = user_to_dict(user)

            return jsonify({
                'status': 'ok',
                'message': 'Profile updated',
                'user': user_data
            })

    except Exception as e:
        log(f"❌ Profile update error: {e}")
        return jsonify({'error': 'Update failed'}), 500


# Helper decorator for protected routes
def login_required(f):
    """Decorator to require login for a route."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function
