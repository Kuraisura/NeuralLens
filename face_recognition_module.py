"""
NEURAL EYE - Face Recognition Module (GPU-Accelerated)
======================================================
Core face detection, recognition, and tracking logic.

Architecture:
- YOLOv8-face on GPU for fast face DETECTION (~3ms per frame with RTX 4050)
- face_recognition (dlib) for face ENCODING (who is it) every N frames
- IoU tracker maintains identity between recognition frames
"""

import os
import cv2
import numpy as np
from datetime import datetime, timedelta
import pickle
import logging
import time

logger = logging.getLogger(__name__)

# Lazy imports
_face_recognition = None
_yolo_model = None


def _ensure_imports():
    """Lazy-load heavy dependencies."""
    global _face_recognition, _yolo_model

    if _face_recognition is None:
        try:
            import face_recognition as fr
            _face_recognition = fr
        except ImportError:
            logger.warning("face_recognition not installed - recognition disabled")

    if _yolo_model is None:
        try:
            from ultralytics import YOLO
            project_root = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(project_root, "yolov8n-face.pt"),
                os.path.join(project_root, "yolov8n.pt"),
                "yolov8n-face.pt",
                "yolov8n.pt",
            ]
            model_path = None
            for c in candidates:
                if os.path.exists(c):
                    model_path = c
                    break

            if model_path:
                _yolo_model = YOLO(model_path)
            else:
                logger.info("No local YOLO model found, downloading yolov8n-face.pt...")
                _yolo_model = YOLO("yolov8n-face.pt")

            import torch
            if torch.cuda.is_available():
                logger.info(f"YOLO loaded on GPU: {torch.cuda.get_device_name(0)}")
            else:
                logger.info("YOLO loaded on CPU")
        except Exception as e:
            logger.warning(f"Could not load YOLO model: {e}")
            _yolo_model = None


# ============================================================================
# IoU Face Tracker
# ============================================================================

