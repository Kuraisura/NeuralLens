"""
NEURAL LENS - Advanced Logging System
Comprehensive logging with rotating files, structured output, and performance monitoring
"""

import logging
import logging.handlers
import json
import traceback
import time
from datetime import datetime
from pathlib import Path
from functools import wraps
import sys
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'duration'):
            log_data['duration_ms'] = record.duration
        
        return json.dumps(log_data)


class PerformanceLogger:
    """Logger for performance monitoring"""
    
    def __init__(self, logger_name='performance'):
        self.logger = logging.getLogger(logger_name)
    
    def log_operation(self, operation: str, duration: float, metadata: Optional[Dict] = None):
        """Log a timed operation"""
        extra = {
            'operation': operation,
            'duration': duration * 1000,  # Convert to ms
            'metadata': metadata or {}
        }
        
        if duration > 1.0:  # Slow operation
            self.logger.warning(f"Slow operation: {operation}", extra=extra)
        else:
            self.logger.info(f"Operation completed: {operation}", extra=extra)


def setup_logging(
    log_level: str = 'INFO',
    log_dir: str = 'logs',
    enable_console: bool = True,
    enable_file: bool = True,
    enable_json: bool = False
) -> None:
    """
    Setup comprehensive logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        enable_console: Enable console logging
        enable_file: Enable file logging
        enable_json: Use JSON structured logging
    """
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        if enable_json:
            console_handler.setFormatter(StructuredFormatter())
        else:
            console_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
        
        root_logger.addHandler(console_handler)
    
    # File handlers
    if enable_file:
        # Main log file (rotating)
        main_handler = logging.handlers.RotatingFileHandler(
            log_path / 'neural_lens.log',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.INFO)
        
        if enable_json:
            main_handler.setFormatter(StructuredFormatter())
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-20s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            main_handler.setFormatter(file_formatter)
        
        root_logger.addHandler(main_handler)
        
        # Error log file (only errors and above)
        error_handler = logging.handlers.RotatingFileHandler(
            log_path / 'errors.log',
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter if not enable_json else StructuredFormatter())
        root_logger.addHandler(error_handler)
        
        # Performance log file
        perf_handler = logging.handlers.RotatingFileHandler(
            log_path / 'performance.log',
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        perf_handler.setLevel(logging.INFO)
        perf_handler.setFormatter(StructuredFormatter() if enable_json else file_formatter)
        
        perf_logger = logging.getLogger('performance')
        perf_logger.addHandler(perf_handler)
        perf_logger.setLevel(logging.INFO)
    
    logging.info("Logging system initialized")
    logging.info(f"Log level: {log_level}, Directory: {log_dir}")


def timed_operation(operation_name: Optional[str] = None):
    """
    Decorator to time and log function execution
    
    Usage:
        @timed_operation('database_query')
        def my_function():
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger = logging.getLogger(func.__module__)
            perf_logger = PerformanceLogger()
            
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                perf_logger.log_operation(op_name, duration)
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"Error in {op_name}: {str(e)}",
                    exc_info=True,
                    extra={'duration': duration * 1000}
                )
                raise
        
        return wrapper
    return decorator


def log_exception(logger: logging.Logger, exception: Exception, context: Optional[Dict] = None):
    """
    Log an exception with full context
    
    Args:
        logger: Logger instance
        exception: Exception to log
        context: Additional context information
    """
    error_data = {
        'exception_type': type(exception).__name__,
        'exception_message': str(exception),
        'traceback': traceback.format_exc()
    }
    
    if context:
        error_data.update(context)
    
    logger.error(
        f"Exception occurred: {type(exception).__name__}",
        extra=error_data,
        exc_info=True
    )


class ErrorHandler:
    """Centralized error handling"""
    
    def __init__(self, logger_name: str = 'error_handler'):
        self.logger = logging.getLogger(logger_name)
        self.error_counts = {}
    
    def handle_error(
        self,
        error: Exception,
        error_type: str = 'general',
        context: Optional[Dict] = None,
        raise_error: bool = True
    ):
        """
        Handle an error with logging and optional re-raising
        
        Args:
            error: The exception
            error_type: Category of error
            context: Additional context
            raise_error: Whether to re-raise the exception
        """
        # Track error counts
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Log with full context
        log_context = {
            'error_type': error_type,
            'error_count': self.error_counts[error_type]
        }
        
        if context:
            log_context.update(context)
        
        log_exception(self.logger, error, log_context)
        
        # Re-raise if requested
        if raise_error:
            raise error
    
    def get_error_stats(self) -> Dict[str, int]:
        """Get error statistics"""
        return self.error_counts.copy()


class RequestLogger:
    """Logger for API requests"""
    
    def __init__(self):
        self.logger = logging.getLogger('api')
    
    def log_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        user_id: Optional[int] = None,
        error: Optional[str] = None
    ):
        """Log API request"""
        extra = {
            'method': method,
            'endpoint': endpoint,
            'status_code': status_code,
            'duration': duration * 1000,
            'user_id': user_id
        }
        
        if error:
            extra['error'] = error
            self.logger.error(f"{method} {endpoint} - {status_code}", extra=extra)
        elif status_code >= 400:
            self.logger.warning(f"{method} {endpoint} - {status_code}", extra=extra)
        else:
            self.logger.info(f"{method} {endpoint} - {status_code}", extra=extra)


# Global error handler instance
error_handler = ErrorHandler()


# Example usage and testing
if __name__ == '__main__':
    # Setup logging
    setup_logging(
        log_level='DEBUG',
        log_dir='logs',
        enable_console=True,
        enable_file=True,
        enable_json=False
    )
    
    logger = logging.getLogger(__name__)
    
    # Test basic logging
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    
    # Test timed operation
    @timed_operation('test_operation')
    def slow_function():
        time.sleep(0.5)
        return "Done"
    
    result = slow_function()
    
    # Test error handling
    try:
        raise ValueError("Test error")
    except Exception as e:
        error_handler.handle_error(
            e,
            error_type='test_error',
            context={'test_data': 'value'},
            raise_error=False
        )
    
    # Test request logging
    request_logger = RequestLogger()
    request_logger.log_request(
        method='GET',
        endpoint='/api/employees',
        status_code=200,
        duration=0.123,
        user_id=1
    )
    
    logger.info("Logging system test completed")
    print("\nError statistics:", error_handler.get_error_stats())
