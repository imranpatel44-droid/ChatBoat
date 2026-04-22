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


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user account."""
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
            return jsonify(result)
    
    return jsonify({'success': False, 'error': 'Invalid request format'}), 400


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and set auth cookies."""
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

            return jsonify(result)
    
    return jsonify({'success': False, 'error': 'Invalid request format'}), 400


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


@auth_bp.route('/auth/status', methods=['GET'])
@token_required
def auth_status(current_user):
    """Check authentication status."""
    return jsonify({
        'success': True,
        'user': current_user
    })


@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout(current_user):
    """Logout user and blacklist tokens."""
    try:
        # Get both access and refresh tokens
        auth_header = request.headers.get('Authorization')
        access_token = None
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header.split(' ')[1]
        
        json_data = request.get_json() if request.is_json else {}
        refresh_token = json_data.get('refresh_token') or request.cookies.get('refresh_token')
        
        if not access_token:
            access_token = request.cookies.get('access_token')

        # Blacklist access token
        if access_token:
            blacklist_token(access_token)
        
        # Blacklist refresh token if provided
        if refresh_token:
            blacklist_token(refresh_token)

        response = make_response(jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }))

        # Clear cookies
        response.set_cookie(
            'access_token',
            '',
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            expires=0,
            max_age=0,
            path='/'
        )

        response.set_cookie(
            'refresh_token',
            '',
            httponly=True,
            secure=SECURE_COOKIES,
            samesite=COOKIE_SAMESITE,
            expires=0,
            max_age=0,
            path='/'
        )

        return response
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Admin session-based routes (for template-based admin interface)
@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login endpoint supporting both JSON and form submissions."""
    error = None
    
    # Admin credentials from environment
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


@auth_bp.route('/admin/logout', methods=['GET'])
def admin_logout():
    """Admin logout endpoint."""
    session.pop('admin_logged_in', None)
    return redirect(url_for('auth.admin_login'))
