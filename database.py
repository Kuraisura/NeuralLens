"""
NEURAL EYE - Database Module
SQLite database operations for employees and attendance logs
"""

import sqlite3
from datetime import datetime, date
import logging
import json

logger = logging.getLogger(__name__)


class Database:
    """Handles all database operations"""
    
    def __init__(self, db_path='neural_eye.db'):
        self.db_path = db_path
        self.init_database()
    
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
    
    
    def init_database(self):
        """Initialize database tables"""
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
                        department_id INTEGER,
                        default_shift_id INTEGER,
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
                
                # Users table (for authentication)
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
                
                # Employees table (extended)
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
                
                # Leave management table
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
                        decision_notes TEXT,
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
                
                # Migration: add decision_notes column if missing (for existing DBs)
                try:
                    cursor.execute("SELECT decision_notes FROM leave_requests LIMIT 1")
                except sqlite3.OperationalError:
                    cursor.execute("ALTER TABLE leave_requests ADD COLUMN decision_notes TEXT")

                # Migration: add missing columns to attendance_logs
                cursor.execute("PRAGMA table_info(attendance_logs)")
                att_columns = {row[1] for row in cursor.fetchall()}
                if 'overtime_minutes' not in att_columns:
                    cursor.execute("ALTER TABLE attendance_logs ADD COLUMN overtime_minutes INTEGER DEFAULT 0")
                if 'notes' not in att_columns:
                    cursor.execute("ALTER TABLE attendance_logs ADD COLUMN notes TEXT")
                if 'modified_by' not in att_columns:
                    cursor.execute("ALTER TABLE attendance_logs ADD COLUMN modified_by INTEGER REFERENCES users(id)")

                # Migration: upgrade employees table from old TEXT schema to FK schema
                cursor.execute("PRAGMA table_info(employees)")
                columns = {row[1] for row in cursor.fetchall()}
                if 'department_id' not in columns:
                    cursor.execute("ALTER TABLE employees ADD COLUMN department_id INTEGER REFERENCES departments(id)")
                    cursor.execute("ALTER TABLE employees ADD COLUMN position_id INTEGER REFERENCES positions(id)")
                    cursor.execute("ALTER TABLE employees ADD COLUMN shift_id INTEGER REFERENCES shifts(id)")
                    cursor.execute("ALTER TABLE employees ADD COLUMN manager_id INTEGER REFERENCES employees(id)")
                    cursor.execute("ALTER TABLE employees ADD COLUMN email TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN phone TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN date_of_birth DATE")
                    cursor.execute("ALTER TABLE employees ADD COLUMN address TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN emergency_contact_name TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN emergency_contact_phone TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN employment_type TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN hire_date DATE")
                    cursor.execute("ALTER TABLE employees ADD COLUMN salary_grade TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN photo_path TEXT")
                    cursor.execute("ALTER TABLE employees ADD COLUMN notes TEXT")
                    # Migrate existing TEXT department/position to FK IDs
                    cursor.execute("SELECT id, department, position FROM employees WHERE department_id IS NULL")
                    for row in cursor.fetchall():
                        emp_id, dept_name, pos_name = row[0], row[1], row[2]
                        dept_id = None
                        pos_id = None
                        if dept_name:
                            cursor.execute("SELECT id FROM departments WHERE name = ?", (dept_name,))
                            r = cursor.fetchone()
                            if r:
                                dept_id = r[0]
                        if pos_name:
                            cursor.execute("SELECT id FROM positions WHERE title = ?", (pos_name,))
                            r = cursor.fetchone()
                            if r:
                                pos_id = r[0]
                        cursor.execute(
                            "UPDATE employees SET department_id = ?, position_id = ? WHERE id = ?",
                            (dept_id, pos_id, emp_id)
                        )
                    logger.info("Migrated employees table to new FK schema")
                
                # Migration: add address breakdown columns
                address_cols = ['street_address', 'region', 'province', 'city', 'barangay', 'postal_code']
                for col in address_cols:
                    if col not in columns:
                        cursor.execute(f"ALTER TABLE employees ADD COLUMN {col} TEXT")
                
                # Migration: add multi-angle face encoding columns
                face_cols = ['face_encoding_front', 'face_encoding_left', 'face_encoding_right']
                for col in face_cols:
                    if col not in columns:
                        cursor.execute(f"ALTER TABLE employees ADD COLUMN {col} BLOB")

                # Migration: add department_id and default_shift_id to positions table
                cursor.execute("PRAGMA table_info(positions)")
                pos_columns = {row[1] for row in cursor.fetchall()}
                if 'department_id' not in pos_columns:
                    cursor.execute("ALTER TABLE positions ADD COLUMN department_id INTEGER")
                if 'default_shift_id' not in pos_columns:
                    cursor.execute("ALTER TABLE positions ADD COLUMN default_shift_id INTEGER")

                # Create indexes for better performance
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
                
                # Insert default data
                self._insert_default_data(cursor)
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    
    def _insert_default_data(self, cursor):
        """Insert default departments, positions, and shifts for a Philippine IT company"""
        departments = [
            ('Executive Management', 'C-suite and executive leadership — CEO, CTO, CFO, COO, CISO, CIO'),
            ('Software Development', 'Full-stack, front-end, back-end, mobile, desktop, and microservices development'),
            ('Quality Assurance & Testing', 'Manual, automated, performance, and security testing across all software products'),
            ('DevOps & Cloud Infrastructure', 'CI/CD pipelines, container orchestration, cloud platforms (AWS/Azure/GCP), and IaC'),
            ('Cybersecurity & Information Security', 'SOC operations, threat intelligence, penetration testing, incident response, and GRC'),
            ('Data Science & Analytics', 'Business intelligence, data engineering, machine learning, and AI solutions'),
            ('Database Administration', 'Relational/NoSQL database management, performance tuning, and data governance'),
            ('Network & Infrastructure', 'LAN/WAN, firewalls, routers/switches, structured cabling, and telecommunications'),
            ('IT Support & Helpdesk', 'Tier 1–3 end-user support, ticketing, device management, and IT asset lifecycle'),
            ('IT Project Management (PMO)', 'Agile/Scrum delivery, project planning, and cross-team coordination'),
            ('Product Management & UX', 'Product strategy, user research, wireframing, and UI/UX design'),
            ('Human Resources', 'Recruitment, employee relations, benefits administration, training, and compliance'),
            ('Finance & Accounting', 'Accounts payable/receivable, budgeting, payroll, and financial reporting'),
            ('Legal & Compliance', 'Contracts, data privacy (DPA/NPC), IP protection, and regulatory compliance'),
            ('Sales & Business Development', 'Client acquisition, account management, and strategic partnerships'),
            ('Marketing & Communications', 'Brand management, digital marketing, PR, and internal communications'),
            ('General & Administrative', 'Facilities, procurement, mailroom, security, and office services'),
        ]
        cursor.execute('SELECT COUNT(*) FROM departments')
        if cursor.fetchone()[0] == 0:
            cursor.executemany('INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)', departments)

        positions = [
            # Executive Management (dept 1, shift 6=Regular)
            ('Chief Executive Officer (CEO)', 'Executive leadership and company strategy', 8, 1, 6),
            ('Chief Technology Officer (CTO)', 'Technology vision and architecture', 8, 1, 6),
            ('Chief Information Officer (CIO)', 'IT strategy and enterprise systems', 8, 1, 6),
            ('Chief Information Security Officer (CISO)', 'Enterprise security posture and compliance', 8, 1, 6),
            ('Chief Financial Officer (CFO)', 'Financial strategy and investor relations', 8, 1, 6),
            ('Chief Operating Officer (COO)', 'Business operations and efficiency', 8, 1, 6),
            # Software Development (dept 2, shift 1=Day or 6=Regular)
            ('Junior Software Engineer', 'Entry-level developer under mentorship', 1, 2, 1),
            ('Mid-Level Software Engineer', 'Independent feature development', 3, 2, 1),
            ('Senior Software Engineer', 'Technical lead and code review', 5, 2, 1),
            ('Staff Engineer', 'Cross-cutting technical decisions and architecture', 6, 2, 1),
            ('Principal Engineer', 'Organization-wide technical direction', 7, 2, 1),
            ('Mobile App Developer (Android/iOS)', 'Native and cross-platform mobile development', 3, 2, 1),
            ('Front-End Developer', 'React/Vue/Angular web interfaces', 3, 2, 1),
            ('Back-End Developer', 'APIs, microservices, and server-side logic', 3, 2, 1),
            ('Full-Stack Developer', 'End-to-end feature development', 4, 2, 1),
            # QA & Testing (dept 3, shift 1=Day)
            ('QA Analyst', 'Manual testing and exploratory testing', 2, 3, 1),
            ('QA Engineer', 'Test automation and framework maintenance', 3, 3, 1),
            ('Senior QA Engineer', 'Test strategy and quality ownership', 5, 3, 1),
            ('Performance Test Engineer', 'Load testing and performance profiling', 4, 3, 1),
            ('Security Test Engineer', 'Security testing and vulnerability validation', 4, 3, 1),
            # DevOps & Cloud (dept 4, shift 1=Day/5=On-Call)
            ('Cloud Engineer', 'Cloud resource management and optimization', 4, 4, 1),
            ('DevOps Engineer', 'CI/CD pipelines and infrastructure automation', 4, 4, 1),
            ('Site Reliability Engineer (SRE)', 'Incident response, SLOs, and reliability', 5, 4, 4),
            ('Platform Engineer', 'Internal developer platform and tooling', 5, 4, 1),
            ('Container/Kubernetes Specialist', 'Container orchestration and service mesh', 4, 4, 1),
            # Cybersecurity (dept 5, shift 4=Rotating or 1=Day)
            ('Security Operations Center (SOC) Analyst', 'Threat monitoring and incident triage', 3, 5, 4),
            ('Senior SOC Analyst', 'Threat hunting and escalated incidents', 5, 5, 4),
            ('Penetration Tester', 'Offensive security and red teaming', 4, 5, 1),
            ('Cybersecurity Analyst', 'Vulnerability assessment and GRC', 4, 5, 1),
            ('Security Architect', 'Security design and Zero Trust implementation', 6, 5, 6),
            ('Incident Response Analyst', 'Breach investigation and forensics', 4, 5, 1),
            # Data Science & Analytics (dept 6, shift 1=Day/6=Regular)
            ('Data Analyst', 'Reporting and dashboarding', 2, 6, 1),
            ('Business Intelligence Analyst', 'ETL and BI tool management', 3, 6, 1),
            ('Data Engineer', 'Data pipeline architecture and maintenance', 4, 6, 1),
            ('Senior Data Engineer', 'Data platform leadership', 5, 6, 1),
            ('Data Scientist', 'Statistical modeling and ML experimentation', 4, 6, 1),
            ('Machine Learning Engineer', 'ML model deployment and MLOps', 5, 6, 1),
            ('AI/Deep Learning Researcher', 'Advanced AI research and prototyping', 5, 6, 6),
            # Database Administration (dept 7, shift 1=Day)
            ('Database Administrator (DBA)', 'Database installation, tuning, and backup', 4, 7, 1),
            ('Senior DBA', 'Multi-database management and performance tuning', 6, 7, 1),
            ('Data Governance Analyst', 'Data quality, cataloging, and lineage', 3, 7, 6),
            # Network & Infrastructure (dept 8, shift 1=Day)
            ('Network Engineer', 'LAN/WAN design and maintenance', 3, 8, 1),
            ('Senior Network Engineer', 'Complex network architecture and troubleshooting', 5, 8, 1),
            ('Systems Administrator', 'Server management and OS maintenance', 3, 8, 1),
            ('Senior Systems Administrator', 'Infrastructure design and automation', 5, 8, 1),
            ('Telecommunications Engineer', 'VoIP, video conferencing, and comms infrastructure', 3, 8, 1),
            # IT Support & Helpdesk (dept 9, shift varies)
            ('IT Support Specialist (Tier 1)', 'First-line end-user support', 1, 9, 4),
            ('IT Support Specialist (Tier 2)', 'Advanced troubleshooting and escalation', 2, 9, 4),
            ('IT Support Specialist (Tier 3)', 'Complex issue resolution and vendor coordination', 3, 9, 1),
            ('IT Asset Manager', 'Hardware lifecycle and procurement tracking', 3, 9, 6),
            ('Desktop/Field Support Engineer', 'On-site device setup and repair', 2, 9, 1),
            # PMO (dept 10, shift 6=Regular)
            ('Scrum Master', 'Agile ceremony facilitation and impediment removal', 3, 10, 1),
            ('Agile Coach', 'Organization-wide agile transformation', 5, 10, 6),
            ('IT Project Manager', 'Project planning, delivery, and stakeholder management', 4, 10, 6),
            ('Senior Project Manager', 'Multi-project program oversight', 6, 10, 6),
            ('Delivery Manager', 'Client-facing project governance', 5, 10, 6),
            # Product & UX (dept 11, shift 1=Day/6=Regular)
            ('UI/UX Designer', 'User interface design and usability testing', 3, 11, 1),
            ('Senior UX Designer', 'Design system ownership and user research', 5, 11, 6),
            ('Product Owner', 'Product backlog and sprint goal alignment', 4, 11, 1),
            ('Product Manager', 'Product vision, roadmap, and market analysis', 5, 11, 6),
            # HR (dept 12, shift 6=Regular)
            ('HR Specialist', 'Recruitment, onboarding, and employee lifecycle', 2, 12, 6),
            ('HR Manager', 'People operations and compliance', 4, 12, 6),
            ('Talent Acquisition Specialist', 'End-to-end recruitment and employer branding', 3, 12, 6),
            ('Training & Development Specialist', 'Learning programs and skills development', 3, 12, 6),
            ('Compensation & Benefits Analyst', 'Salary benchmarking and benefits admin', 3, 12, 6),
            ('HR Business Partner', 'Strategic HR alignment with business units', 5, 12, 6),
            # Finance (dept 13, shift 6=Regular)
            ('Accounting Staff', 'Bookkeeping and AP/AR processing', 1, 13, 6),
            ('Senior Accountant', 'Financial reporting and GL management', 4, 13, 6),
            ('Finance Manager', 'Budgeting and financial planning', 5, 13, 6),
            ('Payroll Specialist', 'Payroll processing and government remittances (SSS, PhilHealth, Pag-IBIG)', 3, 13, 6),
            ('Internal Auditor', 'Compliance audits and SOX controls', 4, 13, 6),
            # Legal & Compliance (dept 14, shift 6=Regular)
            ('Legal Counsel', 'Contract review and legal advisory', 5, 14, 6),
            ('Data Privacy Officer (DPO)', 'NPC compliance and DPA management', 4, 14, 6),
            ('Compliance Analyst', 'Regulatory tracking and policy enforcement', 3, 14, 6),
            # Sales & BD (dept 15, shift 1=Day/6=Regular)
            ('Sales Executive', 'New business acquisition', 2, 15, 1),
            ('Account Manager', 'Client relationship management', 3, 15, 6),
            ('Business Development Manager', 'Strategic partnerships and enterprise deals', 5, 15, 6),
            ('Solutions Architect (Pre-Sales)', 'Technical presales and proposal development', 5, 15, 6),
            # Marketing (dept 16, shift 1=Day/6=Regular)
            ('Digital Marketing Specialist', 'SEO/SEM, social media, and content', 2, 16, 1),
            ('Marketing Manager', 'Campaign strategy and brand management', 4, 16, 6),
            ('Technical Writer', 'Documentation, KB articles, and release notes', 2, 16, 1),
            # General & Administrative (dept 17, varies)
            ('Office Administrator', 'Facilities coordination and vendor management', 2, 17, 6),
            ('Procurement Officer', 'Purchase orders and supplier negotiation', 3, 17, 6),
            ('Security Guard', 'Physical security and access control', 1, 17, 4),
            ('Janitorial/Maintenance', 'Office upkeep and cleanliness', 1, 17, 3),
            ('Receptionist', 'Front desk and visitor management', 1, 17, 1),
        ]
        cursor.execute('SELECT COUNT(*) FROM positions')
        if cursor.fetchone()[0] == 0:
            cursor.executemany('INSERT OR IGNORE INTO positions (title, description, level, department_id, default_shift_id) VALUES (?, ?, ?, ?, ?)', positions)
        else:
            for p in positions:
                cursor.execute(
                    'UPDATE positions SET level=?, department_id=?, default_shift_id=? WHERE title=?',
                    (p[2], p[3], p[4], p[0])
                )

        shifts = [
            ('Day Shift', '08:00:00', '17:00:00', 15),
            ('Mid Shift', '14:00:00', '23:00:00', 15),
            ('Night Shift / Graveyard', '21:00:00', '06:00:00', 15),
            ('Rotating Shifts / 24-7 Support', '00:00:00', '23:59:59', 15),
            ('On-Call / Standby', '00:00:00', '23:59:59', 30),
            ('Regular Hours (No Shift)', '09:00:00', '18:00:00', 0),
        ]
        cursor.execute('SELECT COUNT(*) FROM shifts')
        if cursor.fetchone()[0] == 0:
            cursor.executemany('INSERT OR IGNORE INTO shifts (name, start_time, end_time, grace_period_minutes) VALUES (?, ?, ?, ?)', shifts)
    
    
    def add_employee(self, full_name, employee_id, department="General", 
                     position="Staff", face_encoding=None):
        """Add a new employee to the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Resolve department - accept integer ID or text name
                dept_id = None
                if department is not None:
                    if isinstance(department, int):
                        dept_id = department
                    elif isinstance(department, str) and department.isdigit():
                        dept_id = int(department)
                    elif isinstance(department, str) and department:
                        cursor.execute('SELECT id FROM departments WHERE name = ?', (department,))
                        row = cursor.fetchone()
                        if row:
                            dept_id = row[0]
                        else:
                            cursor.execute('INSERT INTO departments (name) VALUES (?)', (department,))
                            dept_id = cursor.lastrowid
                
                # Resolve position - accept integer ID or text name
                pos_id = None
                if position is not None:
                    if isinstance(position, int):
                        pos_id = position
                    elif isinstance(position, str) and position.isdigit():
                        pos_id = int(position)
                    elif isinstance(position, str) and position:
                        cursor.execute('SELECT id FROM positions WHERE title = ?', (position,))
                        row = cursor.fetchone()
                        if row:
                            pos_id = row[0]
                        else:
                            cursor.execute('INSERT INTO positions (title) VALUES (?)', (position,))
                            pos_id = cursor.lastrowid
                
                cursor.execute('''
                    INSERT INTO employees (full_name, employee_id, department_id, position_id, face_encoding)
                    VALUES (?, ?, ?, ?, ?)
                ''', (full_name, employee_id, dept_id, pos_id, face_encoding))
                
                conn.commit()
                employee_db_id = cursor.lastrowid
                
                logger.info(f"Added employee: {full_name} (ID: {employee_id})")
                return employee_db_id
                
        except sqlite3.IntegrityError:
            logger.warning(f"Employee ID {employee_id} already exists")
            return None
        except Exception as e:
            logger.error(f"Error adding employee: {e}")
            return None
    
    
    def get_employee(self, employee_db_id):
        """Get employee by database ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_db_id,))
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Error fetching employee: {e}")
            return None
    
    
    def get_all_employees(self):
        """Get all active employees"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM employees WHERE active = 1 ORDER BY full_name')
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching employees: {e}")
            return []
    
    
    def get_employee_count(self):
        """Get total number of active employees"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM employees WHERE active = 1')
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            logger.error(f"Error counting employees: {e}")
            return 0
    
    
    def add_attendance_log(self, employee_id, log_type='clock_in', status='ON-TIME'):
        """Add an attendance log entry"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now()
                today = date.today()
                
                if log_type == 'clock_in':
                    cursor.execute('''
                        INSERT INTO attendance_logs (employee_id, clock_in, status, date)
                        VALUES (?, ?, ?, ?)
                    ''', (employee_id, now, status, today))
                else:  # clock_out
                    cursor.execute('''
                        UPDATE attendance_logs 
                        SET clock_out = ?, status = ?
                        WHERE employee_id = ? AND date = ? AND clock_out IS NULL
                    ''', (now, status, employee_id, today))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error adding attendance log: {e}")
            return False
    
    
    def get_today_log(self, employee_id):
        """Get today's attendance log for an employee"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                today = date.today()
                
                cursor.execute('''
                    SELECT * FROM attendance_logs 
                    WHERE employee_id = ? AND date = ?
                    ORDER BY clock_in DESC LIMIT 1
                ''', (employee_id, today))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Error fetching today's log: {e}")
            return None
    
    
    def clock_out_employee(self, employee_id, status='ON-TIME'):
        """Clock out an employee"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now()
                today = date.today()
                
                cursor.execute('''
                    UPDATE attendance_logs 
                    SET clock_out = ?, status = ?
                    WHERE employee_id = ? AND date = ? AND clock_out IS NULL
                ''', (now, status, employee_id, today))
                
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error clocking out employee: {e}")
            return False
    
    
    def get_recent_logs(self, limit=10):
        """Get recent attendance logs with employee details"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        al.*,
                        e.full_name,
                        e.employee_id as emp_id,
                        d.name as department,
                        p.title as position
                    FROM attendance_logs al
                    JOIN employees e ON al.employee_id = e.id
                    LEFT JOIN departments d ON e.department_id = d.id
                    LEFT JOIN positions p ON e.position_id = p.id
                    ORDER BY al.clock_in DESC
                    LIMIT ?
                ''', (limit,))
                
                rows = cursor.fetchall()
                
                logs = []
                for row in rows:
                    log = dict(row)
                    # Format timestamps for frontend
                    if log['clock_in']:
                        log['clock_in'] = log['clock_in']
                    if log['clock_out']:
                        log['clock_out'] = log['clock_out']
                    logs.append(log)
                
                return logs
                
        except Exception as e:
            logger.error(f"Error fetching recent logs: {e}")
            return []
    
    
    def get_today_attendance_count(self):
        """Get count of employees who clocked in today"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                today = date.today()
                
                cursor.execute('''
                    SELECT COUNT(DISTINCT employee_id) 
                    FROM attendance_logs 
                    WHERE date = ?
                ''', (today,))
                
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            logger.error(f"Error counting today's attendance: {e}")
            return 0
    
    
    def get_attendance_by_date(self, target_date):
        """Get all attendance records for a specific date"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        al.*,
                        e.full_name,
                        e.employee_id as emp_id,
                        d.name as department,
                        p.title as position
                    FROM attendance_logs al
                    JOIN employees e ON al.employee_id = e.id
                    LEFT JOIN departments d ON e.department_id = d.id
                    LEFT JOIN positions p ON e.position_id = p.id
                    WHERE al.date = ?
                    ORDER BY al.clock_in DESC
                ''', (target_date,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching attendance by date: {e}")
            return []
    
    
    def get_employee_history(self, employee_id, days=30):
        """Get attendance history for an employee"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM attendance_logs 
                    WHERE employee_id = ?
                    ORDER BY clock_in DESC
                    LIMIT ?
                ''', (employee_id, days))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching employee history: {e}")
            return []
    
    
    def delete_employee(self, employee_id):
        """Soft delete an employee (set active = 0)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE employees SET active = 0 WHERE id = ?', (employee_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting employee: {e}")
            return False
    
    
    def get_statistics(self, start_date=None, end_date=None):
        """Get attendance statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if not start_date:
                    start_date = date.today()
                if not end_date:
                    end_date = date.today()
                
                cursor.execute('''
                    SELECT 
                        status,
                        COUNT(*) as count
                    FROM attendance_logs
                    WHERE date BETWEEN ? AND ?
                    GROUP BY status
                ''', (start_date, end_date))
                
                rows = cursor.fetchall()
                return {row['status']: row['count'] for row in rows}
                
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {}
    
    
    # ===== EXTENDED EMPLOYEE MANAGEMENT =====
    
    def generate_employee_id(self):
        """Auto-generate next employee ID in format EMP-XXXX"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT employee_id FROM employees ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    last_id = row[0]
                    if last_id and last_id.startswith('EMP-'):
                        num = int(last_id.split('-')[1]) + 1
                    else:
                        cursor.execute("SELECT COUNT(*) FROM employees")
                        num = cursor.fetchone()[0] + 1
                else:
                    num = 1
                return f"EMP-{num:04d}"
        except Exception as e:
            logger.error(f"Error generating employee ID: {e}")
            return "EMP-0001"
    
    def add_employee_extended(self, **kwargs):
        """Add employee with all extended fields"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                fields = ['full_name', 'employee_id', 'email', 'phone', 'date_of_birth', 
                         'street_address', 'region', 'province', 'city', 'barangay', 'postal_code',
                         'emergency_contact_name', 'emergency_contact_phone',
                         'department_id', 'position_id', 'shift_id', 'manager_id',
                         'employment_type', 'hire_date', 'salary_grade', 'face_encoding',
                         'photo_path', 'notes',
                         'face_encoding_front', 'face_encoding_left', 'face_encoding_right']
                
                provided_fields = [f for f in fields if f in kwargs]
                placeholders = ', '.join(['?' for _ in provided_fields])
                field_names = ', '.join(provided_fields)
                
                query = f'INSERT INTO employees ({field_names}) VALUES ({placeholders})'
                values = [kwargs[f] for f in provided_fields]
                
                cursor.execute(query, values)
                conn.commit()
                
                employee_id = cursor.lastrowid
                logger.info(f"Added employee: {kwargs.get('full_name')} (ID: {employee_id})")
                
                return employee_id
                
        except sqlite3.IntegrityError as e:
            logger.warning(f"Employee already exists: {e}")
            return None
        except Exception as e:
            logger.error(f"Error adding employee: {e}")
            return None
    
    
    def update_employee(self, employee_id, **kwargs):
        """Update employee information"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Build dynamic UPDATE query
                update_fields = []
                values = []
                
                for key, value in kwargs.items():
                    if key not in ['id', 'date_enrolled']:  # Don't update these
                        update_fields.append(f"{key} = ?")
                        values.append(value)
                
                if not update_fields:
                    return False
                
                values.append(employee_id)
                query = f"UPDATE employees SET {', '.join(update_fields)} WHERE id = ?"
                
                cursor.execute(query, values)
                conn.commit()
                
                return True
                
        except Exception as e:
            logger.error(f"Error updating employee: {e}")
            return False
    
    
    def get_employees_detailed(self, active_only=True, search=None, department_id=None, position_id=None):
        """Get employees with department, position, shift, and manager details"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
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
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching detailed employees: {e}")
            return []
    
    
    # ===== DEPARTMENTS =====
    
    def get_all_departments(self):
        """Get all departments"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM departments ORDER BY name')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching departments: {e}")
            return []
    
    
    def add_department(self, name, description=None, department_head_id=None):
        """Add a new department"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO departments (name, description, department_head_id) VALUES (?, ?, ?)',
                    (name, description, department_head_id)
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding department: {e}")
            return None
    
    
    # ===== POSITIONS =====
    
    def get_all_positions(self):
        """Get all positions"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM positions ORDER BY level')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    
    def add_position(self, title, description=None, level=1):
        """Add a new position"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO positions (title, description, level) VALUES (?, ?, ?)',
                    (title, description, level)
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding position: {e}")
            return None
    
    
    # ===== SHIFTS =====
    
    def get_all_shifts(self):
        """Get all shifts"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM shifts ORDER BY start_time')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching shifts: {e}")
            return []
    
    
    def add_shift(self, name, start_time, end_time, grace_period_minutes=15):
        """Add a new shift"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO shifts (name, start_time, end_time, grace_period_minutes) VALUES (?, ?, ?, ?)',
                    (name, start_time, end_time, grace_period_minutes)
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding shift: {e}")
            return None
    
    
    # ===== LEAVE MANAGEMENT =====
    
    def add_leave_request(self, employee_id, leave_type, start_date, end_date, days_count, reason=None):
        """Add a new leave request"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO leave_requests 
                    (employee_id, leave_type, start_date, end_date, days_count, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (employee_id, leave_type, start_date, end_date, days_count, reason))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding leave request: {e}")
            return None
    
    
    def update_leave_status(self, leave_id, status, approved_by=None, decision_notes=None):
        """Update leave request status"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE leave_requests 
                    SET status = ?, approved_by = ?, decision_date = CURRENT_TIMESTAMP,
                        decision_notes = ?
                    WHERE id = ?
                ''', (status, approved_by, decision_notes, leave_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating leave status: {e}")
            return False
    
    
    def is_employee_eligible_for_leave(self, employee_id):
        """Check if employee has been hired for at least 1 year"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT hire_date FROM employees WHERE id = ?', (employee_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return False
            try:
                hire_date = datetime.strptime(row[0], '%Y-%m-%d')
            except:
                try:
                    hire_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                except:
                    return False
            return (datetime.now() - hire_date).days >= 365


    def get_leave_requests(self, employee_id=None, status=None):
        """Get leave requests with filters"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
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
                
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Error fetching leave requests: {e}")
            return []
    
    
    # ===== AUTHENTICATION =====
    
    def create_user(self, username, password_hash, role='viewer', employee_id=None):
        """Create a new user account"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, employee_id)
                    VALUES (?, ?, ?, ?)
                ''', (username, password_hash, role, employee_id))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"Username {username} already exists")
            return None
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None
    
    
    def get_user(self, username):
        """Get user by username"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE username = ? AND active = 1', (username,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching user: {e}")
            return None
    
    
    def get_user_by_id(self, user_id):
        """Get user by database ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching user by ID: {e}")
            return None
    
    
    def update_last_login(self, user_id):
        """Update user's last login timestamp"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
                    (user_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating last login: {e}")
            return False
    
    
    # ===== AUDIT LOGS =====
    
    def add_audit_log(self, user_id, action, table_name=None, record_id=None, changes=None):
        """Add an audit log entry"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO audit_logs (user_id, action, table_name, record_id, changes)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, action, table_name, record_id, json.dumps(changes) if changes else None))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding audit log: {e}")
            return False
    
    
    def get_audit_logs(self, limit=100):
        """Get recent audit logs"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT al.*, u.username
                    FROM audit_logs al
                    LEFT JOIN users u ON al.user_id = u.id
                    ORDER BY al.timestamp DESC
                    LIMIT ?
                ''', (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching audit logs: {e}")
            return []
    
    
    # ===== REPORTING =====
    
    def get_attendance_report(self, start_date, end_date, department_id=None):
        """Get comprehensive attendance report"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
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
                
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Error generating attendance report: {e}")
            return []
    
    
    def get_employee_stats(self, employee_id, start_date, end_date):
        """Get statistics for a specific employee"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_days,
                        SUM(CASE WHEN status = 'ON-TIME' THEN 1 ELSE 0 END) as on_time_days,
                        SUM(CASE WHEN status = 'LATE' THEN 1 ELSE 0 END) as late_days,
                        SUM(CASE WHEN status = 'UNDERTIME' THEN 1 ELSE 0 END) as undertime_days,
                        SUM(overtime_minutes) as total_overtime_minutes
                    FROM attendance_logs
                    WHERE employee_id = ? AND date BETWEEN ? AND ?
                ''', (employee_id, start_date, end_date))
                
                row = cursor.fetchone()
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"Error fetching employee stats: {e}")
            return None
    
    
    def manual_attendance(self, employee_id, action, timestamp, modified_by, notes=None):
        """Manually add or modify attendance record"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                log_date = datetime.fromisoformat(timestamp).date()
                
                if action == 'clock_in':
                    cursor.execute('''
                        INSERT INTO attendance_logs 
                        (employee_id, clock_in, date, status, notes, modified_by)
                        VALUES (?, ?, ?, 'MANUAL', ?, ?)
                    ''', (employee_id, timestamp, log_date, notes, modified_by))
                elif action == 'clock_out':
                    cursor.execute('''
                        UPDATE attendance_logs
                        SET clock_out = ?, notes = ?, modified_by = ?
                        WHERE employee_id = ? AND date = ? AND clock_out IS NULL
                    ''', (timestamp, notes, modified_by, employee_id, log_date))
                
                conn.commit()
                self.add_audit_log(modified_by, f'Manual {action}', 'attendance_logs', 
                                  employee_id, {'timestamp': timestamp, 'notes': notes})
                return True
                
        except Exception as e:
            logger.error(f"Error with manual attendance: {e}")
            return False
    
    
    def disable_employee(self, employee_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE employees SET active = 0 WHERE id = ?', (employee_id,))
            conn.commit()
            return cursor.rowcount > 0

    def enable_employee(self, employee_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE employees SET active = 1 WHERE id = ?', (employee_id,))
            conn.commit()
            return cursor.rowcount > 0

    def hard_delete_employee(self, employee_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM attendance_logs WHERE employee_id = ?', (employee_id,))
            cursor.execute('DELETE FROM leave_requests WHERE employee_id = ?', (employee_id,))
            cursor.execute('DELETE FROM employees WHERE id = ?', (employee_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    
    def delete_all_data(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM attendance_logs')
            cursor.execute('DELETE FROM leave_requests')
            cursor.execute('DELETE FROM audit_logs')
            cursor.execute('DELETE FROM employees')
            cursor.execute('DELETE FROM users')
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('employees','attendance_logs','leave_requests','audit_logs','users')")
            conn.commit()
            return True
