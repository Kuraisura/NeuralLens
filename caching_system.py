"""
NEURAL LENS - Caching and Performance System
In-memory caching with TTL, LRU eviction, and performance optimization utilities
"""

import time
import threading
from functools import wraps, lru_cache
from collections import OrderedDict
from typing import Any, Callable, Optional, Dict
import logging
import hashlib
import json
import pickle

logger = logging.getLogger(__name__)


class CacheEntry:
    """Represents a single cache entry with TTL"""
    
    def __init__(self, value: Any, ttl: float):
        self.value = value
        self.expiry = time.time() + ttl if ttl > 0 else float('inf')
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        return time.time() > self.expiry


class LRUCache:
    """
    Thread-safe LRU cache with TTL support
    
    Features:
    - Least Recently Used eviction policy
    - Time-to-live (TTL) for entries
    - Thread-safe operations
    - Size limits
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: float = 300):
        """
        Initialize cache
        
        Args:
            max_size: Maximum number of entries
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def _make_key(self, key: Any) -> str:
        """Convert key to string"""
        if isinstance(key, (str, int, float)):
            return str(key)
        # Hash complex objects
        return hashlib.md5(pickle.dumps(key)).hexdigest()
    
    def get(self, key: Any, default: Any = None) -> Any:
        """Get value from cache"""
        str_key = self._make_key(key)
        
        with self.lock:
            if str_key in self.cache:
                entry = self.cache[str_key]
                
                # Check expiry
                if entry.is_expired():
                    del self.cache[str_key]
                    self.misses += 1
                    return default
                
                # Move to end (mark as recently used)
                self.cache.move_to_end(str_key)
                self.hits += 1
                return entry.value
            
            self.misses += 1
            return default
    
    def set(self, key: Any, value: Any, ttl: Optional[float] = None):
        """Set value in cache"""
        str_key = self._make_key(key)
        ttl = ttl if ttl is not None else self.default_ttl
        
        with self.lock:
            # Check if we need to evict
            if str_key not in self.cache and len(self.cache) >= self.max_size:
                # Remove oldest item
                self.cache.popitem(last=False)
                self.evictions += 1
            
            # Add/update entry
            self.cache[str_key] = CacheEntry(value, ttl)
            self.cache.move_to_end(str_key)
    
    def delete(self, key: Any):
        """Remove entry from cache"""
        str_key = self._make_key(key)
        
        with self.lock:
            if str_key in self.cache:
                del self.cache[str_key]
    
    def clear(self):
        """Clear entire cache"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'evictions': self.evictions,
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests
            }
    
    def cleanup_expired(self):
        """Remove expired entries"""
        with self.lock:
            expired_keys = [
                k for k, v in self.cache.items()
                if v.is_expired()
            ]
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")


class CacheManager:
    """Global cache manager with multiple named caches"""
    
    def __init__(self):
        self.caches: Dict[str, LRUCache] = {}
        self.lock = threading.Lock()
    
    def get_cache(
        self,
        name: str,
        max_size: int = 1000,
        default_ttl: float = 300
    ) -> LRUCache:
        """Get or create a named cache"""
        with self.lock:
            if name not in self.caches:
                self.caches[name] = LRUCache(max_size, default_ttl)
                logger.info(f"Created cache '{name}' (max_size={max_size}, ttl={default_ttl}s)")
            
            return self.caches[name]
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all caches"""
        with self.lock:
            return {
                name: cache.get_stats()
                for name, cache in self.caches.items()
            }
    
    def cleanup_all(self):
        """Cleanup expired entries in all caches"""
        with self.lock:
            for cache in self.caches.values():
                cache.cleanup_expired()


# Global cache manager
cache_manager = CacheManager()


def cached(
    cache_name: str = 'default',
    ttl: float = 300,
    key_func: Optional[Callable] = None
):
    """
    Decorator for caching function results
    
    Args:
        cache_name: Name of cache to use
        ttl: Time-to-live in seconds
        key_func: Function to generate cache key from args
    
    Usage:
        @cached('employees', ttl=60)
        def get_employee(emp_id):
            return db.query(emp_id)
    """
    def decorator(func):
        cache = cache_manager.get_cache(cache_name, max_size=1000, default_ttl=ttl)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: use function name and arguments
                cache_key = (func.__name__, args, tuple(sorted(kwargs.items())))
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit: {func.__name__}")
                return result
            
            # Cache miss - compute result
            logger.debug(f"Cache miss: {func.__name__}")
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, ttl)
            
            return result
        
        # Add cache control methods to function
        wrapper.cache_clear = lambda: cache.clear()
        wrapper.cache_stats = lambda: cache.get_stats()
        
        return wrapper
    
    return decorator


class PerformanceConfig:
    """
    Central performance configuration
    Allows runtime tuning of performance parameters
    """
    
    def __init__(self):
        self.config = {
            # Face recognition
            'face_detection_model': 'hog',  # 'hog' or 'cnn'
            'face_num_jitters': 1,
            'face_process_every_n_frames': 2,
            'face_tolerance': 0.6,
            
            # Database
            'db_pool_size': 5,
            'db_cache_timeout': 60,
            
            # Caching
            'cache_enabled': True,
            'cache_default_ttl': 300,
            'cache_max_size': 1000,
            
            # API
            'api_rate_limit': 100,  # requests per minute
            'api_timeout': 30,
            
            # Image processing
            'image_resize_factor': 0.5,
            'jpeg_quality': 85,
            
            # Logging
            'log_level': 'INFO',
            'enable_performance_logging': True
        }
        
        self.lock = threading.Lock()
        self.presets = {
            'fast': {
                'face_detection_model': 'hog',
                'face_num_jitters': 1,
                'face_process_every_n_frames': 3,
                'image_resize_factor': 0.25,
                'jpeg_quality': 75,
            },
            'balanced': {
                'face_detection_model': 'hog',
                'face_num_jitters': 1,
                'face_process_every_n_frames': 2,
                'image_resize_factor': 0.5,
                'jpeg_quality': 85,
            },
            'accurate': {
                'face_detection_model': 'cnn',
                'face_num_jitters': 2,
                'face_process_every_n_frames': 1,
                'image_resize_factor': 0.75,
                'jpeg_quality': 95,
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        with self.lock:
            return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        with self.lock:
            old_value = self.config.get(key)
            self.config[key] = value
            logger.info(f"Performance config updated: {key} = {value} (was: {old_value})")
    
    def update(self, config_dict: Dict[str, Any]):
        """Update multiple configuration values"""
        with self.lock:
            self.config.update(config_dict)
            logger.info(f"Performance config updated: {list(config_dict.keys())}")
    
    def apply_preset(self, preset_name: str):
        """Apply a performance preset"""
        if preset_name not in self.presets:
            raise ValueError(f"Unknown preset: {preset_name}. Available: {list(self.presets.keys())}")
        
        preset_config = self.presets[preset_name]
        self.update(preset_config)
        logger.info(f"Applied performance preset: {preset_name}")
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values"""
        with self.lock:
            return self.config.copy()
    
    def reset(self):
        """Reset to default values"""
        self.apply_preset('balanced')


# Global performance configuration
perf_config = PerformanceConfig()


# Utility functions

def batch_process(items: list, batch_size: int, process_func: Callable):
    """
    Process items in batches for better performance
    
    Args:
        items: List of items to process
        batch_size: Number of items per batch
        process_func: Function to process each batch
    
    Returns:
        List of results
    """
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = process_func(batch)
        results.extend(batch_results)
    
    return results


def memoize_with_expiry(ttl: float = 300):
    """
    Simple memoization decorator with expiry
    Similar to functools.lru_cache but with TTL
    """
    def decorator(func):
        cache = {}
        cache_times = {}
        lock = threading.Lock()
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            
            with lock:
                # Check if cached and not expired
                if key in cache:
                    if time.time() - cache_times[key] < ttl:
                        return cache[key]
                    else:
                        # Expired
                        del cache[key]
                        del cache_times[key]
                
                # Compute result
                result = func(*args, **kwargs)
                cache[key] = result
                cache_times[key] = time.time()
                
                return result
        
        return wrapper
    
    return decorator


# Example usage
if __name__ == '__main__':
    # Test LRU cache
    cache = LRUCache(max_size=3, default_ttl=2)
    
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    cache.set('key3', 'value3')
    
    print("Value:", cache.get('key1'))
    print("Stats:", cache.get_stats())
    
    # Test cached decorator
    @cached('test', ttl=5)
    def expensive_operation(x):
        time.sleep(0.1)
        return x * 2
    
    # First call - cache miss
    start = time.time()
    result1 = expensive_operation(5)
    time1 = time.time() - start
    
    # Second call - cache hit
    start = time.time()
    result2 = expensive_operation(5)
    time2 = time.time() - start
    
    print(f"\nFirst call: {time1:.4f}s")
    print(f"Second call: {time2:.4f}s (speedup: {time1/time2:.1f}x)")
    print("Cache stats:", expensive_operation.cache_stats())
    
    # Test performance config
    print("\nPerformance config:")
    print(perf_config.get_all())
    
    perf_config.apply_preset('fast')
    print("\nAfter 'fast' preset:")
    print(perf_config.get_all())
