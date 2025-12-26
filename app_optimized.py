"""
NEURAL LENS - Optimized Main Application
Enhanced Flask application with performance optimizations and modern features
"""

from flask import Flask, Response, jsonify, render_template, request, session, redirect, url_for
from flask_cors import CORS
from flask_compress import Compress
import cv2
import threading
from datetime import datetime, date, timedelta
import os
import numpy as np
import time

# Import optimized modules
from database_optimized import Database
from face_recognition_optimized import FaceRecognitionSystem
from logging_system import setup_logging, timed_operation, RequestLogger, error_handler
from caching_system import cache_manager, cached, perf_config
from auth import hash_password, verify_password, login_required, api_login_required, role_required
from notifications import get_notification_system

# Setup advanced logging
setup_logging(
    log_level=os.environ.get('LOG_LEVEL', 'INFO'),
    log_dir='logs',
    enable_console=True,
    enable_file=True,
    enable_json=False
)

import logging
logger = logging.getLogger(__name__)
request_logger = RequestLogger()

# Initialize Flask app
app = Flask(__name__, 
            template_folder='frontend',
            static_folder='frontend/static')

# Enable compression for responses
Compress(app)

# CORS configuration
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Security configuration
app.secret_key = os.environ.get('SECRET_KEY', 'neural-lens-secret-key-change-in-production')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    JSON_SORT_KEYS=False,  # Faster JSON serialization
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max request size
)

# Performance configuration
USE_MOCK_CAMERA = os.environ.get('USE_MOCK_CAMERA', 'true').lower() == 'true'
ENABLE_CACHING = True

# Initialize systems
logger.info("Initializing Neural Lens systems...")
db = Database(pool_size=perf_config.get('db_pool_size', 5))
notifications = get_notification_system()
face_system = FaceRecognitionSystem(db, notifications)

# Apply performance preset
preset = os.environ.get('PERFORMANCE_PRESET', 'balanced')
perf_config.apply_preset(preset)
face_system.set_quality_mode(preset)

# Camera management
camera_lock = threading.Lock()
camera = None
frame_cache = {
    'frame': None,
    'timestamp': 0,
    'cache_duration': 0.033  # ~30 FPS
}


def get_mock_frame():
    """Generate optimized mock camera frame"""
    # Cache mock frame generation
    cache = cache_manager.get_cache('mock_frames', max_size=10, default_ttl=60)
    
    cached_frame = cache.get('mock_frame')
    if cached_frame is not None:
        # Add timestamp overlay
        frame = cached_frame.copy()
    else:
        # Generate new frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        # Gradient background
        for i in range(720):
            color_val = int(8 + (i / 720) * 20)
            frame[i, :] = [color_val, color_val * 2, color_val * 3]
        
        # Static elements
        cv2.circle(frame, (640, 360), 150, (0, 242, 255), 3)
        cv2.circle(frame, (640, 360), 5, (0, 242, 255), -1)
        
        # Cache the base frame
        cache.set('mock_frame', frame.copy())
    
    # Add dynamic timestamp
    font = cv2.FONT_HERSHEY_SIMPLEX
    text1 = "NEURAL LENS - MOCK CAMERA MODE"
    text2 = "Position your face here for enrollment"
    text3 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cv2.putText(frame, text1, (320, 300), font, 1.2, (0, 242, 255), 2)
    cv2.putText(frame, text2, (380, 360), font, 0.8, (255, 255, 255), 1)
    cv2.putText(frame, text3, (480, 420), font, 0.7, (0, 242, 255), 1)
    
    return frame


@timed_operation('camera_init')
def get_camera():
    """Get or initialize camera with caching"""
    global camera
    
    if USE_MOCK_CAMERA:
        return None
    
    with camera_lock:
        if camera is None or not camera.isOpened():
            try:
                camera = cv2.VideoCapture(0)
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                camera.set(cv2.CAP_PROP_FPS, 30)
                camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce latency
                
                if not camera.isOpened():
                    logger.warning("Failed to open camera - using mock mode")
                    return None
                
                logger.info("Camera initialized successfully")
            except Exception as e:
                logger.error(f"Camera initialization error: {e}")
                return None
        
        return camera


def generate_frames():
    """Optimized frame generation with caching"""
    consecutive_failures = 0
    max_failures = 10
    jpeg_quality = perf_config.get('jpeg_quality', 85)
    
    while True:
        try:
            current_time = time.time()
            
            # Use cached frame if recent enough
            if (frame_cache['frame'] is not None and 
                current_time - frame_cache['timestamp'] < frame_cache['cache_duration']):
                frame_bytes = frame_cache['frame']
            else:
                # Generate new frame
                if USE_MOCK_CAMERA:
                    frame = get_mock_frame()
                else:
                    cam = get_camera()
                    if cam is None:
                        consecutive_failures += 1
                        if consecutive_failures > max_failures:
                            break
                        continue
                    
                    success, frame = cam.read()
                    if not success:
                        consecutive_failures += 1
                        if consecutive_failures > max_failures:
                            break
                        continue
                
                consecutive_failures = 0
                
                # Process with face recognition (only for real camera)
                if not USE_MOCK_CAMERA:
                    frame = face_system.process_frame(frame)
                
                # Encode frame
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
                ret, buffer = cv2.imencode('.jpg', frame, encode_params)
                
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                
                # Update cache
                frame_cache['frame'] = frame_bytes
                frame_cache['timestamp'] = current_time
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        except Exception as e:
            logger.error(f"Error in frame generation: {e}")
            consecutive_failures += 1
            if consecutive_failures > max_failures:
                break


# ===== ROUTES =====

@app.before_request
def before_request():
    """Log and time each request"""
    request.start_time = time.time()


@app.after_request
def after_request(response):
    """Log request completion"""
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        request_logger.log_request(
            method=request.method,
            endpoint=request.path,
            status_code=response.status_code,
            duration=duration
        )
    
    # Add performance headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    return response


@app.route('/')
def index():
    """Serve main page"""
    return render_template('dashboard_enhanced.html')


@app.route('/enroll')
def enroll_page():
    """Serve enrollment page"""
    return render_template('enroll.html')


@app.route('/video_feed')
def video_feed():
    """Optimized video streaming"""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/stats', methods=['GET'])
