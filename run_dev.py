#!/usr/bin/env python3
"""
MangaNegus Development Server
Runs Flask on port 5000 for development/editing
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from manganegus_app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )
