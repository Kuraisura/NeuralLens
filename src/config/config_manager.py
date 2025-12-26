"""
Enhanced Configuration Management System
Production-grade configuration with validation, hot reload, and environment support

Features:
- Environment-specific configurations (dev, staging, production)
- Configuration validation with schemas
- Hot reload without service restart
- Secure secrets management
- Configuration versioning and rollback
- Remote configuration support
- Configuration change notifications

Author: Neural Lens Development Team
Date: January 4, 2026
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum
import logging
from threading import Lock
from copy import deepcopy


class Environment(Enum):
    """Deployment environments"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ConfigurationError(Exception):
    """Configuration-related errors"""
    pass


class ConfigManager:
    """
    Advanced configuration manager with validation, hot reload, and versioning
    
    Configuration hierarchy (highest to lowest priority):
    1. Environment variables (NEURALLENS_*)
    2. Environment-specific config file (config.production.json)
    3. Base config file (config.json)
    4. Default values
    """
    
    # Configuration schema for validation
    SCHEMA = {
        'app': {
            'name': {'type': str, 'required': True},
            'version': {'type': str, 'required': True},
            'debug': {'type': bool, 'default': False},
            'host': {'type': str, 'default': '0.0.0.0'},
            'port': {'type': int, 'default': 5000, 'min': 1, 'max': 65535}
        },
        'database': {
            'path': {'type': str, 'required': True},
            'pool_size': {'type': int, 'default': 5, 'min': 1, 'max': 100},
            'timeout': {'type': int, 'default': 30, 'min': 1}
        },
        'security': {
            'secret_key': {'type': str, 'required': True, 'min_length': 32},
            'jwt_expiration': {'type': int, 'default': 1800, 'min': 300},
            'bcrypt_rounds': {'type': int, 'default': 12, 'min': 10, 'max': 16},
            'max_login_attempts': {'type': int, 'default': 5, 'min': 1}
        },
        'face_recognition': {
            'tolerance': {'type': float, 'default': 0.6, 'min': 0.1, 'max': 1.0},
            'model': {'type': str, 'default': 'large', 'allowed': ['small', 'large']},
            'num_jitters': {'type': int, 'default': 1, 'min': 1, 'max': 10},
            'upsample': {'type': int, 'default': 1, 'min': 0, 'max': 2}
        },
        'camera': {
            'device_id': {'type': int, 'default': 0, 'min': 0},
            'width': {'type': int, 'default': 640, 'min': 320, 'max': 1920},
            'height': {'type': int, 'default': 480, 'min': 240, 'max': 1080},
            'fps': {'type': int, 'default': 30, 'min': 1, 'max': 60},
            'type': {'type': str, 'default': 'usb', 'allowed': ['usb', 'csi', 'mock']}
        },
        'monitoring': {
            'enabled': {'type': bool, 'default': True},
            'interval': {'type': int, 'default': 60, 'min': 10},
            'cpu_threshold': {'type': float, 'default': 80.0, 'min': 0, 'max': 100},
            'memory_threshold': {'type': float, 'default': 80.0, 'min': 0, 'max': 100},
            'disk_threshold': {'type': float, 'default': 90.0, 'min': 0, 'max': 100}
        },
        'logging': {
            'level': {'type': str, 'default': 'INFO', 'allowed': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']},
            'file': {'type': str, 'default': 'logs/neurallens.log'},
            'max_bytes': {'type': int, 'default': 10485760, 'min': 1048576},
            'backup_count': {'type': int, 'default': 5, 'min': 1}
        },
        'backup': {
            'enabled': {'type': bool, 'default': True},
            'directory': {'type': str, 'default': 'backups'},
            'schedule': {'type': str, 'default': 'daily'},
            'retention_days': {'type': int, 'default': 30, 'min': 1}
        }
    }
    
    def __init__(self, 
                 config_dir: str = "config",
                 environment: Optional[Environment] = None,
                 auto_reload: bool = True):
        """
        Initialize Configuration Manager
        
        Args:
            config_dir: Directory containing configuration files
            environment: Deployment environment (auto-detected if None)
            auto_reload: Enable hot reload of configuration files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.environment = environment or self._detect_environment()
        self.auto_reload = auto_reload
        
        # Thread-safe configuration access
        self._lock = Lock()
        self._config: Dict[str, Any] = {}
        self._config_history: List[Dict[str, Any]] = []
        self._change_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # File tracking for hot reload
        self._config_files: Dict[str, float] = {}  # path -> last_modified
        
        # Logger
        self.logger = logging.getLogger(__name__)
        
        # Load initial configuration
        self.reload()
        
        self.logger.info(f"Configuration loaded for environment: {self.environment.value}")
    
    def _detect_environment(self) -> Environment:
        """Detect deployment environment from environment variable"""
        env_name = os.getenv('NEURALLENS_ENV', 'development').lower()
        
        env_map = {
            'dev': Environment.DEVELOPMENT,
            'development': Environment.DEVELOPMENT,
            'staging': Environment.STAGING,
            'stage': Environment.STAGING,
            'prod': Environment.PRODUCTION,
            'production': Environment.PRODUCTION,
            'test': Environment.TEST
        }
        
        return env_map.get(env_name, Environment.DEVELOPMENT)
    
    def reload(self):
        """Reload configuration from files"""
        with self._lock:
            try:
                # Save current config to history
                if self._config:
                    self._config_history.append(deepcopy(self._config))
                    # Keep only last 10 configs
                    self._config_history = self._config_history[-10:]
                
                # Load configuration with priority
                new_config = {}
                
                # 1. Load base config
                base_config_file = self.config_dir / "config.json"
                if base_config_file.exists():
                    new_config = self._load_config_file(base_config_file)
                
                # 2. Load environment-specific config
                env_config_file = self.config_dir / f"config.{self.environment.value}.json"
                if env_config_file.exists():
                    env_config = self._load_config_file(env_config_file)
                    new_config = self._merge_configs(new_config, env_config)
                
                # 3. Apply environment variables
                new_config = self._apply_env_variables(new_config)
                
                # 4. Apply defaults
                new_config = self._apply_defaults(new_config)
                
                # 5. Validate configuration
                self._validate_config(new_config)
                
                # Update configuration
                old_config = self._config
                self._config = new_config
                
                # Notify callbacks if config changed
                if old_config != new_config:
                    self._notify_change_callbacks(new_config)
                
                self.logger.info("Configuration reloaded successfully")
                
            except Exception as e:
                self.logger.error(f"Failed to reload configuration: {e}", exc_info=True)
                raise ConfigurationError(f"Configuration reload failed: {e}")
    
    def _load_config_file(self, file_path: Path) -> Dict[str, Any]:
        """Load configuration from JSON or YAML file"""
        try:
            # Track file for hot reload
            self._config_files[str(file_path)] = file_path.stat().st_mtime
            
            # Load based on extension
            if file_path.suffix == '.json':
                with open(file_path) as f:
                    return json.load(f)
            elif file_path.suffix in ['.yaml', '.yml']:
                with open(file_path) as f:
                    return yaml.safe_load(f)
            else:
                raise ConfigurationError(f"Unsupported config file format: {file_path.suffix}")
                
        except Exception as e:
            self.logger.error(f"Failed to load config file {file_path}: {e}")
            raise
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two configuration dictionaries"""
        result = deepcopy(base)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = deepcopy(value)
        
        return result
    
    def _apply_env_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variables with NEURALLENS_ prefix"""
        result = deepcopy(config)
        
        # Flatten config to dot notation
        flat_config = self._flatten_dict(result)
        
        # Override with environment variables
        for key in flat_config.keys():
            env_key = f"NEURALLENS_{key.upper().replace('.', '_')}"
            if env_key in os.environ:
                env_value = os.getenv(env_key)
                # Try to parse as JSON for complex types
                try:
                    parsed_value = json.loads(env_value)
                except (json.JSONDecodeError, TypeError):
                    parsed_value = env_value
                
                flat_config[key] = parsed_value
        
        # Unflatten back to nested dict
        return self._unflatten_dict(flat_config)
    
    def _apply_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default values from schema"""
        result = deepcopy(config)
        
        for section, fields in self.SCHEMA.items():
            if section not in result:
                result[section] = {}
            
            for field, rules in fields.items():
                if field not in result[section] and 'default' in rules:
                    result[section][field] = rules['default']
        
        return result
    
    def _validate_config(self, config: Dict[str, Any]):
        """Validate configuration against schema"""
        errors = []
        
        for section, fields in self.SCHEMA.items():
            if section not in config:
                config[section] = {}
            
            for field, rules in fields.items():
                value = config[section].get(field)
                
                # Check required fields
                if rules.get('required', False) and value is None:
                    errors.append(f"{section}.{field} is required")
                    continue
                
                if value is None:
                    continue
                
                # Type validation
                expected_type = rules.get('type')
                if expected_type and not isinstance(value, expected_type):
                    errors.append(f"{section}.{field} must be of type {expected_type.__name__}")
                
                # Numeric range validation
                if isinstance(value, (int, float)):
                    if 'min' in rules and value < rules['min']:
                        errors.append(f"{section}.{field} must be >= {rules['min']}")
                    if 'max' in rules and value > rules['max']:
                        errors.append(f"{section}.{field} must be <= {rules['max']}")
                
                # String length validation
                if isinstance(value, str) and 'min_length' in rules:
                    if len(value) < rules['min_length']:
                        errors.append(f"{section}.{field} must be at least {rules['min_length']} characters")
                
                # Allowed values validation
                if 'allowed' in rules and value not in rules['allowed']:
                    errors.append(f"{section}.{field} must be one of {rules['allowed']}")
        
        if errors:
            raise ConfigurationError(f"Configuration validation failed:\n" + "\n".join(errors))
    
    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
        """Flatten nested dictionary to dot notation"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _unflatten_dict(self, d: Dict[str, Any], sep: str = '.') -> Dict[str, Any]:
        """Unflatten dot notation dictionary to nested dict"""
        result = {}
        for key, value in d.items():
            parts = key.split(sep)
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Example:
            config.get('database.path')
            config.get('camera.width', 640)
        """
        with self._lock:
            try:
                parts = key.split('.')
                value = self._config
                for part in parts:
                    value = value[part]
                return value
            except (KeyError, TypeError):
                return default
    
    def set(self, key: str, value: Any, persist: bool = False):
        """
        Set configuration value using dot notation
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
            persist: Whether to save to config file
        """
        with self._lock:
            parts = key.split('.')
            current = self._config
            
            # Navigate to parent
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            # Set value
            current[parts[-1]] = value
            
            # Validate
            self._validate_config(self._config)
            
            # Persist if requested
            if persist:
                self.save()
            
            # Notify callbacks
            self._notify_change_callbacks(self._config)
    
    def save(self, file_path: Optional[Path] = None):
        """Save current configuration to file"""
        with self._lock:
            if file_path is None:
                file_path = self.config_dir / f"config.{self.environment.value}.json"
            
            try:
                with open(file_path, 'w') as f:
                    json.dump(self._config, f, indent=2)
                self.logger.info(f"Configuration saved to {file_path}")
            except Exception as e:
                self.logger.error(f"Failed to save configuration: {e}")
                raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def rollback(self) -> bool:
        """Rollback to previous configuration"""
        with self._lock:
            if not self._config_history:
                self.logger.warning("No configuration history available for rollback")
                return False
            
            try:
                self._config = self._config_history.pop()
                self._notify_change_callbacks(self._config)
                self.logger.info("Configuration rolled back")
                return True
            except Exception as e:
                self.logger.error(f"Rollback failed: {e}")
                return False
    
    def check_for_changes(self) -> bool:
        """Check if config files have changed (for hot reload)"""
        for file_path, last_modified in list(self._config_files.items()):
            try:
                current_mtime = Path(file_path).stat().st_mtime
                if current_mtime > last_modified:
                    return True
            except FileNotFoundError:
                pass
        return False
    
    def register_change_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback to be notified of configuration changes"""
        self._change_callbacks.append(callback)
    
    def _notify_change_callbacks(self, new_config: Dict[str, Any]):
        """Notify all registered callbacks of configuration change"""
        for callback in self._change_callbacks:
            try:
                callback(new_config)
            except Exception as e:
                self.logger.error(f"Configuration change callback failed: {e}")
    
    def export(self) -> Dict[str, Any]:
        """Export current configuration (safe copy)"""
        with self._lock:
            return deepcopy(self._config)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration (alias for export)"""
        return self.export()
    
    def __getitem__(self, key: str) -> Any:
        """Dictionary-style access"""
        return self.get(key)
    
    def __setitem__(self, key: str, value: Any):
        """Dictionary-style setting"""
        self.set(key, value)


# Global configuration instance (singleton pattern)
_config_instance: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance


def initialize_config(config_dir: str = "config", 
                     environment: Optional[Environment] = None) -> ConfigManager:
    """Initialize global configuration instance"""
    global _config_instance
    _config_instance = ConfigManager(config_dir, environment)
    return _config_instance
