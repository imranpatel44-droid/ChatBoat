import os
import json
import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify

# Constants
CUSTOMERS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'customers')
USERS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'users.json')
BLACKLIST_FILE = os.path.join(os.path.dirname(__file__), 'data', 'token_blacklist.json')
SECRET_KEY = os.getenv('JWT_SECRET_KEY', '').strip()
REFRESH_SECRET_KEY = os.getenv('JWT_REFRESH_SECRET_KEY', '').strip()
if os.getenv('FLASK_ENV') == 'production':
    if not SECRET_KEY:
        raise ValueError('JWT_SECRET_KEY environment variable is required in production')
    if not REFRESH_SECRET_KEY:
        raise ValueError('JWT_REFRESH_SECRET_KEY environment variable is required in production')
else:
    if not SECRET_KEY:
        SECRET_KEY = 'dev-jwt-secret-key-change-me'
    if not REFRESH_SECRET_KEY:
        REFRESH_SECRET_KEY = 'dev-jwt-refresh-secret-key-change-me'
TOKEN_EXPIRY = 1  # hours (shortened for better security)
REFRESH_TOKEN_EXPIRY = 7  # days

# Ensure directories exist
os.makedirs(CUSTOMERS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)

# Initialize blacklist file
if not os.path.exists(BLACKLIST_FILE):
    with open(BLACKLIST_FILE, 'w') as f:
        json.dump([], f)

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def validate_password_strength(password):
    """Validate password strength requirements"""
    if len(password) < 8:
        return {'valid': False, 'error': 'Password must be at least 8 characters long'}
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
    
    if not has_upper:
        return {'valid': False, 'error': 'Password must contain at least one uppercase letter'}
    if not has_lower:
        return {'valid': False, 'error': 'Password must contain at least one lowercase letter'}
    if not has_digit:
        return {'valid': False, 'error': 'Password must contain at least one number'}
    if not has_special:
        return {'valid': False, 'error': 'Password must contain at least one special character'}
    
    return {'valid': True}

def validate_email(email):
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return {'valid': False, 'error': 'Invalid email format'}
    return {'valid': True}

def validate_url(url):
    """Validate URL format"""
    import re
    pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}.*$'
    if not re.match(pattern, url):
        return {'valid': False, 'error': 'Invalid URL format. Must start with http:// or https://'}
    return {'valid': True}

def register_user(username, email, password, name=None, website_url=None):
    """Register a new user with UUID generation"""
    # Validate email format
    email_validation = validate_email(email)
    if not email_validation['valid']:
        return {'success': False, 'error': email_validation['error']}
    
    # Validate password strength
    password_validation = validate_password_strength(password)
    if not password_validation['valid']:
        return {'success': False, 'error': password_validation['error']}
    
    # Validate website URL if provided
    if not website_url:
        return {'success': False, 'error': 'Website URL is required'}
    
    url_validation = validate_url(website_url)
    if not url_validation['valid']:
        return {'success': False, 'error': url_validation['error']}
    
    # Load existing users
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            users = json.load(f)
    else:
        users = {}
    
    # Check if email already exists
    if email in users:
        return {'success': False, 'error': 'User with this email already exists'}
    
    # Generate UUID for customer folder
    customer_id = uuid.uuid4().hex
    
    # Create customer folder structure
    folder_path = os.path.join(CUSTOMERS_DIR, customer_id)
    vector_store_path = os.path.join(folder_path, 'vector_store')
    os.makedirs(vector_store_path, exist_ok=True)
    
    # Initialize empty vector store with necessary files
    with open(os.path.join(vector_store_path, 'documents.json'), 'w') as f:
        json.dump([], f)
    
    # Create empty embeddings.npy file (will be populated when documents are processed)
    import numpy as np
    empty_embeddings = np.array([]).reshape(0, 1536)  # OpenAI embeddings are 1536 dimensions
    np.save(os.path.join(vector_store_path, 'embeddings.npy'), empty_embeddings)
    
    # Create profile.json
    profile = {
        'customer_id': customer_id,
        'username': username,
        'name': name or username,
        'email': email,
        'password_hash': hash_password(password),
        'website_url': website_url,
        'created_at': datetime.now().isoformat(),
        'plan': 'free'
    }
    
    with open(os.path.join(folder_path, 'profile.json'), 'w') as f:
        json.dump(profile, f, indent=2)
    
    # Update users index
    users[email] = {'customer_id': customer_id, 'username': username}
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)
    
    return {'success': True, 'message': 'Registration successful', 'customer_id': customer_id}

def authenticate_user(email, password):
    """Authenticate a user and return JWT token if successful"""
    # Check if users index exists
    if not os.path.exists(USERS_FILE):
        return {'success': False, 'error': 'Authentication failed'}
    
    # Load users index
    with open(USERS_FILE) as f:
        users = json.load(f)
    
    # Check if email exists
    if email not in users:
        return {'success': False, 'error': 'Invalid email or password'}
    
    # Get customer_id
    customer_id = users[email]['customer_id']
    
    # Load profile
    profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
    if not os.path.exists(profile_path):
        return {'success': False, 'error': 'User profile not found'}
    
    with open(profile_path) as f:
        profile = json.load(f)
    
    # Verify password using bcrypt
    stored_hash = profile['password_hash']
    if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
        return {'success': False, 'error': 'Invalid email or password'}
    
    # Generate JWT access token
    access_payload = {
        'customer_id': customer_id,
        'email': email,
        'username': profile['username'],
        'type': 'access',
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY)
    }
    
    # Generate refresh token
    refresh_payload = {
        'customer_id': customer_id,
        'email': email,
        'type': 'refresh',
        'exp': datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRY)
    }
    
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm='HS256')
    refresh_token = jwt.encode(refresh_payload, REFRESH_SECRET_KEY, algorithm='HS256')
    
    return {
        'success': True,
        'token': access_token,
        'refresh_token': refresh_token,
        'customer_id': customer_id,
        'username': profile['username'],
        'email': email,
        'expires_in': TOKEN_EXPIRY * 3600,  # in seconds
        'refresh_expires_in': REFRESH_TOKEN_EXPIRY * 24 * 3600
    }

def is_token_blacklisted(token):
    """Check if token is blacklisted"""
    try:
        with open(BLACKLIST_FILE, 'r') as f:
            blacklist = json.load(f)
            return token in blacklist
    except:
        return False

def blacklist_token(token):
    """Add token to blacklist"""
    try:
        with open(BLACKLIST_FILE, 'r') as f:
            blacklist = json.load(f)
        
        if token not in blacklist:
            blacklist.append(token)
            
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump(blacklist, f)
        
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def refresh_access_token(refresh_token):
    """Generate new access token from refresh token"""
    try:
        # Check if refresh token is blacklisted
        if is_token_blacklisted(refresh_token):
            return {'success': False, 'error': 'Refresh token has been revoked'}
        
        # Decode refresh token
        payload = jwt.decode(refresh_token, REFRESH_SECRET_KEY, algorithms=['HS256'])
        
        # Verify it's a refresh token
        if payload.get('type') != 'refresh':
            return {'success': False, 'error': 'Invalid token type'}
        
        customer_id = payload['customer_id']
        email = payload['email']
        
        # Load user profile to get username
        profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
        if not os.path.exists(profile_path):
            return {'success': False, 'error': 'User not found'}
        
        with open(profile_path) as f:
            profile = json.load(f)
        
        # Generate new access token
        access_payload = {
            'customer_id': customer_id,
            'email': email,
            'username': profile['username'],
            'type': 'access',
            'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY)
        }
        
        new_access_token = jwt.encode(access_payload, SECRET_KEY, algorithm='HS256')
        
        return {
            'success': True,
            'token': new_access_token,
            'expires_in': TOKEN_EXPIRY * 3600
        }
        
    except jwt.ExpiredSignatureError:
        return {'success': False, 'error': 'Refresh token has expired'}
    except jwt.InvalidTokenError:
        return {'success': False, 'error': 'Invalid refresh token'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def token_required(f):
    """Decorator for routes that require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header or HttpOnly cookie
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            token = request.cookies.get('access_token')

        if not token:
            return jsonify({'success': False, 'error': 'Authentication token is missing'}), 401
        
        # Check if token is blacklisted
        if is_token_blacklisted(token):
            return jsonify({'success': False, 'error': 'Token has been revoked'}), 401
        
        try:
            # Decode token
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            
            # Verify it's an access token
            if payload.get('type') != 'access':
                return jsonify({'success': False, 'error': 'Invalid token type'}), 401
            
            customer_id = payload['customer_id']
            
            # Check if user exists
            profile_path = os.path.join(CUSTOMERS_DIR, customer_id, 'profile.json')
            if not os.path.exists(profile_path):
                return jsonify({'success': False, 'error': 'User not found'}), 401
            
            # Pass current user info to the wrapped function
            current_user = {
                'customer_id': customer_id,
                'email': payload.get('email'),
                'username': payload.get('username')
            }
            
            return f(current_user=current_user, *args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token has expired', 'expired': True}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    return decorated

def get_user_vector_store_dir(current_user):
    """Get the vector store directory for a specific customer"""
    customer_id = current_user.get('customer_id')
    if not customer_id:
        raise ValueError("Invalid user: missing customer_id")
    return os.path.join(CUSTOMERS_DIR, customer_id, 'vector_store')