@timed_operation('api_stats')
@cached('api_stats', ttl=5)  # Cache for 5 seconds
def get_stats():
    """Get system statistics with caching"""
    try:
        stats = {
            'total_employees': db.get_employee_count(),
            'today_attendance': len(db.get_attendance_by_date(date.today())),
            'active_now': face_system.get_active_count(),
            'system_health': 'operational',
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(stats)
    except Exception as e:
        error_handler.handle_error(
            e,
            error_type='api_stats',
            raise_error=False
        )
        return jsonify({'error': 'Failed to fetch stats'}), 500


@app.route('/api/attendance/today', methods=['GET'])
@timed_operation('api_attendance_today')
@cached('attendance_today', ttl=10)
def get_todays_attendance():
    """Get today's attendance with caching"""
    try:
        today = date.today()
        all_attendance = db.get_attendance_by_date(today)
        
        # Calculate statistics
        present = len(all_attendance)
        on_time = len([a for a in all_attendance if a.get('status') == 'ON-TIME'])
        late_records = [a for a in all_attendance if a.get('status') == 'LATE']
        late_count = len(late_records)
        
        # Get absent employees
        all_employees = db.get_all_employees()
        attended_ids = set(a.get('employee_id') for a in all_attendance)
        absent_employees = [
            {
                'id': e['id'],
                'full_name': e['full_name'],
                'department': e.get('department_name'),
                'position': e.get('position_title')
            }
            for e in all_employees
            if e['id'] not in attended_ids
        ]
        
        return jsonify({
            'present': present,
            'on_time': on_time,
            'late_count': late_count,
            'absent_count': len(absent_employees),
            'late': late_records[:10],  # Limit to recent 10
            'absent': absent_employees[:20],  # Limit to 20
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        error_handler.handle_error(
            e,
            error_type='api_attendance',
            raise_error=False
        )
        return jsonify({'error': 'Failed to fetch attendance'}), 500


@app.route('/api/employees', methods=['GET'])
@timed_operation('api_employees')
@cached('employees_list', ttl=30)
def get_employees():
    """Get all employees with caching"""
    try:
        employees = db.get_all_employees()
        return jsonify(employees)
    except Exception as e:
        error_handler.handle_error(
            e,
            error_type='api_employees',
            raise_error=False
        )
        return jsonify({'error': 'Failed to fetch employees'}), 500


@app.route('/api/enroll', methods=['POST'])
@timed_operation('api_enroll')
def enroll_employee():
    """Enroll new employee"""
    try:
        data = request.get_json()
        
        # Capture frame
        if USE_MOCK_CAMERA:
            frame = get_mock_frame()
        else:
            cam = get_camera()
            if cam is None:
                return jsonify({'success': False, 'message': 'Camera not available'}), 500
            
            success, frame = cam.read()
            if not success:
                return jsonify({'success': False, 'message': 'Failed to capture frame'}), 500
        
        # Enroll
        result = face_system.enroll_person(
            frame=frame,
            full_name=data.get('full_name'),
            employee_id=data.get('employee_id'),
            email=data.get('email'),
            department_id=data.get('department_id'),
            position_id=data.get('position_id')
        )
        
        # Clear caches
        if result.get('success'):
            cache_manager.get_cache('employees_list').clear()
            cache_manager.get_cache('api_stats').clear()
        
        return jsonify(result)
        
    except Exception as e:
        error_handler.handle_error(
            e,
            error_type='api_enroll',
            raise_error=False
        )
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/performance/stats', methods=['GET'])
def get_performance_stats():
    """Get performance and cache statistics"""
    try:
        stats = {
            'caches': cache_manager.get_all_stats(),
            'config': perf_config.get_all(),
            'errors': error_handler.get_error_stats()
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/performance/config', methods=['POST'])
@role_required('admin')
def update_performance_config():
    """Update performance configuration"""
    try:
        data = request.get_json()
        
        if 'preset' in data:
            perf_config.apply_preset(data['preset'])
            face_system.set_quality_mode(data['preset'])
        else:
            perf_config.update(data)
        
        return jsonify({
            'success': True,
            'config': perf_config.get_all()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/cache/clear', methods=['POST'])
@role_required('admin')
def clear_caches():
    """Clear all caches"""
    try:
        data = request.get_json() or {}
        cache_name = data.get('cache')
        
        if cache_name:
            cache = cache_manager.get_cache(cache_name)
            cache.clear()
            message = f"Cleared cache: {cache_name}"
        else:
            for cache in cache_manager.caches.values():
                cache.clear()
            message = "Cleared all caches"
        
        logger.info(message)
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/health', methods=['GET'])
def system_health():
    """System health check"""
    try:
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'camera': 'mock' if USE_MOCK_CAMERA else 'real',
            'database': 'connected',
            'face_recognition': 'active',
            'cache_hit_rate': cache_manager.get_all_stats(),
        }
        return jsonify(health)
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


# Cleanup on shutdown
def cleanup():
    """Cleanup resources"""
    logger.info("Shutting down Neural Lens...")
    
    if camera is not None:
        camera.release()
    
    face_system.cleanup()
    db.close()
    
    logger.info("Shutdown complete")


import atexit
atexit.register(cleanup)


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("NEURAL LENS - Advanced Face Recognition System")
    logger.info("=" * 60)
    logger.info(f"Performance preset: {preset}")
    logger.info(f"Camera mode: {'MOCK' if USE_MOCK_CAMERA else 'REAL'}")
    logger.info(f"Caching: {'ENABLED' if ENABLE_CACHING else 'DISABLED'}")
    logger.info("=" * 60)
    
    # Run application
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,  # Set to False in production
        threaded=True
    )
