"""
Initialize database with default admin user and sample data
Run this script once after setting up the system
"""

from database import Database
from auth import hash_password
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_system():
    """Initialize the system with default data"""
    try:
        db = Database()
        
        # Create default admin user
        admin_password = hash_password('admin')  # Change this!
        admin_id = db.create_user(
            username='admin',
            password_hash=admin_password,
            role='admin'
        )
        
        if admin_id:
            logger.info("✓ Default admin user created (username: admin, password: admin)")
            logger.info("  ⚠️  IMPORTANT: Change the admin password immediately!")
        else:
            logger.info("ℹ Admin user already exists")
        
        # Create sample manager user
        manager_password = hash_password('manager123')
        manager_id = db.create_user(
            username='manager',
            password_hash=manager_password,
            role='manager'
        )
        
        if manager_id:
            logger.info("✓ Sample manager user created (username: manager, password: manager123)")
        
        # Create sample viewer user
        viewer_password = hash_password('viewer123')
        viewer_id = db.create_user(
            username='viewer',
            password_hash=viewer_password,
            role='viewer'
        )
        
        if viewer_id:
            logger.info("✓ Sample viewer user created (username: viewer, password: viewer123)")
        
        logger.info("\n" + "="*60)
        logger.info("System initialized successfully!")
        logger.info("="*60)
        logger.info("\nAvailable user roles:")
        logger.info("  • ADMIN   - Full system access")
        logger.info("  • MANAGER - Can manage employees and approve leave")
        logger.info("  • VIEWER  - Read-only access")
        logger.info("\nDefault login credentials:")
        logger.info("  Username: admin")
        logger.info("  Password: admin")
        logger.info("\n⚠️  SECURITY: Change default passwords before deploying!")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error initializing system: {e}")
        raise


if __name__ == '__main__':
    init_system()
