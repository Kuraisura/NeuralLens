"""
Comprehensive Security Manager
Handles encryption, hashing, JWT tokens, and security utilities
"""

import os
import base64
import hmac
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import bcrypt
import jwt
import logging

logger = logging.getLogger(__name__)


class SecurityManager:
    """
    Comprehensive security manager for encryption, hashing, and authentication
    """
    
    def __init__(self, master_key: Optional[bytes] = None, jwt_secret: Optional[str] = None):
        """
        Initialize security manager
        
        Args:
            master_key: Master encryption key (32 bytes). If None, generates new key.
            jwt_secret: Secret for JWT signing. If None, generates new secret.
        """
        self.master_key = master_key or Fernet.generate_key()
        self.cipher = Fernet(self.master_key)
        
        self.jwt_secret = jwt_secret or base64.b64encode(os.urandom(32)).decode()
        self.jwt_algorithm = 'HS256'
        self.jwt_expiration_minutes = 30
        
        logger.info("Security Manager initialized")
    
    # =================================================================
    # Encryption / Decryption
    # =================================================================
    
    def encrypt_data(self, plaintext: bytes) -> bytes:
        """
        Encrypt data using Fernet (AES-128-CBC + HMAC)
        
        Args:
            plaintext: Data to encrypt
            
        Returns:
            Encrypted ciphertext
        """
        try:
            return self.cipher.encrypt(plaintext)
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise
    
    def decrypt_data(self, ciphertext: bytes) -> bytes:
        """
        Decrypt data
        
        Args:
            ciphertext: Encrypted data
            
        Returns:
            Decrypted plaintext
        """
        try:
            return self.cipher.decrypt(ciphertext)
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise
    
    def encrypt_string(self, plaintext: str) -> str:
        """Encrypt string and return base64 encoded result"""
        encrypted = self.encrypt_data(plaintext.encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')
    
    def decrypt_string(self, ciphertext: str) -> str:
        """Decrypt base64 encoded string"""
        encrypted = base64.b64decode(ciphertext.encode('utf-8'))
        decrypted = self.decrypt_data(encrypted)
        return decrypted.decode('utf-8')
    
    def encrypt_file(self, input_path: str, output_path: str) -> bool:
        """
        Encrypt file
        
        Args:
            input_path: Path to plaintext file
            output_path: Path to save encrypted file
            
        Returns:
            True if successful
        """
        try:
            with open(input_path, 'rb') as f:
                plaintext = f.read()
            
            ciphertext = self.encrypt_data(plaintext)
            
            with open(output_path, 'wb') as f:
                f.write(ciphertext)
            
            logger.info(f"File encrypted: {input_path} -> {output_path}")
            return True
        except Exception as e:
            logger.error(f"File encryption error: {e}")
            return False
    
    def decrypt_file(self, input_path: str, output_path: str) -> bool:
        """
        Decrypt file
        
        Args:
            input_path: Path to encrypted file
            output_path: Path to save decrypted file
            
        Returns:
            True if successful
        """
        try:
            with open(input_path, 'rb') as f:
                ciphertext = f.read()
            
            plaintext = self.decrypt_data(ciphertext)
            
            with open(output_path, 'wb') as f:
                f.write(plaintext)
            
            logger.info(f"File decrypted: {input_path} -> {output_path}")
            return True
        except Exception as e:
            logger.error(f"File decryption error: {e}")
            return False
    
    # =================================================================
    # AES-GCM (Authenticated Encryption)
    # =================================================================
    
    @staticmethod
    def encrypt_aes_gcm(plaintext: bytes, key: bytes, associated_data: Optional[bytes] = None) -> Dict:
        """
        Encrypt using AES-256-GCM (authenticated encryption)
        
        Args:
            plaintext: Data to encrypt
            key: 32-byte encryption key
            associated_data: Additional authenticated data (optional)
            
        Returns:
            Dict with 'ciphertext' and 'nonce'
        """
        nonce = os.urandom(12)  # 96-bit nonce
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'nonce': base64.b64encode(nonce).decode('utf-8')
        }
    
    @staticmethod
    def decrypt_aes_gcm(ciphertext: str, nonce: str, key: bytes, 
                       associated_data: Optional[bytes] = None) -> bytes:
        """
        Decrypt AES-256-GCM
        
        Args:
            ciphertext: Base64 encoded ciphertext
            nonce: Base64 encoded nonce
            key: 32-byte decryption key
            associated_data: Additional authenticated data (must match encryption)
            
        Returns:
            Decrypted plaintext
        """
        ct = base64.b64decode(ciphertext)
        n = base64.b64decode(nonce)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(n, ct, associated_data)
    
    # =================================================================
    # Password Hashing
    # =================================================================
    
    @staticmethod
    def hash_password(password: str, rounds: int = 12) -> str:
        """
        Hash password using bcrypt
        
        Args:
            password: Plain text password
            rounds: Cost factor (default 12, range 4-31)
            
        Returns:
            Hashed password string
        """
        salt = bcrypt.gensalt(rounds=rounds)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verify password against hash
        
        Args:
            password: Plain text password
            hashed: Bcrypt hash
            
        Returns:
            True if password matches
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    @staticmethod
    def derive_key_from_password(password: str, salt: bytes, 
                                 length: int = 32, iterations: int = 100000) -> bytes:
        """
        Derive encryption key from password using PBKDF2
        
        Args:
            password: Password string
            salt: Salt bytes (should be random and stored)
            length: Key length in bytes
            iterations: Number of iterations
            
        Returns:
            Derived key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    # =================================================================
    # JWT Tokens
    # =================================================================
    
    def generate_jwt(self, payload: Dict[str, Any], 
                    expiration_minutes: Optional[int] = None) -> str:
        """
        Generate JWT token
        
        Args:
            payload: Token payload (claims)
            expiration_minutes: Token expiration (default 30 minutes)
            
        Returns:
            JWT token string
        """
        exp_minutes = expiration_minutes or self.jwt_expiration_minutes
        
        # Add standard claims
        token_payload = payload.copy()
        token_payload['iat'] = datetime.utcnow()
        token_payload['exp'] = datetime.utcnow() + timedelta(minutes=exp_minutes)
        
        token = jwt.encode(token_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token
    
    def verify_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded payload if valid, None if invalid
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
    
    def refresh_jwt(self, token: str) -> Optional[str]:
        """
        Refresh JWT token if still valid
        
        Args:
            token: Current JWT token
            
        Returns:
            New JWT token if current token is valid, None otherwise
        """
        payload = self.verify_jwt(token)
        if payload:
            # Remove standard claims before regenerating
            payload.pop('iat', None)
            payload.pop('exp', None)
            return self.generate_jwt(payload)
        return None
    
    # =================================================================
    # Secure Hashing
    # =================================================================
    
    @staticmethod
    def sha256_hash(data: bytes) -> str:
        """Compute SHA-256 hash"""
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def hmac_sha256(data: bytes, key: bytes) -> str:
        """Compute HMAC-SHA256"""
        return hmac.new(key, data, hashlib.sha256).hexdigest()
    
    @staticmethod
    def generate_random_bytes(length: int = 32) -> bytes:
        """Generate cryptographically secure random bytes"""
        return os.urandom(length)
    
    @staticmethod
    def generate_random_string(length: int = 32) -> str:
        """Generate cryptographically secure random string"""
        random_bytes = os.urandom(length)
        return base64.urlsafe_b64encode(random_bytes).decode('utf-8')[:length]
    
    # =================================================================
    # Secure Comparison
    # =================================================================
    
    @staticmethod
    def constant_time_compare(a: str, b: str) -> bool:
        """
        Constant-time string comparison (prevents timing attacks)
        
        Args:
            a: First string
            b: Second string
            
        Returns:
            True if strings are equal
        """
        return hmac.compare_digest(a, b)


# Singleton instance
_security_manager = None


def get_security_manager() -> SecurityManager:
    """Get singleton security manager instance"""
    global _security_manager
    if _security_manager is None:
        # In production, load master_key and jwt_secret from secure storage
        _security_manager = SecurityManager()
    return _security_manager


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create security manager
    sec_mgr = SecurityManager()
    
    # Test encryption
    print("=== Encryption Test ===")
    plaintext = "Sensitive data"
    encrypted = sec_mgr.encrypt_string(plaintext)
    decrypted = sec_mgr.decrypt_string(encrypted)
    print(f"Original: {plaintext}")
    print(f"Encrypted: {encrypted}")
    print(f"Decrypted: {decrypted}")
    assert plaintext == decrypted
    
    # Test password hashing
    print("\n=== Password Hashing Test ===")
    password = "SecurePassword123!"
    hashed = SecurityManager.hash_password(password)
    print(f"Password: {password}")
    print(f"Hashed: {hashed}")
    print(f"Verify (correct): {SecurityManager.verify_password(password, hashed)}")
    print(f"Verify (wrong): {SecurityManager.verify_password('WrongPassword', hashed)}")
    
    # Test JWT
    print("\n=== JWT Test ===")
    payload = {'user_id': 123, 'role': 'admin'}
    token = sec_mgr.generate_jwt(payload)
    print(f"Token: {token}")
    
    decoded = sec_mgr.verify_jwt(token)
    print(f"Decoded: {decoded}")
    
    # Test AES-GCM
    print("\n=== AES-GCM Test ===")
    key = SecurityManager.generate_random_bytes(32)
    data = b"Very secret data"
    encrypted_gcm = SecurityManager.encrypt_aes_gcm(data, key, associated_data=b"context")
    print(f"Encrypted: {encrypted_gcm}")
    
    decrypted_gcm = SecurityManager.decrypt_aes_gcm(
        encrypted_gcm['ciphertext'], 
        encrypted_gcm['nonce'], 
        key, 
        associated_data=b"context"
    )
    print(f"Decrypted: {decrypted_gcm}")
    assert data == decrypted_gcm
    
    print("\n✓ All security tests passed!")
