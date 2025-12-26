"""
NEURAL EYE - Service Layer
Business logic and orchestration layer following clean architecture
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date, timedelta
import logging
import numpy as np
import cv2

from config import Config

logger = logging.getLogger(__name__)


class CacheManager:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.now() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache with TTL"""
        ttl = ttl or self.default_ttl
        expiry = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (value, expiry)
    
    def delete(self, key: str):
        """Delete key from cache"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern"""
        keys_to_delete = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self._cache[key]


# Global cache instance
cache = CacheManager(default_ttl=Config.CACHE_DEFAULT_TIMEOUT)


class ICameraSource(ABC):
    """Interface for camera source (Strategy Pattern)"""
    
    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame from camera"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if camera is available"""
        pass
    
    @abstractmethod
    def release(self):
        """Release camera resources"""
        pass


class RealCamera(ICameraSource):
    """Real camera implementation with timeout-protected initialization"""
    
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.camera: Optional[cv2.VideoCapture] = None
        self._initialize()
    
    def _initialize(self):
        """Initialize camera with multi-backend fallback and timeout protection"""
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
                    cap = cv2.VideoCapture(idx, backend)
                    if not cap.isOpened():
                        continue
                    
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAMERA_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAMERA_HEIGHT)
                    cap.set(cv2.CAP_PROP_FPS, Config.CAMERA_FPS)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # Test read with timeout to prevent hanging
                    test_result = [False]
                    def _test_read(c=cap):
                        try:
                            ret, frame = c.read()
                            test_result[0] = ret and frame is not None and frame.size > 0
                        except Exception:
                            pass
                    
                    t = _threading.Thread(target=_test_read, daemon=True)
                    t.start()
                    t.join(timeout=5)
                    
                    if t.is_alive():
                        logger.warning(f"Camera read timed out index={idx} backend={backend}")
                        # Do NOT call cap.release() - it will also hang
                        continue
                    
                    if test_result[0]:
                        self.camera = cap
                        logger.info(f"RealCamera opened (index={idx}, backend={backend})")
                        return
                    try:
                        cap.release()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"Camera init failed index={idx} backend={backend}: {e}")
        
        logger.warning("No working camera found for RealCamera")
        self.camera = None
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame from real camera"""
        if self.camera is None or not self.camera.isOpened():
            return False, None
        
        return self.camera.read()
    
    def is_available(self) -> bool:
        """Check if camera is available"""
        return self.camera is not None and self.camera.isOpened()
    
    def release(self):
        """Release camera"""
        if self.camera is not None:
            self.camera.release()
            self.camera = None


class MockCamera(ICameraSource):
    """Mock camera for development/testing"""
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Generate mock frame"""
        frame = np.zeros((Config.CAMERA_HEIGHT, Config.CAMERA_WIDTH, 3), dtype=np.uint8)
        
        # Create gradient effect
        for i in range(Config.CAMERA_HEIGHT):
            color_val = int(8 + (i / Config.CAMERA_HEIGHT) * 20)
            frame[i, :] = [color_val, color_val * 2, color_val * 3]
        
        # Add text overlay
        font = cv2.FONT_HERSHEY_SIMPLEX
        text1 = "NEURAL EYE - MOCK CAMERA MODE"
        text2 = "Position your face here for enrollment"
        text3 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cv2.putText(frame, text1, (320, 300), font, 1.2, (0, 242, 255), 2)
        cv2.putText(frame, text2, (380, 360), font, 0.8, (255, 255, 255), 1)
        cv2.putText(frame, text3, (480, 420), font, 0.7, (0, 242, 255), 1)
        
        # Add circle indicator
        center_x = Config.CAMERA_WIDTH // 2
        center_y = Config.CAMERA_HEIGHT // 2
        cv2.circle(frame, (center_x, center_y), 150, (0, 242, 255), 3)
        cv2.circle(frame, (center_x, center_y), 5, (0, 242, 255), -1)
        
        return True, frame
    
    def is_available(self) -> bool:
        """Mock camera is always available"""
        return True
    
    def release(self):
        """Nothing to release for mock camera"""
        pass


