#!/usr/bin/env python3
"""
Clear all data from the database (keeps the file, deletes all records).
Run this while the server is running to reset all data.
"""
import sqlite3

def clear_database():
    db_path = 'neural_eye.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Clear all tables
    tables = [
        'attendance_logs',
        'leave_requests', 
        'audit_logs',
        'employees',
        'users',
        'departments',
        'positions',
        'shifts'
    ]
    
    for table in tables:
        try:
            cursor.execute(f'DELETE FROM {table}')
            print(f"  Cleared: {table}")
        except Exception as e:
            print(f"  Error clearing {table}: {e}")
    
    # Reset auto-increment counters
    cursor.execute("DELETE FROM sqlite_sequence")
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*50)
    print("ALL DATA CLEARED")
    print("="*50)
    print("\nThe database is now empty.")
    print("Default departments, positions, and shifts will be")
    print("recreated automatically when you restart the server.")
    print("\nNOTE: To recreate default users (admin/manager/viewer),")
    print("restart the server or run create_default_users.py")
    print("="*50)

if __name__ == '__main__':
    clear_database()
