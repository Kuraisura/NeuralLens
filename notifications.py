"""
NEURAL EYE - Notification System
Email and notification handling for system events
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationSystem:
    """Handles email notifications and alerts"""
    
    def __init__(self, smtp_server=None, smtp_port=587, smtp_user=None, smtp_password=None):
        self.smtp_server = smtp_server or "smtp.gmail.com"
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.enabled = bool(smtp_user and smtp_password)
        
        if not self.enabled:
            logger.warning("Notification system disabled: No SMTP credentials configured")
    
    
    def send_email(self, to_email, subject, body, html_body=None):
        """Send an email notification"""
        if not self.enabled:
            logger.info(f"[MOCK EMAIL] To: {to_email}, Subject: {subject}")
            return True  # Return success in mock mode
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_user
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add plain text part
            text_part = MIMEText(body, 'plain')
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, 'html')
                msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    
    def notify_late_arrival(self, employee_name, employee_email, clock_in_time):
        """Send notification for late arrival"""
        subject = f"Late Arrival Alert - {employee_name}"
        
        body = f"""
Hello {employee_name},

This is an automated notification that you clocked in late today.

Clock In Time: {clock_in_time.strftime('%I:%M %p')}
Date: {clock_in_time.strftime('%B %d, %Y')}

Please ensure to arrive on time as per company policy.

Best regards,
Neural Eye Attendance System
        """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #ff9800; margin-top: 0;">⚠️ Late Arrival Alert</h2>
                <p>Hello <strong>{employee_name}</strong>,</p>
                <p>This is an automated notification that you clocked in late today.</p>
                <div style="background: #fff3e0; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Clock In Time:</strong> {clock_in_time.strftime('%I:%M %p')}</p>
                    <p style="margin: 5px 0;"><strong>Date:</strong> {clock_in_time.strftime('%B %d, %Y')}</p>
                </div>
                <p>Please ensure to arrive on time as per company policy.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Best regards,<br>
                    <strong>Neural Eye Attendance System</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(employee_email, subject, body, html_body)
    
    
    def notify_manager_late_arrival(self, manager_email, employee_name, department, clock_in_time):
        """Notify manager about employee late arrival"""
        subject = f"Team Member Late Arrival - {employee_name}"
        
        body = f"""
Hello Manager,

This is an automated notification that one of your team members arrived late.

Employee: {employee_name}
Department: {department}
Clock In Time: {clock_in_time.strftime('%I:%M %p')}
Date: {clock_in_time.strftime('%B %d, %Y')}

You may want to follow up with this employee.

Best regards,
Neural Eye Attendance System
        """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #2196f3; margin-top: 0;">📊 Team Attendance Alert</h2>
                <p>Hello Manager,</p>
                <p>This is an automated notification that one of your team members arrived late.</p>
                <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Employee:</strong> {employee_name}</p>
                    <p style="margin: 5px 0;"><strong>Department:</strong> {department}</p>
                    <p style="margin: 5px 0;"><strong>Clock In Time:</strong> {clock_in_time.strftime('%I:%M %p')}</p>
                    <p style="margin: 5px 0;"><strong>Date:</strong> {clock_in_time.strftime('%B %d, %Y')}</p>
                </div>
                <p>You may want to follow up with this employee.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Best regards,<br>
                    <strong>Neural Eye Attendance System</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(manager_email, subject, body, html_body)
    
    
    def notify_new_enrollment(self, employee_name, employee_id, employee_email):
        """Welcome email for newly enrolled employee"""
        subject = f"Welcome to Neural Eye - {employee_name}"
        
        body = f"""
Hello {employee_name},

Welcome to the Neural Eye Attendance System!

Your biometric profile has been successfully enrolled.

Employee ID: {employee_id}

You can now use the facial recognition system for attendance tracking. Simply position yourself in front of the camera to clock in and out automatically.

For any questions or assistance, please contact your HR department.

