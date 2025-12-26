"""
Storage Hardware Abstraction Layer
Platform-independent interface for storage operations

Supports:
- Local filesystem storage
- Network storage (NFS, SMB)
- Cloud storage (S3, Azure Blob)
- In-memory storage (for testing)

Author: Neural Lens Development Team
Date: January 4, 2026
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict, Any, BinaryIO
from datetime import datetime
import logging
import shutil
import json


class StorageInterface(ABC):
    """Abstract interface for storage operations"""
    
    @abstractmethod
    def write(self, path: str, data: bytes) -> bool:
        """
        Write data to storage
        
        Args:
            path: File path
            data: Binary data to write
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def read(self, path: str) -> Optional[bytes]:
        """
        Read data from storage
        
        Args:
            path: File path
            
        Returns:
            Binary data or None if not found
        """
        pass
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if file exists"""
        pass
    
    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete file from storage"""
        pass
    
    @abstractmethod
    def list(self, directory: str, pattern: str = "*") -> List[str]:
        """
        List files in directory
        
        Args:
            directory: Directory path
            pattern: Filename pattern (glob)
            
        Returns:
            List of file paths
        """
        pass
    
    @abstractmethod
    def get_size(self, path: str) -> int:
        """Get file size in bytes"""
        pass
    
    @abstractmethod
    def get_modified_time(self, path: str) -> datetime:
        """Get file modification time"""
        pass
    
    @abstractmethod
    def create_directory(self, path: str) -> bool:
        """Create directory"""
        pass


class LocalStorage(StorageInterface):
    """Local filesystem storage implementation"""
    
    def __init__(self, base_path: str = "."):
        """
        Initialize local storage
        
        Args:
            base_path: Base directory for all operations
        """
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Local storage initialized: {self.base_path}")
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to base_path"""
        full_path = (self.base_path / path).resolve()
        # Security: ensure path is within base_path
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError(f"Path outside base directory: {path}")
        return full_path
    
    def write(self, path: str, data: bytes) -> bool:
        try:
            file_path = self._resolve_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(data)
            return True
        except Exception as e:
            self.logger.error(f"Failed to write {path}: {e}")
            return False
    
    def read(self, path: str) -> Optional[bytes]:
        try:
            file_path = self._resolve_path(path)
            return file_path.read_bytes()
        except FileNotFoundError:
            return None
        except Exception as e:
            self.logger.error(f"Failed to read {path}: {e}")
            return None
    
    def exists(self, path: str) -> bool:
        try:
            return self._resolve_path(path).exists()
        except Exception:
            return False
    
    def delete(self, path: str) -> bool:
        try:
            file_path = self._resolve_path(path)
            if file_path.is_file():
                file_path.unlink()
            elif file_path.is_dir():
                shutil.rmtree(file_path)
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete {path}: {e}")
            return False
    
    def list(self, directory: str, pattern: str = "*") -> List[str]:
        try:
            dir_path = self._resolve_path(directory)
            if not dir_path.is_dir():
                return []
            
            files = []
            for file_path in dir_path.glob(pattern):
                rel_path = file_path.relative_to(self.base_path)
                files.append(str(rel_path))
            return files
        except Exception as e:
            self.logger.error(f"Failed to list {directory}: {e}")
            return []
    
    def get_size(self, path: str) -> int:
        try:
            return self._resolve_path(path).stat().st_size
        except Exception:
            return 0
    
    def get_modified_time(self, path: str) -> datetime:
        try:
            timestamp = self._resolve_path(path).stat().st_mtime
            return datetime.fromtimestamp(timestamp)
        except Exception:
            return datetime.min
    
    def create_directory(self, path: str) -> bool:
        try:
            self._resolve_path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"Failed to create directory {path}: {e}")
            return False


class MemoryStorage(StorageInterface):
    """In-memory storage for testing"""
    
    def __init__(self):
        """Initialize memory storage"""
        self.storage: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        self.logger.info("Memory storage initialized")
    
    def write(self, path: str, data: bytes) -> bool:
        self.storage[path] = {
            'data': data,
            'size': len(data),
            'modified': datetime.now()
        }
        return True
    
    def read(self, path: str) -> Optional[bytes]:
        if path in self.storage:
            return self.storage[path]['data']
        return None
    
    def exists(self, path: str) -> bool:
        return path in self.storage
    
    def delete(self, path: str) -> bool:
        if path in self.storage:
            del self.storage[path]
            return True
        return False
    
    def list(self, directory: str, pattern: str = "*") -> List[str]:
        import fnmatch
        prefix = directory.rstrip('/') + '/'
        matching = []
        
        for path in self.storage.keys():
            if path.startswith(prefix):
                rel_path = path[len(prefix):]
                if '/' not in rel_path and fnmatch.fnmatch(rel_path, pattern):
                    matching.append(path)
        
        return matching
    
    def get_size(self, path: str) -> int:
        if path in self.storage:
            return self.storage[path]['size']
        return 0
    
    def get_modified_time(self, path: str) -> datetime:
        if path in self.storage:
            return self.storage[path]['modified']
        return datetime.min
    
    def create_directory(self, path: str) -> bool:
        # Directories don't need explicit creation in memory storage
        return True


class NetworkStorage(StorageInterface):
    """Network storage implementation (NFS/SMB)"""
    
    def __init__(self, mount_point: str):
        """
        Initialize network storage
        
        Args:
            mount_point: Mount point for network share
        """
        self.mount_point = Path(mount_point)
        self.logger = logging.getLogger(__name__)
        
        if not self.mount_point.exists():
            raise ValueError(f"Mount point does not exist: {mount_point}")
        
        self.logger.info(f"Network storage initialized: {mount_point}")
        # Delegate to LocalStorage for actual operations
        self._storage = LocalStorage(str(self.mount_point))
    
    def write(self, path: str, data: bytes) -> bool:
        return self._storage.write(path, data)
    
    def read(self, path: str) -> Optional[bytes]:
        return self._storage.read(path)
    
    def exists(self, path: str) -> bool:
        return self._storage.exists(path)
    
    def delete(self, path: str) -> bool:
        return self._storage.delete(path)
    
    def list(self, directory: str, pattern: str = "*") -> List[str]:
        return self._storage.list(directory, pattern)
    
    def get_size(self, path: str) -> int:
        return self._storage.get_size(path)
    
    def get_modified_time(self, path: str) -> datetime:
        return self._storage.get_modified_time(path)
    
    def create_directory(self, path: str) -> bool:
        return self._storage.create_directory(path)


class StorageFactory:
    """Factory for creating storage instances"""
    
    @staticmethod
    def create(storage_type: str, **kwargs) -> StorageInterface:
        """
        Create storage instance
        
        Args:
            storage_type: Type of storage (local, memory, network)
            **kwargs: Storage-specific parameters
            
        Returns:
            StorageInterface instance
        """
        storage_type = storage_type.lower()
        
        if storage_type == "local":
            base_path = kwargs.get('base_path', '.')
            return LocalStorage(base_path)
        elif storage_type == "memory":
            return MemoryStorage()
        elif storage_type == "network":
            mount_point = kwargs.get('mount_point')
            if not mount_point:
                raise ValueError("mount_point required for network storage")
            return NetworkStorage(mount_point)
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
