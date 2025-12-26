"""
Hardware Abstraction Layer (HAL) - Camera Interface
Provides abstract interface for different camera types
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Tuple
import numpy as np
import cv2
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CameraInterface(ABC):
    """Abstract base class for camera devices"""
    
    @abstractmethod
    def open(self) -> bool:
        """Open camera device"""
        pass
    
    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from camera
        
        Returns:
            Tuple of (success, frame) where frame is numpy array in BGR format
        """
        pass
    
    @abstractmethod
    def close(self) -> bool:
        """Close camera device"""
        pass
    
    @abstractmethod
    def is_opened(self) -> bool:
        """Check if camera is opened"""
        pass
    
    @abstractmethod
    def get_properties(self) -> Dict:
        """Get camera properties"""
        pass
    
    @abstractmethod
    def set_property(self, prop: str, value: any) -> bool:
        """Set camera property"""
        pass


class USBCamera(CameraInterface):
    """USB/Webcam implementation with timeout-protected initialization"""
    
    def __init__(self, camera_index: int = 0, width: int = 1280, height: int = 720, fps: int = 30):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.capture = None
        
    def open(self) -> bool:
        """Open USB camera with multi-backend fallback and timeout protection"""
        import sys
        import threading as _threading
        
        indices = [self.camera_index] + [i for i in range(3) if i != self.camera_index]
        if sys.platform.startswith('win'):
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        else:
            backends = [cv2.CAP_ANY]
        
        for idx in indices:
            for backend in backends:
                try:
                    self.capture = cv2.VideoCapture(idx, backend)
                    if not self.capture.isOpened():
                        self.capture = None
                        continue
                    
                    self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self.capture.set(cv2.CAP_PROP_FPS, self.fps)
                    self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # Test read with timeout to prevent hanging
                    test_result = [False]
                    def _test_read(c=self.capture):
                        try:
                            ret, frame = c.read()
                            test_result[0] = ret and frame is not None and frame.size > 0
                        except Exception:
                            pass
                    
                    t = _threading.Thread(target=_test_read, daemon=True)
                    t.start()
                    t.join(timeout=5)
                    
                    if t.is_alive():
                        logger.warning(f"USB Camera read timed out index={idx} backend={backend}")
                        # Do NOT call capture.release() - it will also hang
                        self.capture = None
                        continue
                    
                    if test_result[0]:
                        logger.info(f"USB Camera opened: index={idx}, backend={backend} ({self.width}x{self.height} @ {self.fps}fps)")
                        return True
                    try:
                        self.capture.release()
                    except Exception:
                        pass
                    self.capture = None
                except Exception as e:
                    logger.warning(f"USB Camera open failed index={idx} backend={backend}: {e}")
                    self.capture = None
        
        logger.error("Failed to open USB camera on any index or backend")
        return False
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame from USB camera"""
        if self.capture is None or not self.capture.isOpened():
            return False, None
        
        ret, frame = self.capture.read()
        return ret, frame
    
    def close(self) -> bool:
        """Close USB camera"""
        if self.capture:
            self.capture.release()
            self.capture = None
            logger.info("USB Camera closed")
            return True
        return False
    
    def is_opened(self) -> bool:
        """Check if camera is opened"""
        return self.capture is not None and self.capture.isOpened()
    
    def get_properties(self) -> Dict:
        """Get camera properties"""
        if not self.is_opened():
            return {}
        
        return {
            'width': int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': int(self.capture.get(cv2.CAP_PROP_FPS)),
            'brightness': self.capture.get(cv2.CAP_PROP_BRIGHTNESS),
            'contrast': self.capture.get(cv2.CAP_PROP_CONTRAST),
            'saturation': self.capture.get(cv2.CAP_PROP_SATURATION),
            'hue': self.capture.get(cv2.CAP_PROP_HUE),
        }
    
    def set_property(self, prop: str, value: any) -> bool:
        """Set camera property"""
        if not self.is_opened():
            return False
        
        prop_map = {
            'width': cv2.CAP_PROP_FRAME_WIDTH,
            'height': cv2.CAP_PROP_FRAME_HEIGHT,
            'fps': cv2.CAP_PROP_FPS,
            'brightness': cv2.CAP_PROP_BRIGHTNESS,
            'contrast': cv2.CAP_PROP_CONTRAST,
            'saturation': cv2.CAP_PROP_SATURATION,
            'hue': cv2.CAP_PROP_HUE,
            'auto_exposure': cv2.CAP_PROP_AUTO_EXPOSURE,
            'auto_wb': cv2.CAP_PROP_AUTO_WB,
        }
        
        if prop not in prop_map:
            logger.warning(f"Unknown property: {prop}")
            return False
        
        return self.capture.set(prop_map[prop], value)


class CSICamera(CameraInterface):
    """MIPI CSI camera implementation (Raspberry Pi Camera)"""
    
    def __init__(self, camera_id: int = 0, width: int = 1280, height: int = 720, fps: int = 30):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.capture = None
        
    def open(self) -> bool:
        """Open CSI camera using GStreamer pipeline"""
        try:
            # GStreamer pipeline for Raspberry Pi Camera
            gst_pipeline = (
                f'nvarguscamerasrc sensor-id={self.camera_id} ! '
                f'video/x-raw(memory:NVMM), width={self.width}, height={self.height}, '
                f'framerate={self.fps}/1 ! nvvidconv flip-method=0 ! '
                f'video/x-raw, width={self.width}, height={self.height}, format=BGRx ! '
                f'videoconvert ! video/x-raw, format=BGR ! appsink'
            )
            
            self.capture = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
            
            if not self.capture.isOpened():
                logger.error(f"Failed to open CSI camera {self.camera_id}")
                return False
            
            logger.info(f"CSI Camera opened: {self.camera_id} ({self.width}x{self.height} @ {self.fps}fps)")
            return True
        except Exception as e:
            logger.error(f"Error opening CSI camera: {e}")
            return False
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame from CSI camera"""
        if self.capture is None or not self.capture.isOpened():
            return False, None
        
        ret, frame = self.capture.read()
        return ret, frame
    
    def close(self) -> bool:
        """Close CSI camera"""
        if self.capture:
            self.capture.release()
            self.capture = None
            logger.info("CSI Camera closed")
            return True
        return False
    
    def is_opened(self) -> bool:
        """Check if camera is opened"""
        return self.capture is not None and self.capture.isOpened()
    
    def get_properties(self) -> Dict:
        """Get camera properties"""
        return {
            'width': self.width,
            'height': self.height,
            'fps': self.fps,
            'type': 'CSI'
        }
    
    def set_property(self, prop: str, value: any) -> bool:
        """Set camera property (limited support for CSI)"""
        logger.warning("CSI camera property setting not fully supported")
        return False