Best regards,
Neural Eye System
        """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #00bcd4; margin-top: 0;">🎉 Welcome to Neural Eye!</h2>
                <p>Hello <strong>{employee_name}</strong>,</p>
                <p>Welcome to the Neural Eye Attendance System!</p>
                <div style="background: #e0f7fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;">✅ Your biometric profile has been successfully enrolled.</p>
                    <p style="margin: 5px 0;"><strong>Employee ID:</strong> {employee_id}</p>
                </div>
                <h3 style="color: #00796b;">How to Use:</h3>
                <ol style="line-height: 1.8;">
                    <li>Position yourself in front of the camera</li>
                    <li>Wait for recognition (usually instant)</li>
                    <li>Automatic clock in/out will be recorded</li>
                </ol>
                <p>For any questions or assistance, please contact your HR department.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Best regards,<br>
                    <strong>Neural Eye System</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(employee_email, subject, body, html_body)
    
    
    def notify_leave_request(self, manager_email, employee_name, leave_type, start_date, end_date, days_count):
        """Notify manager about new leave request"""
        subject = f"Leave Request - {employee_name}"
        
        body = f"""
Hello Manager,

A new leave request requires your attention.

Employee: {employee_name}
Leave Type: {leave_type}
Start Date: {start_date}
End Date: {end_date}
Days Count: {days_count} day(s)

Please review and approve/reject this request in the system.

Best regards,
Neural Eye System
        """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: #ff9800; margin-top: 0;">📅 New Leave Request</h2>
                <p>Hello Manager,</p>
                <p>A new leave request requires your attention.</p>
                <div style="background: #fff3e0; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Employee:</strong> {employee_name}</p>
                    <p style="margin: 5px 0;"><strong>Leave Type:</strong> {leave_type}</p>
                    <p style="margin: 5px 0;"><strong>Start Date:</strong> {start_date}</p>
                    <p style="margin: 5px 0;"><strong>End Date:</strong> {end_date}</p>
                    <p style="margin: 5px 0;"><strong>Duration:</strong> {days_count} day(s)</p>
                </div>
                <p>Please review and approve/reject this request in the system.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Best regards,<br>
                    <strong>Neural Eye System</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(manager_email, subject, body, html_body)
    
    
    def notify_leave_decision(self, employee_email, employee_name, leave_type, status, decision_by):
        """Notify employee about leave request decision"""
        subject = f"Leave Request {status} - {leave_type}"
        
        status_color = "#4caf50" if status == "Approved" else "#f44336"
        status_icon = "✅" if status == "Approved" else "❌"
        
        body = f"""
Hello {employee_name},

Your leave request has been {status.lower()}.

Leave Type: {leave_type}
Status: {status}
Decided by: {decision_by}

Thank you.

Best regards,
Neural Eye System
        """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <h2 style="color: {status_color}; margin-top: 0;">{status_icon} Leave Request {status}</h2>
                <p>Hello <strong>{employee_name}</strong>,</p>
                <p>Your leave request has been <strong>{status.lower()}</strong>.</p>
                <div style="background: {'#e8f5e9' if status == 'Approved' else '#ffebee'}; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Leave Type:</strong> {leave_type}</p>
                    <p style="margin: 5px 0;"><strong>Status:</strong> <span style="color: {status_color};">{status}</span></p>
                    <p style="margin: 5px 0;"><strong>Decided by:</strong> {decision_by}</p>
                </div>
                <p>Thank you.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    Best regards,<br>
                    <strong>Neural Eye System</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(employee_email, subject, body, html_body)


# Singleton instance
_notification_system = None

def get_notification_system():
    """Get the global notification system instance"""
    global _notification_system
    if _notification_system is None:
        # Initialize with environment variables or config
        import os
        _notification_system = NotificationSystem(
            smtp_user=os.environ.get('SMTP_USER'),
            smtp_password=os.environ.get('SMTP_PASSWORD'),
            smtp_server=os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
            smtp_port=int(os.environ.get('SMTP_PORT', 587))
        )
    return _notification_system
