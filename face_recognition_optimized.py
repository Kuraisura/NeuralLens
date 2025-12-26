"""
NEURAL EYE - Optimized Face Recognition Module
Enhanced face detection with multi-threading and caching
"""

import cv2
import face_recognition
import numpy as np
from datetime import datetime, timedelta
import pickle
import os
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import threading

logger = logging.getLogger(__name__)


class FaceRecognitionSystem:
    """Optimized face recognition with caching and parallel processing"""
    
    def __init__(self, database, notification_system=None):
        self.db = database
        self.notifications = notification_system
        
        # Face recognition cache
        self.known_encodings = []
        self.known_names = []
        self.known_ids = []
        self.encodings_lock = threading.RLock()
        
        # Tracking for attendance
        self.last_recognition = {}
        self.cooldown_period = timedelta(seconds=10)
        
        # Performance optimization
        self.process_every_n_frames = 2
        self.frame_counter = 0
        self.last_face_locations = []
        self.last_face_names = []
        self.recognition_cache = {}
        self.cache_lifetime = 5  # seconds
        
        # Thread pool for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Attendance schedule
        self.work_start_time = datetime.strptime("08:00:00", "%H:%M:%S").time()
        self.work_end_time = datetime.strptime("17:00:00", "%H:%M:%S").time()
        self.grace_period_minutes = 15
        
        # Model selection for different quality levels
        self.detection_model = 'hog'  # 'hog' for speed, 'cnn' for accuracy
        self.num_jitters = 1  # Lower for speed, higher for accuracy
        
        # Load known faces
        self.load_known_faces()
    
    def set_quality_mode(self, mode='balanced'):
        """
        Set face recognition quality mode
        - 'fast': Maximum speed, lower accuracy
        - 'balanced': Good balance (default)
        - 'accurate': Maximum accuracy, slower
        """
        if mode == 'fast':
            self.detection_model = 'hog'
            self.num_jitters = 1
            self.process_every_n_frames = 3
        elif mode == 'balanced':
            self.detection_model = 'hog'
            self.num_jitters = 1
            self.process_every_n_frames = 2
        elif mode == 'accurate':
            self.detection_model = 'cnn'
            self.num_jitters = 2
            self.process_every_n_frames = 1
        
        logger.info(f"Face recognition quality mode set to: {mode}")
    
    def load_known_faces(self):
        """Load face encodings from database with optimization"""
        try:
            with self.encodings_lock:
                employees = self.db.get_all_employees()
                
                self.known_encodings = []
                self.known_names = []
                self.known_ids = []
                
                for emp in employees:
                    if emp.get('face_encoding'):
                        try:
                            encoding = pickle.loads(emp['face_encoding'])
                            self.known_encodings.append(encoding)
                            self.known_names.append(emp['full_name'])
                            self.known_ids.append(emp['id'])
                        except Exception as e:
                            logger.warning(f"Failed to load encoding for {emp['full_name']}: {e}")
                
                logger.info(f"Loaded {len(self.known_encodings)} face encodings")
                
        except Exception as e:
            logger.error(f"Error loading face encodings: {e}")
    
    def reload_encodings(self):
        """Reload face encodings (for when new employees are added)"""
        self.load_known_faces()
        self.recognition_cache.clear()
    
    @lru_cache(maxsize=100)
    def _get_cached_face_distance(self, encoding_tuple, known_encoding_tuple):
        """Cached face distance calculation"""
        encoding = np.array(encoding_tuple)
        known_encoding = np.array(known_encoding_tuple)
        return np.linalg.norm(encoding - known_encoding)
    
    def enroll_person(self, frame, full_name, employee_id, **kwargs):
        """Enroll a new person with optimized face detection"""
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize frame for faster processing
            scale_factor = 0.5
            small_frame = cv2.resize(rgb_frame, (0, 0), fx=scale_factor, fy=scale_factor)
            
            # Detect faces
            face_locations = face_recognition.face_locations(
                small_frame, 
                model=self.detection_model
            )
            
            if len(face_locations) == 0:
                return {
                    'success': False,
                    'message': 'No face detected. Please ensure your face is visible.'
                }
            
            if len(face_locations) > 1:
                return {
                    'success': False,
                    'message': 'Multiple faces detected. Please ensure only one person is in frame.'
                }
            
            # Scale back face location
            top, right, bottom, left = face_locations[0]
            face_locations = [(
                int(top / scale_factor),
                int(right / scale_factor),
                int(bottom / scale_factor),
                int(left / scale_factor)
            )]
            
            # Get face encoding from original size frame
            face_encodings = face_recognition.face_encodings(
                rgb_frame, 
                face_locations,
                num_jitters=self.num_jitters
            )
            
            if len(face_encodings) == 0:
                return {
                    'success': False,
                    'message': 'Could not encode face. Please try again with better lighting.'
                }
            
            encoding = face_encodings[0]
            
            # Check for duplicate faces
            if len(self.known_encodings) > 0:
                matches = face_recognition.compare_faces(
                    self.known_encodings, 
                    encoding, 
                    tolerance=0.5
                )
                if any(matches):
                    match_idx = matches.index(True)
                    return {
                        'success': False,
                        'message': f'This face is already enrolled for {self.known_names[match_idx]}'
                    }
            
            # Save to database
            encoding_blob = pickle.dumps(encoding)
            
            employee_data = {
                'full_name': full_name,
                'employee_id': employee_id,
                'face_encoding': encoding_blob,
                **kwargs
            }
            
            db_id = self.db.add_employee(**employee_data)
            
            if db_id:
                # Update in-memory cache
                with self.encodings_lock:
                    self.known_encodings.append(encoding)
                    self.known_names.append(full_name)
                    self.known_ids.append(db_id)
                
                return {
                    'success': True,
                    'message': f'Successfully enrolled {full_name}',
                    'employee_db_id': db_id
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to save to database. Employee ID may already exist.'
                }
                
        except Exception as e:
            logger.error(f"Error enrolling person: {e}")
            return {
                'success': False,
                'message': f'Enrollment error: {str(e)}'
            }
    
    def process_frame(self, frame):
        """
        Process video frame with face recognition - optimized version
        Returns frame with annotations
        """
        try:
            self.frame_counter += 1
            
            # Process only every Nth frame for performance
            if self.frame_counter % self.process_every_n_frames == 0:
                # Resize frame for faster processing
                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                
                # Find faces
                face_locations = face_recognition.face_locations(
                    rgb_small_frame,
                    model=self.detection_model
                )
                
                # Get face encodings
                face_encodings = face_recognition.face_encodings(
                    rgb_small_frame, 
                    face_locations,
                    num_jitters=1
                )
                
                # Scale back face locations
                self.last_face_locations = [
                    (top * 4, right * 4, bottom * 4, left * 4)
                    for (top, right, bottom, left) in face_locations
                ]
                
                # Recognize faces
                self.last_face_names = []
                
                with self.encodings_lock:
                    for face_encoding in face_encodings:
                        name = "Unknown"
                        
                        if len(self.known_encodings) > 0:
                            # Compare faces
                            matches = face_recognition.compare_faces(
                                self.known_encodings,
                                face_encoding,
                                tolerance=0.6
                            )
                            
                            # Find best match
                            face_distances = face_recognition.face_distance(
                                self.known_encodings,
                                face_encoding
                            )
                            
                            if len(face_distances) > 0:
                                best_match_index = np.argmin(face_distances)
                                
                                if matches[best_match_index]:
                                    name = self.known_names[best_match_index]
                                    employee_id = self.known_ids[best_match_index]
                                    
                                    # Log attendance
                                    self._log_attendance_async(employee_id, name)
                        
                        self.last_face_names.append(name)
            
            # Draw annotations on frame
            annotated_frame = self._draw_annotations(
                frame,
                self.last_face_locations,
                self.last_face_names
            )
            
            return annotated_frame
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
            return frame
    
    def _log_attendance_async(self, employee_id, name):
        """Log attendance asynchronously to avoid blocking"""
        try:
            current_time = datetime.now()
            
            # Check cooldown
            if employee_id in self.last_recognition:
                time_diff = current_time - self.last_recognition[employee_id]
                if time_diff < self.cooldown_period:
                    return
            
            # Update last recognition time
            self.last_recognition[employee_id] = current_time
            
            # Submit to thread pool
            self.executor.submit(self._log_attendance_worker, employee_id, name, current_time)
            
        except Exception as e:
            logger.error(f"Error in async attendance logging: {e}")
    
    def _log_attendance_worker(self, employee_id, name, timestamp):
        """Worker function for attendance logging"""
        try:
            # Determine status
            status = self._determine_attendance_status(timestamp.time())
            
            # Log to database
            self.db.log_attendance(employee_id, timestamp, status)
            
            # Send notification if configured
            if self.notifications:
                message = f"{name} clocked in at {timestamp.strftime('%H:%M:%S')} - {status}"
                self.notifications.send_notification(
                    'attendance',
                    message,
                    {'employee_id': employee_id, 'status': status}
                )
            
            logger.info(f"Attendance logged: {name} - {status}")
            
        except Exception as e:
            logger.error(f"Error in attendance worker: {e}")
    
    def _determine_attendance_status(self, time_obj):
        """Determine if attendance is on-time, late, or early"""
        grace_time = datetime.combine(
            datetime.today(),
            self.work_start_time
        ) + timedelta(minutes=self.grace_period_minutes)
        
        current_datetime = datetime.combine(datetime.today(), time_obj)
        work_start = datetime.combine(datetime.today(), self.work_start_time)
        
        if current_datetime <= grace_time:
            return 'ON-TIME'
        elif current_datetime <= datetime.combine(datetime.today(), self.work_end_time):
            return 'LATE'
        else:
            return 'AFTER-HOURS'
    
    def _draw_annotations(self, frame, face_locations, face_names):
        """Draw face detection boxes and names on frame"""
        for (top, right, bottom, left), name in zip(face_locations, face_names):
            # Choose color based on recognition
            if name == "Unknown":
                color = (0, 0, 255)  # Red
            else:
                color = (0, 255, 0)  # Green
            
            # Draw rectangle
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            
            # Draw label background
            cv2.rectangle(
                frame,
                (left, bottom - 35),
                (right, bottom),
                color,
                cv2.FILLED
            )
            
            # Draw text
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(
                frame,
                name,
                (left + 6, bottom - 6),
                font,
                0.6,
                (255, 255, 255),
                1
            )
        
        # Draw stats
        stats_text = f"Faces: {len(face_locations)} | FPS: ~{30 // self.process_every_n_frames}"
        cv2.putText(
            frame,
            stats_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )
        
        return frame
    
    def get_active_count(self):
        """Get count of employees who clocked in today"""
        try:
            from datetime import date
            attendance = self.db.get_attendance_by_date(date.today())
            return len(set(a['employee_id'] for a in attendance))
        except Exception as e:
            logger.error(f"Error getting active count: {e}")
            return 0
    
    def cleanup(self):
        """Clean up resources"""
        self.executor.shutdown(wait=False)
        logger.info("Face recognition system cleaned up")