class CameraService:
    """Service for managing camera operations"""
    
    def __init__(self, use_mock: bool = None):
        use_mock = use_mock if use_mock is not None else Config.USE_MOCK_CAMERA
        
        if use_mock:
            self.camera: ICameraSource = MockCamera()
            logger.info("Using mock camera")
        else:
            self.camera: ICameraSource = RealCamera(Config.CAMERA_INDEX)
            logger.info("Using real camera")
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame from camera"""
        return self.camera.read_frame()
    
    def is_available(self) -> bool:
        """Check if camera is available"""
        return self.camera.is_available()
    
    def release(self):
        """Release camera resources"""
        self.camera.release()


class FaceEncodingCache:
    """Cache for face encodings with efficient lookup"""
    
    def __init__(self, max_size: int = None):
        self.max_size = max_size or Config.FACE_ENCODING_CACHE_SIZE
        self.encodings: List[np.ndarray] = []
        self.names: List[str] = []
        self.ids: List[int] = []
    
    def add(self, encoding: np.ndarray, name: str, employee_id: int):
        """Add face encoding to cache"""
        if len(self.encodings) >= self.max_size:
            # Remove oldest entry
            self.encodings.pop(0)
            self.names.pop(0)
            self.ids.pop(0)
        
        self.encodings.append(encoding)
        self.names.append(name)
        self.ids.append(employee_id)
    
    def clear(self):
        """Clear cache"""
        self.encodings.clear()
        self.names.clear()
        self.ids.clear()
    
    def size(self) -> int:
        """Get cache size"""
        return len(self.encodings)
    
    def get_all(self) -> Tuple[List[np.ndarray], List[str], List[int]]:
        """Get all cached encodings"""
        return self.encodings, self.names, self.ids


class AttendanceCalculator:
    """Service for attendance status calculations"""
    
    def __init__(self):
        self.work_start = Config.get_work_start_time()
        self.work_end = Config.get_work_end_time()
        self.grace_period = Config.GRACE_PERIOD_MINUTES
    
    def calculate_status(self, clock_in_time: datetime,
                        clock_out_time: Optional[datetime] = None) -> str:
        """Calculate attendance status"""
        if not clock_in_time:
            return "SYNCING"
        
        clock_in_only = clock_in_time.time()
        
        # Calculate late threshold
        grace_end = (
            datetime.combine(date.today(), self.work_start) +
            timedelta(minutes=self.grace_period)
        ).time()
        
        # If clocked out
        if clock_out_time:
            clock_out_only = clock_out_time.time()
            
            # Check undertime
            if clock_out_only < self.work_end:
                return "UNDERTIME"
            
            # Check overtime
            overtime_threshold = (
                datetime.combine(date.today(), self.work_end) +
                timedelta(hours=1)
            ).time()
            
            if clock_out_only > overtime_threshold:
                return "OVERTIME"
            
            return "ON-TIME"
        
        # Still clocked in
        if clock_in_only > grace_end:
            return "LATE"
        
        return "ON-TIME"
    
    def is_late(self, clock_in_time: datetime) -> bool:
        """Check if clock in time is late"""
        grace_end = (
            datetime.combine(date.today(), self.work_start) +
            timedelta(minutes=self.grace_period)
        ).time()
        return clock_in_time.time() > grace_end


class EmployeeService:
    """Service for employee-related business logic"""
    
    def __init__(self, employee_repo, cache_manager: CacheManager):
        self.repo = employee_repo
        self.cache = cache_manager
    
    def get_employee(self, employee_id: int, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get employee with caching"""
        cache_key = f"employee:{employee_id}"
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        employee = self.repo.get_by_id(employee_id)
        
        if employee and use_cache:
            self.cache.set(cache_key, employee)
        
        return employee
    
    def get_all_employees(self, active_only: bool = True, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Get all employees with caching"""
        cache_key = f"employees:all:{active_only}"
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        employees = self.repo.get_all(active_only)
        
        if use_cache:
            self.cache.set(cache_key, employees, ttl=60)  # Cache for 1 minute
        
        return employees
    
    def create_employee(self, **kwargs) -> Tuple[bool, Optional[int], Optional[str]]:
        """Create employee with validation"""
        # Validate required fields
        if not kwargs.get('full_name') or not kwargs.get('employee_id'):
            return False, None, "Full name and employee ID are required"
        
        # Validate email format if provided
        email = kwargs.get('email')
        if email and '@' not in email:
            return False, None, "Invalid email format"
        
        # Create employee
        employee_id = self.repo.create(**kwargs)
        
        if employee_id:
            # Invalidate cache
            self.cache.invalidate_pattern('employees:')
            return True, employee_id, None
        
        return False, None, "Failed to create employee (may already exist)"
    
    def update_employee(self, employee_id: int, **kwargs) -> Tuple[bool, Optional[str]]:
        """Update employee with cache invalidation"""
        success = self.repo.update(employee_id, **kwargs)
        
        if success:
            # Invalidate cache
            self.cache.delete(f"employee:{employee_id}")
            self.cache.invalidate_pattern('employees:')
        
        return success, None if success else "Update failed"
    
    def deactivate_employee(self, employee_id: int) -> bool:
        """Deactivate employee"""
        success = self.repo.deactivate(employee_id)
        
        if success:
            # Invalidate cache
            self.cache.delete(f"employee:{employee_id}")
            self.cache.invalidate_pattern('employees:')
        
        return success


class AttendanceService:
    """Service for attendance-related business logic"""
    
    def __init__(self, attendance_repo, calculator: AttendanceCalculator):
        self.repo = attendance_repo
        self.calculator = calculator
        self.last_recognition: Dict[int, datetime] = {}
        self.cooldown_period = timedelta(seconds=Config.RECOGNITION_COOLDOWN_SECONDS)
    
    def record_clock_in(self, employee_id: int, timestamp: datetime = None) -> Tuple[bool, str, Optional[str]]:
        """Record clock in with validation"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # Check if already clocked in today
        existing_log = self.repo.get_today_log(employee_id)
        if existing_log:
            return False, "ALREADY_CLOCKED_IN", "Employee already clocked in today"
        
        # Calculate status
        status = self.calculator.calculate_status(timestamp)
        
        # Record clock in
        log_id = self.repo.clock_in(employee_id, status, timestamp)
        
        if log_id:
            return True, status, None
        
        return False, "ERROR", "Failed to record clock in"
    
    def record_clock_out(self, employee_id: int, timestamp: datetime = None) -> Tuple[bool, str, Optional[str]]:
        """Record clock out with validation"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # Check if clocked in
        existing_log = self.repo.get_today_log(employee_id)
        if not existing_log:
            return False, "NOT_CLOCKED_IN", "Employee not clocked in today"
        
        if existing_log.get('clock_out'):
            return False, "ALREADY_CLOCKED_OUT", "Employee already clocked out"
        
        # Calculate status
        clock_in_time = datetime.fromisoformat(existing_log['clock_in']) if isinstance(
            existing_log['clock_in'], str
        ) else existing_log['clock_in']
        
        status = self.calculator.calculate_status(clock_in_time, timestamp)
        
        # Record clock out
        success = self.repo.clock_out(employee_id, status, timestamp)
        
        if success:
            return True, status, None
        
        return False, "ERROR", "Failed to record clock out"
    
    def can_record_attendance(self, employee_id: int) -> bool:
        """Check if attendance can be recorded (cooldown check)"""
        if employee_id not in self.last_recognition:
            return True
        
        last_seen = self.last_recognition[employee_id]
        return datetime.now() - last_seen >= self.cooldown_period
    
    def mark_recognized(self, employee_id: int):
        """Mark employee as recognized (for cooldown)"""
        self.last_recognition[employee_id] = datetime.now()
    
    def get_today_summary(self) -> Dict[str, Any]:
        """Get today's attendance summary"""
        today = date.today()
        all_attendance = self.repo.get_by_date(today)
        
        present = len(all_attendance)
        on_time = len([a for a in all_attendance if a.get('status') == 'ON-TIME'])
        late_records = [a for a in all_attendance if a.get('status') == 'LATE']
        late_count = len(late_records)
        
        return {
            'present': present,
            'on_time': on_time,
            'late_count': late_count,
            'late': late_records
        }


class ValidationService:
    """Service for input validation and sanitization"""
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        """Sanitize string input"""
        if not value:
            return ""
        
        # Remove special characters that could cause issues
        sanitized = value.strip()[:max_length]
        return sanitized
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        if not email:
            return False
        
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number"""
        if not phone:
            return False
        
        # Remove common formatting
        cleaned = phone.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
        return cleaned.isdigit() and 10 <= len(cleaned) <= 15
    
    @staticmethod
    def validate_date(date_str: str) -> Tuple[bool, Optional[date]]:
        """Validate and parse date string"""
        if not date_str:
            return False, None
        
        try:
            parsed_date = date.fromisoformat(date_str)
            return True, parsed_date
        except ValueError:
            return False, None
