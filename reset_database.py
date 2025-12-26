#!/usr/bin/env python3
"""
Clear all data from the database and recreate default users.
Run this script while the server is STOPPED.
"""
import sqlite3
import os
import sys

def clear_and_reset():
    db_path = 'neural_eye.db'
    
    # If database exists, delete it
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"Deleted existing database: {db_path}")
        except PermissionError:
            print(f"Cannot delete {db_path} - file is locked.")
            print("Please stop the server first, then run this script.")
            sys.exit(1)
    
    # Import and create fresh database
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from database import Database
    from auth import hash_password
    
    db = Database()
    print("Created fresh database with default departments, positions, and shifts.")
    
    # Create default users
    db.create_user('admin', hash_password('admin'), 'admin')
    db.create_user('manager', hash_password('manager'), 'manager')
    db.create_user('viewer', hash_password('viewer'), 'viewer')
    
    print("\n" + "="*50)
    print("DATABASE RESET COMPLETE")
    print("="*50)
    print("\nDefault users created:")
    print("  admin / admin (Admin role)")
    print("  manager / manager (Manager role)")
    print("  viewer / viewer (Viewer role)")
    print("\nAll previous employee and attendance data has been cleared.")
    print("="*50)

if __name__ == '__main__':
    clear_and_reset()
