"""
NEURAL EYE - Utilities Module
Logging, monitoring, and common utility functions
"""

import logging
import logging.handlers
from typing import Callable, Any
from functools import wraps
from time import time
from pathlib import Path
import sys

from config import Config


class StructuredLogger:
    """Structured logging with context support"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_logger()
    
    def _setup_logger(self):
        """Setup logger with handlers"""
        self.logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper()))
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        if Config.LOG_FILE:
            file_handler = logging.handlers.RotatingFileHandler(
                Config.LOG_FILE,
                maxBytes=Config.LOG_MAX_BYTES,
                backupCount=Config.LOG_BACKUP_COUNT
            )
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
    
    def info(self, message: str, **context):
        """Log info with context"""
        self._log(logging.INFO, message, context)
    
    def debug(self, message: str, **context):
        """Log debug with context"""
        self._log(logging.DEBUG, message, context)
    
    def warning(self, message: str, **context):
        """Log warning with context"""
        self._log(logging.WARNING, message, context)
    
    def error(self, message: str, **context):
        """Log error with context"""
        self._log(logging.ERROR, message, context)
    
    def critical(self, message: str, **context):
        """Log critical with context"""
        self._log(logging.CRITICAL, message, context)
    
    def _log(self, level: int, message: str, context: dict):
        """Internal logging with context"""
        if context:
            context_str = ' | '.join([f"{k}={v}" for k, v in context.items()])
            message = f"{message} | {context_str}"
        
        self.logger.log(level, message)


class PerformanceMonitor:
    """Performance monitoring and profiling"""
    
    def __init__(self):
        self.metrics = {}
        self.logger = StructuredLogger(__name__)
    
    def time_function(self, func: Callable) -> Callable:
        """Decorator to measure function execution time"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time() - start_time
                func_name = f"{func.__module__}.{func.__name__}"
                
                # Update metrics
                if func_name not in self.metrics:
                    self.metrics[func_name] = {
                        'calls': 0,
                        'total_time': 0,
                        'avg_time': 0,
                        'min_time': float('inf'),
                        'max_time': 0
                    }
                
                metrics = self.metrics[func_name]
                metrics['calls'] += 1
                metrics['total_time'] += elapsed
                metrics['avg_time'] = metrics['total_time'] / metrics['calls']
                metrics['min_time'] = min(metrics['min_time'], elapsed)
                metrics['max_time'] = max(metrics['max_time'], elapsed)
                
                # Log if slow
                if elapsed > 1.0:  # More than 1 second
                    self.logger.warning(
                        f"Slow function execution: {func_name}",
                        duration=f"{elapsed:.2f}s"
                    )
        
        return wrapper
    
    def get_metrics(self) -> dict:
        """Get all performance metrics"""
        return self.metrics
    
    def reset_metrics(self):
        """Reset all metrics"""
        self.metrics.clear()


class ErrorTracker:
    """Track and log application errors"""
    
    def __init__(self):
        self.errors = []
        self.max_errors = 1000
        self.logger = StructuredLogger(__name__)
    
    def track_error(self, error: Exception, context: dict = None):
        """Track an error with context"""
        error_data = {
            'type': type(error).__name__,
            'message': str(error),
            'context': context or {},
            'timestamp': time()
        }
        
        self.errors.append(error_data)
        
        # Keep only recent errors
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
        
        # Log the error
        self.logger.error(
            f"Error tracked: {error_data['type']}",
            message=error_data['message'],
            **error_data['context']
        )
    
    def get_recent_errors(self, count: int = 10) -> list:
        """Get recent errors"""
        return self.errors[-count:]
    
    def get_error_count(self) -> int:
        """Get total error count"""
        return len(self.errors)
    
    def clear_errors(self):
        """Clear all tracked errors"""
        self.errors.clear()


class HealthCheck:
    """System health check utilities"""
    
    def __init__(self):
        self.logger = StructuredLogger(__name__)
    
    def check_database(self, db) -> bool:
        """Check database connectivity"""
        try:
            # Simple query to check connectivity
            db.employees.count()
            return True
        except Exception as e:
            self.logger.error("Database health check failed", error=str(e))
            return False
    
    def check_camera(self, camera_service) -> bool:
        """Check camera availability"""
        try:
            return camera_service.is_available()
        except Exception as e:
            self.logger.error("Camera health check failed", error=str(e))
            return False
    
    def check_disk_space(self) -> bool:
        """Check available disk space"""
        try:
            import shutil
            stats = shutil.disk_usage('.')
            
            # Check if less than 1GB available
            available_gb = stats.free / (1024 ** 3)
            if available_gb < 1:
                self.logger.warning(
                    "Low disk space",
                    available_gb=f"{available_gb:.2f}"
                )
                return False
            return True
        except Exception as e:
            self.logger.error("Disk space check failed", error=str(e))
            return False
    
    def get_system_status(self, db, camera_service) -> dict:
        """Get comprehensive system status"""
        return {
            'database': self.check_database(db),
            'camera': self.check_camera(camera_service),
            'disk_space': self.check_disk_space(),
            'timestamp': time()
        }


# Global instances
performance_monitor = PerformanceMonitor()
error_tracker = ErrorTracker()
health_check = HealthCheck()


def monitor_performance(func: Callable) -> Callable:
    """Decorator to monitor function performance"""
    return performance_monitor.time_function(func)


def log_errors(logger: StructuredLogger):
    """Decorator to log and track errors"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_tracker.track_error(e, {'function': func.__name__})
                logger.error(
                    f"Error in {func.__name__}",
                    error=str(e),
                    type=type(e).__name__
                )
                raise
        return wrapper
    return decorator


def ensure_directory_exists(directory: Path):
    """Ensure directory exists, create if not"""
    directory.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal"""
    import re
    # Remove any path separators and special characters
    safe_name = re.sub(r'[^\w\s.-]', '', filename)
    # Remove any .. sequences
    safe_name = safe_name.replace('..', '')
    return safe_name


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_client_ip(request) -> str:
    """Get client IP address from request"""
    # Check for proxy headers
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr or 'unknown'
