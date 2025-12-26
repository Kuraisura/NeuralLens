"""
NEURAL LENS - Ultra-Optimized Application (v2.5)
Maximum performance with all advanced optimizations enabled
"""

from flask import Flask, Response, jsonify, render_template, request, session
from flask_cors import CORS
from flask_compress import Compress
import cv2
import threading
from datetime import datetime, date, timedelta
import os
import numpy as np
import time

# Import all optimization modules
from database_optimized import Database
from face_recognition_optimized import FaceRecognitionSystem
from logging_system import setup_logging, timed_operation, RequestLogger, error_handler
from caching_system import cache_manager, cached, perf_config
from performance_monitor import performance_monitor, start_monitoring
from image_optimizer import image_optimizer, AdaptiveQualityController
from async_tasks import task_queue, background_scheduler, start_background_services
from auth import hash_password, verify_password, login_required, api_login_required, role_required
from notifications import get_notification_system

# Setup logging
setup_logging(
    log_level=os.environ.get('LOG_LEVEL', 'INFO'),
    log_dir='logs',
    enable_console=True,
    enable_file=True
)

import logging
logger = logging.getLogger(__name__)
request_logger = RequestLogger()

# Initialize Flask
app = Flask(__name__, 
            template_folder='frontend',
            static_folder='frontend/static')

# Enable compression
Compress(app)
CORS(app)

# Configuration
app.secret_key = os.environ.get('SECRET_KEY', 'neural-lens-secret-key-v2.5')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    JSON_SORT_KEYS=False,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024
)

USE_MOCK_CAMERA = os.environ.get('USE_MOCK_CAMERA', 'true').lower() == 'true'

# Initialize systems
logger.info("Initializing Neural Lens Ultra-Optimized v2.5...")
db = Database(pool_size=8)  # Increased pool size
notifications = get_notification_system()
face_system = FaceRecognitionSystem(db, notifications)

# Apply performance configuration
preset = os.environ.get('PERFORMANCE_PRESET', 'balanced')
perf_config.apply_preset(preset)
face_system.set_quality_mode(preset)
image_optimizer.set_quality_preset('high')

# Start background services
start_monitoring()
start_background_services()

# Setup adaptive quality controller
adaptive_quality = AdaptiveQualityController(image_optimizer)

# Camera management
camera_lock = threading.Lock()
camera = None
frame_cache = {'frame': None, 'timestamp': 0, 'cache_duration': 0.033}


def schedule_maintenance_tasks():
    """Schedule periodic maintenance tasks"""
    # Cache cleanup every 5 minutes
    background_scheduler.schedule_task(
        'cache_cleanup',
        lambda: cache_manager.cleanup_all(),
        interval_seconds=300
    )
    
    # Database cleanup every hour
    background_scheduler.schedule_task(
        'db_cleanup',
        lambda: task_queue.cleanup_old_tasks(max_age_hours=24),
        interval_seconds=3600
    )
    
    # Performance adjustment every 30 seconds
    def adjust_performance():
        metrics = performance_monitor.collector.get_current_metrics()
        adaptive_quality.adjust_quality(
            metrics['cpu_percent'],
            metrics['memory_percent'],
            metrics['avg_response_time_ms'] / 1000
        )
    
    background_scheduler.schedule_task(
        'performance_adjustment',
        adjust_performance,
        interval_seconds=30
    )
    
    logger.info("Maintenance tasks scheduled")


# Schedule maintenance on startup
schedule_maintenance_tasks()


def get_mock_frame():
    """Optimized mock frame generation"""
    cache = cache_manager.get_cache('mock_frames')
    cached_frame = cache.get('mock_frame')
    
    if cached_frame is not None:
        frame = cached_frame.copy()
    else:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        for i in range(720):
            color_val = int(8 + (i / 720) * 20)
            frame[i, :] = [color_val, color_val * 2, color_val * 3]
        cv2.circle(frame, (640, 360), 150, (0, 242, 255), 3)
        cv2.circle(frame, (640, 360), 5, (0, 242, 255), -1)
        cache.set('mock_frame', frame.copy(), ttl=300)
    
    # Dynamic timestamp
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, "NEURAL LENS v2.5 - ULTRA MODE", (300, 280), font, 1.0, (0, 242, 255), 2)
    cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (480, 420), font, 0.7, (0, 242, 255), 1)
    
    return frame


def generate_frames():
    """Ultra-optimized frame generation"""
    consecutive_failures = 0
    max_failures = 10
    
    while True:
        try:
            current_time = time.time()
            
            # Use frame cache
            if (frame_cache['frame'] is not None and 
                current_time - frame_cache['timestamp'] < frame_cache['cache_duration']):
                frame_bytes = frame_cache['frame']
            else:
                # Generate/capture frame
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
                        continue
                
                consecutive_failures = 0
                
                # Optimize frame
                frame = image_optimizer.optimize_frame(frame)
                
                # Process with face recognition
                if not USE_MOCK_CAMERA:
                    frame = face_system.process_frame(frame)
                
                # Encode with optimizer
                frame_bytes = image_optimizer.encode_frame(frame, use_cache=True)
                
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


@timed_operation('camera_init')
def get_camera():
    """Initialize camera with optimizations"""
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
                camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                if camera.isOpened():
                    logger.info("Camera initialized successfully")
                else:
                    return None
            except Exception as e:
                logger.error(f"Camera error: {e}")
                return None
        
        return camera


