"""
NEURAL LENS - Image Optimization Module
Advanced image processing and optimization for better performance
"""

import cv2
import numpy as np
from PIL import Image
import io
import logging
from typing import Tuple, Optional, Union
from functools import lru_cache
import hashlib

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """Advanced image optimization for face recognition and streaming"""
    
    def __init__(self):
        self.quality_presets = {
            'low': {'jpeg_quality': 60, 'scale': 0.5, 'format': 'JPEG'},
            'medium': {'jpeg_quality': 75, 'scale': 0.75, 'format': 'JPEG'},
            'high': {'jpeg_quality': 85, 'scale': 1.0, 'format': 'JPEG'},
            'ultra': {'jpeg_quality': 95, 'scale': 1.0, 'format': 'PNG'}
        }
        self.current_preset = 'high'
        self.cache_enabled = True
        self._encoding_cache = {}
    
    def set_quality_preset(self, preset: str):
        """Set image quality preset"""
        if preset in self.quality_presets:
            self.current_preset = preset
            logger.info(f"Image quality preset set to: {preset}")
        else:
            raise ValueError(f"Unknown preset: {preset}")
    
    def optimize_frame(self, frame: np.ndarray, 
                      quality: Optional[str] = None,
                      max_dimension: Optional[int] = None) -> np.ndarray:
        """
        Optimize a video frame for processing
        
        Args:
            frame: Input frame (BGR format)
            quality: Quality preset name
            max_dimension: Maximum width or height
        
        Returns:
            Optimized frame
        """
        try:
            preset = self.quality_presets[quality or self.current_preset]
            
            # Resize if needed
            if max_dimension or preset['scale'] != 1.0:
                frame = self._smart_resize(frame, preset['scale'], max_dimension)
            
            # Apply sharpening for better face detection
            frame = self._apply_sharpening(frame)
            
            # Adjust brightness/contrast if needed
            frame = self._auto_adjust(frame)
            
            return frame
            
        except Exception as e:
            logger.error(f"Error optimizing frame: {e}")
            return frame
    
    def _smart_resize(self, frame: np.ndarray, 
                     scale: float = 1.0,
                     max_dimension: Optional[int] = None) -> np.ndarray:
        """Smart resizing with aspect ratio preservation"""
        height, width = frame.shape[:2]
        
        # Calculate new dimensions
        if max_dimension:
            if width > height:
                new_width = min(width, max_dimension)
                new_height = int(height * (new_width / width))
            else:
                new_height = min(height, max_dimension)
                new_width = int(width * (new_height / height))
        else:
            new_width = int(width * scale)
            new_height = int(height * scale)
        
        # Use appropriate interpolation
        if scale < 1.0:
            interpolation = cv2.INTER_AREA  # Best for downscaling
        else:
            interpolation = cv2.INTER_CUBIC  # Best for upscaling
        
        return cv2.resize(frame, (new_width, new_height), interpolation=interpolation)
    
    def _apply_sharpening(self, frame: np.ndarray, strength: float = 0.5) -> np.ndarray:
        """Apply subtle sharpening to improve face detection"""
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]]) * strength / 9
        
        sharpened = cv2.filter2D(frame, -1, kernel)
        return cv2.addWeighted(frame, 1.0 - strength, sharpened, strength, 0)
    
    def _auto_adjust(self, frame: np.ndarray) -> np.ndarray:
        """Auto-adjust brightness and contrast"""
        # Convert to LAB color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        # Merge channels
        lab = cv2.merge([l, a, b])
        
        # Convert back to BGR
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def encode_frame(self, frame: np.ndarray, 
                    quality: Optional[str] = None,
                    use_cache: bool = True) -> bytes:
        """
        Encode frame to JPEG bytes with optional caching
        
        Args:
            frame: Input frame
            quality: Quality preset
            use_cache: Enable frame caching
        
        Returns:
            Encoded JPEG bytes
        """
        try:
            preset = self.quality_presets[quality or self.current_preset]
            
            # Generate cache key if caching enabled
            if use_cache and self.cache_enabled:
                cache_key = self._generate_cache_key(frame, preset['jpeg_quality'])
                if cache_key in self._encoding_cache:
                    return self._encoding_cache[cache_key]
            
            # Encode with OpenCV (faster)
            encode_params = [
                cv2.IMWRITE_JPEG_QUALITY, preset['jpeg_quality'],
                cv2.IMWRITE_JPEG_OPTIMIZE, 1,
                cv2.IMWRITE_JPEG_PROGRESSIVE, 1
            ]
            
            success, buffer = cv2.imencode('.jpg', frame, encode_params)
            
            if not success:
                raise ValueError("Failed to encode frame")
            
            frame_bytes = buffer.tobytes()
            
            # Cache result
            if use_cache and self.cache_enabled:
                self._encoding_cache[cache_key] = frame_bytes
                
                # Limit cache size
                if len(self._encoding_cache) > 10:
                    # Remove oldest entry
                    self._encoding_cache.pop(next(iter(self._encoding_cache)))
            
            return frame_bytes
            
        except Exception as e:
            logger.error(f"Error encoding frame: {e}")
            # Fallback to basic encoding
            _, buffer = cv2.imencode('.jpg', frame)
            return buffer.tobytes()
    
    def _generate_cache_key(self, frame: np.ndarray, quality: int) -> str:
        """Generate cache key from frame and quality"""
        # Use hash of small region for speed
        region = frame[::10, ::10].tobytes()
        key = hashlib.md5(region + str(quality).encode()).hexdigest()[:16]
        return key
    
    def optimize_for_enrollment(self, frame: np.ndarray) -> np.ndarray:
        """
        Optimize frame specifically for enrollment
        Higher quality for better encoding
        """
        # Use higher resolution for enrollment
        optimized = self.optimize_frame(frame, quality='ultra')
        
        # Additional noise reduction
        optimized = cv2.fastNlMeansDenoisingColored(optimized, None, 10, 10, 7, 21)
        
        return optimized
    
    def create_thumbnail(self, frame: np.ndarray, 
                        size: Tuple[int, int] = (150, 150)) -> np.ndarray:
        """Create thumbnail of frame"""
        return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    
    def convert_to_webp(self, frame: np.ndarray, quality: int = 80) -> bytes:
        """
        Convert frame to WebP format (better compression than JPEG)
        Requires Pillow with WebP support
        """
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create PIL Image
            pil_image = Image.fromarray(rgb_frame)
            
            # Save to WebP
            buffer = io.BytesIO()
            pil_image.save(buffer, format='WEBP', quality=quality, method=6)
            
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error converting to WebP: {e}")
            # Fallback to JPEG
            return self.encode_frame(frame, quality='high')
    
    def batch_process_frames(self, frames: list, 
                            quality: str = 'medium') -> list:
        """
        Process multiple frames in batch
        More efficient for bulk operations
        """
        optimized_frames = []
        
        for frame in frames:
            optimized = self.optimize_frame(frame, quality=quality)
            optimized_frames.append(optimized)
        
        return optimized_frames
    
    def clear_cache(self):
        """Clear encoding cache"""
        self._encoding_cache.clear()
        logger.info("Image encoding cache cleared")
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        return {
            'cache_size': len(self._encoding_cache),
            'cache_enabled': self.cache_enabled,
            'current_preset': self.current_preset
        }


