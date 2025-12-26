"""Create demo employee for testing profile page"""
from database import Database
from datetime import date, timedelta
import random

db = Database()

print("\n" + "="*60)
print("CREATING DEMO EMPLOYEE FOR PROFILE PAGE TESTING")
print("="*60)

# Create demo employee
demo_data = {
    'full_name': 'John Anderson',
    'employee_id': 'EMP-2026-001',
    'email': 'john.anderson@neuraleye.com',
    'phone': '+1-555-0123',
    'address': '123 Tech Street, Silicon Valley, CA 94025',
    'date_of_birth': '1990-05-15',
    'hire_date': '2024-01-15',
    'department_id': 1,  # Usually IT/Engineering
    'position_id': 1,    # Usually Software Engineer or similar
    'shift_id': 1,       # Usually Day Shift
    'employment_type': 'Full-time',
    'salary_grade': 'Level 3',
    'manager_id': None,
    'emergency_contact_name': 'Jane Anderson',
    'emergency_contact_phone': '+1-555-0124',
    'notes': 'Demo employee for testing profile page features',
    'active': True
}

try:
    # First ensure we have departments, positions, and shifts
    depts = db.get_all_departments()
    if not depts:
        print("\n📁 Creating demo department...")
        dept_id = db.add_department('Engineering', 'Software Engineering Department')
        demo_data['department_id'] = dept_id
        print(f"   ✓ Created department ID: {dept_id}")
    else:
        demo_data['department_id'] = depts[0]['id']
        print(f"   ✓ Using existing department: {depts[0]['name']}")
    
    positions = db.get_all_positions()
    if not positions:
        print("\n💼 Creating demo position...")
        pos_id = db.add_position('Senior Software Engineer', 'Full-stack development', 'Tech')
        demo_data['position_id'] = pos_id
        print(f"   ✓ Created position ID: {pos_id}")
    else:
        demo_data['position_id'] = positions[0]['id']
        print(f"   ✓ Using existing position: {positions[0]['title']}")
    
    shifts = db.get_all_shifts()
    if not shifts:
        print("\n🕐 Creating demo shift...")
        shift_id = db.add_shift('Day Shift', '09:00:00', '17:00:00', 'Standard 9-5 shift')
        demo_data['shift_id'] = shift_id
        print(f"   ✓ Created shift ID: {shift_id}")
    else:
        demo_data['shift_id'] = shifts[0]['id']
        print(f"   ✓ Using existing shift: {shifts[0]['name']}")
    
    # Add employee
    print(f"\n👤 Creating employee: {demo_data['full_name']}...")
    
    # Get dept and position names
    dept_name = next((d['name'] for d in depts if d['id'] == demo_data['department_id']), 'General')
    pos_name = next((p['title'] for p in positions if p['id'] == demo_data['position_id']), 'Employee')
    
    employee_id = db.add_employee(
        full_name=demo_data['full_name'],
        employee_id=demo_data['employee_id'],
        department=dept_name,
        position=pos_name
    )
    
    if employee_id:
        print(f"   ✓ Employee created with ID: {employee_id}")
        
        print(f"\n✅ DEMO EMPLOYEE CREATED SUCCESSFULLY")
        print(f"{'='*60}")
        print(f"Name: {demo_data['full_name']}")
        print(f"Employee ID: {demo_data['employee_id']}")
        print(f"Department: {dept_name}")
        print(f"Position: {pos_name}")
        print(f"Database ID: {employee_id}")
        print(f"\n{'='*60}")
        print(f"🌐 VIEW PROFILE PAGE:")
        print(f"   http://localhost:5000/profile/{employee_id}")
        print(f"{'='*60}\n")
        print(f"⚠️  Note: Extended fields (email, phone, etc.) will show 'N/A'")
        print(f"   The database schema needs to be updated to support them.")
        print(f"   The profile page is fully functional and ready for testing!")
        
    else:
        print("   ❌ Failed to create employee")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
