"""
NEURAL EYE - Facial Recognition Attendance System
Main Flask Application Server
"""

from flask import Flask, Response, jsonify, render_template, request, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import cv2
import sys
import threading
import logging
from datetime import datetime, date, timedelta
import os
from pathlib import Path
import base64
import numpy as np
import time

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import Database
from face_recognition_module import FaceRecognitionSystem
from auth import verify_password, login_required, api_login_required, role_required
from notifications import get_notification_system

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
            template_folder='frontend',
            static_folder='frontend/static')
# Enable CORS for all origins so localhost and 192.168.x.x work the same
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Initialize SocketIO for WebSocket support
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

# Secret key for sessions
app.secret_key = os.environ.get('SECRET_KEY', 'neural-eye-secret-key-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Configuration
USE_MOCK_CAMERA = os.environ.get('USE_MOCK_CAMERA', 'false').lower() in ('1', 'true', 'yes')
runtime_use_mock = USE_MOCK_CAMERA
MOCK_IMAGE_PATH = 'frontend/static/mock_camera.jpg'

# Initialize systems
db = Database()
notifications = get_notification_system()
face_system = FaceRecognitionSystem(db, notifications)

# Global camera lock
camera_lock = threading.Lock()
camera = None
selected_camera_index = None  # User-selected camera index (None = auto-detect)

# Frame cache for enrollment endpoint (avoids redundant processing)
_frame_cache = {'frame': None, 'timestamp': 0, 'jpeg': None}

# Shared latest frame from generate_frames (avoids dual-reader crash)
_latest_frame = {'frame': None, 'lock': threading.Lock()}
_frame_cache_lock = threading.Lock()

# Camera name database for common devices
_CAMERA_NAMES = {
    'droidcam': 'DroidCam',
    'irif': 'IRIF Camera',
    'hd camera': 'HD Webcam',
    'webcam': 'Webcam',
    'usb video': 'USB Camera',
    'usb2.0': 'USB Camera',
    'virtual': 'Virtual Camera',
    'obs': 'OBS Virtual Camera',
    'snap camera': 'Snap Camera',
    'meet': 'Google Meet Camera',
    'teams': 'Teams Camera',
}


def _identify_camera(index, backend):
    """Try to open a camera and return its name, capabilities, and type."""
    try:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            return None

        # Quick test read
        test_ok = [False]
        def _try():
            ret, frame = cap.read()
            test_ok[0] = ret and frame is not None and frame.size > 0
        t = threading.Thread(target=_try, daemon=True)
        t.start()
        t.join(timeout=2.0)

        if not test_ok[0]:
            cap.release()
            return None

        # Read properties
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # Try to get camera name via DirectShow (Windows)
        name = None
        if sys.platform.startswith('win') and backend == cv2.CAP_DSHOW:
            try:
                name_prop = cap.getBackendName() if hasattr(cap, 'getBackendName') else None
            except Exception:
                name_prop = None

        # Fallback name from index
        if not name:
            name = f"Camera {index}"

        cap.release()

        # Detect if virtual camera
        is_virtual = _is_virtual_camera(name, index, width, height)

        return {
            'index': index,
            'backend': int(backend),
            'backend_name': _backend_name(backend),
            'name': name,
            'width': width,
            'height': height,
            'fps': round(fps, 1) if fps > 0 else 0,
            'is_virtual': is_virtual,
        }
    except Exception as e:
        return None


# Known virtual camera names (lowercase matching)
VIRTUAL_CAMERA_KEYWORDS = [
    'droidcam', 'obs virtual', 'snap camera', 'manycam', 'xsplit',
    'eviacam', 'webcamoid', 'vdo.ninja', 'roidcam', 'ivcam',
    'epoccam', 'iriun', 'camo', 'newline', 'ndi',
]


def _is_virtual_camera(name, index, width, height):
    """Heuristic to detect if a camera is virtual based on name and properties."""
    name_lower = name.lower()
    # Check name against known virtual camera keywords
    for keyword in VIRTUAL_CAMERA_KEYWORDS:
        if keyword in name_lower:
            return True
    # Virtual cameras often have unusual resolutions or very low FPS
    return False


def _backend_name(backend):
    names = {cv2.CAP_DSHOW: 'DirectShow', cv2.CAP_MSMF: 'Media Foundation', cv2.CAP_ANY: 'Any'}
    return names.get(backend, str(backend))


def scan_cameras():
    """Scan cameras. Fast path: try index 0 first, then scan remaining."""
    cameras = []
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if sys.platform.startswith('win') else [cv2.CAP_ANY]
    seen = set()

    # Fast path: try index 0 first (most common for webcams)
    for backend in backends:
        info = _identify_camera(0, backend)
        if info:
            cameras.append(info)
            seen.add((0, backend))
            break

    # Then scan remaining indices
    for idx in range(1, 6):
        for backend in backends:
            key = (idx, backend)
            if key in seen:
                continue
            seen.add(key)
            info = _identify_camera(idx, backend)
            if info:
                res_key = (idx, info['width'], info['height'])
                already = any(c['index'] == idx and c['width'] == info['width'] and c['height'] == info['height'] for c in cameras)
                if not already:
                    cameras.append(info)
                break

    # Sort: physical first, then virtual
    cameras.sort(key=lambda c: (c['is_virtual'], c['index']))
    return cameras

# Camera configuration
CAMERA_OPEN_TIMEOUT = 5   # seconds to wait for camera to open
CAMERA_READ_TIMEOUT = 3   # seconds to wait for a frame read
CAMERA_RETRY_DELAY = 2    # seconds between retry attempts
CAMERA_MAX_RETRIES = 5    # max retries before giving up


class CameraReader:
    """Thread-safe camera reader with bufferless reading for network streams.
    
    On Windows, cv2.VideoCapture.read() can hang indefinitely if the camera
    is busy, locked by another app, or has driver issues. This class runs
    the read in a background thread and always keeps only the LATEST frame,
    discarding old ones. This eliminates buffering delay for DroidCam/RTSP.
    """
    
    def __init__(self, capture, read_timeout=CAMERA_READ_TIMEOUT):
        self._capture = capture
        self._read_timeout = read_timeout
        self._frame = None
        self._frame_ready = threading.Event()
        self._running = False
        self._thread = None
        self._error = None
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()
    
    def start(self):
        """Start the background reader thread"""
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()
    
    def _reader_loop(self):
        """Background thread that continuously reads frames, keeping only latest."""
        while self._running:
            try:
                with self._capture_lock:
                    if self._capture is None or not self._capture.isOpened():
                        self._error = "Camera closed"
                        break
                    ret, frame = self._capture.read()
                if ret and frame is not None and frame.size > 0:
                    with self._lock:
                        self._frame = frame
                    self._error = None
                    self._frame_ready.set()
                else:
                    self._error = "Failed to read frame"
            except Exception as e:
                self._error = str(e)
    
    def read(self):
        """Read the latest frame (non-blocking, always newest)."""
        self._frame_ready.clear()
        if self._frame_ready.wait(timeout=self._read_timeout):
            with self._lock:
                if self._frame is not None:
                    return True, self._frame.copy()
        return False, None
    
    @property
    def is_alive(self):
        """Check if the reader thread is running and healthy"""
        return (self._running and 
                self._thread is not None and 
                self._thread.is_alive() and 
                self._error is None)
    
    def stop(self):
        """Stop the background reader thread"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
    
    def release(self):
        """Stop reader and release camera."""
        self.stop()
        with self._capture_lock:
            self._capture = None


def _open_camera_with_timeout(index, backend):
    """Try to open a camera with timeout protection.
    
    On Windows, cv2.VideoCapture.read() can hang indefinitely if the camera
    is busy, locked by another app, or has driver issues. We run the test
    read in a daemon thread with a timeout. If it hangs, we abandon the
    camera (don't try to release it) and move to the next option.
    
    Returns:
        CameraReader if successful, None otherwise.
    """
    try:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            return None
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Test read with timeout - this is the critical fix for Windows
        test_result = [None, False]
        
        def _test_read():
            try:
                ret, frame = cap.read()
                test_result[0] = ret
                test_result[1] = ret and frame is not None and frame.size > 0
            except Exception:
                test_result[1] = False
        
        test_thread = threading.Thread(target=_test_read, daemon=True)
        test_thread.start()
        test_thread.join(timeout=CAMERA_OPEN_TIMEOUT)
        
        if test_thread.is_alive():
            # Thread still running = read is hanging.
            # CRITICAL: Do NOT call cap.release() here - it will also hang
            # on Windows. Just abandon this cap and let GC handle it.
            logger.warning(
                f"Camera read timed out on index={index} backend={backend} "
                f"(camera may be busy or locked by another application)"
            )
            return None
        
        if not test_result[1]:
            # Test read failed cleanly - safe to release
            try:
                cap.release()
            except Exception:
                pass
            return None
        
        # Camera works - create threaded reader
        reader = CameraReader(cap)
        reader.start()
        
        # Verify reader is getting frames
        import time
        time.sleep(0.3)
        if not reader.is_alive:
            reader.release()
            return None
        
        logger.info(f"Camera opened (index={index}, backend={backend})")
        return reader
        
    except Exception as e:
        logger.warning(f"Camera open failed index={index} backend={backend}: {e}")
        return None


def get_mock_frame():
    """Generate a mock camera frame"""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    for i in range(720):
        color_val = int(8 + (i / 720) * 20)
        frame[i, :] = [color_val, color_val * 2, color_val * 3]
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    text1 = "NEURAL EYE - MOCK CAMERA MODE"
    text2 = "Position your face here for enrollment"
    text3 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cv2.putText(frame, text1, (320, 300), font, 1.2, (0, 242, 255), 2)
    cv2.putText(frame, text2, (380, 360), font, 0.8, (255, 255, 255), 1)
    cv2.putText(frame, text3, (480, 420), font, 0.7, (0, 242, 255), 1)
    
    cv2.circle(frame, (640, 360), 150, (0, 242, 255), 3)
    cv2.circle(frame, (640, 360), 5, (0, 242, 255), -1)
    
    return frame


def get_camera():
    """Get camera - tries index 0 first (most common), then falls back to scan."""
    global camera, selected_camera_index
    
    if USE_MOCK_CAMERA:
        return None
    
    with camera_lock:
        if camera is not None:
            if isinstance(camera, CameraReader):
                if camera.is_alive:
                    return camera
                camera.release()
                camera = None
            elif hasattr(camera, 'isOpened'):
                try:
                    if camera.isOpened():
                        camera.release()
                except Exception:
                    pass
                camera = None
        
        # If user selected a specific camera, try that
        if selected_camera_index is not None:
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if sys.platform.startswith('win') else [cv2.CAP_ANY]
            for backend in backends:
                reader = _open_camera_with_timeout(selected_camera_index, backend)
                if reader is not None:
                    camera = reader
                    return camera
        
        # Fast path: try index 0 (where most webcams are)
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if sys.platform.startswith('win') else [cv2.CAP_ANY]
        for backend in backends:
            reader = _open_camera_with_timeout(0, backend)
            if reader is not None:
                camera = reader
                return camera
        
        # Slow path: scan all
        scanned = scan_cameras()
        for cam in scanned:
            reader = _open_camera_with_timeout(cam['index'], cam['backend'])
            if reader is not None:
                camera = reader
                return camera
        
        logger.warning("No camera found. Connect a webcam.")
        return None


def generate_frames(mode='live'):
    """Generate video frames for MJPEG stream.
    
    mode='live': Draw face detection boxes (for Live Dashboard)
    mode='enroll': Raw frames, no boxes (for Enrollment page)
    """
    global runtime_use_mock, camera
    
    while True:
        try:
            if USE_MOCK_CAMERA:
                runtime_use_mock = True
                frame = get_mock_frame()
            else:
                cam = get_camera()
                if cam is None:
                    runtime_use_mock = True
                    frame = get_mock_frame()
                else:
                    try:
                        success, frame = cam.read()
                    except Exception:
                        success = False
                    if not success:
                        runtime_use_mock = True
                        frame = get_mock_frame()
                    else:
                        runtime_use_mock = False
            
            # Cache the latest frame for face-status endpoint (avoids dual-reader crash)
            if not runtime_use_mock and frame is not None:
                with _latest_frame['lock']:
                    _latest_frame['frame'] = frame.copy()
            
            # Only draw boxes in live mode (not enrollment)
            if not runtime_use_mock and frame is not None and mode == 'live':
                frame = face_system.process_frame(frame, skip_overlay=False)
            
            ret, buffer = cv2.imencode('.jpg', frame, 
                                      [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        except Exception as e:
            logger.error(f"Error in frame generation: {e}")
            time.sleep(0.01)



@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')


@app.route('/enroll')
def enroll_page():
    """Serve the enrollment page"""
    return render_template('enroll.html')


@app.route('/video_feed')
def video_feed():
    """Video streaming route. mode=live draws boxes, mode=enroll returns raw frames."""
    mode = request.args.get('mode', 'live')
    return Response(
        generate_frames(mode=mode),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get recent attendance logs"""
    try:
        limit = request.args.get('limit', default=10, type=int)
        logs = db.get_recent_logs(limit)
        return jsonify(logs)
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/attendance/today', methods=['GET'])
def get_todays_attendance():
    """Get today's attendance summary with late arrivals and absences"""
    try:
        from datetime import date
        today = date.today()
        
        # Get all attendance records for today
        try:
            all_attendance = db.get_attendance_by_date(today)
        except Exception as e:
            logger.error(f"Error fetching attendance by date: {e}")
            all_attendance = []
        
        # Calculate statistics
        present = len(all_attendance)
        on_time = len([a for a in all_attendance if a.get('status') == 'ON-TIME'])
        late_records = [a for a in all_attendance if a.get('status') == 'LATE']
        late_count = len(late_records)
        
        # Get all active employees
        try:
            all_employees = db.get_employees_detailed(active_only=True)
        except Exception as e:
            logger.error(f"Error fetching detailed employees: {e}")
            # Fallback to basic employee list
            try:
                all_employees = db.get_all_employees()
            except Exception as e2:
                logger.error(f"Error fetching employees fallback: {e2}")
                all_employees = []
        
        active_employees = [e for e in all_employees if e.get('active', True)]
        
        # Find absent employees (active but no attendance today)
        attended_employee_ids = set(a.get('employee_id') for a in all_attendance)
        absent_employees = [
            {
                'id': e['id'],
                'full_name': e['full_name'],
                'department': e.get('department_name') or e.get('department', 'N/A'),
                'position': e.get('position_title') or e.get('position', 'N/A')
            }
            for e in active_employees
            if e['id'] not in attended_employee_ids
        ]
        
        return jsonify({
            'present': present,
            'on_time': on_time,
            'late_count': late_count,
            'absent_count': len(absent_employees),
            'late': late_records,
            'absent': absent_employees
        })
        
    except Exception as e:
        logger.error(f"Error fetching today's attendance: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees', methods=['GET'])
def get_employees():
    """Get all registered employees"""
    try:
        employees = db.get_all_employees()
        for emp in employees:
            emp.pop('face_encoding', None)
            emp.pop('face_encoding_front', None)
            emp.pop('face_encoding_left', None)
            emp.pop('face_encoding_right', None)
        return jsonify(employees)
    except Exception as e:
        logger.error(f"Error fetching employees: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    try:
        stats = {
            'total_employees': db.get_employee_count(),
            'today_attendance': db.get_today_attendance_count(),
            'active_now': face_system.get_active_count()
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/force_clockout/<int:employee_id>', methods=['POST'])
def force_clockout(employee_id):
    """Manually clock out an employee"""
    try:
        success = db.clock_out_employee(employee_id)
        if success:
            return jsonify({'success': True, 'message': 'Employee clocked out'})
        else:
            return jsonify({'success': False, 'message': 'Failed to clock out'}), 400
    except Exception as e:
        logger.error(f"Error forcing clock out: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for frontend to verify backend is alive"""
    # Determine actual camera mode based on runtime state
    actual_camera_mode = 'mock'
    if not USE_MOCK_CAMERA and not runtime_use_mock:
        # Only report 'real' if we actually have a working camera
        with camera_lock:
            if camera is not None and isinstance(camera, CameraReader) and camera.is_alive:
                actual_camera_mode = 'real'
            elif camera is not None and hasattr(camera, 'isOpened') and camera.isOpened():
                actual_camera_mode = 'real'
    
    return jsonify({
        'status': 'ok',
        'camera_mode': actual_camera_mode,
        'config_camera_mode': 'mock' if USE_MOCK_CAMERA else 'real',
        'runtime_camera_mode': 'mock' if runtime_use_mock else 'real',
        'camera_available': camera is not None,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/admin/reset-database', methods=['POST'])
@api_login_required
@role_required('admin')
def reset_database():
    """Reset database - clears all employee and attendance data (admin only)"""
    try:
        # Clear all data tables but keep default departments/positions/shifts
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM attendance_logs')
            cursor.execute('DELETE FROM leave_requests')
            cursor.execute('DELETE FROM audit_logs')
            cursor.execute('DELETE FROM employees')
            cursor.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('attendance_logs', 'leave_requests', 'audit_logs', 'employees')"
            )
            conn.commit()
        
        # Reload face encodings
        face_system.load_known_faces()
        
        msg = 'Database reset successfully. All employee and attendance data cleared.'
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/employee/generate-id', methods=['GET'])
def generate_employee_id():
    """Auto-generate next employee ID in format EMP-XXXX"""
    emp_id = db.generate_employee_id()
    return jsonify({'employee_id': emp_id})


@app.route('/api/camera/status', methods=['GET'])
def camera_status():
    """Check camera status for debugging"""
    status = {
        'use_mock_camera': USE_MOCK_CAMERA,
        'runtime_use_mock': runtime_use_mock,
        'camera_object_exists': camera is not None,
        'camera_is_opened': False,
        'camera_type': type(camera).__name__ if camera else None,
        'selected_camera_index': selected_camera_index,
    }
    
    if camera is not None:
        if isinstance(camera, CameraReader):
            status['camera_is_opened'] = camera.is_alive
            status['camera_error'] = camera._error
        elif hasattr(camera, 'isOpened'):
            status['camera_is_opened'] = camera.isOpened()
    
    return jsonify(status)


@app.route('/api/camera/scan', methods=['GET'])
def camera_scan():
    """Scan and list all available cameras on the system."""
    cameras = scan_cameras()
    return jsonify({
        'success': True,
        'cameras': cameras,
        'count': len(cameras),
        'selected_index': selected_camera_index,
    })


@app.route('/api/camera/select', methods=['POST'])
def camera_select():
    """Select a specific camera by index, or set to null for auto-detect."""
    global selected_camera_index, camera
    data = request.json or {}
    index = data.get('index')  # null = auto-detect

    if index is not None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid camera index'}), 400

    # Release current camera
    with camera_lock:
        if camera is not None:
            if isinstance(camera, CameraReader):
                camera.release()
            elif hasattr(camera, 'release'):
                camera.release()
            camera = None

    selected_camera_index = index
    logger.info(f"Camera selected: {'auto-detect' if index is None else f'index {index}'}")

    # Try to open the new camera
    cam = get_camera()
    if cam is not None:
        return jsonify({'success': True, 'message': f'Camera {index} activated' if index is not None else 'Auto-detect camera activated'})
    else:
        return jsonify({'success': False, 'message': 'Selected camera not available'})


@app.route('/api/camera/test', methods=['GET'])
def camera_test():
    """Test camera capture - returns a single frame"""
    if USE_MOCK_CAMERA:
        frame = get_mock_frame()
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(buffer.tobytes(), mimetype='image/jpeg')
    
    cam = get_camera()
    if cam is None:
        return jsonify({'error': 'Camera not available. Check camera connection.'}), 500
    
    ret, frame = cam.read()
    if not ret:
        return jsonify({'error': 'Failed to capture frame. Camera may be busy.'}), 500
    
    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(buffer.tobytes(), mimetype='image/jpeg')


@app.route('/api/camera/frame', methods=['GET'])
def camera_frame():
    """Get a single processed frame from the server camera.
    
    Query params:
        angle: 'front', 'left', 'right' - for multi-angle capture guidance
        raw: '1' - return raw frame without face boxes or overlay
    
    Returns a JPEG image.
    """
    import time as _time
    now = _time.time()

    angle = request.args.get('angle', 'front')
    raw = request.args.get('raw', '0') == '1'
    
    # Return cached frame if fresh (< 2s old)
    with _frame_cache_lock:
        if _frame_cache['jpeg'] and (now - _frame_cache['timestamp']) < 2.0:
            return Response(_frame_cache['jpeg'], mimetype='image/jpeg')
    
    if USE_MOCK_CAMERA:
        frame = get_mock_frame()
    else:
        cam = get_camera()
        if cam is None:
            return jsonify({'error': 'Camera not available'}), 503
        
        ret, frame = cam.read()
        if not ret:
            return jsonify({'error': 'Failed to capture frame'}), 500
    
    if raw:
        processed_frame = frame
    else:
        processed_frame = face_system.process_frame(frame, skip_overlay=True)
    
    ret, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ret:
        return jsonify({'error': 'Failed to encode frame'}), 500
    
    jpeg_bytes = buffer.tobytes()
    
    # Cache the result
    with _frame_cache_lock:
        _frame_cache['jpeg'] = jpeg_bytes
        _frame_cache['timestamp'] = now
    
    return Response(jpeg_bytes, mimetype='image/jpeg')


@app.route('/api/camera/face-status', methods=['GET'])
def camera_face_status():
    """Lightweight face detection for real-time overlay. Uses cached frame from MJPEG stream."""
    try:
        # Use cached frame from generate_frames (avoids dual-reader crash on Windows)
        with _latest_frame['lock']:
            frame = _latest_frame['frame']
        
        if frame is None:
            return jsonify({"face_count": 0, "faces": []})

        # Fast: YOLO detection only (~3ms on GPU)
        face_boxes = face_system._detect_faces(frame)
        faces = []

        for box in face_boxes:
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            area = (x2 - x1) * (y2 - y1)
            entry = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "area": area}
            faces.append(entry)

        # Only return largest face
        if faces:
            faces.sort(key=lambda f: f["area"], reverse=True)
            faces = [faces[0]]

        return jsonify({
            "face_count": len(faces),
            "faces": faces
        })
    except Exception as e:
        logger.error(f"[FaceStatus] Error: {type(e).__name__}: {e}")
        return jsonify({"face_count": 0, "faces": []})


@app.route('/api/camera/process-frame', methods=['POST'])
def process_browser_frame():
    """Process a frame captured from the browser's camera.
    
    Accepts a base64-encoded JPEG frame from the browser,
    runs face recognition on it, and returns the annotated frame.
    
    Request body: { "frame": "data:image/jpeg;base64,..." }
    Response: { "frame": "data:image/jpeg;base64,...", "faces": [...], "recognized": [...] }
    """
    try:
        data = request.get_json()
        if not data or 'frame' not in data:
            return jsonify({'error': 'No frame provided'}), 400
        
        frame_data = data['frame']
        
        # Strip data URL prefix if present
        if ',' in frame_data:
            frame_data = frame_data.split(',', 1)[1]
        
        # Decode base64 to image
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({'error': 'Failed to decode frame'}), 400
        
        # Process with face recognition
        processed_frame = face_system.process_frame(frame)
        
        # Encode result back to base64 JPEG
        ret, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            return jsonify({'error': 'Failed to encode frame'}), 500
        
        result_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        
        # Get face info
        recognized = []
        for name in face_system.last_face_names:
            if name != "Unknown":
                recognized.append(name)
        
        return jsonify({
            'frame': f'data:image/jpeg;base64,{result_base64}',
            'face_count': len(face_system.last_face_locations),
            'recognized': recognized,
            'fps': round(face_system.fps, 1),
            'detection_ms': round(face_system.last_detection_ms, 1),
            'recognition_ms': round(face_system.last_recognition_ms, 1),
            'total_ms': round(face_system.last_total_ms, 1),
            'frame_number': face_system._frame_count,
            'dnn_detector': face_system.yolo_available,
        })
        
    except Exception as e:
        logger.error(f"Error processing browser frame: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/camera/detect-faces', methods=['POST'])
def detect_faces_from_browser():
    """Face detection + recognition from browser frame. YOLOv8 on GPU."""
    try:
        data = request.get_json()
        if not data or 'frame' not in data:
            return jsonify({'faces': [], 'face_count': 0})
        
        frame_data = data['frame']
        if ',' in frame_data:
            frame_data = frame_data.split(',', 1)[1]
        
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({'faces': [], 'face_count': 0})
        
        # YOLOv8 detection on GPU
        face_boxes = face_system._detect_faces(frame)
        
        # Run recognition on detected faces
        names = [None] * len(face_boxes)
        confs = [0.0] * len(face_boxes)
        if face_boxes and face_system.face_recognition_available:
            names, confs, _ = face_system._recognize_faces(frame, face_boxes)
        
        faces = []
        for i, box in enumerate(face_boxes):
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            name = names[i] if i < len(names) else None
            conf = confs[i] if i < len(confs) else 0.0
            faces.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "name": name if name else "UNRECOGNIZED",
                "confidence": round(conf, 2)
            })
        
        return jsonify({'faces': faces, 'face_count': len(faces)})
        
    except Exception as e:
        logger.error(f"[DetectFaces] Error: {e}")
        return jsonify({'faces': [], 'face_count': 0})


# ============================================================================
# WebSocket Face Detection (low-latency browser webcam)
# ============================================================================

@socketio.on('detect_frame')
def handle_detect_frame(data):
    """
    WebSocket endpoint for real-time face detection.
    EXACT COPY of DroidCam logic: YOLO detect -> recognize -> return name+conf.
    """
    try:
        frame_data = data.get('frame', '')
        if ',' in frame_data:
            frame_data = frame_data.split(',', 1)[1]
        
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            emit('detect_result', {'faces': [], 'face_count': 0})
            return
        
        # Step 1: YOLO-face detection on GPU (~3ms)
        face_boxes = face_system._detect_faces(frame)
        
        # Step 2: Face recognition (CPU, every N frames) — SAME AS DROIDCAM
        do_recognize = (face_system._frame_count % face_system.recognition_interval == 0)
        names = [None] * len(face_boxes)
        confs = [0.0] * len(face_boxes)
        
        if do_recognize and face_boxes and face_system.face_recognition_available:
            names, confs, _ = face_system._recognize_faces(frame, face_boxes)
        
        # Step 3: IoU tracking — SAME AS DROIDCAM
        tracked = face_system._tracker.update(face_boxes, names, confs)
        
        # Step 4: Build response with name+confidence — SAME AS DROIDCAM
        faces = []
        for i, (name, conf) in enumerate(tracked):
            if i < len(face_boxes):
                x1, y1, x2, y2 = face_boxes[i]
                faces.append({
                    "x1": int(x1), "y1": int(y1),
                    "x2": int(x2), "y2": int(y2),
                    "name": name if name else "UNRECOGNIZED",
                    "confidence": round(conf, 2)
                })
        
        emit('detect_result', {'faces': faces, 'face_count': len(faces)})
        
    except Exception as e:
        logger.error(f"[WebSocket] Detection error: {e}")
        emit('detect_result', {'faces': [], 'face_count': 0})


@app.route('/api/camera/enroll-frame', methods=['POST'])
def enroll_from_browser_frame():
    """Enroll an employee using frames from the server camera.
    
    Supports multi-angle enrollment (front, left, right).
    Employee ID is auto-generated if not provided.
    
    Request body: { 
        "frame_front": "data:image/jpeg;base64,...",  (required)
        "frame_left": "data:image/jpeg;base64,...",   (optional)
        "frame_right": "data:image/jpeg;base64,...",  (optional)
        "full_name": "...",
        ... other fields
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        full_name = data.get('full_name', '').strip()
        if not full_name:
            return jsonify({'success': False, 'error': 'Full name is required'}), 400
        
        # Auto-generate employee ID
        employee_id = data.get('employee_id', '').strip()
        if not employee_id:
            employee_id = db.generate_employee_id()
        
        # Get frame data - support both single frame and multi-angle
        frame_front_data = data.get('frame_front', '') or data.get('frame', '')
        
        if not frame_front_data:
            return jsonify({'success': False, 'error': 'No camera frame provided. Please capture your face.'}), 400
        
        def decode_frame(frame_data):
            if ',' in frame_data:
                frame_data = frame_data.split(',', 1)[1]
            frame_bytes = base64.b64decode(frame_data)
            nparr = np.frombuffer(frame_bytes, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        frame_front = decode_frame(frame_front_data)
        if frame_front is None:
            return jsonify({'success': False, 'error': 'Failed to decode camera frame'}), 400
        
        # Collect additional fields
        additional_fields = {
            'email': data.get('email'),
            'phone': data.get('phone'),
            'department_id': data.get('department_id'),
            'position_id': data.get('position_id'),
            'shift_id': data.get('shift_id'),
            'employment_type': data.get('employment_type'),
            'hire_date': data.get('hire_date'),
            'date_of_birth': data.get('date_of_birth'),
            'street_address': data.get('street_address'),
            'region': data.get('region'),
            'province': data.get('province'),
            'city': data.get('city'),
            'barangay': data.get('barangay'),
            'postal_code': data.get('postal_code'),
            'emergency_contact_name': data.get('emergency_contact_name'),
            'emergency_contact_phone': data.get('emergency_contact_phone'),
        }
        
        # Check for multi-angle frames
        frame_left_data = data.get('frame_left', '')
        frame_right_data = data.get('frame_right', '')
        
        if frame_left_data or frame_right_data:
            # Multi-angle enrollment
            frames_dict = {'front': frame_front}
            if frame_left_data:
                frame_left = decode_frame(frame_left_data)
                if frame_left is not None:
                    frames_dict['left'] = frame_left
            if frame_right_data:
                frame_right = decode_frame(frame_right_data)
                if frame_right is not None:
                    frames_dict['right'] = frame_right
            
            result = face_system.enroll_person_multi(frames_dict, full_name, employee_id, **additional_fields)
        else:
            # Single angle enrollment
            result = face_system.enroll_person(frame_front, full_name, employee_id, **additional_fields)
        
        if result['success']:
            result['employee_id_display'] = employee_id
            if 'user_id' in session:
                db.add_audit_log(
                    session['user_id'],
                    'Enroll employee (server camera)',
                    'employees',
                    result.get('employee_id'),
                    {'name': full_name, 'emp_id': employee_id}
                )
            face_system.reload_faces()
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error enrolling from frame: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system-info', methods=['GET'])
def get_system_info():
    """Get system information"""
    try:
        # Determine actual camera mode
        actual_camera_mode = 'mock'
        if not USE_MOCK_CAMERA and not runtime_use_mock:
            with camera_lock:
                if camera is not None and isinstance(camera, CameraReader) and camera.is_alive:
                    actual_camera_mode = 'real'
                elif camera is not None and hasattr(camera, 'isOpened') and camera.isOpened():
                    actual_camera_mode = 'real'
        
        return jsonify({
            'camera_mode': actual_camera_mode,
            'status': 'operational',
            'database_connected': True,
            'total_employees': db.get_employee_count(),
            'face_recognition_available': face_system.face_recognition_available
        })
    except Exception as e:
        logger.error(f"Error fetching system info: {e}")
        return jsonify({'error': str(e)}), 500


# ===== AUTHENTICATION ROUTES =====

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'GET':
        return render_template('login.html')
    
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400
        
        user = db.get_user(username)
        
        if not user or not verify_password(password, user['password_hash']):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        
        # Set session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_role'] = user['role']
        session['employee_id'] = user['employee_id']
        
        # Update last login
        db.update_last_login(user['id'])
        
        return jsonify({'success': True, 'role': user['role']})
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Login failed'}), 500


@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/api/current-user', methods=['GET'])
def get_current_user():
    """Get current logged-in user info"""
    if 'user_id' in session:
        return jsonify({
            'logged_in': True,
            'username': session.get('username'),
            'role': session.get('user_role')
        })
    return jsonify({'logged_in': False})


# ===== EMPLOYEE MANAGEMENT ROUTES =====

@app.route('/dashboard')
@login_required
def dashboard():
    """Employee management dashboard"""
    return render_template('dashboard.html')


@app.route('/profile/<int:employee_id>')
@login_required
def employee_profile(employee_id):
    """Employee profile page"""
    return render_template('profile.html', employee_id=employee_id)


@app.route('/api/employees/detailed', methods=['GET'])
@api_login_required
def get_employees_detailed():
    """Get employees with detailed information"""
    try:
        search = request.args.get('search', '')
        department_id = request.args.get('department_id', type=int)
        position_id = request.args.get('position_id', type=int)
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        employees = db.get_employees_detailed(
            active_only=active_only,
            search=search if search else None,
            department_id=department_id,
            position_id=position_id
        )
        
        # Remove face_encoding from response (too large)
        for emp in employees:
            emp.pop('face_encoding', None)
        
        return jsonify(employees)
        
    except Exception as e:
        logger.error(f"Error fetching detailed employees: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>', methods=['GET', 'PUT', 'DELETE'])
@api_login_required
def manage_employee(employee_id):
    """Get, update, or deactivate an employee"""
    try:
        if request.method == 'GET':
            employee = db.get_employee(employee_id)
            if employee:
                employee.pop('face_encoding', None)  # Don't send encoding
                return jsonify(employee)
            return jsonify({'error': 'Employee not found'}), 404
        
        elif request.method == 'PUT':
            data = request.get_json()
            # Remove fields that shouldn't be updated
            data.pop('id', None)
            data.pop('face_encoding', None)
            data.pop('date_enrolled', None)
            
            success = db.update_employee(employee_id, **data)
            
            if success:
                # Log the change
                if 'user_id' in session:
                    db.add_audit_log(
                        session['user_id'], 
                        'Update employee', 
                        'employees', 
                        employee_id, 
                        data
                    )
                return jsonify({'success': True, 'message': 'Employee updated'})
            return jsonify({'success': False, 'message': 'Update failed'}), 400
        
        elif request.method == 'DELETE':
            # Soft delete
            success = db.delete_employee(employee_id)
            if success:
                if 'user_id' in session:
                    db.add_audit_log(
                        session['user_id'], 
                        'Deactivate employee', 
                        'employees', 
                        employee_id
                    )
                # Reload face encodings
                face_system.load_known_faces()
                return jsonify({'success': True, 'message': 'Employee deactivated'})
            return jsonify({'success': False, 'message': 'Deactivation failed'}), 400
            
    except Exception as e:
        logger.error(f"Error managing employee: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>/delete', methods=['POST'])
@api_login_required
def hard_delete_employee(employee_id):
    """Hard delete an employee and related records from the database"""
    try:
        success = db.hard_delete_employee(employee_id)
        if success:
            face_system.load_known_faces()
            if 'user_id' in session:
                db.add_audit_log(
                    session['user_id'],
                    'Hard delete employee',
                    'employees',
                    employee_id
                )
            return jsonify({'success': True, 'message': 'Employee deleted'})
        return jsonify({'success': False, 'message': 'Employee not found'}), 404
    except Exception as e:
        logger.error(f"Error hard deleting employee: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>/disable', methods=['POST'])
def disable_employee(employee_id):
    if db.disable_employee(employee_id):
        face_system.reload_faces()
        return jsonify({'success': True, 'message': 'Employee disabled'})
    return jsonify({'success': False, 'message': 'Employee not found'}), 404

@app.route('/api/employees/<int:employee_id>/enable', methods=['POST'])
def enable_employee(employee_id):
    if db.enable_employee(employee_id):
        face_system.reload_faces()
        return jsonify({'success': True, 'message': 'Employee enabled'})
    return jsonify({'success': False, 'message': 'Employee not found'}), 404


@app.route('/api/employees/delete-all', methods=['POST'])
@api_login_required
@role_required('admin')
def delete_all_employees():
    """Delete all employees and related data"""
    try:
        db.delete_all_data()
        face_system.load_known_faces()
        if 'user_id' in session:
            db.add_audit_log(
                session['user_id'],
                'Delete all employee data',
                'employees',
                None
            )
        return jsonify({'success': True, 'message': 'All data cleared'})
    except Exception as e:
        logger.error(f"Error deleting all data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>/photo', methods=['GET'])
def get_employee_photo(employee_id):
    """Get employee photo"""
    try:
        employee = db.get_employee(employee_id)
        if employee and employee.get('photo_path'):
            photo_dir = Path('face_data')
            return send_from_directory(photo_dir.parent, employee['photo_path'])
        return '', 404
    except Exception as e:
        logger.error(f"Error fetching photo: {e}")
        return '', 404


@app.route('/api/employees/<int:employee_id>/history', methods=['GET'])
@api_login_required
def get_employee_attendance_history(employee_id):
    """Get attendance history for an employee"""
    try:
        days = request.args.get('days', default=30, type=int)
        history = db.get_employee_history(employee_id, days)
        return jsonify(history)
    except Exception as e:
        logger.error(f"Error fetching employee history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/employees/<int:employee_id>/stats', methods=['GET'])
@api_login_required
def get_employee_statistics(employee_id):
    """Get statistics for an employee"""
    try:
        # Get date range from query params
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')
        
        if start_str:
            start_date = date.fromisoformat(start_str)
        if end_str:
            end_date = date.fromisoformat(end_str)
        
        stats = db.get_employee_stats(employee_id, start_date, end_date)
        return jsonify(stats if stats else {})
        
    except Exception as e:
        logger.error(f"Error fetching employee stats: {e}")
        return jsonify({'error': str(e)}), 500


# ===== DEPARTMENT/POSITION/SHIFT ROUTES =====

@app.route('/api/departments', methods=['GET', 'POST'])
def manage_departments():
    """Get all departments (public) or add a new one (auth required)"""
    if request.method == 'GET':
        departments = db.get_all_departments()
        return jsonify(departments)
    
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    dept_id = db.add_department(
        data['name'],
        data.get('description'),
        data.get('department_head_id')
    )
    return jsonify({'success': True, 'id': dept_id}), 201


@app.route('/api/positions', methods=['GET', 'POST'])
def manage_positions():
    """Get all positions (public) or add a new one (auth required)"""
    if request.method == 'GET':
        positions = db.get_all_positions()
        return jsonify(positions)
    
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    pos_id = db.add_position(
        data['title'],
        data.get('description'),
        data.get('level', 1)
    )
    return jsonify({'success': True, 'id': pos_id}), 201


@app.route('/api/shifts', methods=['GET', 'POST'])
def manage_shifts():
    """Get all shifts (public) or add a new one (auth required)"""
    if request.method == 'GET':
        shifts = db.get_all_shifts()
        return jsonify(shifts)
    
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json()
    shift_id = db.add_shift(
        data['name'],
        data['start_time'],
        data['end_time'],
        data.get('grace_period_minutes', 15)
    )
    return jsonify({'success': True, 'id': shift_id}), 201


# ===== LEAVE MANAGEMENT ROUTES =====

@app.route('/api/leave-requests', methods=['GET', 'POST'])
@api_login_required
def manage_leave_requests():
    """Get or create leave requests"""
    if request.method == 'GET':
        employee_id = request.args.get('employee_id', type=int)
        status = request.args.get('status')
        requests = db.get_leave_requests(employee_id, status)
        return jsonify(requests)
    
    elif request.method == 'POST':
        data = request.get_json()
        leave_id = db.add_leave_request(
            data['employee_id'],
            data['leave_type'],
            data['start_date'],
            data['end_date'],
            data['days_count'],
            data.get('reason')
        )
        
        # Send notification to manager
        if leave_id:
            try:
                # Get employee details
                employee = db.get_employee(data['employee_id'])
                if employee and employee.get('manager_name'):
                    # In a real system, you'd look up manager's email from users table
                    # For now, we'll just log it
                    logger.info(f"Leave request {leave_id} submitted by {employee['full_name']}")
                    # notifications.notify_leave_request(
                    #     manager_email,
                    #     employee['full_name'],
                    #     data['leave_type'],
                    #     data['start_date'],
                    #     data['end_date'],
                    #     data['days_count']
                    # )
            except Exception as e:
                logger.warning(f"Failed to send leave request notification: {e}")
        
        return jsonify({'success': True, 'id': leave_id}), 201


@app.route('/api/leave-requests/<int:leave_id>/approve', methods=['POST'])
@api_login_required
@role_required('manager')
def approve_leave(leave_id):
    """Approve or reject a leave request"""
    try:
        data = request.get_json()
        status = data.get('status', 'Approved')
        decision_notes = data.get('decision_notes', '')
        
        # Get leave request details before updating
        leave_request = db.get_leave_requests(leave_id=leave_id)
        if not leave_request:
            return jsonify({'success': False, 'error': 'Leave request not found'}), 404
        
        leave_req = leave_request[0] if isinstance(leave_request, list) else leave_request
        
        success = db.update_leave_status(
            leave_id,
            status,
            session.get('user_id'),
            decision_notes
        )
        
        if success:
            db.add_audit_log(
                session['user_id'],
                f'Leave request {status}',
                'leave_requests',
                leave_id
            )
            
            # Send notification to employee
            try:
                employee = db.get_employee(leave_req.get('employee_id'))
                if employee and employee.get('email'):
                    # Get approver name
                    approver = db.get_user_by_id(session.get('user_id'))
                    approver_name = approver.get('username', 'Manager') if approver else 'Manager'
                    
                    notifications.notify_leave_decision(
                        employee['email'],
                        employee['full_name'],
                        leave_req.get('leave_type', 'Leave'),
                        status,
                        approver_name
                    )
            except Exception as e:
                logger.warning(f"Failed to send leave decision notification: {e}")
            
            return jsonify({'success': True})
            return jsonify({'success': False}), 400
        
    except Exception as e:
        logger.error(f"Error approving leave: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/leave-requests/list', methods=['GET'])
def list_leave_requests():
    """Get leave requests with optional employee filter"""
    employee_id = request.args.get('employee_id', type=int)
    requests = db.get_leave_requests(employee_id)
    return jsonify({'success': True, 'requests': requests})


@app.route('/api/leave-requests/create', methods=['POST'])
def create_leave_request():
    """Create a new leave request with eligibility check"""
    data = request.json
    employee_id = data.get('employee_id')
    leave_type = data.get('leave_type')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    reason = data.get('reason')
    if not all([employee_id, leave_type, start_date, end_date]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    if not db.is_employee_eligible_for_leave(employee_id):
        return jsonify({'success': False, 'message': 'Employee must be employed for at least 1 year to be eligible for leave'}), 403
    request_id = db.add_leave_request(employee_id, leave_type, start_date, end_date, reason)
    return jsonify({'success': True, 'request_id': request_id, 'message': 'Leave request submitted'})


@app.route('/api/leave-requests/<int:request_id>/status', methods=['POST'])
def update_leave_request_status(request_id):
    """Update leave request status (approve/reject)"""
    data = request.json
    status = data.get('status')
    reviewed_by = data.get('reviewed_by', 'admin')
    if status not in ('approved', 'rejected'):
        return jsonify({'success': False, 'message': 'Status must be approved or rejected'}), 400
    if db.update_leave_status(request_id, status, reviewed_by):
        return jsonify({'success': True, 'message': f'Leave request {status}'})
    return jsonify({'success': False, 'message': 'Request not found'}), 404


# ===== REPORTING ROUTES =====

@app.route('/reports')
@login_required
def reports_page():
    """Reports and analytics page"""
    return render_template('reports.html')


@app.route('/leaves')
@login_required
def leaves_page():
    """Leave management page"""
    return render_template('leaves.html')


@app.route('/settings')
@login_required
@role_required('admin')
def settings_page():
    """System settings and configuration page (admin only)"""
    return render_template('settings.html')


@app.route('/api/reports/attendance', methods=['GET'])
@api_login_required
def get_attendance_report():
    """Get attendance report for date range"""
    try:
        # Get date range
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')
        department_id = request.args.get('department_id', type=int)
        
        if start_str:
            start_date = date.fromisoformat(start_str)
        if end_str:
            end_date = date.fromisoformat(end_str)
        
        report = db.get_attendance_report(start_date, end_date, department_id)
        return jsonify(report)
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/summary', methods=['GET'])
@api_login_required
def get_report_summary():
    """Get summary statistics for reporting"""
    try:
        today = date.today()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        summary = {
            'today': db.get_statistics(today, today),
            'this_week': db.get_statistics(week_ago, today),
            'this_month': db.get_statistics(month_ago, today),
            'total_employees': db.get_employee_count(),
            'today_attendance': db.get_today_attendance_count()
        }
        
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return jsonify({'error': str(e)}), 500


# ===== MANUAL ATTENDANCE =====

@app.route('/api/attendance/manual', methods=['POST'])
@api_login_required
@role_required('manager')
def manual_attendance_entry():
    """Manually add or modify attendance"""
    try:
        data = request.get_json()
        
        success = db.manual_attendance(
            data['employee_id'],
            data['action'],  # 'clock_in' or 'clock_out'
            data['timestamp'],
            session['user_id'],
            data.get('notes')
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Attendance recorded'})
        return jsonify({'success': False, 'message': 'Failed to record'}), 400
        
    except Exception as e:
        logger.error(f"Error with manual attendance: {e}")
        return jsonify({'error': str(e)}), 500


# ===== AUDIT LOGS =====

@app.route('/api/audit-logs', methods=['GET'])
@api_login_required
@role_required('admin')
def get_audit_logs():
    """Get audit logs"""
    try:
        limit = request.args.get('limit', default=100, type=int)
        logs = db.get_audit_logs(limit)
        return jsonify(logs)
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
        return jsonify({'error': str(e)}), 500


# ===== ENHANCED ENROLLMENT =====

@app.route('/api/enroll', methods=['POST'])
def enroll_employee():
    """Enroll a new employee with extended information"""
    global camera
    try:
        data = request.get_json()
        
        if not data or 'full_name' not in data or 'employee_id' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: full_name and employee_id'
            }), 400
        
        full_name = data['full_name'].strip()
        employee_id = data['employee_id'].strip()
        
        # Validate input
        if not full_name or not employee_id:
            return jsonify({
                'success': False,
                'message': 'Full name and employee ID cannot be empty'
            }), 400
        
        # Collect all additional fields
        additional_fields = {
            'email': data.get('email'),
            'phone': data.get('phone'),
            'date_of_birth': data.get('date_of_birth'),
            'address': data.get('address'),
            'emergency_contact_name': data.get('emergency_contact_name'),
            'emergency_contact_phone': data.get('emergency_contact_phone'),
            'department_id': data.get('department_id'),
            'position_id': data.get('position_id'),
            'shift_id': data.get('shift_id'),
            'manager_id': data.get('manager_id'),
            'employment_type': data.get('employment_type', 'Full-time'),
            'hire_date': data.get('hire_date'),
            'salary_grade': data.get('salary_grade'),
            'notes': data.get('notes')
        }
        
        # Handle photo if provided
        if 'photo' in data:
            # Decode base64 photo and save
            photo_data = data['photo'].split(',')[1] if ',' in data['photo'] else data['photo']
            photo_bytes = base64.b64decode(photo_data)
            
            # Save photo
            photo_dir = Path('face_data')
            photo_dir.mkdir(exist_ok=True)
            photo_filename = f"{employee_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            photo_path = photo_dir / photo_filename
            
            with open(photo_path, 'wb') as f:
                f.write(photo_bytes)
            
            additional_fields['photo_path'] = str(photo_path)
        
        if USE_MOCK_CAMERA:
            # Mock enrollment
            result = face_system.enroll_person_mock(
                full_name, employee_id, **additional_fields
            )
        else:
            # Capture face from camera
            cam = get_camera()
            if cam is None:
                return jsonify({
                    'success': False,
                    'message': 'Camera not available. Please check that a camera is connected and not used by another application.'
                }), 500
            
            # Read frame with timeout protection
            success, frame = cam.read()
            if not success:
                # Try to recover camera
                with camera_lock:
                    if camera is not None:
                        camera.release()
                        camera = None
                cam = get_camera()
                if cam is not None:
                    success, frame = cam.read()
                
                if not success:
                    return jsonify({
                        'success': False,
                        'message': 'Failed to capture image from camera. The camera may be busy or disconnected.'
                    }), 500
            
            # Enroll with extended fields
            result = face_system.enroll_person(
                frame, full_name, employee_id, **additional_fields
            )
        
        if result['success']:
            # Send welcome email if email provided
            email = additional_fields.get('email')
            if email:
                try:
                    notifications.notify_new_enrollment(full_name, employee_id, email)
                except Exception as e:
                    logger.warning(f"Failed to send enrollment notification: {e}")
            
            # Log enrollment
            if 'user_id' in session:
                db.add_audit_log(
                    session['user_id'],
                    'Enroll employee',
                    'employees',
                    result.get('employee_id'),
                    {'name': full_name, 'emp_id': employee_id}
                )
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error enrolling employee: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500


def cleanup():
    """Clean up resources on shutdown"""
    if camera is not None:
        if isinstance(camera, CameraReader):
            camera.release()
        else:
            try:
                camera.release()
            except Exception:
                pass
    cv2.destroyAllWindows()
    logger.info("Resources cleaned up")


if __name__ == '__main__':
    try:
        logger.info("=" * 60)
        logger.info("NEURAL EYE - Facial Recognition System")
        logger.info("=" * 60)
        logger.info("Initializing system...")
        
        # Ensure required directories exist
        os.makedirs('frontend/static', exist_ok=True)
        os.makedirs('face_data', exist_ok=True)
        
        # Log camera mode
        if USE_MOCK_CAMERA:
            logger.info("WARNING: RUNNING IN MOCK CAMERA MODE")
            logger.info("   Set USE_MOCK_CAMERA = False to use real camera")
        else:
            logger.info("Real camera mode enabled")
        
        logger.info("="*60)
        logger.info("Server starting on http://localhost:5000")
        logger.info("Dashboard: http://localhost:5000")
        logger.info("Enrollment: http://localhost:5000/enroll")
        logger.info("WebSocket: ws://localhost:5000/socket.io")
        logger.info("="*60)
        
        # Use SocketIO for WebSocket support (enables real-time face detection)
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=True,
            use_reloader=False,  # Prevent double initialization
            allow_unsafe_werkzeug=True  # Required for debug mode
        )
    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        cleanup()
