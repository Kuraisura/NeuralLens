"""
Quick System Test - Verify all components are working
Run this after starting the server to test major functionality
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5000"

def test_system():
    """Run comprehensive system tests"""
    print("=" * 70)
    print("NEURAL EYE - SYSTEM VERIFICATION TEST")
    print("=" * 70)
    print(f"Testing server at: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = {
        'passed': 0,
        'failed': 0,
        'total': 0
    }
    
    # Test 1: Server is running
    print("Test 1: Server Availability")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print("✅ PASS - Server is responding")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Server returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Server not reachable: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 2: Database endpoints
    print("Test 2: Database Endpoints")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/api/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ PASS - Database responding")
            print(f"   Total Employees: {data.get('total_employees', 0)}")
            print(f"   Today Attendance: {data.get('today_attendance', 0)}")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Stats endpoint returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Database error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 3: Login endpoint
    print("Test 3: Authentication System")
    print("-" * 70)
    try:
        response = requests.post(
            f"{BASE_URL}/login",
            json={"username": "admin", "password": "admin"},
            timeout=5
        )
        if response.status_code == 200:
            print("✅ PASS - Authentication working")
            print("   Default admin credentials accepted")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Login failed with {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Authentication error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 4: Departments API
    print("Test 4: Organizational Data")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/api/departments", timeout=5)
        if response.status_code == 200:
            departments = response.json()
            print(f"✅ PASS - Organizational data available")
            print(f"   Departments loaded: {len(departments)}")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Departments endpoint returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Organizational data error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 5: Positions API
    print("Test 5: Position Data")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/api/positions", timeout=5)
        if response.status_code == 200:
            positions = response.json()
            print(f"✅ PASS - Position data available")
            print(f"   Positions loaded: {len(positions)}")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Positions endpoint returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Position data error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 6: Shifts API
    print("Test 6: Shift Data")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/api/shifts", timeout=5)
        if response.status_code == 200:
            shifts = response.json()
            print(f"✅ PASS - Shift data available")
            print(f"   Shifts loaded: {len(shifts)}")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Shifts endpoint returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Shift data error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 7: System info endpoint
    print("Test 7: System Information")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/api/system-info", timeout=5)
        if response.status_code == 200:
            info = response.json()
            print(f"✅ PASS - System info available")
            print(f"   Camera Mode: {info.get('camera_mode', 'unknown')}")
            print(f"   Server Time: {info.get('server_time', 'unknown')}")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - System info endpoint returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - System info error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 8: Attendance logs endpoint
    print("Test 8: Attendance Logs")
    print("-" * 70)
    try:
        response = requests.get(f"{BASE_URL}/api/logs", timeout=5)
        if response.status_code == 200:
            logs = response.json()
            print(f"✅ PASS - Attendance logs accessible")
            print(f"   Current logs: {len(logs)}")
            results['passed'] += 1
        else:
            print(f"❌ FAIL - Logs endpoint returned {response.status_code}")
            results['failed'] += 1
    except Exception as e:
        print(f"❌ FAIL - Attendance logs error: {e}")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {results['total']}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    
    pass_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
    print(f"Pass Rate: {pass_rate:.1f}%")
    print()
    
    if results['failed'] == 0:
        print("🎉 ALL TESTS PASSED! System is fully operational!")
        print("\n✅ You can now:")
        print("   1. Open http://localhost:5000/login")
        print("   2. Login with: admin / admin")
        print("   3. Explore the dashboard")
        print("   4. Enroll employees")
        print("   5. Test face recognition")
        print("   6. Generate reports")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        print("   Server may still be functional for passing tests.")
    
    print("\n" + "=" * 70)
    
    return results['failed'] == 0


if __name__ == "__main__":
    print("\n⚠️  Make sure the server is running first!")
    print("   Run: python app.py")
    print("   Then run this test script in another terminal.\n")
    
    input("Press Enter to start testing...")
    
    success = test_system()
    
    exit(0 if success else 1)
