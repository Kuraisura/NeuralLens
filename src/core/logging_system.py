"""
Advanced Logging System with Structured Logging, Rotation, and Remote Support
"""

import logging
import logging.handlers
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
import traceback


class LogLevel(Enum):
    """Log level enumeration"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields if present
        if hasattr(record, 'custom_fields'):
            log_data.update(record.custom_fields)
        
        return json.dumps(log_data)


class LogManager:
    """
    Centralized logging manager with multiple handlers
    """
    
    def __init__(self, app_name: str = "neural_lens"):
        self.app_name = app_name
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Configure root logger
        self.root_logger = logging.getLogger()
        self.root_logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        self.root_logger.handlers.clear()
        
        # Setup handlers
        self._setup_console_handler()
        self._setup_file_handler()
        self._setup_error_file_handler()
        self._setup_audit_handler()
        
    def _setup_console_handler(self):
        """Setup console output handler"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Simple format for console
        console_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        
        self.root_logger.addHandler(console_handler)
    
    def _setup_file_handler(self):
        """Setup rotating file handler for general logs"""
        log_file = self.log_dir / f"{self.app_name}.log"
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Structured format for file
        file_handler.setFormatter(StructuredFormatter())
        
        self.root_logger.addHandler(file_handler)
    
    def _setup_error_file_handler(self):
        """Setup dedicated error log file"""
        error_log_file = self.log_dir / f"{self.app_name}_errors.log"
        
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredFormatter())
        
        self.root_logger.addHandler(error_handler)
    
    def _setup_audit_handler(self):
        """Setup audit log handler"""
        audit_log_file = self.log_dir / f"{self.app_name}_audit.log"
        
        audit_handler = logging.handlers.TimedRotatingFileHandler(
            audit_log_file,
            when='midnight',
            interval=1,
            backupCount=365,  # Keep 1 year of audit logs
            encoding='utf-8'
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(StructuredFormatter())
        
        # Create separate audit logger
        self.audit_logger = logging.getLogger('audit')
        self.audit_logger.addHandler(audit_handler)
        self.audit_logger.propagate = False
    
    def setup_syslog_handler(self, host: str = 'localhost', port: int = 514):
        """Setup syslog handler for remote logging"""
        try:
            syslog_handler = logging.handlers.SysLogHandler(address=(host, port))
            syslog_handler.setLevel(logging.WARNING)
            
            syslog_format = logging.Formatter(
                f'{self.app_name}: %(name)s - %(levelname)s - %(message)s'
            )
            syslog_handler.setFormatter(syslog_format)
            
            self.root_logger.addHandler(syslog_handler)
            logging.info(f"Syslog handler configured: {host}:{port}")
        except Exception as e:
            logging.error(f"Failed to setup syslog handler: {e}")
    
    @staticmethod
    def log_with_context(logger: logging.Logger, level: LogLevel, 
                        message: str, **context):
        """Log message with custom context fields"""
        record = logger.makeRecord(
            logger.name, level.value, '', 0, message, (), None
        )
        record.custom_fields = context
        logger.handle(record)
    
    def log_audit(self, action: str, user: str, resource: str, 
                  result: str, details: Optional[Dict] = None):
        """Log audit trail entry"""
        audit_entry = {
            'action': action,
            'user': user,
            'resource': resource,
            'result': result,
            'ip_address': details.get('ip_address') if details else None,
            'user_agent': details.get('user_agent') if details else None,
        }
        
        if details:
            audit_entry['details'] = details
        
        record = self.audit_logger.makeRecord(
            'audit', logging.INFO, '', 0, 
            f"{action} by {user} on {resource}: {result}",
            (), None
        )
        record.custom_fields = audit_entry
        self.audit_logger.handle(record)


# Global log manager instance
_log_manager = None


def get_log_manager() -> LogManager:
    """Get singleton log manager instance"""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager


def setup_logging(app_name: str = "neural_lens", 
                 syslog_host: Optional[str] = None,
                 syslog_port: int = 514):
    """
    Setup application logging
    
    Args:
        app_name: Application name for log files
        syslog_host: Remote syslog server (optional)
        syslog_port: Syslog port
    """
    manager = LogManager(app_name)
    
    if syslog_host:
        manager.setup_syslog_handler(syslog_host, syslog_port)
    
    return manager


# Example usage
if __name__ == "__main__":
    # Setup logging
    log_mgr = setup_logging("test_app")
    
    # Get logger
    logger = logging.getLogger(__name__)
    
    # Standard logging
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # Logging with context
    LogManager.log_with_context(
        logger, LogLevel.INFO,
        "User action",
        user_id=123,
        action="login",
        ip_address="192.168.1.100"
    )
    
    # Audit logging
    log_mgr.log_audit(
        action="FACE_ENROLLMENT",
        user="admin@example.com",
        resource="employee_123",
        result="SUCCESS",
        details={'ip_address': '192.168.1.100'}
    )
    
    # Exception logging
    try:
        1 / 0
    except Exception as e:
        logger.exception("Exception occurred")
    
    print(f"\nLogs written to: {log_mgr.log_dir}")
