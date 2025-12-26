"""
NEURAL EYE - Authentication Module
Handles user authentication and session management
"""

import hashlib
import secrets
from functools import wraps
from flask import session, redirect, url_for, jsonify
import logging

logger = logging.getLogger(__name__)


def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password, password_hash):
    """Verify password against hash"""
    return hash_password(password) == password_hash


def generate_session_token():
    """Generate a secure session token"""
    return secrets.token_hex(32)


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def api_login_required(f):
    """Decorator to require login for API routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def role_required(required_role):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session:
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            
            role_hierarchy = {'viewer': 0, 'manager': 1, 'admin': 2}
            user_level = role_hierarchy.get(session.get('user_role'), -1)
            required_level = role_hierarchy.get(required_role, 999)
            
            if user_level < required_level:
                return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
