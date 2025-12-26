"""
NEURAL EYE - Real-Time Face Recognition (DroidCam & Webcam)
=============================================================
Complete face recognition pipeline cloned from the main Flask app.
Optimized for DroidCam network streams with threaded frame capture.

Pipeline:
  Haar cascade (face detection) -> face_recognition (encoding) -> DB matching

Usage:
    py -3.12 yolo_face_detect.py                                         # Webcam 0
    py -3.12 yolo_face_detect.py --source 1                              # Webcam 1
    py -3.12 yolo_face_detect.py --source http://192.168.1.5:4747/video  # DroidCam
    py -3.12 yolo_face_detect.py --source rtsp://...                     # RTSP
    py -3.12 yolo_face_detect.py --db neural_eye.db --tolerance 0.45    # Custom DB
"""

import cv2
import numpy as np
import threading
import time
import argparse
import sys
import os
import pickle
import sqlite3
from datetime import datetime, timedelta

# ============================================================================
# Threaded Video Capture (eliminates network stream latency)
# ============================================================================

class ThreadedCapture:
    """
    Background thread that continuously reads frames from a video source.
    Always keeps only the LATEST frame — old frames are discarded.
    This eliminates the buffering delay typical of network streams (DroidCam, RTSP).
    """

    def __init__(self, source, backend=cv2.CAP_ANY):
        self.source = source
        self.backend = backend
        self.frame = None
        self.grabbed = False
        self.running = False
        self.lock = threading.Lock()
        self.cap = None
        self.thread = None
        self.fps_read = 0.0
        self._frame_count = 0
        self._fps_timer = time.perf_counter()

    def start(self):
        """Open capture and start background reader thread."""
        if isinstance(self.source, str) and self.source.isdigit():
            self.source = int(self.source)

        if isinstance(self.source, int):
            # USB webcam — try DirectShow first (Windows), then MSMF, then ANY
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
            for be in backends:
                self.cap = cv2.VideoCapture(self.source, be)
                if self.cap.isOpened():
                    self.backend = be
                    break
        else:
            # Network stream — FFMPEG backend for lower latency
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)

        if not self.cap or not self.cap.isOpened():
            print(f"[ERROR] Cannot open video source: {self.source}")
            return False

        # Optimize buffer for minimal latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Test read with timeout
        test_ok = [False]
        def _test():
            ret, f = self.cap.read()
            test_ok[0] = ret and f is not None and f.size > 0
        t = threading.Thread(target=_test, daemon=True)
        t.start()
        t.join(timeout=5.0)

        if not test_ok[0]:
            print(f"[ERROR] Cannot read from source: {self.source}")
            self.cap.release()
            return False

        # Read initial frame
        ret, frame = self.cap.read()
        self.grabbed = ret
        self.frame = frame
        self.running = True

        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

        src_type = "Webcam" if isinstance(self.source, int) else "Network"
        print(f"  Source type    : {src_type}")
        print(f"  Source         : {self.source}")
        print(f"  Backend        : {self.backend}")
        print(f"  Resolution     : {int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        return True

    def _reader(self):
        """Background thread: grab frames as fast as possible, keep only latest."""
        while self.running:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            with self.lock:
                self.frame = frame
                self.grabbed = True

            self._frame_count += 1
            elapsed = time.perf_counter() - self._fps_timer
            if elapsed >= 1.0:
                self.fps_read = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_timer = time.perf_counter()

    def read(self):
        """Get the latest frame (non-blocking)."""
        with self.lock:
            if self.frame is None:
                return False, None
            return self.grabbed, self.frame.copy()

    def stop(self):
        """Stop reader and release capture."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()

    @property
    def is_opened(self):
        return self.cap is not None and self.cap.isOpened()


# ============================================================================
# Face Detection (YOLOv8-face on GPU — detects faces directly)
# ============================================================================

class FaceDetector:
    """
    Face detection using YOLOv8-face on GPU.
    Model trained specifically on faces — no hybrid needed.
    """

    def __init__(self, model_path="yolov8n-face.pt", confidence=0.5):
        self.confidence = confidence
        self.model = None
        self._fr = None

        # Load YOLO model
        try:
            from ultralytics import YOLO
            import torch

            print(f"  CUDA Available : {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                print(f"  GPU Device     : {torch.cuda.get_device_name(0)}")

            self.model = YOLO(model_path)
            print(f"  YOLO model     : loaded ({model_path})")
            print(f"  Detected class : {self.model.names}")
            print(f"  Device         : {'GPU (CUDA)' if torch.cuda.is_available() else 'CPU'}")
        except Exception as e:
            print(f"[ERROR] Failed to load YOLO: {e}")
            sys.exit(1)

        # HOG fallback
        try:
            import face_recognition
            self._fr = face_recognition
            print("  HOG fallback  : available")
        except ImportError:
            print("  HOG fallback  : not available")

    def detect(self, frame):
        """
        Detect faces using YOLOv8-face on GPU.
        Returns list of (x1, y1, x2, y2) tuples — FACE-sized boxes.
        """
        if self.model is None or frame is None:
            return []

        h, w = frame.shape[:2]
        boxes = []

        try:
            results = self.model.predict(
                source=frame,
                conf=self.confidence,
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

            # Keep only the largest face
            if len(boxes) > 1:
                boxes.sort(key=lambda b: (b[2]-b[0]) * (b[3]-b[1]), reverse=True)
                boxes = [boxes[0]]

        except Exception as e:
            print(f"[Detection Error] {e}")

        # HOG fallback
        if not boxes and self._fr is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = self._fr.face_locations(rgb, model='hog')
                for (top, right, bottom, left) in face_locations:
                    x1 = max(0, left)
                    y1 = max(0, top)
                    x2 = min(w, right)
                    y2 = min(h, bottom)
                    if x2 > x1 and y2 > y1:
                        boxes.append((x1, y1, x2, y2))
            except Exception:
                pass

        return boxes


# ============================================================================
# Face Recognition (face_recognition library — same as main app)
# ============================================================================

class FaceRecognizer:
    """
    Face encoding and matching against known faces from database.
    Cloned from face_recognition_module.py _recognize_faces().
    """

    def __init__(self, tolerance=0.5, encoding_scale=0.25, recognition_interval=15):
        self.tolerance = tolerance
        self.encoding_scale = encoding_scale
        self.recognition_interval = recognition_interval

        self.known_encodings = []
        self.known_names = []
        self.known_ids = []

        self._frame_count = 0

        # Try to import face_recognition
        self._fr = None
        try:
            import face_recognition
            self._fr = face_recognition
        except ImportError:
            print("[WARNING] face_recognition not installed — recognition disabled")

    def load_from_db(self, db_path):
        """Load face encodings from SQLite database."""
        if not os.path.exists(db_path):
            print(f"[WARNING] Database not found: {db_path}")
            return 0

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, full_name, face_encoding FROM employees WHERE face_encoding IS NOT NULL")
            rows = cursor.fetchall()
            conn.close()

            self.known_encodings = []
            self.known_names = []
            self.known_ids = []

            for row in rows:
                encoding = pickle.loads(row['face_encoding'])
                self.known_encodings.append(encoding)
                self.known_names.append(row['full_name'])
                self.known_ids.append(row['id'])

            print(f"  Loaded faces  : {len(self.known_encodings)} from {db_path}")
            return len(self.known_encodings)
        except Exception as e:
            print(f"[ERROR] Failed to load database: {e}")
            return 0

    def recognize(self, frame, boxes):
        """
        Encode faces and match against known database.
        Returns (names, confidences, emp_ids) lists.
        """
        self._frame_count += 1
        do_recognize = (self._frame_count % self.recognition_interval == 0)

        if not do_recognize or not self.known_encodings or not boxes or self._fr is None:
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
                encs = self._fr.face_encodings(small, model='hog', num_jitters=1)
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

            dists = self._fr.face_distance(self.known_encodings, encs[0])
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


# ============================================================================
# IoU Face Tracker (same as main app)
# ============================================================================

class FaceTracker:
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
# Attendance Logger (same logic as main app)
# ============================================================================

class AttendanceLogger:
    """Log attendance to console (mirrors main app _log_attendance)."""

    def __init__(self, cooldown_seconds=10):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.last_recognition = {}
        self.work_start = datetime.strptime("08:00", "%H:%M").time()
        self.work_end = datetime.strptime("17:00", "%H:%M").time()
        self.grace_minutes = 15

    def log(self, name, emp_id):
        """Log recognition event with cooldown."""
        now = datetime.now()

        if emp_id in self.last_recognition:
            if now - self.last_recognition[emp_id] < self.cooldown:
                return

        self.last_recognition[emp_id] = now
        status = self._calculate_status(now)
        time_str = now.strftime("%I:%M:%S %p")

        print(f"  [ATTENDANCE] {name} | {time_str} | {status}")

    def _calculate_status(self, now):
        grace_end = (datetime.combine(now.date(), self.work_start) +
                     timedelta(minutes=self.grace_minutes)).time()
        if now.time() > grace_end:
            return "LATE"
        return "ON-TIME"


# ============================================================================
# FPS Counter
# ============================================================================

class FPSCounter:
    """Smooth FPS calculation using rolling average."""

    def __init__(self, smooth=0.9):
        self.smooth = smooth
        self.fps = 0.0
        self._frame_count = 0
        self._last_time = time.perf_counter()

    def update(self):
        self._frame_count += 1
        now = time.perf_counter()
        elapsed = now - self._last_time
        if elapsed >= 0.5:
            instant_fps = self._frame_count / elapsed
            self.fps = self.fps * self.smooth + instant_fps * (1 - self.smooth)
            self._frame_count = 0
            self._last_time = now

    def get(self):
        return self.fps


# ============================================================================
# Drawing Utilities
# ============================================================================

def draw_results(frame, boxes, names, confs, fps, read_fps, det_ms, rec_ms):
    """Draw face boxes, names, and HUD overlay — red UNRECOGNIZED style."""
    h, w = frame.shape[:2]

    for i, (x1, y1, x2, y2) in enumerate(boxes):
        name = names[i] if i < len(names) else None
        conf = confs[i] if i < len(confs) else 0.0

        if name and name != "Unknown":
            color = (0, 255, 136)  # Green = recognized
            label = f"{name} ({conf:.0%})"
        else:
            color = (0, 0, 255)  # Red = UNRECOGNIZED (BGR format)
            label = "UNRECOGNIZED"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, cv2.FILLED)
        cv2.putText(frame, label, (x1 + 4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    # HUD overlay
    y = 25
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    y += 25
    cv2.putText(frame, f"Read: {read_fps:.1f}", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    y += 22
    cv2.putText(frame, f"Det: {det_ms:.1f}ms  Rec: {rec_ms:.1f}ms", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    y += 22
    cv2.putText(frame, f"Faces: {len(boxes)}", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # Timestamp
    ts = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    cv2.putText(frame, ts, (w - 250, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    return frame


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="NEURAL EYE - Face Recognition (DroidCam & Webcam)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py -3.12 yolo_face_detect.py                                         # Webcam 0
  py -3.12 yolo_face_detect.py --source 1                              # Webcam 1
  py -3.12 yolo_face_detect.py --source http://192.168.1.5:4747/video  # DroidCam
  py -3.12 yolo_face_detect.py --tolerance 0.45                        # Stricter matching
        """
    )
    parser.add_argument("--source", type=str, default="0",
                        help="Webcam index (0,1,2) or URL (http://.../video)")
    parser.add_argument("--db", type=str, default="neural_eye.db",
                        help="SQLite database path (default: neural_eye.db)")
    parser.add_argument("--conf", type=float, default=0.5,
                        help="Detection confidence threshold (default: 0.5)")
    parser.add_argument("--tolerance", type=float, default=0.5,
                        help="Face matching tolerance (lower = stricter, default: 0.5)")
    parser.add_argument("--width", type=int, default=640,
                        help="Capture width (default: 640)")
    parser.add_argument("--height", type=int, default=480,
                        help="Capture height (default: 480)")
    parser.add_argument("--rec-interval", type=int, default=15,
                        help="Run recognition every N frames (default: 15)")
    args = parser.parse_args()

    print("=" * 60)
    print("  NEURAL EYE - Face Recognition")
    print("=" * 60)

    # Initialize components
    print("\n[1/5] Face Detector")
    detector = FaceDetector()

    print("\n[2/5] Face Recognizer")
    recognizer = FaceRecognizer(
        tolerance=args.tolerance,
        recognition_interval=args.rec_interval
    )

    print("\n[3/5] Database")
    count = recognizer.load_from_db(args.db)

    print("\n[4/5] Tracker")
    tracker = FaceTracker()
    print("  IoU tracker   : ready")

    print("\n[5/5] Video Capture")
    source = args.source
    if source.isdigit():
        source = int(source)

    capture = ThreadedCapture(source)
    if not capture.start():
        print("[FATAL] Cannot start video capture")
        sys.exit(1)

    # Attendance logger
    attendance = AttendanceLogger()

    print(f"\n{'='*60}")
    print(f"  Recognition  : {'ON' if recognizer._fr else 'OFF (detection only)'}")
    print(f"  Known faces  : {count}")
    print(f"  Tolerance    : {args.tolerance}")
    print(f"  Resolution   : {args.width}x{args.height}")
    print(f"{'='*60}")
    print(f"\nControls: 'q' = quit | 's' = screenshot | 'r' = reload faces\n")

    fps_counter = FPSCounter()
    frame_num = 0
    last_det_ms = 0.0
    last_rec_ms = 0.0

    try:
        while True:
            ret, frame = capture.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            frame = cv2.resize(frame, (args.width, args.height))

            # Step 1: Detect faces
            t0 = time.perf_counter()
            boxes = detector.detect(frame)
            last_det_ms = (time.perf_counter() - t0) * 1000

            # Step 2: Recognize faces
            t1 = time.perf_counter()
            names, confs, emp_ids = recognizer.recognize(frame, boxes)
            last_rec_ms = (time.perf_counter() - t1) * 1000

            # Step 3: IoU tracking
            tracked = tracker.update(boxes, names, confs)

            # Step 4: Log attendance
            for i, (name, conf) in enumerate(tracked):
                if name and i < len(emp_ids) and emp_ids[i]:
                    attendance.log(name, emp_ids[i])

            # Step 5: Draw results
            tracked_names = [t[0] for t in tracked]
            tracked_confs = [t[1] for t in tracked]
            fps_counter.update()

            frame = draw_results(
                frame, boxes, tracked_names, tracked_confs,
                fps_counter.get(), capture.fps_read,
                last_det_ms, last_rec_ms
            )

            cv2.imshow("NEURAL EYE - Face Recognition", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f"screenshot_{int(time.time())}.jpg"
                cv2.imwrite(filename, frame)
                print(f"  [SCREENSHOT] {filename}")
            elif key == ord('r'):
                recognizer.load_from_db(args.db)
                print("  [RELOAD] Faces reloaded from database")

            frame_num += 1

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        capture.stop()
        cv2.destroyAllWindows()
        print(f"\nProcessed {frame_num} frames")


if __name__ == "__main__":
    main()
