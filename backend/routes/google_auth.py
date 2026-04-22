"""Google OAuth authentication routes."""
import os
import json
import uuid
import secrets
import hashlib
import datetime
import threading

# Fix for local development - allow HTTP
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Blueprint, request, jsonify, make_response, redirect, url_for, session
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from auth import CUSTOMERS_DIR

# In-memory storage for OAuth state (thread-safe)
oauth_storage = {}
oauth_lock = threading.Lock()

def store_oauth_state(state, code_verifier):
    """Store OAuth state and code verifier."""
    with oauth_lock:
        oauth_storage[state] = {
            'code_verifier': code_verifier,
            'created': datetime.datetime.now()
        }

def get_oauth_state(state):
    """Retrieve OAuth state and code verifier."""
    with oauth_lock:
        return oauth_storage.get(state)

def clear_oauth_state(state):
    """Clear OAuth state after use."""
    with oauth_lock:
        oauth_storage.pop(state, None)

# Clean up old entries periodically (older than 10 minutes)
def cleanup_oauth_storage():
    """Clean up old OAuth entries."""
    import time
    while True:
        time.sleep(300)  # Every 5 minutes
        with oauth_lock:
            now = datetime.datetime.now()
            to_remove = []
            for state, data in oauth_storage.items():
                if (now - data['created']).total_seconds() > 600:
                    to_remove.append(state)
            for state in to_remove:
                oauth_storage.pop(state, None)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_oauth_storage, daemon=True)
cleanup_thread.start()

google_auth_bp = Blueprint('google_auth', __name__, url_prefix='/backend/api/auth/google')

CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), '..', 'client_secrets.json')
GOOGLE_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), '..', 'google_settings.json')

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/drive.readonly'
]

REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/backend/api/auth/google/callback')