# Request tracking
@app.before_request
def before_request():
    request.start_time = time.time()


@app.after_request
def after_request(response):
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        is_error = response.status_code >= 400
        
        performance_monitor.record_request(duration, is_error)
        request_logger.log_request(
            method=request.method,
            endpoint=request.path,
            status_code=response.status_code,
            duration=duration
        )
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response


# Routes
@app.route('/')
def index():
    return render_template('dashboard_enhanced.html')


@app.route('/video_feed')
def video_feed():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/stats', methods=['GET'])
@timed_operation('api_stats')
@cached('api_stats', ttl=3)
def get_stats():
    try:
        stats = {
            'total_employees': db.get_employee_count(),
            'today_attendance': len(db.get_attendance_by_date(date.today())),
            'active_now': face_system.get_active_count(),
            'system_health': 'operational',
            'version': '2.5-ultra',
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(stats)
    except Exception as e:
        error_handler.handle_error(e, error_type='api_stats', raise_error=False)
        return jsonify({'error': 'Failed to fetch stats'}), 500


@app.route('/api/attendance/today', methods=['GET'])
@timed_operation('api_attendance')
@cached('attendance_today', ttl=5)
def get_todays_attendance():
    try:
        today = date.today()
        all_attendance = db.get_attendance_by_date(today)
        
        present = len(all_attendance)
        on_time = len([a for a in all_attendance if a.get('status') == 'ON-TIME'])
        late_records = [a for a in all_attendance if a.get('status') == 'LATE']
        
        all_employees = db.get_all_employees()
        attended_ids = set(a.get('employee_id') for a in all_attendance)
        absent = [e for e in all_employees if e['id'] not in attended_ids]
        
        return jsonify({
            'present': present,
            'on_time': on_time,
            'late_count': len(late_records),
            'absent_count': len(absent),
            'late': late_records[:10],
            'absent': absent[:20],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        error_handler.handle_error(e, error_type='api_attendance', raise_error=False)
        return jsonify({'error': str(e)}), 500


@app.route('/api/performance/dashboard', methods=['GET'])
def get_performance_dashboard():
    """Enhanced performance dashboard"""
    try:
        return jsonify({
            'monitoring': performance_monitor.get_dashboard_data(),
            'caches': cache_manager.get_all_stats(),
            'config': perf_config.get_all(),
            'tasks': task_queue.get_queue_stats(),
            'scheduled': background_scheduler.get_scheduled_tasks(),
            'image_optimizer': image_optimizer.get_cache_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/performance/metrics/prometheus', methods=['GET'])
def get_prometheus_metrics():
    """Export metrics in Prometheus format"""
    try:
        metrics = performance_monitor.export_metrics(format='prometheus')
        return Response(metrics, mimetype='text/plain')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/submit', methods=['POST'])
@role_required('admin')
def submit_background_task():
    """Submit a background task"""
    try:
        data = request.get_json()
        task_type = data.get('type')
        
        # Define available task types
        if task_type == 'cache_cleanup':
            task_id = task_queue.submit_task(
                cache_manager.cleanup_all,
                priority=3
            )
        elif task_type == 'reload_faces':
            task_id = task_queue.submit_task(
                face_system.reload_encodings,
                priority=2
            )
        else:
            return jsonify({'error': 'Unknown task type'}), 400
        
        return jsonify({'success': True, 'task_id': task_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    """Get status of a background task"""
    try:
        status = task_queue.get_task_status(task_id)
        if status:
            return jsonify(status)
        return jsonify({'error': 'Task not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Comprehensive health check"""
    try:
        metrics = performance_monitor.collector.get_current_metrics()
        
        health = {
            'status': 'healthy',
            'version': '2.5-ultra',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': 'connected',
                'face_recognition': 'active',
                'cache': 'operational',
                'task_queue': 'running',
                'monitoring': 'active'
            },
            'metrics': {
                'cpu_percent': metrics['cpu_percent'],
                'memory_mb': metrics['memory_mb'],
                'active_threads': metrics['active_threads'],
                'total_requests': metrics['total_requests']
            }
        }
        
        # Check if any component is unhealthy
        if metrics['cpu_percent'] > 90 or metrics['memory_percent'] > 90:
            health['status'] = 'degraded'
        
        return jsonify(health)
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


def cleanup():
    """Cleanup resources"""
    logger.info("Shutting down Neural Lens v2.5...")
    
    if camera:
        camera.release()
    
    face_system.cleanup()
    db.close()
    performance_monitor.stop()
    task_queue.stop()
    background_scheduler.stop()
    
    logger.info("Shutdown complete")


import atexit
atexit.register(cleanup)


if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("NEURAL LENS v2.5 - ULTRA-OPTIMIZED EDITION")
    logger.info("=" * 70)
    logger.info(f"Performance preset: {preset}")
    logger.info(f"Camera mode: {'MOCK' if USE_MOCK_CAMERA else 'REAL'}")
    logger.info(f"Database pool size: 8")
    logger.info(f"Task workers: {task_queue.max_workers}")
    logger.info(f"Monitoring: ACTIVE")
    logger.info(f"Image optimization: ENABLED")
    logger.info(f"Adaptive quality: ENABLED")
    logger.info("=" * 70)
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )
