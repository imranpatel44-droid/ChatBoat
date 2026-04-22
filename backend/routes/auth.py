```python
"""Authentication routes blueprint."""
import os
from flask import Blueprint, request, jsonify, make_response, session, redirect, url_for
from functools import wraps

from auth import (
    register_user,
    authenticate_user,
    token_required,
    refresh_access_token,
    blacklist_token,
    TOKEN_EXPIRY,
    REFRESH_TOKEN_EXPIRY,
)

# Create blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/backend/api')

# Secure cookie settings
SECURE_COOKIES = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
COOKIE_SAMESITE = os.getenv('COOKIE_SAMESITE', 'Strict')


def login_required(f):
    """Decorator for routes that require admin session login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Admin login required'}), 401
            return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# =========================
# REGISTER (UPDATED SAFELY)
# =========================
@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user account."""
    try:
        if request.is_json:
            json_data = request.get_json()
            if json_data:
                username = json_data.get('username')
                email = json_data.get('email')
                password = json_data.get('password')
                website_url = json_data.get('website_url')
                name = json_data.get('name', username)
                
                if not all([username, email, password, website_url]):
                    return jsonify({'success': False, 'error': 'Missing required fields'}), 400
                
                result = register_user(username, email, password, name, website_url)

                # ✅ FIX: Ensure consistent response
                if isinstance(result, dict):
                    if result.get('success'):
                        return jsonify({
                            'success': True,
                            'message': result.get('message', 'User registered successfully')
                        }), 200
                    else:
                        return jsonify({
                            'success': False,
                            'error': result.get('error', 'Registration failed')
                        }), 400

                return jsonify({'success': False, 'error': 'Unexpected response'}), 500

        return jsonify({'success': False, 'error': 'Invalid request format'}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================
# LOGIN (UPDATED SAFELY)
# =========================
@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and set auth cookies."""
    try:
        if request.is_json:
            json_data = request.get_json()
            if json_data:
                email = json_data.get('email')
                password = json_data.get('password')
                
                if not all([email, password]):
                    return jsonify({'success': False, 'error': 'Missing required fields'}), 400
                
                result = authenticate_user(email, password)

                if result.get('success'):
                    response = make_response(jsonify({
                        'success': True,
                        'customer_id': result['customer_id'],
                        'username': result['username'],
                        'email': result['email']
                    }))

                    response.set_cookie(
                        'access_token',
                        result['token'],
                        httponly=True,
                        secure=SECURE_COOKIES,
                        samesite=COOKIE_SAMESITE,
                        max_age=result.get('expires_in', TOKEN_EXPIRY * 3600),
                        path='/'
                    )

                    response.set_cookie(
                        'refresh_token',
                        result['refresh_token'],
                        httponly=True,
                        secure=SECURE_COOKIES,
                        samesite=COOKIE_SAMESITE,
                        max_age=result.get('refresh_expires_in', REFRESH_TOKEN_EXPIRY * 24 * 3600),
                        path='/'
                    )

                    return response

                # ✅ FIX: always return proper error
                return jsonify({
                    'success': False,
                    'error': result.get('error', 'Invalid credentials')
                }), 401

        return jsonify({'success': False, 'error': 'Invalid request format'}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================
# REFRESH (UNCHANGED)
# =========================
@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    """Refresh access token using refresh token."""
    if request.is_json:
        json_data = request.get_json()
        if json_data:
            refresh_token = json_data.get('refresh_token') or request.cookies.get('refresh_token')
            
            if not refresh_token:
                return jsonify({'success': False, 'error': 'Refresh token is required'}), 400
            
            result = refresh_access_token(refresh_token)

            if result.get('success'):
                response = make_response(jsonify({
                    'success': True,
                    'expires_in': result.get('expires_in')
                }))

                response.set_cookie(
                    'access_token',
                    result['token'],
                    httponly=True,
                    secure=SECURE_COOKIES,
                    samesite=COOKIE_SAMESITE,
                    max_age=result.get('expires_in', TOKEN_EXPIRY * 3600),
                    path='/'
                )

                return response

            return jsonify(result)
    
    return jsonify({'success': False, 'error': 'Invalid request format'}), 400


# =========================
# AUTH STATUS (UNCHANGED)
# =========================
@auth_bp.route('/auth/status', methods=['GET'])
@token_required
def auth_status(current_user):
    """Check authentication status."""
    return jsonify({
        'success': True,
        'user': current_user
    })


# =========================
# LOGOUT (UNCHANGED)
# =========================
@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout(current_user):
    """Logout user and blacklist tokens."""
    try:
        auth_header = request.headers.get('Authorization')
        access_token = None
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header.split(' ')[1]
        
        json_data = request.get_json() if request.is_json else {}
        refresh_token = json_data.get('refresh_token') or request.cookies.get('refresh_token')
        
        if not access_token:
            access_token = request.cookies.get('access_token')

        if access_token:
            blacklist_token(access_token)
        
        if refresh_token:
            blacklist_token(refresh_token)

        response = make_response(jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }))

        response.set_cookie('access_token', '', expires=0, max_age=0)
        response.set_cookie('refresh_token', '', expires=0, max_age=0)

        return response
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================
# ADMIN LOGIN (UNCHANGED)
# =========================
@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
    
    if request.method == 'POST':
        username = None
        password = None
        
        if request.is_json:
            json_data = request.get_json()
            if json_data:
                username = json_data.get('username')
                password = json_data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')
        
        if username == admin_username and password == admin_password:
            session['admin_logged_in'] = True
            if request.is_json:
                return jsonify({'success': True})
            else:
                return redirect(url_for('admin.admin_dashboard'))
        else:
            error = 'Invalid credentials. Please try again.'
            if request.is_json:
                return jsonify({'success': False, 'error': error})
    
    return jsonify({'success': False, 'error': error}) if request.is_json else error


# =========================
# ADMIN LOGOUT (UNCHANGED)
# =========================
@auth_bp.route('/admin/logout', methods=['GET'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('auth.admin_login'))
```
