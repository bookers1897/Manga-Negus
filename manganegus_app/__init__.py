# Load environment variables FIRST before any other imports
from dotenv import load_dotenv
load_dotenv()

import os
import sys
import json
import time
import shutil
import zipfile
import threading
import secrets
from typing import Dict, List, Optional, Any
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask import g
import uuid

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__,
               static_folder='../static',
               template_folder='../templates',
               instance_relative_config=True)
    
    # =============================================================================
    # CONFIGURATION
    # =============================================================================
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    def get_or_create_secret_key() -> str:
        # ... (secret key logic remains the same)
        env_key = os.environ.get('SECRET_KEY')
        if env_key:
            return env_key
        key_file = os.path.join(BASE_DIR, '..', '.secret_key')
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                return f.read().strip()
        new_key = secrets.token_hex(32)
        with open(key_file, 'w') as f:
            f.write(new_key)
        return new_key

    app.config.from_mapping(
        JSON_SORT_KEYS=False,
        SECRET_KEY=get_or_create_secret_key(),
    )

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # =============================================================================
    # LOGGING, CSRF, RATE LIMITING, and OTHER EXTENSIONS
    # =============================================================================
    from .log import log, msg_queue
    from .csrf import ensure_csrf_token, get_csrf_token
    from .rate_limit import init_rate_limiting

    # Initialize rate limiting (disable in debug if needed)
    init_rate_limiting(app)

    @app.before_request
    def assign_request_id():
        g.request_id = uuid.uuid4().hex[:12]

    app.before_request(ensure_csrf_token)

    @app.route('/api/csrf-token')
    def csrf_token_route():
        return get_csrf_token()

    # =============================================================================
    # APPLICATION EXTENSIONS (Library, Downloader)
    # =============================================================================
    # Import singleton instances from extensions module
    from .extensions import library, downloader

    # =============================================================================
    # BLUEPRINTS & ROUTES
    # =============================================================================
    from .routes.main_api import main_bp
    from .routes.sources_api import sources_bp
    from .routes.manga_api import manga_bp
    from .routes.library_api import library_bp
    from .routes.downloads_api import downloads_bp
    from .routes.metadata_api import metadata_api_bp
    from .routes.history_api import history_bp
    from .routes.cloud_api import cloud_bp
    from .routes.auth_api import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(sources_bp)
    app.register_blueprint(manga_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(downloads_bp)
    app.register_blueprint(metadata_api_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(cloud_bp)
    app.register_blueprint(auth_bp)
    
    # =============================================================================
    # INITIALIZATION LOGIC (from old if __name__ == '__main__')
    # =============================================================================
    with app.app_context():
        # Register logging callback for sources
        from sources.base import set_log_callback
        set_log_callback(log)

        # Initialize sources
        from sources import get_source_manager
        manager = get_source_manager()

        print("=" * 60)
        print("  MangaNegus v4.0 - Authentication & Performance Edition")
        print("=" * 60)
        print(f"\n📚 Loaded {len(manager.sources)} sources:")
        for source in manager.sources.values():
            status = "✅" if source.is_available else "❌"
            print(f"   {status} {source.icon} {source.name} ({source.id})")

        if manager.active_source:
            print(f"\n🎯 Active source: {manager.active_source.name}")
        
        # Set config for app.run()
        app.config['HOST'] = os.environ.get('FLASK_HOST', '127.0.0.1')
        app.config['PORT'] = int(os.environ.get('FLASK_PORT', '5000'))
        app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 'yes')

        print(f"\n🌐 Server: http://{app.config['HOST']}:{app.config['PORT']}")
        if app.config['DEBUG']:
            print("⚠️  Debug mode is ON - do not use in production!")
        print("=" * 60)

    return app

# App instance should be created by the caller (run.py or WSGI entrypoint)
