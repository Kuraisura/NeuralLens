"""Quick test for employee profile page"""
from database import Database

db = Database()
employees = db.get_all_employees()

print(f"\n{'='*50}")
print(f"EMPLOYEE DATABASE STATUS")
print(f"{'='*50}")
print(f"Total Employees: {len(employees)}")

if employees:
    print(f"\nFirst 5 Employees:")
    for i, emp in enumerate(employees[:5], 1):
        print(f"  {i}. ID: {emp['id']}, Name: {emp['full_name']}")
    
    # Test profile page data
    first_emp = employees[0]
    emp_id = first_emp['id']
    
    print(f"\n{'='*50}")
    print(f"TESTING PROFILE PAGE DATA FOR: {first_emp['full_name']}")
    print(f"{'='*50}")
    
    # Test employee details
    details = db.get_employee(emp_id)
    print(f"\n✓ Employee Details: {details['full_name']}")
    print(f"  Department: {details.get('department_name', 'N/A')}")
    print(f"  Position: {details.get('position_title', 'N/A')}")
    print(f"  Email: {details.get('email', 'N/A')}")
    
    # Test stats
    from datetime import date, timedelta
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    stats = db.get_employee_stats(emp_id, start_date, end_date)
    
    if stats:
        print(f"\n✓ Statistics (30 days):")
        print(f"  Total Days: {stats.get('total_days', 0)}")
        print(f"  On-Time: {stats.get('on_time_days', 0)}")
        print(f"  Late: {stats.get('late_days', 0)}")
        print(f"  Overtime Minutes: {stats.get('total_overtime_minutes', 0)}")
    
    # Test history
    history = db.get_employee_history(emp_id, 10)
    print(f"\n✓ Attendance History: {len(history)} records")
    
    if history:
        print(f"\n  Recent attendance:")
        for record in history[:3]:
            print(f"    {record['date']}: {record['status']}")
    
    print(f"\n{'='*50}")
    print(f"✅ Profile page ready for Employee ID: {emp_id}")
    print(f"   URL: http://localhost:5000/profile/{emp_id}")
    print(f"{'='*50}\n")
else:
    print("\n⚠️  No employees found. Enroll someone first!")
    print("   Go to: http://localhost:5000/enroll")
    print()
