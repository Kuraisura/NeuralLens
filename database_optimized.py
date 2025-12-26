"""
NEURAL EYE - Optimized Database Module
Enhanced SQLite database operations with connection pooling and caching
"""

import sqlite3
from datetime import datetime, date
import logging
from pathlib import Path
import json
from contextlib import contextmanager
from functools import lru_cache
import threading
from queue import Queue, Empty
import time

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe connection pool for SQLite"""
    
    def __init__(self, db_path, pool_size=5):
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool = Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize connection pool"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self.pool.put(conn)
    
    def _create_connection(self):
        """Create a new database connection"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=-64000')  # 64MB cache
        conn.execute('PRAGMA temp_store=MEMORY')
        return conn
    
    def get_connection(self, timeout=5):
        """Get a connection from the pool"""
        try:
            return self.pool.get(timeout=timeout)
        except Empty:
            # Pool exhausted, create temporary connection
            logger.warning("Connection pool exhausted, creating temporary connection")
            return self._create_connection()
    
    def return_connection(self, conn):
        """Return connection to pool"""
        try:
            self.pool.put_nowait(conn)
        except:
            # Pool full, close excess connection
            conn.close()
    
    def close_all(self):
        """Close all connections in pool"""
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except Empty:
                break


class Database:
    """Optimized database handler with connection pooling and caching"""
    
    def __init__(self, db_path='neural_eye.db', pool_size=5):
        self.db_path = db_path
        self.pool = ConnectionPool(db_path, pool_size)
        self.cache_timeout = 60  # seconds
        self._cache = {}
        self._cache_timestamps = {}
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = self.pool.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            self.pool.return_connection(conn)
    
    def _invalidate_cache(self, key=None):
        """Invalidate cache entries"""
        if key:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
    
    def _get_cached(self, key):
        """Get cached value if not expired"""
        if key in self._cache:
            timestamp = self._cache_timestamps.get(key, 0)
            if time.time() - timestamp < self.cache_timeout:
                return self._cache[key]
            else:
                self._invalidate_cache(key)
        return None
    
    def _set_cached(self, key, value):
        """Set cached value"""
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()
    
    def init_database(self):
        """Initialize database tables with optimizations"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
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
                
                # Create comprehensive indexes for performance
                indexes = [
                    'CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_logs(date)',
                    'CREATE INDEX IF NOT EXISTS idx_attendance_employee ON attendance_logs(employee_id)',
                    'CREATE INDEX IF NOT EXISTS idx_attendance_composite ON attendance_logs(employee_id, date)',
                    'CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(active)',
                    'CREATE INDEX IF NOT EXISTS idx_employees_dept ON employees(department_id)',
                    'CREATE INDEX IF NOT EXISTS idx_leave_employee ON leave_requests(employee_id)',
                    'CREATE INDEX IF NOT EXISTS idx_leave_status ON leave_requests(status)',
                    'CREATE INDEX IF NOT EXISTS idx_leave_dates ON leave_requests(start_date, end_date)',
                    'CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)',
                    'CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)',
                ]
                
                for index_query in indexes:
                    cursor.execute(index_query)
                
                # Insert default data
                self._insert_default_data(cursor)
                
                logger.info("Optimized database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def _insert_default_data(self, cursor):
        """Insert default departments, positions, and shifts"""
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
    
    def get_all_employees(self, include_inactive=False):
        """Get all employees with caching"""
        cache_key = f'employees_all_{include_inactive}'
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT e.*, 
                           d.name as department_name,
                           p.title as position_title,
                           s.name as shift_name
                    FROM employees e
                    LEFT JOIN departments d ON e.department_id = d.id
                    LEFT JOIN positions p ON e.position_id = p.id
                    LEFT JOIN shifts s ON e.shift_id = s.id
                '''
                
                if not include_inactive:
                    query += ' WHERE e.active = 1'
                
                query += ' ORDER BY e.full_name'
                
                cursor.execute(query)
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                
                self._set_cached(cache_key, result)
                return result
                
        except Exception as e:
            logger.error(f"Error fetching employees: {e}")
            return []
    
    def get_employee_by_id(self, employee_id):
        """Get single employee by ID with caching"""
        cache_key = f'employee_{employee_id}'
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT e.*, 
                           d.name as department_name,
                           p.title as position_title,
                           s.name as shift_name
                    FROM employees e
                    LEFT JOIN departments d ON e.department_id = d.id
                    LEFT JOIN positions p ON e.position_id = p.id
                    LEFT JOIN shifts s ON e.shift_id = s.id
                    WHERE e.id = ?
                ''', (employee_id,))
                
                row = cursor.fetchone()
                if row:
                    result = dict(row)
                    self._set_cached(cache_key, result)
                    return result
                return None
                
        except Exception as e:
            logger.error(f"Error fetching employee: {e}")
            return None
    
    def add_employee(self, **kwargs):
        """Add new employee (invalidates cache)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build dynamic query based on provided fields
                fields = list(kwargs.keys())
                placeholders = ', '.join(['?' for _ in fields])
                field_names = ', '.join(fields)
                
                query = f'INSERT INTO employees ({field_names}) VALUES ({placeholders})'
                cursor.execute(query, list(kwargs.values()))
                
                employee_id = cursor.lastrowid
                self._invalidate_cache()  # Clear all employee caches
                
                logger.info(f"Added employee: {kwargs.get('full_name')} (ID: {employee_id})")
                return employee_id
                
        except sqlite3.IntegrityError as e:
            logger.warning(f"Employee integrity error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error adding employee: {e}")
            return None
    
    def update_employee(self, employee_id, **kwargs):
        """Update employee information (invalidates cache)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build dynamic update query
                set_clause = ', '.join([f'{field} = ?' for field in kwargs.keys()])
                query = f'UPDATE employees SET {set_clause} WHERE id = ?'
                values = list(kwargs.values()) + [employee_id]
                
                cursor.execute(query, values)
                
                self._invalidate_cache()  # Clear all employee caches
                logger.info(f"Updated employee ID: {employee_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating employee: {e}")
            return False
    
    def log_attendance(self, employee_id, clock_in_time, status='ON-TIME'):
        """Log attendance record (invalidates related caches)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO attendance_logs (employee_id, clock_in, status, date)
                    VALUES (?, ?, ?, ?)
                ''', (employee_id, clock_in_time, status, date.today()))
                
                log_id = cursor.lastrowid
                self._invalidate_cache('attendance_today')
                
                logger.info(f"Logged attendance for employee ID {employee_id}: {status}")
                return log_id
                
        except Exception as e:
            logger.error(f"Error logging attendance: {e}")
            return None
    
    def get_attendance_by_date(self, target_date):
        """Get attendance records for a specific date with caching"""
        cache_key = f'attendance_{target_date}'
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT a.*, e.full_name, e.employee_id as emp_code,
                           d.name as department, p.title as position
                    FROM attendance_logs a
                    JOIN employees e ON a.employee_id = e.id
                    LEFT JOIN departments d ON e.department_id = d.id
                    LEFT JOIN positions p ON e.position_id = p.id
                    WHERE a.date = ?
                    ORDER BY a.clock_in DESC
                ''', (target_date,))
                
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                
                self._set_cached(cache_key, result)
                return result
                
        except Exception as e:
            logger.error(f"Error fetching attendance: {e}")
            return []
    
    def get_employee_count(self):
        """Get count of active employees with caching"""
        cache_key = 'employee_count'
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM employees WHERE active = 1')
                count = cursor.fetchone()[0]
                self._set_cached(cache_key, count)
                return count
        except Exception as e:
            logger.error(f"Error getting employee count: {e}")
            return 0
    
    def close(self):
        """Close all database connections"""
        self.pool.close_all()
        logger.info("Database connections closed")
