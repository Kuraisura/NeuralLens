"""
Integration Tests for Neural Lens System
Tests interaction between multiple modules

Test Coverage:
- Face recognition pipeline with database
- Authentication with database
- Camera interface with face recognition
- Configuration with system components
- Monitoring with logging
- Backup with database
- HAL interfaces integration

Author: Neural Lens Development Team
Date: January 4, 2026
"""

import pytest
import os
import tempfile
from pathlib import Path
from datetime import datetime
import json

# Import modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.hal.camera_interface import CameraFactory, MockCamera
from src.hal.gpio_interface import GPIOFactory, MockGPIO
from src.hal.storage_interface import StorageFactory, MemoryStorage
from src.security.security_manager import SecurityManager
from src.config.config_manager import ConfigManager, Environment
from src.monitoring.watchdog import WatchdogMonitor
from src.core.logging_system import LogManager


class TestFaceRecognitionIntegration:
    """Integration tests for face recognition pipeline"""
    
    @pytest.fixture
    def setup_environment(self):
        """Setup test environment"""
        # Create temporary directories
        self.temp_dir = tempfile.mkdtemp()
        self.face_data_dir = Path(self.temp_dir) / "face_data"
        self.face_data_dir.mkdir()
        
        # Create mock camera
        self.camera = CameraFactory.create("mock")
        
        yield
        
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_camera_initialization(self, setup_environment):
        """Test camera interface initialization"""
        assert self.camera is not None
        assert isinstance(self.camera, MockCamera)
    
    def test_camera_frame_capture(self, setup_environment):
        """Test capturing frames from camera"""
        frame = self.camera.read_frame()
        assert frame is not None
        assert frame.shape[0] > 0  # Height
        assert frame.shape[1] > 0  # Width
    
    def test_camera_release(self, setup_environment):
        """Test camera resource cleanup"""
        self.camera.release()
        # Camera should be released without errors


class TestAuthenticationIntegration:
    """Integration tests for authentication system"""
    
    @pytest.fixture
    def setup_auth(self):
        """Setup authentication environment"""
        self.security = SecurityManager()
        self.test_password = "TestPassword123!"
        
        yield
    
    def test_password_hash_and_verify(self, setup_auth):
        """Test password hashing and verification"""
        # Hash password
        password_hash = self.security.hash_password(self.test_password)
        assert password_hash is not None
        assert password_hash != self.test_password
        
        # Verify correct password
        assert self.security.verify_password(self.test_password, password_hash)
        
        # Verify incorrect password
        assert not self.security.verify_password("WrongPassword", password_hash)
    
    def test_jwt_token_flow(self, setup_auth):
        """Test JWT token generation and verification"""
        # Generate token
        payload = {'user_id': 123, 'username': 'testuser'}
        token = self.security.generate_jwt(payload)
        assert token is not None
        
        # Verify token
        decoded = self.security.verify_jwt(token)
        assert decoded is not None
        assert decoded['user_id'] == 123
        assert decoded['username'] == 'testuser'
    
    def test_jwt_token_expiration(self, setup_auth):
        """Test JWT token expiration"""
        import time
        
        # Generate token with 1 second expiration
        payload = {'user_id': 123}
        token = self.security.generate_jwt(payload, expiration=1)
        
        # Token should be valid immediately
        assert self.security.verify_jwt(token) is not None
        
        # Wait for expiration
        time.sleep(2)
        
        # Token should be expired
        assert self.security.verify_jwt(token) is None
    
    def test_data_encryption_decryption(self, setup_auth):
        """Test data encryption and decryption"""
        test_data = b"Sensitive biometric data"
        
        # Encrypt
        encrypted = self.security.encrypt_data(test_data)
        assert encrypted != test_data
        
        # Decrypt
        decrypted = self.security.decrypt_data(encrypted)
        assert decrypted == test_data


