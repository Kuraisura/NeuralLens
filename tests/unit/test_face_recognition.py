"""
Unit Tests for Face Recognition System
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from face_recognition_module import FaceRecognitionSystem


class TestFaceRecognitionSystem(unittest.TestCase):
    """Test cases for FaceRecognitionSystem"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.mock_notifications = Mock()
        self.face_system = FaceRecognitionSystem(self.mock_db, self.mock_notifications)
    
    def test_initialization(self):
        """Test system initialization"""
        self.assertIsNotNone(self.face_system)
        self.assertEqual(len(self.face_system.known_encodings), 0)
        self.assertEqual(len(self.face_system.known_names), 0)
    
    def test_load_known_faces(self):
        """Test loading face encodings from database"""
        # Mock employee data
        mock_employees = [
            {
                'id': 1,
                'first_name': 'John',
                'last_name': 'Doe',
                'face_encoding': np.random.rand(128).tobytes()
            },
            {
                'id': 2,
                'first_name': 'Jane',
                'last_name': 'Smith',
                'face_encoding': np.random.rand(128).tobytes()
            }
        ]
        
        self.mock_db.get_all_employees.return_value = mock_employees
        
        self.face_system.load_known_faces()
        
        self.assertEqual(len(self.face_system.known_encodings), 2)
        self.assertEqual(len(self.face_system.known_names), 2)
        self.assertEqual(self.face_system.known_names[0], 'John Doe')
    
    @patch('face_recognition.face_locations')
    @patch('face_recognition.face_encodings')
    def test_process_frame_no_faces(self, mock_encodings, mock_locations):
        """Test processing frame with no faces"""
        mock_locations.return_value = []
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = self.face_system.process_frame(frame)
        
        self.assertEqual(len(result), 0)
    
    @patch('face_recognition.face_locations')
    @patch('face_recognition.face_encodings')
    @patch('face_recognition.compare_faces')
    def test_process_frame_with_known_face(self, mock_compare, mock_encodings, mock_locations):
        """Test processing frame with known face"""
        # Setup mocks
        mock_locations.return_value = [(0, 100, 100, 0)]
        mock_encoding = np.random.rand(128)
        mock_encodings.return_value = [mock_encoding]
        mock_compare.return_value = [True]
        
        # Load one known face
        self.face_system.known_encodings = [np.random.rand(128)]
        self.face_system.known_names = ['Test User']
        self.face_system.known_ids = [1]
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = self.face_system.process_frame(frame)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Test User')
    
    def test_check_cooldown_active(self):
        """Test cooldown period check"""
        employee_id = 1
        self.face_system.last_recognition[employee_id] = datetime.now()
        
        is_cooled_down = self.face_system.check_cooldown(employee_id)
        
        self.assertFalse(is_cooled_down)
    
    def test_check_cooldown_expired(self):
        """Test expired cooldown period"""
        employee_id = 1
        self.face_system.last_recognition[employee_id] = datetime.now() - timedelta(seconds=15)
        
        is_cooled_down = self.face_system.check_cooldown(employee_id)
        
        self.assertTrue(is_cooled_down)
    
    def test_is_tardy_on_time(self):
        """Test tardiness check - on time"""
        # 8:05 AM (within grace period)
        timestamp = datetime.now().replace(hour=8, minute=5, second=0, microsecond=0)
        
        is_tardy = self.face_system.is_tardy(timestamp)
        
        self.assertFalse(is_tardy)
    
    def test_is_tardy_late(self):
        """Test tardiness check - late"""
        # 8:20 AM (beyond grace period)
        timestamp = datetime.now().replace(hour=8, minute=20, second=0, microsecond=0)
        
        is_tardy = self.face_system.is_tardy(timestamp)
        
        self.assertTrue(is_tardy)
    
    def test_enroll_face_success(self):
        """Test successful face enrollment"""
        employee_id = 1
        images = [np.random.rand(480, 640, 3) for _ in range(5)]
        
        with patch('face_recognition.face_encodings') as mock_encodings:
            mock_encodings.side_effect = [[np.random.rand(128)] for _ in range(5)]
            self.mock_db.update_face_encoding.return_value = True
            
            result = self.face_system.enroll_face(employee_id, images)
            
            self.assertTrue(result)
            self.mock_db.update_face_encoding.assert_called_once()
    
    def test_enroll_face_no_face_detected(self):
        """Test enrollment failure - no face detected"""
        employee_id = 1
        images = [np.random.rand(480, 640, 3)]
        
        with patch('face_recognition.face_encodings') as mock_encodings:
            mock_encodings.return_value = []
            
            result = self.face_system.enroll_face(employee_id, images)
            
            self.assertFalse(result)


class TestDatabaseIntegration(unittest.TestCase):
    """Test database operations (integration tests)"""
    
    def setUp(self):
        """Set up test database"""
        # These would use a test database
        pass
    
    def test_create_employee(self):
        """Test employee creation"""
        pass
    
    def test_log_attendance(self):
        """Test attendance logging"""
        pass


class TestAuthenticationSystem(unittest.TestCase):
    """Test authentication and authorization"""
    
    def test_password_hashing(self):
        """Test password hashing"""
        from auth import hash_password, verify_password
        
        password = "TestPassword123!"
        hashed = hash_password(password)
        
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))
    
    def test_jwt_generation(self):
        """Test JWT token generation and verification"""
        pass


class TestPerformance(unittest.TestCase):
    """Performance tests"""
    
    def test_recognition_speed(self):
        """Test face recognition performance"""
        import time
        
        # This would test that recognition completes within 500ms
        pass
    
    def test_database_query_speed(self):
        """Test database query performance"""
        pass


if __name__ == '__main__':
    unittest.main()
