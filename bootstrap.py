"""
NEURAL EYE - Application Bootstrap
Initialize and configure the application with improved architecture
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config, get_config
from database_new import Database
from services import (
    CameraService, 
    cache, 
    AttendanceCalculator,
    EmployeeService,
    AttendanceService
)
from auth_new import auth_service
from utils import StructuredLogger, performance_monitor, error_tracker, health_check
from notifications import get_notification_system

# Initialize logger
logger = StructuredLogger(__name__)


class Application:
    """Main application class with dependency injection"""
    
    def __init__(self, config_env: str = None):
        """Initialize application with configuration"""
        logger.info("Initializing Neural Eye Application")
        
        # Load configuration
        self.config = get_config(config_env)
        logger.info(f"Configuration loaded: {config_env or 'default'}")
        
        # Initialize core services
        self._init_database()
        self._init_services()
        self._init_camera()
        
        logger.info("Application initialized successfully")
    
    def _init_database(self):
        """Initialize database with connection pooling"""
        logger.info("Initializing database...")
        try:
            self.db = Database(
                database_path=self.config.DATABASE_PATH,
                pool_size=self.config.DATABASE_POOL_SIZE
            )
            logger.info(f"Database initialized: {self.config.DATABASE_PATH}")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def _init_services(self):
        """Initialize business logic services"""
        logger.info("Initializing services...")
        
        # Initialize calculator
        self.attendance_calculator = AttendanceCalculator()
        
        # Initialize services with dependency injection
        self.employee_service = EmployeeService(
            self.db.employees,
            cache
        )
        
        self.attendance_service = AttendanceService(
            self.db.attendance,
            self.attendance_calculator
        )
        
        # Initialize notification system
        self.notification_system = get_notification_system()
        
        logger.info("Services initialized")
    
    def _init_camera(self):
        """Initialize camera service"""
        logger.info("Initializing camera...")
        try:
            self.camera_service = CameraService(
                use_mock=self.config.USE_MOCK_CAMERA
            )
            
            if self.camera_service.is_available():
                logger.info(f"Camera initialized: {'Mock' if self.config.USE_MOCK_CAMERA else 'Real'}")
            else:
                logger.warning("Camera not available, switching to mock mode")
                self.camera_service = CameraService(use_mock=True)
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            # Fall back to mock camera
            self.camera_service = CameraService(use_mock=True)
    
    def get_health_status(self) -> dict:
        """Get application health status"""
        return health_check.get_system_status(self.db, self.camera_service)
    
    def get_performance_metrics(self) -> dict:
        """Get performance metrics"""
        return performance_monitor.get_metrics()
    
    def get_recent_errors(self, count: int = 10) -> list:
        """Get recent errors"""
        return error_tracker.get_recent_errors(count)
    
    def shutdown(self):
        """Gracefully shutdown application"""
        logger.info("Shutting down application...")
        
        try:
            # Release camera
            if hasattr(self, 'camera_service'):
                self.camera_service.release()
                logger.info("Camera released")
            
            # Close database connections
            if hasattr(self, 'db'):
                self.db.close()
                logger.info("Database connections closed")
            
            # Clear caches
            cache.clear()
            logger.info("Cache cleared")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        
        logger.info("Application shutdown complete")


def create_app(config_env: str = None) -> Application:
    """Factory function to create application instance"""
    return Application(config_env)


if __name__ == '__main__':
    # For testing purposes
    app = create_app()
    print(app.config.display_info())
    print("\nHealth Status:", app.get_health_status())
    app.shutdown()