class MockCamera(CameraInterface):
    """Mock camera for testing (loads static image)"""
    
    def __init__(self, image_path: str = 'frontend/static/mock_camera.jpg'):
        self.image_path = image_path
        self.frame = None
        self._is_opened = False
        
    def open(self) -> bool:
        """Load mock image"""
        try:
            if not Path(self.image_path).exists():
                logger.warning(f"Mock image not found: {self.image_path}, creating blank frame")
                self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
            else:
                self.frame = cv2.imread(self.image_path)
                if self.frame is None:
                    logger.error(f"Failed to load mock image: {self.image_path}")
                    return False
            
            self._is_opened = True
            logger.info(f"Mock camera opened with image: {self.image_path}")
            return True
        except Exception as e:
            logger.error(f"Error opening mock camera: {e}")
            return False
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Return static mock frame"""
        if not self._is_opened or self.frame is None:
            return False, None
        
        # Return a copy to simulate real camera
        return True, self.frame.copy()
    
    def close(self) -> bool:
        """Close mock camera"""
        self._is_opened = False
        self.frame = None
        logger.info("Mock camera closed")
        return True
    
    def is_opened(self) -> bool:
        """Check if mock camera is opened"""
        return self._is_opened
    
    def get_properties(self) -> Dict:
        """Get mock camera properties"""
        if self.frame is not None:
            h, w = self.frame.shape[:2]
            return {
                'width': w,
                'height': h,
                'fps': 30,
                'type': 'Mock'
            }
        return {}
    
    def set_property(self, prop: str, value: any) -> bool:
        """Mock camera has no settable properties"""
        return False


class CameraFactory:
    """Factory for creating camera instances"""
    
    @staticmethod
    def create_camera(camera_type: str, **kwargs) -> CameraInterface:
        """Create camera instance based on type
        
        Args:
            camera_type: 'usb', 'csi', or 'mock'
            **kwargs: Camera-specific parameters
            
        Returns:
            CameraInterface implementation
        """
        camera_type = camera_type.lower()
        
        if camera_type == 'usb':
            return USBCamera(
                camera_index=kwargs.get('camera_index', 0),
                width=kwargs.get('width', 1280),
                height=kwargs.get('height', 720),
                fps=kwargs.get('fps', 30)
            )
        elif camera_type == 'csi':
            return CSICamera(
                camera_id=kwargs.get('camera_id', 0),
                width=kwargs.get('width', 1280),
                height=kwargs.get('height', 720),
                fps=kwargs.get('fps', 30)
            )
        elif camera_type == 'mock':
            return MockCamera(
                image_path=kwargs.get('image_path', 'frontend/static/mock_camera.jpg')
            )
        else:
            raise ValueError(f"Unknown camera type: {camera_type}")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create mock camera for testing
    camera = CameraFactory.create_camera('mock')
    
    if camera.open():
        ret, frame = camera.read_frame()
        if ret:
            print(f"Frame shape: {frame.shape}")
            print(f"Properties: {camera.get_properties()}")
        camera.close()