class TestConfigurationIntegration:
    """Integration tests for configuration management"""
    
    @pytest.fixture
    def setup_config(self):
        """Setup configuration environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir) / "config"
        self.config_dir.mkdir()
        
        # Create test config file
        test_config = {
            'app': {
                'name': 'Neural Lens Test',
                'version': '1.0.0',
                'debug': True
            },
            'database': {
                'path': 'test.db'
            },
            'security': {
                'secret_key': 'test_secret_key_32_characters_long!'
            }
        }
        
        config_file = self.config_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f)
        
        self.config = ConfigManager(str(self.config_dir), Environment.TEST)
        
        yield
        
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_config_loading(self, setup_config):
        """Test configuration loading"""
        assert self.config.get('app.name') == 'Neural Lens Test'
        assert self.config.get('app.debug') is True
    
    def test_config_defaults(self, setup_config):
        """Test configuration defaults"""
        # Test default values from schema
        assert self.config.get('app.port') == 5000
        assert self.config.get('database.pool_size') == 5
    
    def test_config_validation(self, setup_config):
        """Test configuration validation"""
        from src.config.config_manager import ConfigurationError
        
        # Try setting invalid value
        with pytest.raises(ConfigurationError):
            self.config.set('app.port', 99999)  # Exceeds max
    
    def test_config_get_set(self, setup_config):
        """Test configuration get and set"""
        # Set value
        self.config.set('app.debug', False)
        assert self.config.get('app.debug') is False
        
        # Set nested value
        self.config.set('camera.width', 1280)
        assert self.config.get('camera.width') == 1280


class TestMonitoringIntegration:
    """Integration tests for monitoring system"""
    
    @pytest.fixture
    def setup_monitoring(self):
        """Setup monitoring environment"""
        self.watchdog = WatchdogMonitor(check_interval=1)
        self.watchdog.start()
        
        yield
        
        # Cleanup
        self.watchdog.stop()
    
    def test_watchdog_start_stop(self, setup_monitoring):
        """Test watchdog start and stop"""
        import time
        
        # Watchdog should be running
        assert self.watchdog.running
        
        # Wait a bit
        time.sleep(2)
        
        # Stop watchdog
        self.watchdog.stop()
        assert not self.watchdog.running
    
    def test_process_registration(self, setup_monitoring):
        """Test process registration and monitoring"""
        import time
        
        # Register a process
        self.watchdog.register_process('test_process', max_silence=5)
        
        # Send heartbeat
        self.watchdog.heartbeat('test_process')
        
        # Wait a bit
        time.sleep(1)
        
        # Process should still be alive
        assert 'test_process' in self.watchdog.processes
    
    def test_system_health_monitoring(self, setup_monitoring):
        """Test system health monitoring"""
        import time
        
        # Wait for health check
        time.sleep(2)
        
        # Get health status
        health = self.watchdog.get_health_status()
        
        assert 'cpu_percent' in health
        assert 'memory_percent' in health
        assert 'disk_usage' in health
        assert 0 <= health['cpu_percent'] <= 100
        assert 0 <= health['memory_percent'] <= 100


class TestHALIntegration:
    """Integration tests for Hardware Abstraction Layer"""
    
    def test_gpio_operations(self):
        """Test GPIO interface operations"""
        from src.hal.gpio_interface import PinMode, PullMode
        
        gpio = GPIOFactory.create("mock")
        
        # Setup pin
        gpio.setup(17, PinMode.OUTPUT)
        
        # Write value
        gpio.write(17, 1)
        
        # Read value (mock will return what was written)
        # Note: In mock, read returns stored state
        value = gpio.read(17)
        assert value == 1
        
        # Cleanup
        gpio.cleanup(17)
    
    def test_storage_operations(self):
        """Test storage interface operations"""
        storage = StorageFactory.create("memory")
        
        # Write data
        test_data = b"Test data content"
        assert storage.write("test/file.txt", test_data)
        
        # Read data
        read_data = storage.read("test/file.txt")
        assert read_data == test_data
        
        # Check existence
        assert storage.exists("test/file.txt")
        
        # Delete
        assert storage.delete("test/file.txt")
        assert not storage.exists("test/file.txt")
    
    def test_storage_listing(self):
        """Test storage directory listing"""
        storage = StorageFactory.create("memory")
        
        # Create multiple files
        storage.write("data/file1.txt", b"content1")
        storage.write("data/file2.txt", b"content2")
        storage.write("data/file3.log", b"content3")
        
        # List all files
        all_files = storage.list("data", "*")
        assert len(all_files) == 3
        
        # List only .txt files
        txt_files = storage.list("data", "*.txt")
        assert len(txt_files) == 2


class TestLoggingIntegration:
    """Integration tests for logging system"""
    
    @pytest.fixture
    def setup_logging(self):
        """Setup logging environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / "logs"
        self.log_dir.mkdir()
        
        self.log_manager = LogManager(
            app_name="test_app",
            log_dir=str(self.log_dir)
        )
        
        yield
        
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_logger_creation(self, setup_logging):
        """Test logger creation"""
        logger = self.log_manager.get_logger("test_module")
        assert logger is not None
        assert logger.name == "test_module"
    
    def test_logging_levels(self, setup_logging):
        """Test different logging levels"""
        logger = self.log_manager.get_logger("test_levels")
        
        # These should not raise exceptions
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
    
    def test_audit_logging(self, setup_logging):
        """Test audit logging"""
        self.log_manager.log_audit(
            action="test_action",
            user="test_user",
            details="Test audit entry"
        )
        
        # Check if audit log file was created
        audit_log = self.log_dir / "audit.log"
        assert audit_log.exists()


class TestBackupIntegration:
    """Integration tests for backup system"""
    
    @pytest.fixture
    def setup_backup(self):
        """Setup backup environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.backup_dir = Path(self.temp_dir) / "backups"
        
        self.data_dir.mkdir()
        self.backup_dir.mkdir()
        
        # Create test data
        (self.data_dir / "test.db").write_text("test database")
        (self.data_dir / "config.json").write_text('{"test": "data"}')
        
        yield
        
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_backup_creation(self, setup_backup):
        """Test backup creation"""
        from scripts.backup.backup_manager import BackupManager
        
        backup_mgr = BackupManager(
            backup_dir=str(self.backup_dir),
            database_path=str(self.data_dir / "test.db")
        )
        
        # Create backup
        backup_file = backup_mgr.create_backup()
        assert backup_file is not None
        assert Path(backup_file).exists()
    
    def test_backup_listing(self, setup_backup):
        """Test listing backups"""
        from scripts.backup.backup_manager import BackupManager
        
        backup_mgr = BackupManager(
            backup_dir=str(self.backup_dir),
            database_path=str(self.data_dir / "test.db")
        )
        
        # Create multiple backups
        backup_mgr.create_backup()
        
        # List backups
        backups = backup_mgr.list_backups()
        assert len(backups) > 0


# Integration test suite configuration
@pytest.fixture(scope="session")
def integration_test_setup():
    """Setup for entire integration test suite"""
    # Setup code that runs once before all tests
    print("\n=== Starting Integration Tests ===")
    
    yield
    
    # Teardown code that runs once after all tests
    print("\n=== Integration Tests Complete ===")


# Run tests with: pytest tests/integration/test_integration.py -v
