"""Settings routes for storing OAuth credentials."""
import os
import json
from flask import Blueprint, request, jsonify
from auth import CUSTOMERS_DIR

settings_bp = Blueprint('settings', __name__, url_prefix='/backend/api/settings')

GOOGLE_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), '..', 'google_settings.json')

def get_google_settings():
    """Get Google OAuth settings."""
    if os.path.exists(GOOGLE_SETTINGS_FILE):
        with open(GOOGLE_SETTINGS_FILE) as f:
            return json.load(f)
    return {}

def save_google_settings(settings):
    """Save Google OAuth settings."""
    with open(GOOGLE_SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

@settings_bp.route('/google', methods=['GET'])
def get_google_settings_endpoint():
    """Get current Google OAuth settings (without secrets)."""
    settings = get_google_settings()
    
    return jsonify({
        'configured': bool(settings.get('client_id')),
        'client_id': settings.get('client_id', ''),
        'client_secret_configured': bool(settings.get('client_secret'))
    })

@settings_bp.route('/google', methods=['POST'])
def save_google_settings_endpoint():
    """Save Google OAuth settings."""
    if not request.is_json:
        return jsonify({'error': 'Invalid request format'}), 400
    
    data = request.get_json()
    client_id = data.get('client_id', '').strip()
    client_secret = data.get('client_secret', '').strip()
    
    if not client_id or not client_secret:
        return jsonify({'error': 'Client ID and Client Secret are required'}), 400
    
    settings = {
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/backend/api/auth/google/callback')
    }
    
    save_google_settings(settings)
    
    return jsonify({'success': True, 'message': 'Google OAuth settings saved successfully'})

@settings_bp.route('/google/check', methods=['GET'])
def check_google_settings():
    """Check if Google OAuth is configured."""
    settings = get_google_settings()
    
    if not settings.get('client_id') or not settings.get('client_secret'):
        return jsonify({'configured': False, 'message': 'Google OAuth not configured'})
    
    return jsonify({'configured': True})
