"""Flask application factory with blueprints."""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os
import sys
import signal
import logging

# Load environment variables early
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import blueprints
from routes import auth_bp, admin_bp, widget_bp, google_auth_bp, settings_bp, init_drive_monitor
from drive_monitor import DriveMonitor

# Import services for initialization
import openai


def setup_logging(app: Flask):
    """Configure centralized logging for the application."""
    log_level = logging.INFO
    if app.debug:
        log_level = logging.DEBUG
    
    # Remove existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Set app logger
    app.logger.setLevel(log_level)


def create_app():
    """Application factory pattern for creating Flask app."""
    app = Flask(__name__)
    
    # Setup logging
    setup_logging(app)
    logger = logging.getLogger(__name__)
    
    # Initialize rate limiter
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    app.extensions['limiter'] = limiter
    
    # Enable CORS
    cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000')
    allowed_origins = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
    
    CORS(app, resources={
        r"/backend/api/*": {
            "origins": allowed_origins or ["http://localhost:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Widget-API-Key", "X-Customer-ID", "X-Parent-URL"],
            "supports_credentials": True
        }
    })
    
    # Secret key
    if os.getenv('FLASK_ENV') == 'production':
        secret_key = os.getenv('SECRET_KEY')
        if not secret_key:
            raise ValueError("SECRET_KEY environment variable is required in production")
    else:
        secret_key = os.getenv('SECRET_KEY', 'default-secret-key-for-development')
    
    app.secret_key = secret_key
    
    # Session configuration for OAuth
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 600  # 10 minutes
    
    # Production security settings
    if os.getenv('FLASK_ENV') == 'production':
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
        
        @app.after_request
        def set_security_headers(response):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            return response
    
    # Configure OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        if os.getenv('FLASK_ENV') == 'production':
            raise ValueError("OPENAI_API_KEY environment variable is required in production")
        logger.warning("OPENAI_API_KEY is not set; OpenAI-dependent features may not work")
    openai.api_key = api_key
    
    # Make OpenAI key available to services
    app.config['OPENAI_API_KEY'] = api_key
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(widget_bp)
    app.register_blueprint(google_auth_bp)
    app.register_blueprint(settings_bp)
    
    # Initialize drive monitor and pass to admin blueprint
    drive_monitor = DriveMonitor(document_manager=None)
    drive_monitor.start()
    init_drive_monitor(drive_monitor)
    
    # Store drive monitor in app config for access in routes
    app.config['DRIVE_MONITOR'] = drive_monitor
    
    # Graceful shutdown handler
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, stopping services...")
        drive_monitor.stop()
        logger.info("Services stopped, shutting down.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Health check endpoint
    @app.route('/backend/api/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy'})
    
    # Serve React App
    build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_react(path):
        if not os.path.exists(build_dir):
            return jsonify({'error': 'Frontend not built. Run "npm run build" in the frontend directory.'}), 503
        if path != "" and os.path.exists(os.path.join(build_dir, path)):
            return send_from_directory(build_dir, path)
        else:
            return send_from_directory(build_dir, 'index.html')
    
    # Global error handlers
    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith('/backend/api/'):
            return jsonify({'error': 'Not found'}), 404
        if not os.path.exists(build_dir):
            return jsonify({'error': 'Frontend not built. Run "npm run build" in the frontend directory.'}), 503
        return send_from_directory(build_dir, 'index.html')
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Internal server error")
        return jsonify({'error': 'Internal server error'}), 500
    
    logger.info("Flask application initialized with blueprints")
    return app


# Create app instance for direct execution
app = create_app()

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') != 'production'
    port = int(os.getenv('PORT', 5000))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
