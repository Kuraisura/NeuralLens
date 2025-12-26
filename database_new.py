"""
NEURAL EYE - Database Module (Refactored)
Modern database layer with connection pooling, repository pattern, and proper OOP
"""

import sqlite3
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from threading import Lock
import logging
import json
from pathlib import Path
from abc import ABC, abstractmethod
from queue import Queue, Empty
import pickle

from config import Config

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe database connection pool for better performance"""
    
    def __init__(self, database_path: str, pool_size: int = 10, timeout: int = 30):
        self.database_path = database_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool: Queue = Queue(maxsize=pool_size)
        self._lock = Lock()
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize connection pool"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
        logger.info(f"Initialized connection pool with {self.pool_size} connections")
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection"""
        conn = sqlite3.connect(
            self.database_path,
            timeout=self.timeout,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute('PRAGMA foreign_keys = ON')
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode = WAL')
        return conn
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)"""
        conn = None
        try:
            conn = self._pool.get(timeout=self.timeout)
            yield conn
            conn.commit()
        except Empty:
            logger.error("Connection pool exhausted")
            raise Exception("No database connections available")
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                self._pool.put(conn)
    
    def close_all(self):
        """Close all connections in the pool"""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break
        logger.info("Connection pool closed")


class BaseRepository(ABC):
    """Base repository class with common database operations"""
    
    def __init__(self, connection_pool: ConnectionPool):
        self.pool = connection_pool
    
    @contextmanager
    def get_connection(self):
        """Get database connection from pool"""
        with self.pool.get_connection() as conn:
            yield conn
    
    def execute_query(self, query: str, params: Tuple = ()) -> List[sqlite3.Row]:
        """Execute a SELECT query and return results"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_one(self, query: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
        """Execute a SELECT query and return one result"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    
    def execute_write(self, query: str, params: Tuple = ()) -> int:
        """Execute INSERT/UPDATE/DELETE and return affected rows or last row ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[Tuple]) -> int:
        """Execute multiple INSERT/UPDATE statements"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount


class EmployeeRepository(BaseRepository):
    """Repository for employee data access"""
    
    def create(self, **kwargs) -> Optional[int]:
        """Create a new employee"""
        try:
            fields = ['full_name', 'employee_id', 'email', 'phone', 'date_of_birth',
                     'address', 'emergency_contact_name', 'emergency_contact_phone',
                     'department_id', 'position_id', 'shift_id', 'manager_id',
                     'employment_type', 'hire_date', 'salary_grade', 'face_encoding',
                     'photo_path', 'notes']
            
            provided = {k: v for k, v in kwargs.items() if k in fields and v is not None}
            field_names = ', '.join(provided.keys())
            placeholders = ', '.join(['?' for _ in provided])
            
            query = f'INSERT INTO employees ({field_names}) VALUES ({placeholders})'
            return self.execute_write(query, tuple(provided.values()))
            
        except sqlite3.IntegrityError as e:
            logger.warning(f"Employee already exists: {e}")
            return None
    
    def get_by_id(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get employee by ID"""
        row = self.execute_one('SELECT * FROM employees WHERE id = ?', (employee_id,))
        return dict(row) if row else None
    
    def get_by_employee_id(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Get employee by employee ID string"""
        row = self.execute_one('SELECT * FROM employees WHERE employee_id = ?', (employee_id,))
        return dict(row) if row else None
    
    def get_all(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all employees"""
        query = 'SELECT * FROM employees'
        if active_only:
            query += ' WHERE active = 1'
        query += ' ORDER BY full_name'
        
        rows = self.execute_query(query)
        return [dict(row) for row in rows]
    
    def get_detailed(self, active_only: bool = True, search: str = None,
                    department_id: int = None, position_id: int = None) -> List[Dict[str, Any]]:
        """Get employees with joined data"""
        query = '''
            SELECT 
                e.*,
                d.name as department_name,
                p.title as position_title,
                s.name as shift_name,
                s.start_time,
                s.end_time,
                m.full_name as manager_name
            FROM employees e
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN positions p ON e.position_id = p.id
            LEFT JOIN shifts s ON e.shift_id = s.id
            LEFT JOIN employees m ON e.manager_id = m.id
            WHERE 1=1
        '''
        
        params = []
        
        if active_only:
            query += ' AND e.active = 1'
        
        if search:
            query += ' AND (e.full_name LIKE ? OR e.employee_id LIKE ? OR e.email LIKE ?)'
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])
        
        if department_id:
            query += ' AND e.department_id = ?'
            params.append(department_id)
        
        if position_id:
            query += ' AND e.position_id = ?'
            params.append(position_id)
        
        query += ' ORDER BY e.full_name'
        
        rows = self.execute_query(query, tuple(params))
        return [dict(row) for row in rows]
    
    def update(self, employee_id: int, **kwargs) -> bool:
        """Update employee information"""
        # Remove fields that shouldn't be updated
        kwargs.pop('id', None)
        kwargs.pop('date_enrolled', None)
        
        if not kwargs:
            return False
        
        set_clause = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [employee_id]
        
        query = f"UPDATE employees SET {set_clause} WHERE id = ?"
        return self.execute_write(query, tuple(values)) > 0
    
    def deactivate(self, employee_id: int) -> bool:
        """Soft delete an employee"""
        return self.execute_write(
            'UPDATE employees SET active = 0 WHERE id = ?',
            (employee_id,)
        ) > 0
    
    def count(self, active_only: bool = True) -> int:
        """Count employees"""
        query = 'SELECT COUNT(*) FROM employees'
        if active_only:
            query += ' WHERE active = 1'
        row = self.execute_one(query)
        return row[0] if row else 0