class _FaceTracker:
    """Lightweight IoU-based tracker to match faces across frames."""

    def __init__(self, iou_threshold=0.3, max_age=30):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.tracks = {}
        self._next_id = 0
        self._frame_count = 0

    @staticmethod
    def _iou(box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0

    def update(self, boxes, names, confidences):
        """Match detected boxes to tracked faces."""
        self._frame_count += 1
        result = []

        for tid in self.tracks:
            self.tracks[tid]['seen'] = False

        matched_tracks = set()

        for i, det_box in enumerate(boxes):
            best_iou = 0
            best_tid = None
            for tid, trk in self.tracks.items():
                if tid in matched_tracks:
                    continue
                iou = self._iou(det_box, trk['bbox'])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            if best_tid is not None and best_iou >= self.iou_threshold:
                trk = self.tracks[best_tid]
                trk['bbox'] = det_box
                trk['seen'] = True
                trk['age'] = 0
                trk['last_seen'] = self._frame_count
                if names[i] is not None:
                    trk['name'] = names[i]
                    trk['conf'] = confidences[i]
                result.append((trk['name'], trk['conf']))
                matched_tracks.add(best_tid)
            else:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = {
                    'bbox': det_box,
                    'name': names[i],
                    'conf': confidences[i],
                    'seen': True,
                    'last_seen': self._frame_count,
                    'age': 0,
                }
                result.append((names[i], confidences[i]))
                matched_tracks.add(tid)

        stale = [t for t, trk in self.tracks.items()
                 if self._frame_count - trk['last_seen'] > self.max_age]
        for t in stale:
            del self.tracks[t]

        return result


# ============================================================================
# Face Recognition System
# ============================================================================

class FaceRecognitionSystem:
    """GPU-accelerated face recognition: YOLO detection + dlib encoding."""

    def __init__(self, database, notification_system=None, camera_index=0):
        self.db = database
        self.notifications = notification_system
        self.known_encodings = []
        self.known_names = []
        self.known_ids = []

        self.camera_index = camera_index

        # Attendance tracking
        self.last_recognition = {}
        self.cooldown_period = timedelta(seconds=10)

        # Work schedule (PHT)
        self.work_start_time = datetime.strptime("08:00:00", "%H:%M:%S").time()
        self.work_end_time = datetime.strptime("17:00:00", "%H:%M:%S").time()
        self.grace_period_minutes = 15

        # --- Config ---
        self.recognition_interval = 15    # Run encoding every N frames
        self.tolerance = 0.5              # Face matching tolerance
        self.encoding_scale = 0.25        # Downscale for faster encoding
        self.detection_confidence = 0.35  # YOLO detection confidence (lowered for glasses/lighting)
        self.iou_threshold = 0.3          # IoU for tracking
        self.max_track_age = 30           # Remove stale tracks

        # Internal state
        self._frame_count = 0
        self._tracker = _FaceTracker(self.iou_threshold, self.max_track_age)

        # Public state (read by app.py)
        self.last_face_locations = []
        self.last_face_names = []
        self.last_recognized_ids = []

        # Performance stats
        self.last_detection_ms = 0.0
        self.last_recognition_ms = 0.0
        self.last_total_ms = 0.0
        self.fps = 0.0
        self._fps_frame_count = 0
        self._fps_last_time = time.perf_counter()

        # Feature availability
        self.yolo_available = False
        self.face_recognition_available = False

        # Initialize YOLO model
        _ensure_imports()
        self.yolo_available = _yolo_model is not None
        self.face_recognition_available = _face_recognition is not None

        if self.yolo_available:
            logger.info("YOLOv8-face detector ready (GPU)")
        else:
            logger.warning("YOLO not available - detection disabled")

        if not self.face_recognition_available:
            logger.warning("face_recognition not installed - recognition disabled")

        # Load known faces
        if self.face_recognition_available:
            self.load_known_faces()

    @staticmethod
    def get_camera_capture(preferred_index=0):
        """Open camera with multi-backend fallback."""
        import threading as _threading

        indices = [preferred_index] + [i for i in range(3) if i != preferred_index]
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if os.name == 'nt' else [cv2.CAP_ANY]

        for idx in indices:
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if not cap.isOpened():
                        continue
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                    test_ok = [False]
                    def _test(c=cap):
                        ret, f = c.read()
                        test_ok[0] = ret and f is not None and f.size > 0
                    t = _threading.Thread(target=_test, daemon=True)
                    t.start()
                    t.join(timeout=5)

                    if t.is_alive() or not test_ok[0]:
                        try: cap.release()
                        except: pass
                        continue

                    logger.info(f"Camera opened: index={idx}, backend={backend}")
                    return cap
                except Exception as e:
                    try: cap.release()
                    except: pass

        logger.error("No working camera found")
        return None

    def load_known_faces(self):
        """Load face encodings from database."""
        try:
            employees = self.db.get_all_employees()
            self.known_encodings = []
            self.known_names = []
            self.known_ids = []

            for emp in employees:
                if emp.get('face_encoding'):
                    encoding = pickle.loads(emp['face_encoding'])
                    self.known_encodings.append(encoding)
                    self.known_names.append(emp['full_name'])
                    self.known_ids.append(emp['id'])

            logger.info(f"Loaded {len(self.known_encodings)} face encodings")
        except Exception as e:
            logger.error(f"Error loading face encodings: {e}")

    def reload_faces(self):
        """Reload face encodings from database."""
        self.load_known_faces()

    # ------------------------------------------------------------------
    # Detection (YOLOv8 on GPU — same as standalone script)
    # ------------------------------------------------------------------

    def _detect_faces(self, frame):
        """
        Face detection using YOLOv8 on GPU.
        Uses yolov8n.pt which detects 'person' class (class 0).
        Returns bounding boxes around detected persons/faces.
        """
        h, w = frame.shape[:2]
        boxes = []

        # YOLOv8-face detection on GPU (detects FACE class directly)
        if _yolo_model is not None:
            try:
                results = _yolo_model.predict(
                    source=frame,
                    conf=0.5,
                    verbose=False,
                    device=0,
                )

                for result in results:
                    if result.boxes is None:
                        continue
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        x1 = max(0, min(x1, w - 1))
                        y1 = max(0, min(y1, h - 1))
                        x2 = max(0, min(x2, w - 1))
                        y2 = max(0, min(y2, h - 1))
                        if x2 > x1 and y2 > y1:
                            boxes.append((x1, y1, x2, y2))

            except Exception as e:
                logger.debug(f"[Detection] YOLO error: {e}")

        # Keep only the largest face (closest person)
        if len(boxes) > 1:
            boxes.sort(key=lambda b: (b[2]-b[0]) * (b[3]-b[1]), reverse=True)
            boxes = [boxes[0]]

        # Fallback: face_recognition HOG if YOLO finds nothing
        if not boxes and _face_recognition is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = _face_recognition.face_locations(rgb, model='hog')
                for (top, right, bottom, left) in face_locations:
                    x1 = max(0, left)
                    y1 = max(0, top)
                    x2 = min(w, right)
                    y2 = min(h, bottom)
                    if x2 > x1 and y2 > y1:
                        boxes.append((x1, y1, x2, y2))
                logger.debug(f"[Detection] HOG fallback: {len(boxes)} face(s)")
            except Exception:
                pass

        logger.debug(f"[Detection] Final count: {len(boxes)}")
        return boxes

    # ------------------------------------------------------------------
    # Recognition (face_recognition on CPU - runs every N frames)
    # ------------------------------------------------------------------

    def _recognize_faces(self, frame, boxes):
        """Encode faces and match against known database."""
        if not self.known_encodings or not boxes or _face_recognition is None:
            return [None] * len(boxes), [0.0] * len(boxes), [None] * len(boxes)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        names = []
        confidences = []
        emp_ids = []

        for (x1, y1, x2, y2) in boxes:
            face_region = rgb[y1:y2, x1:x2]
            if face_region.size == 0:
                names.append(None)
                confidences.append(0.0)
                emp_ids.append(None)
                continue

            # Downscale for faster encoding
            small = cv2.resize(face_region, (0, 0),
                               fx=self.encoding_scale, fy=self.encoding_scale)

            try:
                encs = _face_recognition.face_encodings(small, model='hog', num_jitters=1)
            except Exception:
                names.append(None)
                confidences.append(0.0)
                emp_ids.append(None)
                continue

            if not encs:
                names.append(None)
                confidences.append(0.0)
                emp_ids.append(None)
                continue

            dists = _face_recognition.face_distance(self.known_encodings, encs[0])
            best = np.argmin(dists)
            best_dist = dists[best]

            if best_dist < self.tolerance:
                conf = 1.0 - best_dist
                names.append(self.known_names[best])
                confidences.append(conf)
                emp_ids.append(self.known_ids[best])
            else:
                names.append(None)
                confidences.append(0.0)
                emp_ids.append(None)

        return names, confidences, emp_ids

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def process_frame(self, frame, skip_overlay=False):
        """
        Process frame: YOLO detect (every frame) -> encode (every N frames) -> track.
        Returns annotated frame.
        
        Args:
            frame: Input frame
            skip_overlay: If True, skip HUD overlay (for enrollment camera)
        """
        if frame is None:
            return frame

        t_start = time.perf_counter()
        self._frame_count += 1
        annotate = frame.copy()

        # Step 1: YOLO face detection (GPU, ~3ms)
        t_det = time.perf_counter()
        boxes = self._detect_faces(frame)
        self.last_detection_ms = (time.perf_counter() - t_det) * 1000

        # Step 2: Face recognition (CPU, every N frames)
        do_recognize = (self._frame_count % self.recognition_interval == 0)

        names = [None] * len(boxes)
        confs = [0.0] * len(boxes)
        emp_ids = [None] * len(boxes)

        t_rec = time.perf_counter()
        if do_recognize and boxes and self.face_recognition_available:
            names, confs, emp_ids = self._recognize_faces(frame, boxes)
        self.last_recognition_ms = (time.perf_counter() - t_rec) * 1000 if do_recognize else 0.0

        # Step 3: IoU tracking
        tracked = self._tracker.update(boxes, names, confs)

        # Build public state
        self.last_face_locations = list(boxes)
        self.last_face_names = []
        self.last_recognized_ids = []

        for i, (name, conf) in enumerate(tracked):
            self.last_face_names.append(name if name else "Unknown")
            self.last_recognized_ids.append(emp_ids[i] if i < len(emp_ids) else None)
            if name and emp_ids[i]:
                self._log_attendance(emp_ids[i], name)

        # Draw annotations
        for i, (name, conf) in enumerate(tracked):
            if i < len(boxes):
                x1, y1, x2, y2 = boxes[i]
                self._draw_face(annotate, x1, y1, x2, y2, name, conf)

        self.last_total_ms = (time.perf_counter() - t_start) * 1000

        # Update FPS
        self._fps_frame_count += 1
        now = time.perf_counter()
        if now - self._fps_last_time >= 1.0:
            self.fps = self._fps_frame_count / (now - self._fps_last_time)
            self._fps_frame_count = 0
            self._fps_last_time = now

        self._add_hud_overlay(annotate, skip=skip_overlay)
        return annotate

    def _draw_face(self, frame, x1, y1, x2, y2, name, confidence):
        """Draw face bounding box and label — red UNRECOGNIZED style."""
        if name and name != "Unknown":
            color = (0, 255, 136)  # Green for recognized
            label = f"{name} ({confidence:.0%})"
        else:
            color = (0, 0, 255)  # Red for unrecognized (BGR format)
            label = "UNRECOGNIZED"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 10, y1), color, cv2.FILLED)
        cv2.putText(frame, label, (x1 + 5, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------

    def _log_attendance(self, employee_db_id, name):
        """Log attendance if cooldown period has passed."""
        now = datetime.now()

        if employee_db_id in self.last_recognition:
            last_seen = self.last_recognition[employee_db_id]
            if now - last_seen < self.cooldown_period:
                return

        self.last_recognition[employee_db_id] = now
        existing_log = self.db.get_today_log(employee_db_id)

        if existing_log is None:
            status = self.calculate_status(now)
            self.db.add_attendance_log(employee_db_id, 'clock_in', status)
            logger.info(f"Clocked IN: {name} at {now.strftime('%H:%M:%S')} - Status: {status}")

            if status == "LATE" and self.notifications:
                try:
                    employee = self.db.get_employee(employee_db_id)
                    if employee and employee.get('email'):
                        self.notifications.notify_late_arrival(name, employee['email'], now)
                except Exception as e:
                    logger.warning(f"Failed to send late arrival notification: {e}")

        elif existing_log and existing_log.get('clock_out') is None:
            clock_in_time = datetime.fromisoformat(existing_log['clock_in'])
            time_elapsed = now - clock_in_time
            if time_elapsed > timedelta(seconds=30):
                status = self.calculate_status(existing_log['clock_in'], now)
                self.db.clock_out_employee(employee_db_id, status)
                logger.info(f"Clocked OUT: {name} at {now.strftime('%H:%M:%S')} - Status: {status}")

    def calculate_status(self, clock_in_time, clock_out_time=None):
        """Calculate attendance status."""
        if not clock_in_time:
            return "SYNCING"

        clock_in_dt = datetime.fromisoformat(clock_in_time) if isinstance(clock_in_time, str) else clock_in_time
        clock_in_time_only = clock_in_dt.time()

        grace_end = (datetime.combine(datetime.today(), self.work_start_time) +
                     timedelta(minutes=self.grace_period_minutes)).time()

        if clock_out_time:
            clock_out_dt = datetime.fromisoformat(clock_out_time) if isinstance(clock_out_time, str) else clock_out_time
            clock_out_time_only = clock_out_dt.time()
            if clock_out_time_only < self.work_end_time:
                return "UNDERTIME"
            overtime_threshold = (datetime.combine(datetime.today(), self.work_end_time) +
                                  timedelta(hours=1)).time()
            if clock_out_time_only > overtime_threshold:
                return "OVERTIME"
            return "ON-TIME"

        if clock_in_time_only > grace_end:
            return "LATE"
        return "ON-TIME"

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------

    def _add_hud_overlay(self, frame, skip=False):
        """Add HUD elements to the frame. Skip if skip=True (for enrollment)."""
        if skip:
            return
        # HUD overlay removed — clean video feed
        pass

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------

    def enroll_person(self, frame, full_name, employee_id, **kwargs):
        """Enroll a new person: detect face with YOLO, encode with face_recognition."""
        if _face_recognition is None:
            return {
                'success': False,
                'message': 'Face recognition library not installed.'
            }
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Detect face with YOLO
            if self.yolo_available:
                boxes = self._detect_faces(frame)
                if len(boxes) == 0:
                    return {'success': False, 'message': 'No face detected. Please ensure your face is visible.'}
                if len(boxes) > 1:
                    return {'success': False, 'message': 'Multiple faces detected. Please ensure only one person is in frame.'}
                x1, y1, x2, y2 = boxes[0]
                face_locations = [(y1, x2, y2, x1)]
            else:
                face_locations = _face_recognition.face_locations(rgb_frame, model='hog')
                if len(face_locations) == 0:
                    return {'success': False, 'message': 'No face detected.'}
                if len(face_locations) > 1:
                    return {'success': False, 'message': 'Multiple faces detected.'}

            face_encodings = _face_recognition.face_encodings(rgb_frame, face_locations)
            if not face_encodings:
                return {'success': False, 'message': 'Could not encode face.'}

            encoding = face_encodings[0]

            # Check if already enrolled
            if self.known_encodings:
                matches = _face_recognition.compare_faces(self.known_encodings, encoding, tolerance=0.5)
                if True in matches:
                    matched_idx = matches.index(True)
                    return {'success': False, 'message': f'Face already enrolled as {self.known_names[matched_idx]}'}

            encoding_bytes = pickle.dumps(encoding)

            employee_data = {
                'full_name': full_name,
                'employee_id': employee_id,
                'face_encoding': encoding_bytes
            }

            for key, value in kwargs.items():
                if key == 'photo':
                    continue
                if value is not None:
                    employee_data[key] = value

            emp_db_id = self.db.add_employee_extended(**employee_data)

            if emp_db_id:
                self.known_encodings.append(encoding)
                self.known_names.append(full_name)
                self.known_ids.append(emp_db_id)
                logger.info(f"Enrolled new employee: {full_name} (ID: {employee_id})")
                return {'success': True, 'message': f'Successfully enrolled {full_name}', 'employee_id': emp_db_id}
            else:
                return {'success': False, 'message': 'Failed to save to database.'}

        except Exception as e:
            logger.error(f"Error enrolling person: {e}")
            return {'success': False, 'message': f'Enrollment error: {str(e)}'}

    def enroll_person_multi(self, frames_dict, full_name, employee_id, **kwargs):
        """Enroll with multiple face angles (front, left, right).
        
        Args:
            frames_dict: {'front': frame, 'left': frame, 'right': frame}
            full_name: Employee name
            employee_id: Employee ID
            **kwargs: Additional fields for database
        
        Returns:
            dict with success status
        """
        if _face_recognition is None:
            return {'success': False, 'message': 'Face recognition library not installed.'}
        
        try:
            encodings = {}
            for angle, frame in frames_dict.items():
                if frame is None:
                    continue
                
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                if self.yolo_available:
                    boxes = self._detect_faces(frame)
                    if len(boxes) == 0:
                        return {'success': False, 'message': f'No face detected in {angle} angle. Please try again.'}
                    if len(boxes) > 1:
                        return {'success': False, 'message': f'Multiple faces in {angle} angle. Only one person allowed.'}
                    x1, y1, x2, y2 = boxes[0]
                    face_locations = [(y1, x2, y2, x1)]
                else:
                    face_locations = _face_recognition.face_locations(rgb_frame, model='hog')
                    if len(face_locations) == 0:
                        return {'success': False, 'message': f'No face detected in {angle} angle.'}
                    if len(face_locations) > 1:
                        return {'success': False, 'message': f'Multiple faces in {angle} angle.'}
                
                face_encodings = _face_recognition.face_encodings(rgb_frame, face_locations)
                if not face_encodings:
                    return {'success': False, 'message': f'Could not encode face in {angle} angle.'}
                
                encodings[angle] = face_encodings[0]
            
            if 'front' not in encodings:
                return {'success': False, 'message': 'Front face capture is required.'}
            
            # Check if already enrolled
            if self.known_encodings:
                matches = _face_recognition.compare_faces(self.known_encodings, encodings['front'], tolerance=0.5)
                if True in matches:
                    matched_idx = matches.index(True)
                    return {'success': False, 'message': f'Face already enrolled as {self.known_names[matched_idx]}'}
            
            # Save encodings
            employee_data = {
                'full_name': full_name,
                'employee_id': employee_id,
                'face_encoding': pickle.dumps(encodings['front']),
            }
            
            if 'left' in encodings:
                employee_data['face_encoding_left'] = pickle.dumps(encodings['left'])
            if 'right' in encodings:
                employee_data['face_encoding_right'] = pickle.dumps(encodings['right'])
            
            for key, value in kwargs.items():
                if key in ('photo', 'frame'):
                    continue
                if value is not None:
                    employee_data[key] = value
            
            emp_db_id = self.db.add_employee_extended(**employee_data)
            
            if emp_db_id:
                self.known_encodings.append(encodings['front'])
                self.known_names.append(full_name)
                self.known_ids.append(emp_db_id)
                logger.info(f"Enrolled new employee (multi-angle): {full_name} (ID: {employee_id})")
                return {'success': True, 'message': f'Successfully enrolled {full_name}', 'employee_id': emp_db_id}
            else:
                return {'success': False, 'message': 'Failed to save to database.'}
        
        except Exception as e:
            logger.error(f"Error in multi-angle enrollment: {e}")
            return {'success': False, 'message': f'Enrollment error: {str(e)}'}

    def enroll_person_mock(self, full_name, employee_id, **kwargs):
        """Enroll a person without face data (mock mode)."""
        try:
            dummy_encoding = np.random.rand(128)
            encoding_bytes = pickle.dumps(dummy_encoding)

            extra = {k: v for k, v in kwargs.items() if v not in (None, '')}
            extra.pop('department', None)
            extra.pop('position', None)

            dept_name = extra.pop('department_id', None) or extra.pop('department', 'General')
            pos_name = extra.pop('position_id', None) or extra.pop('position', 'Staff')

            emp_db_id = self.db.add_employee(
                full_name=full_name,
                employee_id=employee_id,
                department=dept_name,
                position=pos_name,
                face_encoding=encoding_bytes,
                **extra
            )

            if emp_db_id:
                self.known_encodings.append(dummy_encoding)
                self.known_names.append(full_name)
                self.known_ids.append(emp_db_id)
                logger.info(f"[MOCK] Enrolled new employee: {full_name} (ID: {employee_id})")
                return {'success': True, 'message': f'Successfully enrolled {full_name} (Mock Mode)',
                        'employee_id': emp_db_id, 'mode': 'mock'}
            else:
                return {'success': False, 'message': 'Failed to save to database.'}
        except Exception as e:
            logger.error(f"Error in mock enrollment: {e}")
            return {'success': False, 'message': f'Enrollment error: {str(e)}'}

    def get_active_count(self):
        """Get count of currently recognized faces."""
        return len([n for n in self.last_face_names if n and n != "Unknown"])