class FrameBuffer:
    """
    Circular buffer for video frames
    Reduces memory allocation overhead
    """
    
    def __init__(self, buffer_size: int = 5, frame_shape: Tuple[int, int, int] = (720, 1280, 3)):
        self.buffer_size = buffer_size
        self.frame_shape = frame_shape
        self.buffer = [np.zeros(frame_shape, dtype=np.uint8) for _ in range(buffer_size)]
        self.current_index = 0
        self.lock = np.threading.Lock()
    
    def get_frame(self) -> np.ndarray:
        """Get next available frame buffer"""
        with self.lock:
            frame = self.buffer[self.current_index]
            self.current_index = (self.current_index + 1) % self.buffer_size
            return frame
    
    def copy_frame(self, source: np.ndarray) -> np.ndarray:
        """Copy source frame to buffer"""
        with self.lock:
            target = self.buffer[self.current_index]
            np.copyto(target, source)
            self.current_index = (self.current_index + 1) % self.buffer_size
            return target


class AdaptiveQualityController:
    """
    Automatically adjust image quality based on system load
    """
    
    def __init__(self, optimizer: ImageOptimizer):
        self.optimizer = optimizer
        self.cpu_threshold = 75  # %
        self.memory_threshold = 80  # %
        self.response_time_threshold = 0.5  # seconds
        self.auto_adjust_enabled = True
    
    def adjust_quality(self, cpu_usage: float, 
                      memory_usage: float,
                      avg_response_time: float):
        """Automatically adjust quality based on system metrics"""
        if not self.auto_adjust_enabled:
            return
        
        current_preset = self.optimizer.current_preset
        
        # Determine if we need to lower quality
        if (cpu_usage > self.cpu_threshold or 
            memory_usage > self.memory_threshold or 
            avg_response_time > self.response_time_threshold):
            
            # Downgrade quality
            if current_preset == 'ultra':
                self.optimizer.set_quality_preset('high')
                logger.info("Quality downgraded to 'high' due to system load")
            elif current_preset == 'high':
                self.optimizer.set_quality_preset('medium')
                logger.info("Quality downgraded to 'medium' due to system load")
            elif current_preset == 'medium':
                self.optimizer.set_quality_preset('low')
                logger.info("Quality downgraded to 'low' due to system load")
        
        # Determine if we can increase quality
        elif (cpu_usage < self.cpu_threshold * 0.6 and 
              memory_usage < self.memory_threshold * 0.7 and 
              avg_response_time < self.response_time_threshold * 0.5):
            
            # Upgrade quality
            if current_preset == 'low':
                self.optimizer.set_quality_preset('medium')
                logger.info("Quality upgraded to 'medium'")
            elif current_preset == 'medium':
                self.optimizer.set_quality_preset('high')
                logger.info("Quality upgraded to 'high'")
            elif current_preset == 'high':
                self.optimizer.set_quality_preset('ultra')
                logger.info("Quality upgraded to 'ultra'")


# Global image optimizer instance
image_optimizer = ImageOptimizer()


if __name__ == '__main__':
    # Test image optimizer
    import time
    
    # Create test frame
    test_frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    
    optimizer = ImageOptimizer()
    
    print("Testing image optimization...")
    
    # Test different quality presets
    for preset in ['low', 'medium', 'high', 'ultra']:
        optimizer.set_quality_preset(preset)
        
        start_time = time.time()
        optimized = optimizer.optimize_frame(test_frame)
        encoded = optimizer.encode_frame(optimized)
        duration = time.time() - start_time
        
        print(f"\nPreset: {preset}")
        print(f"  Original size: {test_frame.shape}")
        print(f"  Optimized size: {optimized.shape}")
        print(f"  Encoded size: {len(encoded) / 1024:.1f} KB")
        print(f"  Processing time: {duration*1000:.1f} ms")
    
    # Test caching
    print("\n" + "="*60)
    print("Testing encoding cache...")
    
    start_time = time.time()
    _ = optimizer.encode_frame(test_frame, use_cache=False)
    no_cache_time = time.time() - start_time
    
    start_time = time.time()
    _ = optimizer.encode_frame(test_frame, use_cache=True)
    first_cache_time = time.time() - start_time
    
    start_time = time.time()
    _ = optimizer.encode_frame(test_frame, use_cache=True)
    cached_time = time.time() - start_time
    
    print(f"Without cache: {no_cache_time*1000:.2f} ms")
    print(f"First cache: {first_cache_time*1000:.2f} ms")
    print(f"Cached: {cached_time*1000:.2f} ms")
    print(f"Speedup: {no_cache_time/cached_time:.1f}x")
    
    print("\nImage optimization test completed")
