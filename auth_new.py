"""
NEURAL EYE - Enhanced Authentication Module
Secure authentication with bcrypt, rate limiting, and session management
"""

import bcrypt
import secrets
import jwt
from functools import wraps
from flask import session, redirect, url_for, jsonify, request
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from collections import defaultdict
import threading

from config import Config

logger = logging.getLogger(__name__)


class PasswordHasher:
    """Secure password hashing using bcrypt"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt with salt"""
        if not password:
            raise ValueError("Password cannot be empty")
        
        # Generate salt and hash
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        if not password or not password_hash:
            return False
        
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
        """Validate password meets security requirements"""
        if len(password) < Config.PASSWORD_MIN_LENGTH:
            return False, f"Password must be at least {Config.PASSWORD_MIN_LENGTH} characters long"
        
        # Check for at least one uppercase, one lowercase, one digit
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        
        if not (has_upper and has_lower and has_digit):
            return False, "Password must contain uppercase, lowercase, and digit"
        
        return True, None


class RateLimiter:
    """Thread-safe rate limiter for login attempts"""
    
    def __init__(self, max_attempts: int = None, window_minutes: int = None):
        self.max_attempts = max_attempts or Config.MAX_LOGIN_ATTEMPTS
        self.window_minutes = window_minutes or Config.LOGIN_ATTEMPT_WINDOW_MINUTES
        self.attempts = defaultdict(list)  # ip -> list of timestamps
        self.lock = threading.Lock()
    
    def is_rate_limited(self, identifier: str) -> tuple[bool, Optional[int]]:
        """Check if identifier is rate limited. Returns (is_limited, seconds_until_reset)"""
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(minutes=self.window_minutes)
            
            # Remove old attempts
            self.attempts[identifier] = [
                ts for ts in self.attempts[identifier]
                if ts > cutoff
            ]
            
            # Check if rate limited
            if len(self.attempts[identifier]) >= self.max_attempts:
                oldest_attempt = min(self.attempts[identifier])
                reset_time = oldest_attempt + timedelta(minutes=self.window_minutes)
                seconds_until_reset = int((reset_time - now).total_seconds())
                return True, max(0, seconds_until_reset)
            
            return False, None
    
    def record_attempt(self, identifier: str):
        """Record a login attempt"""
        with self.lock:
            self.attempts[identifier].append(datetime.now())
    
    def reset(self, identifier: str):
        """Reset attempts for identifier (on successful login)"""
        with self.lock:
            if identifier in self.attempts:
                del self.attempts[identifier]


class TokenManager:
    """JWT token management for API authentication"""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or Config.SECRET_KEY
    
    def generate_token(self, user_id: int, username: str, role: str,
                      expires_hours: int = None) -> str:
        """Generate JWT token"""
        expires_hours = expires_hours or Config.SESSION_LIFETIME_HOURS
        
        payload = {
            'user_id': user_id,
            'username': username,
            'role': role,
            'exp': datetime.utcnow() + timedelta(hours=expires_hours),
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return token
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None


class SessionManager:
    """Enhanced session management"""
    
    @staticmethod
    def create_session(user_id: int, username: str, role: str, employee_id: int = None):
        """Create a new user session"""
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        session['user_role'] = role
        session['employee_id'] = employee_id
        session['session_token'] = secrets.token_hex(32)
        session['login_time'] = datetime.now().isoformat()
        session['last_activity'] = datetime.now().isoformat()
        
        logger.info(f"Session created for user: {username} (role: {role})")
    
    @staticmethod
    def refresh_activity():
        """Update last activity timestamp"""
        if 'user_id' in session:
            session['last_activity'] = datetime.now().isoformat()
    
    @staticmethod
    def is_session_valid() -> bool:
        """Check if session is still valid"""
        if 'user_id' not in session:
            return False
        
        # Check session lifetime
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            session_age = datetime.now() - login_time
            max_age = timedelta(hours=Config.SESSION_LIFETIME_HOURS)
            
            if session_age > max_age:
                logger.info(f"Session expired for user: {session.get('username')}")
                return False
        
        return True
    
    @staticmethod
    def destroy_session():
        """Destroy current session"""
        username = session.get('username', 'unknown')
        session.clear()
        logger.info(f"Session destroyed for user: {username}")


class AuthenticationService:
    """Main authentication service orchestrating all auth operations"""
    
    def __init__(self):
        self.password_hasher = PasswordHasher()
        self.rate_limiter = RateLimiter()
        self.token_manager = TokenManager()
        self.session_manager = SessionManager()
    
    def authenticate_user(self, username: str, password: str, ip_address: str,
                         user_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Authenticate user with rate limiting"""
        # Check rate limiting
        is_limited, reset_seconds = self.rate_limiter.is_rate_limited(ip_address)
        if is_limited:
            return False, f"Too many login attempts. Try again in {reset_seconds} seconds."
        
        # Record attempt
        self.rate_limiter.record_attempt(ip_address)
        
        # Verify password
        if not user_data or not self.password_hasher.verify_password(
            password, user_data.get('password_hash', '')
        ):
            return False, "Invalid credentials"
        
        # Reset rate limiter on successful login
        self.rate_limiter.reset(ip_address)
        
        # Create session
        self.session_manager.create_session(
            user_data['id'],
            user_data['username'],
            user_data['role'],
            user_data.get('employee_id')
        )
        
        return True, None
    
    def change_password(self, user_id: int, old_password: str, new_password: str,
                       current_hash: str) -> tuple[bool, Optional[str]]:
        """Change user password"""
        # Verify old password
        if not self.password_hasher.verify_password(old_password, current_hash):
            return False, "Current password is incorrect"
        
        # Validate new password strength
        is_valid, error_msg = self.password_hasher.validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg
        
        # Hash new password
        new_hash = self.password_hasher.hash_password(new_password)
        
        return True, new_hash


# Global auth service instance
auth_service = AuthenticationService()


# Decorators for route protection
def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not SessionManager.is_session_valid():
            SessionManager.destroy_session()
            return redirect(url_for('login'))
        
        SessionManager.refresh_activity()
        return f(*args, **kwargs)
    
    return decorated_function


def api_login_required(f):
    """Decorator to require login for API routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session or token
        if not SessionManager.is_session_valid():
            # Try JWT token
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                payload = auth_service.token_manager.verify_token(token)
                
                if payload:
                    # Create temporary session from token
                    session['user_id'] = payload['user_id']
                    session['username'] = payload['username']
                    session['user_role'] = payload['role']
                    return f(*args, **kwargs)
            
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        SessionManager.refresh_activity()
        return f(*args, **kwargs)
    
    return decorated_function


def role_required(required_role: str):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not SessionManager.is_session_valid():
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            
            role_hierarchy = {'viewer': 0, 'manager': 1, 'admin': 2}
            user_level = role_hierarchy.get(session.get('user_role'), -1)
            required_level = role_hierarchy.get(required_role, 999)
            
            if user_level < required_level:
                return jsonify({
                    'success': False,
                    'message': 'Insufficient permissions'
                }), 403
            
            SessionManager.refresh_activity()
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def generate_session_token() -> str:
    """Generate a secure session token"""
    return secrets.token_hex(32)


# Legacy function compatibility
def hash_password(password: str) -> str:
    """Legacy function - use PasswordHasher instead"""
    return PasswordHasher.hash_password(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Legacy function - use PasswordHasher instead"""
    return PasswordHasher.verify_password(password, password_hash)