def get_client_config():
    """Get Google OAuth client configuration."""
    # First check google_settings.json (user configured via frontend)
    if os.path.exists(GOOGLE_SETTINGS_FILE):
        with open(GOOGLE_SETTINGS_FILE) as f:
            settings = json.load(f)
        if settings.get('client_id') and settings.get('client_secret'):
            return {
                "web": {
                    "client_id": settings['client_id'],
                    "client_secret": settings['client_secret'],
                    "redirect_uris": [settings.get('redirect_uri', REDIRECT_URI)],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
    
    # Then check client_secrets.json
    if os.path.exists(CLIENT_SECRETS_FILE):
        with open(CLIENT_SECRETS_FILE) as f:
            config = json.load(f)
        if config.get('web', {}).get('client_id') != 'YOUR_GOOGLE_CLIENT_ID':
            return config
    
    # Then check environment variables
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return None
    
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

def save_credentials(customer_id, credentials):
    """Save Google OAuth credentials for customer."""
    profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
    
    if not os.path.exists(profile_path):
        return False
    
    with open(profile_path) as f:
        profile = json.load(f)
    
    profile['google_access_token'] = credentials.token
    profile['google_refresh_token'] = credentials.refresh_token
    profile['google_token_expiry'] = credentials.expiry.isoformat() if credentials.expiry else None
    
    with open(profile_path, 'w') as f:
        json.dump(profile, f, indent=2)
    
    return True

def get_credentials(customer_id):
    """Get Google OAuth credentials for a customer."""
    profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
    
    if not os.path.exists(profile_path):
        return None
    
    with open(profile_path) as f:
        profile = json.load(f)
    
    access_token = profile.get('google_access_token')
    refresh_token = profile.get('google_refresh_token')
    
    if not access_token:
        return None
    
    client_config = get_client_config()
    if not client_config:
        return None
    
    token_info = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer',
    }
    
    credentials = Credentials.from_authorized_user_info(token_info, SCOPES)
    
    return credentials

@google_auth_bp.route('/login', methods=['GET'])
def google_login():
    """Initiate Google OAuth flow."""
    try:
        client_config = get_client_config()
        
        if not client_config:
            return jsonify({'error': 'Google OAuth not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env file'}), 500
        
        # Create flow with PKCE
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        # Generate code verifier and challenge for PKCE
        code_verifier = secrets.token_urlsafe(32)
        
        # Create the authorization URL manually with PKCE
        from urllib.parse import urlencode
        code_challenge = hashlib.sha256(code_verifier.encode()).hexdigest()
        
        auth_params = {
            'response_type': 'code',
            'client_id': client_config['web']['client_id'],
            'redirect_uri': REDIRECT_URI,
            'scope': ' '.join(SCOPES),
            'access_type': 'offline',
            'prompt': 'consent',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        authorization_url = 'https://accounts.google.com/o/oauth2/auth?' + urlencode(auth_params)
        
        # Generate state
        state = secrets.token_urlsafe(32)
        
        # Store state and code verifier
        store_oauth_state(state, code_verifier)
        
        print(f"Stored code_verifier for state: {state[:10]}...")
        
        return jsonify({'authorization_url': authorization_url})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@google_auth_bp.route('/callback', methods=['GET'])
def google_callback():
    """Handle Google OAuth callback."""
    try:
        # Check for error in query params
        error = request.args.get('error')
        if error:
            error_description = request.args.get('error_description', error)
            print(f"Google OAuth Error: {error} - {error_description}")
            return redirect(f'/admin/dashboard?error=oauth_failed&message={error_description}')
        
        client_config = get_client_config()
        
        if not client_config:
            return jsonify({'error': 'Google OAuth not configured'}), 500
        
        # Get state from query params and retrieve code verifier
        state = request.args.get('state')
        if not state:
            print("Missing state in callback")
            return redirect('/admin/dashboard?error=oauth_failed&message=Missing state')
        
        oauth_data = get_oauth_state(state)
        if not oauth_data:
            print(f"No OAuth data found for state: {state[:10]}...")
            return redirect('/admin/dashboard?error=oauth_failed&message=Missing code verifier')
        
        code_verifier = oauth_data['code_verifier']
        
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        # Fetch token with code verifier - manual token exchange
        from urllib.parse import urlencode
        import requests
        
        auth_code = request.args.get('code')
        
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'client_id': client_config['web']['client_id'],
            'client_secret': client_config['web']['client_secret'],
            'code': auth_code,
            'code_verifier': code_verifier,
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI
        }
        
        token_response = requests.post(token_url, data=token_data)
        
        if token_response.status_code != 200:
            print(f"Token exchange failed: {token_response.text}")
            return redirect('/admin/dashboard?error=oauth_failed&message=Token exchange failed')
        
        token_info = token_response.json()
        
        credentials = Credentials(
            token=token_info['access_token'],
            refresh_token=token_info.get('refresh_token'),
            token_uri=token_url,
            client_id=client_config['web']['client_id'],
            client_secret=client_config['web']['client_secret'],
            scopes=SCOPES
        )
        
        oauth2_service = build('oauth2', 'v2', credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        
        email = user_info.get('email')
        
        USERS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')
        
        customer_id = None
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE) as f:
                users = json.load(f)
            if email in users:
                customer_id = users[email]['customer_id']
        
        if not customer_id:
            return redirect('/admin/login?error=no_account')
        
        save_credentials(customer_id, credentials)
        
        # Clear OAuth state
        clear_oauth_state(state)
        
        return redirect(f'/admin/dashboard?google_auth=success')
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Google OAuth Exception: {str(e)}")
        error_msg = str(e)
        return redirect(f'/admin/dashboard?error=oauth_failed&message={error_msg}')

@google_auth_bp.route('/folders', methods=['GET'])
def get_drive_folders():
    """Get list of folders from user's Google Drive."""
    customer_id = request.headers.get('X-Customer-ID')
    
    if not customer_id:
        return jsonify({'error': 'Customer ID is required'}), 400
    
    credentials = get_credentials(customer_id)
    
    if not credentials:
        return jsonify({'error': 'Please connect your Google account first'}), 401
    
    try:
        service = build('drive', 'v3', credentials=credentials)
        
        results = []
        page_token = None
        
        while True:
            response = service.files().list(
                q="mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="nextPageToken, files(id, name, parents)",
                pageSize=100,
                pageToken=page_token
            ).execute()
            
            results.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            
            if not page_token:
                break
        
        return jsonify({'folders': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@google_auth_bp.route('/select-folder', methods=['POST'])
def select_drive_folder():
    """Save selected Drive folder for a customer."""
    if not request.is_json:
        return jsonify({'error': 'Invalid request format'}), 400
    
    data = request.get_json()
    customer_id = data.get('customer_id')
    folder_id = data.get('folder_id')
    folder_name = data.get('folder_name')
    
    if not all([customer_id, folder_id, folder_name]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    customer_folder = os.path.join(CUSTOMERS_DIR, customer_id)
    
    if not os.path.exists(customer_folder):
        return jsonify({'error': 'Customer not found'}), 404
    
    folder_link = f"https://drive.google.com/drive/folders/{folder_id}"
    
    drive_config = {
        'folder_id': folder_id,
        'folder_name': folder_name,
        'folder_link': folder_link,
        'connected_at': datetime.datetime.now().isoformat()
    }
    
    with open(os.path.join(customer_folder, 'drive_config.json'), 'w') as f:
        json.dump(drive_config, f, indent=2)
    
    return jsonify({'success': True, 'folder_link': folder_link, 'drive_config': drive_config})

@google_auth_bp.route('/status', methods=['GET'])
def google_auth_status():
    """Check if user has connected Google account."""
    customer_id = request.headers.get('X-Customer-ID')
    
    if not customer_id:
        return jsonify({'error': 'Customer ID is required'}), 400
    
    profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
    
    if not os.path.exists(profile_path):
        return jsonify({'connected': False})
    
    with open(profile_path) as f:
        profile = json.load(f)
    
    connected = bool(profile.get('google_access_token'))
    
    return jsonify({
        'connected': connected,
        'email': profile.get('email'),
        'name': profile.get('name')
    })

@google_auth_bp.route('/disconnect', methods=['POST'])
def disconnect_google():
    """Disconnect Google account from customer."""
    data = request.get_json() or {}
    customer_id = data.get('customer_id')
    
    if not customer_id:
        return jsonify({'error': 'Customer ID is required'}), 400
    
    profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
    
    if not os.path.exists(profile_path):
        return jsonify({'error': 'Customer not found'}), 404
    
    with open(profile_path) as f:
        profile = json.load(f)
    
    profile.pop('google_access_token', None)
    profile.pop('google_refresh_token', None)
    profile.pop('google_token_expiry', None)
    
    with open(profile_path, 'w') as f:
        json.dump(profile, f, indent=2)
    
    return jsonify({'success': True})
