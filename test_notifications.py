"""
Test script for notification system
Run this to verify email notifications work (or run in mock mode)
"""

from notifications import get_notification_system
from datetime import datetime

def test_notifications():
    """Test all notification types"""
    print("=" * 60)
    print("NEURAL EYE - Notification System Test")
    print("=" * 60)
    
    # Get notification system
    notif = get_notification_system()
    
    if notif.enabled:
        print("✅ SMTP configured - Will send real emails")
        print(f"   SMTP Server: {notif.smtp_server}:{notif.smtp_port}")
        print(f"   SMTP User: {notif.smtp_user}")
    else:
        print("⚠️  SMTP not configured - Running in MOCK mode")
        print("   Set environment variables to enable real emails:")
        print("   - SMTP_USER")
        print("   - SMTP_PASSWORD")
        print("   - SMTP_SERVER (optional)")
        print("   - SMTP_PORT (optional)")
    
    print("\n" + "=" * 60)
    print("Testing notification templates...")
    print("=" * 60)
    
    # Test data
    test_email = "test@example.com"
    test_employee = "John Doe"
    test_time = datetime.now()
    
    # Test 1: Late Arrival Notification
    print("\n1. Testing Late Arrival Notification...")
    result = notif.notify_late_arrival(test_employee, test_email, test_time)
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    
    # Test 2: Manager Late Alert
    print("\n2. Testing Manager Late Alert...")
    result = notif.notify_manager_late_arrival(
        test_email, 
        test_employee, 
        "IT Department", 
        test_time
    )
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    
    # Test 3: New Enrollment Welcome
    print("\n3. Testing New Enrollment Welcome...")
    result = notif.notify_new_enrollment(test_employee, "EMP001", test_email)
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    
    # Test 4: Leave Request Notification
    print("\n4. Testing Leave Request Notification...")
    result = notif.notify_leave_request(
        test_email,
        test_employee,
        "Vacation",
        "2026-01-15",
        "2026-01-20",
        5
    )
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    
    # Test 5: Leave Decision Notification (Approved)
    print("\n5. Testing Leave Decision (Approved)...")
    result = notif.notify_leave_decision(
        test_email,
        test_employee,
        "Vacation",
        "Approved",
        "Manager Smith"
    )
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    
    # Test 6: Leave Decision Notification (Rejected)
    print("\n6. Testing Leave Decision (Rejected)...")
    result = notif.notify_leave_decision(
        test_email,
        test_employee,
        "Sick Leave",
        "Rejected",
        "Manager Smith"
    )
    print(f"   Result: {'✅ Success' if result else '❌ Failed'}")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    
    if not notif.enabled:
        print("\n💡 Tip: To enable real email sending:")
        print("   1. Create a Gmail account or use existing")
        print("   2. Enable 2-Factor Authentication")
        print("   3. Generate App Password (Google Account → Security → App Passwords)")
        print("   4. Set environment variables:")
        print('      $env:SMTP_USER = "your-email@gmail.com"')
        print('      $env:SMTP_PASSWORD = "your-app-password"')
        print("   5. Run this test again")


if __name__ == "__main__":
    test_notifications()
