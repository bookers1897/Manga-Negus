from manganegus_app import create_app

app = create_app()

if __name__ == '__main__':
    # Configuration from environment variables is now handled inside the app factory
    # You can still override them here for local runs if needed
    host = app.config.get('HOST', '127.0.0.1')
    port = app.config.get('PORT', 5000)
    debug = app.config.get('DEBUG', False)
    
    app.run(host=host, port=port, debug=debug)