class AttendanceRepository(BaseRepository):
    """Repository for attendance data access"""
    
    def clock_in(self, employee_id: int, status: str = 'ON-TIME',
                timestamp: datetime = None) -> Optional[int]:
        """Record clock in"""
        if timestamp is None:
            timestamp = datetime.now()
        
        return self.execute_write('''
            INSERT INTO attendance_logs (employee_id, clock_in, status, date)
            VALUES (?, ?, ?, ?)
        ''', (employee_id, timestamp, status, timestamp.date()))
    
    def clock_out(self, employee_id: int, status: str = 'ON-TIME',
                 timestamp: datetime = None) -> bool:
        """Record clock out"""
        if timestamp is None:
            timestamp = datetime.now()
        
        return self.execute_write('''
            UPDATE attendance_logs 
            SET clock_out = ?, status = ?
            WHERE employee_id = ? AND date = ? AND clock_out IS NULL
        ''', (timestamp, status, employee_id, timestamp.date())) > 0
    
    def get_today_log(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get today's attendance log"""
        row = self.execute_one('''
            SELECT * FROM attendance_logs 
            WHERE employee_id = ? AND date = ?
            ORDER BY clock_in DESC LIMIT 1
        ''', (employee_id, date.today()))
        return dict(row) if row else None
    
    def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent attendance logs with employee info"""
        rows = self.execute_query('''
            SELECT 
                al.*,
                e.full_name,
                e.employee_id as emp_id,
                e.department_id,
                e.position_id
            FROM attendance_logs al
            JOIN employees e ON al.employee_id = e.id
            ORDER BY al.clock_in DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in rows]
    
    def get_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Get all attendance for a specific date"""
        rows = self.execute_query('''
            SELECT al.*, e.full_name, e.employee_id as emp_id
            FROM attendance_logs al
            JOIN employees e ON al.employee_id = e.id
            WHERE al.date = ?
            ORDER BY al.clock_in
        ''', (target_date,))
        return [dict(row) for row in rows]
    
    def get_employee_history(self, employee_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Get attendance history for an employee"""
        rows = self.execute_query('''
            SELECT * FROM attendance_logs 
            WHERE employee_id = ?
            ORDER BY clock_in DESC
            LIMIT ?
        ''', (employee_id, days))
        return [dict(row) for row in rows]
    
    def count_today(self) -> int:
        """Count distinct employees who clocked in today"""
        row = self.execute_one('''
            SELECT COUNT(DISTINCT employee_id) 
            FROM attendance_logs 
            WHERE date = ?
        ''', (date.today(),))
        return row[0] if row else 0
    
    def get_statistics(self, start_date: date, end_date: date) -> Dict[str, int]:
        """Get attendance statistics for date range"""
        rows = self.execute_query('''
            SELECT status, COUNT(*) as count
            FROM attendance_logs
            WHERE date BETWEEN ? AND ?
            GROUP BY status
        ''', (start_date, end_date))
        return {row['status']: row['count'] for row in rows}
    
    def get_employee_stats(self, employee_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get statistics for a specific employee"""
        row = self.execute_one('''
            SELECT 
                COUNT(*) as total_days,
                SUM(CASE WHEN status = 'ON-TIME' THEN 1 ELSE 0 END) as on_time_days,
                SUM(CASE WHEN status = 'LATE' THEN 1 ELSE 0 END) as late_days,
                SUM(CASE WHEN status = 'UNDERTIME' THEN 1 ELSE 0 END) as undertime_days,
                SUM(overtime_minutes) as total_overtime_minutes
            FROM attendance_logs
            WHERE employee_id = ? AND date BETWEEN ? AND ?
        ''', (employee_id, start_date, end_date))
        return dict(row) if row else {}
    
    def manual_entry(self, employee_id: int, action: str, timestamp: str,
                    modified_by: int, notes: str = None) -> bool:
        """Manually add or modify attendance record"""
        log_date = datetime.fromisoformat(timestamp).date()
        
        if action == 'clock_in':
            return self.execute_write('''
                INSERT INTO attendance_logs 
                (employee_id, clock_in, date, status, notes, modified_by)
                VALUES (?, ?, ?, 'MANUAL', ?, ?)
            ''', (employee_id, timestamp, log_date, notes, modified_by)) > 0
        elif action == 'clock_out':
            return self.execute_write('''
                UPDATE attendance_logs
                SET clock_out = ?, notes = ?, modified_by = ?
                WHERE employee_id = ? AND date = ? AND clock_out IS NULL
            ''', (timestamp, notes, modified_by, employee_id, log_date)) > 0
        
        return False


class UserRepository(BaseRepository):
    """Repository for user authentication data"""
    
    def create(self, username: str, password_hash: str, role: str = 'viewer',
              employee_id: int = None) -> Optional[int]:
        """Create a new user"""
        try:
            return self.execute_write('''
                INSERT INTO users (username, password_hash, role, employee_id)
                VALUES (?, ?, ?, ?)
            ''', (username, password_hash, role, employee_id))
        except sqlite3.IntegrityError:
            logger.warning(f"Username {username} already exists")
            return None
    
    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        row = self.execute_one(
            'SELECT * FROM users WHERE username = ? AND active = 1',
            (username,)
        )
        return dict(row) if row else None
    
    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        row = self.execute_one('SELECT * FROM users WHERE id = ?', (user_id,))
        return dict(row) if row else None
    
    def update_last_login(self, user_id: int) -> bool:
        """Update last login timestamp"""
        return self.execute_write('''
            UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
        ''', (user_id,)) > 0
    
    def update_password(self, user_id: int, password_hash: str) -> bool:
        """Update user password"""
        return self.execute_write('''
            UPDATE users SET password_hash = ? WHERE id = ?
        ''', (password_hash, user_id)) > 0


class LeaveRepository(BaseRepository):
    """Repository for leave management"""
    
    def create(self, employee_id: int, leave_type: str, start_date: date,
              end_date: date, days_count: float, reason: str = None) -> Optional[int]:
        """Create a leave request"""
        return self.execute_write('''
            INSERT INTO leave_requests 
            (employee_id, leave_type, start_date, end_date, days_count, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (employee_id, leave_type, start_date, end_date, days_count, reason))
    
    def get_all(self, employee_id: int = None, status: str = None) -> List[Dict[str, Any]]:
        """Get leave requests with filters"""
        query = '''
            SELECT lr.*, e.full_name, e.employee_id as emp_id,
                   u.username as approved_by_name
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.id
            LEFT JOIN users u ON lr.approved_by = u.id
            WHERE 1=1
        '''
        params = []
        
        if employee_id:
            query += ' AND lr.employee_id = ?'
            params.append(employee_id)
        
        if status:
            query += ' AND lr.status = ?'
            params.append(status)
        
        query += ' ORDER BY lr.request_date DESC'
        
        rows = self.execute_query(query, tuple(params))
        return [dict(row) for row in rows]
    
    def update_status(self, leave_id: int, status: str, approved_by: int = None,
                     decision_notes: str = None) -> bool:
        """Update leave request status"""
        return self.execute_write('''
            UPDATE leave_requests 
            SET status = ?, approved_by = ?, decision_date = CURRENT_TIMESTAMP,
                decision_notes = ?
            WHERE id = ?
        ''', (status, approved_by, decision_notes, leave_id)) > 0


class AuditRepository(BaseRepository):
    """Repository for audit logs"""
    
    def create(self, user_id: int, action: str, table_name: str = None,
              record_id: int = None, changes: Dict = None) -> bool:
        """Create an audit log entry"""
        return self.execute_write('''
            INSERT INTO audit_logs (user_id, action, table_name, record_id, changes)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, table_name, record_id, json.dumps(changes) if changes else None)) > 0
    
    def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit logs"""
        rows = self.execute_query('''
            SELECT al.*, u.username
            FROM audit_logs al
            LEFT JOIN users u ON al.user_id = u.id
            ORDER BY al.timestamp DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in rows]


class LookupRepository(BaseRepository):
    """Repository for lookup tables (departments, positions, shifts)"""
    
    def get_all_departments(self) -> List[Dict[str, Any]]:
        """Get all departments"""
        rows = self.execute_query('SELECT * FROM departments ORDER BY name')
        return [dict(row) for row in rows]
    
    def add_department(self, name: str, description: str = None,
                      department_head_id: int = None) -> Optional[int]:
        """Add a department"""
        return self.execute_write('''
            INSERT INTO departments (name, description, department_head_id) 
            VALUES (?, ?, ?)
        ''', (name, description, department_head_id))
    
    def get_all_positions(self) -> List[Dict[str, Any]]:
        """Get all positions"""
        rows = self.execute_query('SELECT * FROM positions ORDER BY level')
        return [dict(row) for row in rows]
    
    def add_position(self, title: str, description: str = None, level: int = 1) -> Optional[int]:
        """Add a position"""
        return self.execute_write('''
            INSERT INTO positions (title, description, level) VALUES (?, ?, ?)
        ''', (title, description, level))
    
    def get_all_shifts(self) -> List[Dict[str, Any]]:
        """Get all shifts"""
        rows = self.execute_query('SELECT * FROM shifts ORDER BY start_time')
        return [dict(row) for row in rows]
    
    def add_shift(self, name: str, start_time: str, end_time: str,
                 grace_period_minutes: int = 15) -> Optional[int]:
        """Add a shift"""
        return self.execute_write('''
            INSERT INTO shifts (name, start_time, end_time, grace_period_minutes) 
            VALUES (?, ?, ?, ?)
        ''', (name, start_time, end_time, grace_period_minutes))


class Database:
    """Main database class orchestrating all repositories"""
    
    def __init__(self, database_path: str = None, pool_size: int = None):
        self.database_path = database_path or Config.DATABASE_PATH
        self.pool_size = pool_size or Config.DATABASE_POOL_SIZE
        
        # Initialize connection pool
        self.pool = ConnectionPool(self.database_path, self.pool_size)
        
        # Initialize repositories
        self.employees = EmployeeRepository(self.pool)
        self.attendance = AttendanceRepository(self.pool)
        self.users = UserRepository(self.pool)
        self.leaves = LeaveRepository(self.pool)
        self.audit = AuditRepository(self.pool)
        self.lookups = LookupRepository(self.pool)
        
        # Initialize database schema
        self._init_schema()
        
        logger.info(f"Database initialized: {self.database_path}")
    
    def _init_schema(self):
        """Initialize database schema"""
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create all tables
            self._create_tables(cursor)
            self._create_indexes(cursor)
            self._insert_default_data(cursor)
            
            conn.commit()
    
    def _create_tables(self, cursor):
        """Create all database tables"""
        # Departments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                department_head_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_head_id) REFERENCES employees(id)
            )
        ''')
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE NOT NULL,
                description TEXT,
                level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Shifts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                grace_period_minutes INTEGER DEFAULT 15,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'viewer',
                employee_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                active BOOLEAN DEFAULT 1,
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            )
        ''')
        
        # Employees table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                employee_id TEXT UNIQUE NOT NULL,
                email TEXT,
                phone TEXT,
                date_of_birth DATE,
                address TEXT,
                emergency_contact_name TEXT,
                emergency_contact_phone TEXT,
                department_id INTEGER,
                position_id INTEGER,
                shift_id INTEGER,
                manager_id INTEGER,
                employment_type TEXT DEFAULT 'Full-time',
                hire_date DATE DEFAULT CURRENT_DATE,
                salary_grade TEXT,
                face_encoding BLOB,
                photo_path TEXT,
                date_enrolled TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1,
                notes TEXT,
                FOREIGN KEY (department_id) REFERENCES departments(id),
                FOREIGN KEY (position_id) REFERENCES positions(id),
                FOREIGN KEY (shift_id) REFERENCES shifts(id),
                FOREIGN KEY (manager_id) REFERENCES employees(id)
            )
        ''')
        
        # Attendance logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                clock_in TIMESTAMP,
                clock_out TIMESTAMP,
                status TEXT DEFAULT 'SYNCING',
                date DATE DEFAULT CURRENT_DATE,
                overtime_minutes INTEGER DEFAULT 0,
                notes TEXT,
                modified_by INTEGER,
                FOREIGN KEY (employee_id) REFERENCES employees(id),
                FOREIGN KEY (modified_by) REFERENCES users(id)
            )
        ''')
        
        # Leave requests table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                leave_type TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                days_count REAL NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'Pending',
                approved_by INTEGER,
                decision_notes TEXT,
                request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                decision_date TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employees(id),
                FOREIGN KEY (approved_by) REFERENCES users(id)
            )
        ''')
        
        # Audit logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                table_name TEXT,
                record_id INTEGER,
                changes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
    
    def _create_indexes(self, cursor):
        """Create database indexes for performance"""
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_attendance_date 
            ON attendance_logs(date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_attendance_employee 
            ON attendance_logs(employee_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_employees_active
            ON employees(active)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_leave_employee
            ON leave_requests(employee_id)
        ''')
    
    def _insert_default_data(self, cursor):
        """Insert default lookup data"""
        # Default departments
        departments = [
            ('Human Resources', 'Manages employee relations and benefits'),
            ('Engineering', 'Software development and technical operations'),
            ('Sales', 'Business development and client relations'),
            ('Marketing', 'Brand management and promotion'),
            ('Finance', 'Financial planning and accounting'),
            ('Operations', 'Day-to-day business operations'),
            ('General', 'General staff')
        ]
        
        cursor.execute('SELECT COUNT(*) FROM departments')
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                'INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)',
                departments
            )
        
        # Default positions
        positions = [
            ('Intern', 'Entry-level trainee', 1),
            ('Junior', 'Junior-level employee', 2),
            ('Staff', 'Regular staff member', 3),
            ('Senior', 'Senior-level employee', 4),
            ('Lead', 'Team lead', 5),
            ('Manager', 'Department manager', 6),
            ('Director', 'Executive director', 7),
            ('VP', 'Vice President', 8),
            ('C-Level', 'Executive leadership', 9)
        ]
        
        cursor.execute('SELECT COUNT(*) FROM positions')
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                'INSERT OR IGNORE INTO positions (title, description, level) VALUES (?, ?, ?)',
                positions
            )
        
        # Default shifts
        shifts = [
            ('Day Shift', '08:00:00', '17:00:00', 15),
            ('Night Shift', '20:00:00', '05:00:00', 15),
            ('Morning Shift', '06:00:00', '14:00:00', 15),
            ('Afternoon Shift', '14:00:00', '22:00:00', 15),
            ('Flexible', '00:00:00', '23:59:59', 60)
        ]
        
        cursor.execute('SELECT COUNT(*) FROM shifts')
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                'INSERT OR IGNORE INTO shifts (name, start_time, end_time, grace_period_minutes) VALUES (?, ?, ?, ?)',
                shifts
            )
    
    def close(self):
        """Close all database connections"""
        self.pool.close_all()
    
    # Legacy compatibility methods (delegate to repositories)
    def get_employee(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.employees.get_by_id(employee_id)
    
    def get_all_employees(self) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.employees.get_all()
    
    def get_employee_count(self) -> int:
        """Legacy method for compatibility"""
        return self.employees.count()
    
    def add_employee_extended(self, **kwargs) -> Optional[int]:
        """Legacy method for compatibility"""
        return self.employees.create(**kwargs)
    
    def update_employee(self, employee_id: int, **kwargs) -> bool:
        """Legacy method for compatibility"""
        return self.employees.update(employee_id, **kwargs)
    
    def delete_employee(self, employee_id: int) -> bool:
        """Legacy method for compatibility"""
        return self.employees.deactivate(employee_id)
    
    def add_attendance_log(self, employee_id: int, log_type: str = 'clock_in',
                          status: str = 'ON-TIME') -> bool:
        """Legacy method for compatibility"""
        if log_type == 'clock_in':
            return self.attendance.clock_in(employee_id, status) is not None
        else:
            return self.attendance.clock_out(employee_id, status)
    
    def get_today_log(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.attendance.get_today_log(employee_id)
    
    def clock_out_employee(self, employee_id: int, status: str = 'ON-TIME') -> bool:
        """Legacy method for compatibility"""
        return self.attendance.clock_out(employee_id, status)
    
    def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.attendance.get_recent_logs(limit)
    
    def get_today_attendance_count(self) -> int:
        """Legacy method for compatibility"""
        return self.attendance.count_today()
    
    def get_attendance_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Get attendance by date"""
        return self.attendance.get_by_date(target_date)
    
    def get_employees_detailed(self, **kwargs) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.employees.get_detailed(**kwargs)
    
    def get_employee_history(self, employee_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.attendance.get_employee_history(employee_id, days)
    
    def get_employee_stats(self, employee_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        """Legacy method for compatibility"""
        return self.attendance.get_employee_stats(employee_id, start_date, end_date)
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.users.get_by_username(username)
    
    def update_last_login(self, user_id: int) -> bool:
        """Legacy method for compatibility"""
        return self.users.update_last_login(user_id)
    
    def create_user(self, username: str, password_hash: str, role: str = 'viewer',
                   employee_id: int = None) -> Optional[int]:
        """Legacy method for compatibility"""
        return self.users.create(username, password_hash, role, employee_id)
    
    def add_audit_log(self, user_id: int, action: str, table_name: str = None,
                     record_id: int = None, changes: Dict = None) -> bool:
        """Legacy method for compatibility"""
        return self.audit.create(user_id, action, table_name, record_id, changes)
    
    def get_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.audit.get_recent(limit)
    
    def get_all_departments(self) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.lookups.get_all_departments()
    
    def add_department(self, name: str, description: str = None, department_head_id: int = None) -> Optional[int]:
        """Legacy method for compatibility"""
        return self.lookups.add_department(name, description, department_head_id)
    
    def get_all_positions(self) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.lookups.get_all_positions()
    
    def add_position(self, title: str, description: str = None, level: int = 1) -> Optional[int]:
        """Legacy method for compatibility"""
        return self.lookups.add_position(title, description, level)
    
    def get_all_shifts(self) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        return self.lookups.get_all_shifts()
    
    def add_shift(self, name: str, start_time: str, end_time: str, grace_period_minutes: int = 15) -> Optional[int]:
        """Legacy method for compatibility"""
        return self.lookups.add_shift(name, start_time, end_time, grace_period_minutes)
    
    def get_leave_requests(self, employee_id: int = None, status: str = None, leave_id: int = None) -> List[Dict[str, Any]]:
        """Legacy method for compatibility"""
        if leave_id:
            # Return specific leave request as list for compatibility
            result = self.leaves.get_all()
            return [r for r in result if r['id'] == leave_id]
        return self.leaves.get_all(employee_id, status)
    
    def add_leave_request(self, employee_id: int, leave_type: str, start_date: date,
                         end_date: date, days_count: float, reason: str = None) -> Optional[int]:
        """Legacy method for compatibility"""
        return self.leaves.create(employee_id, leave_type, start_date, end_date, days_count, reason)
    
    def update_leave_status(self, leave_id: int, status: str, approved_by: int = None,
                           decision_notes: str = None) -> bool:
        """Legacy method for compatibility"""
        return self.leaves.update_status(leave_id, status, approved_by, decision_notes)
    
    def manual_attendance(self, employee_id: int, action: str, timestamp: str,
                         modified_by: int, notes: str = None) -> bool:
        """Legacy method for compatibility"""
        success = self.attendance.manual_entry(employee_id, action, timestamp, modified_by, notes)
        if success:
            self.audit.create(modified_by, f'Manual {action}', 'attendance_logs',
                            employee_id, {'timestamp': timestamp, 'notes': notes})
        return success
    
    def get_statistics(self, start_date: date, end_date: date) -> Dict[str, int]:
        """Legacy method for compatibility"""
        return self.attendance.get_statistics(start_date, end_date)
    
    def get_attendance_report(self, start_date: date, end_date: date, department_id: int = None) -> List[Dict[str, Any]]:
        """Get comprehensive attendance report"""
        query = '''
            SELECT 
                e.id,
                e.full_name,
                e.employee_id,
                d.name as department,
                p.title as position,
                al.date,
                al.clock_in,
                al.clock_out,
                al.status,
                al.overtime_minutes
            FROM attendance_logs al
            JOIN employees e ON al.employee_id = e.id
            LEFT JOIN departments d ON e.department_id = d.id
            LEFT JOIN positions p ON e.position_id = p.id
            WHERE al.date BETWEEN ? AND ?
        '''
        params = [start_date, end_date]
        
        if department_id:
            query += ' AND e.department_id = ?'
            params.append(department_id)
        
        query += ' ORDER BY al.date DESC, e.full_name'
        
        rows = self.employees.execute_query(query, tuple(params))
        return [dict(row) for row in rows]
