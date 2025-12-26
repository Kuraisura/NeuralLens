"""
NEURAL EYE - Configuration Management
Centralized configuration using environment variables with validation
"""

import os
from typing import List, Optional
from datetime import time
import secrets
from pathlib import Path


class Config:
    """Base configuration class with validation and type safety"""
    
    # Application Settings
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '5000'))
    SECRET_KEY: str = os.getenv('SECRET_KEY', secrets.token_hex(32))
    
    # Database Settings
    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'neural_eye.db')
    DATABASE_POOL_SIZE: int = int(os.getenv('DATABASE_POOL_SIZE', '10'))
    DATABASE_TIMEOUT: int = int(os.getenv('DATABASE_TIMEOUT', '30'))
    
    # Camera Settings
    USE_MOCK_CAMERA: bool = os.getenv('USE_MOCK_CAMERA', 'False').lower() == 'true'
    CAMERA_INDEX: int = int(os.getenv('CAMERA_INDEX', '0'))
    CAMERA_WIDTH: int = int(os.getenv('CAMERA_WIDTH', '1280'))
    CAMERA_HEIGHT: int = int(os.getenv('CAMERA_HEIGHT', '720'))
    CAMERA_FPS: int = int(os.getenv('CAMERA_FPS', '30'))
    
    # Face Recognition Settings
    FACE_DETECTION_MODEL: str = os.getenv('FACE_DETECTION_MODEL', 'hog')
    FACE_RECOGNITION_TOLERANCE: float = float(os.getenv('FACE_RECOGNITION_TOLERANCE', '0.5'))
    PROCESS_EVERY_N_FRAMES: int = int(os.getenv('PROCESS_EVERY_N_FRAMES', '2'))
    FACE_ENCODING_CACHE_SIZE: int = int(os.getenv('FACE_ENCODING_CACHE_SIZE', '1000'))
    
    # Attendance Settings (Manila Time - PHT)
    WORK_START_TIME: str = os.getenv('WORK_START_TIME', '08:00:00')
    WORK_END_TIME: str = os.getenv('WORK_END_TIME', '17:00:00')
    GRACE_PERIOD_MINUTES: int = int(os.getenv('GRACE_PERIOD_MINUTES', '15'))
    RECOGNITION_COOLDOWN_SECONDS: int = int(os.getenv('RECOGNITION_COOLDOWN_SECONDS', '10'))
    
    # API Settings
    API_TIMEOUT_SECONDS: int = int(os.getenv('API_TIMEOUT_SECONDS', '4'))
    LOG_FETCH_INTERVAL_SECONDS: int = int(os.getenv('LOG_FETCH_INTERVAL_SECONDS', '5'))
    MAX_LOGS_DISPLAYED: int = int(os.getenv('MAX_LOGS_DISPLAYED', '10'))
    
    # Security Settings
    ALLOWED_ORIGINS: List[str] = os.getenv(
        'ALLOWED_ORIGINS', 
        'http://localhost:5000,http://127.0.0.1:5000'
    ).split(',')
    SESSION_LIFETIME_HOURS: int = int(os.getenv('SESSION_LIFETIME_HOURS', '24'))
    MAX_LOGIN_ATTEMPTS: int = int(os.getenv('MAX_LOGIN_ATTEMPTS', '5'))
    LOGIN_ATTEMPT_WINDOW_MINUTES: int = int(os.getenv('LOGIN_ATTEMPT_WINDOW_MINUTES', '15'))
    PASSWORD_MIN_LENGTH: int = int(os.getenv('PASSWORD_MIN_LENGTH', '8'))
    
    # File Paths
    FACE_DATA_DIR: Path = Path(os.getenv('FACE_DATA_DIR', 'face_data'))
    FRONTEND_DIR: Path = Path(os.getenv('FRONTEND_DIR', 'frontend'))
    STATIC_DIR: Path = Path(os.getenv('STATIC_DIR', 'frontend/static'))
    
    # SMTP Settings for notifications
    SMTP_SERVER: Optional[str] = os.getenv('SMTP_SERVER')
    SMTP_PORT: int = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER: Optional[str] = os.getenv('SMTP_USER')
    SMTP_PASSWORD: Optional[str] = os.getenv('SMTP_PASSWORD')
    SMTP_USE_TLS: bool = os.getenv('SMTP_USE_TLS', 'True').lower() == 'true'
    
    # Cache Settings
    CACHE_TYPE: str = os.getenv('CACHE_TYPE', 'simple')  # 'simple', 'redis'
    CACHE_DEFAULT_TIMEOUT: int = int(os.getenv('CACHE_DEFAULT_TIMEOUT', '300'))
    REDIS_URL: Optional[str] = os.getenv('REDIS_URL')
    
    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: Optional[str] = os.getenv('LOG_FILE', 'neural_eye.log')
    LOG_MAX_BYTES: int = int(os.getenv('LOG_MAX_BYTES', '10485760'))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration settings"""
        errors = []
        
        # Validate face detection model
        if cls.FACE_DETECTION_MODEL not in ['hog', 'cnn']:
            errors.append("FACE_DETECTION_MODEL must be 'hog' or 'cnn'")
        
        # Validate tolerance
        if not 0 < cls.FACE_RECOGNITION_TOLERANCE <= 1:
            errors.append("FACE_RECOGNITION_TOLERANCE must be between 0 and 1")
        
        # Validate time formats
        try:
            time.fromisoformat(cls.WORK_START_TIME)
            time.fromisoformat(cls.WORK_END_TIME)
        except ValueError:
            errors.append("WORK_START_TIME and WORK_END_TIME must be in HH:MM:SS format")
        
        # Validate directories
        if not cls.FRONTEND_DIR.exists():
            errors.append(f"Frontend directory not found: {cls.FRONTEND_DIR}")
        
        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(errors))
        
        return True
    
    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure required directories exist"""
        cls.FACE_DATA_DIR.mkdir(exist_ok=True, parents=True)
        cls.STATIC_DIR.mkdir(exist_ok=True, parents=True)
    
    @classmethod
    def get_work_start_time(cls) -> time:
        """Get work start time as time object"""
        return time.fromisoformat(cls.WORK_START_TIME)
    
    @classmethod
    def get_work_end_time(cls) -> time:
        """Get work end time as time object"""
        return time.fromisoformat(cls.WORK_END_TIME)
    
    @classmethod
    def display_info(cls) -> str:
        """Display configuration information (for debugging)"""
        return f"""
Neural Eye Configuration:
------------------------
Debug: {cls.DEBUG}
Host: {cls.HOST}:{cls.PORT}
Database: {cls.DATABASE_PATH}
Camera Mode: {'Mock' if cls.USE_MOCK_CAMERA else 'Real'}
Face Detection Model: {cls.FACE_DETECTION_MODEL}
Work Hours: {cls.WORK_START_TIME} - {cls.WORK_END_TIME}
Cache Type: {cls.CACHE_TYPE}
        """.strip()


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    USE_MOCK_CAMERA = True


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    USE_MOCK_CAMERA = False


class TestingConfig(Config):
    """Testing environment configuration"""
    DEBUG = True
    DATABASE_PATH = ':memory:'
    USE_MOCK_CAMERA = True


# Configuration factory
def get_config(env: str = None) -> Config:
    """Get configuration based on environment"""
    env = env or os.getenv('FLASK_ENV', 'development')
    
    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig
    }
    
    config_class = config_map.get(env, Config)
    config_class.validate()
    config_class.ensure_directories()
    
    return config_class
