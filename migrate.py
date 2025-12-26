"""
NEURAL EYE - Migration Script
Helper script to migrate from old architecture to new improved architecture
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime

from utils import StructuredLogger

logger = StructuredLogger(__name__)


class MigrationHelper:
    """Helper class for migrating to improved architecture"""
    
    def __init__(self):
        self.backup_dir = Path('backups') / datetime.now().strftime('%Y%m%d_%H%M%S')
        self.migrations = []
    
    def backup_file(self, filepath: str):
        """Backup a file before migration"""
        try:
            source = Path(filepath)
            if not source.exists():
                logger.warning(f"File not found for backup: {filepath}")
                return False
            
            # Create backup directory
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            destination = self.backup_dir / source.name
            shutil.copy2(source, destination)
            
            logger.info(f"Backed up {filepath} to {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup {filepath}: {e}")
            return False
    
    def rename_old_files(self):
        """Rename old implementation files"""
        files_to_rename = [
            ('database.py', 'database_old.py'),
            ('auth.py', 'auth_old.py'),
        ]
        
        for old_name, new_name in files_to_rename:
            try:
                old_path = Path(old_name)
                new_path = Path(new_name)
                
                if old_path.exists() and not new_path.exists():
                    # Backup first
                    self.backup_file(old_name)
                    # Rename
                    old_path.rename(new_path)
                    logger.info(f"Renamed {old_name} to {new_name}")
                    self.migrations.append(f"✓ Renamed {old_name} → {new_name}")
                else:
                    logger.info(f"Skipping {old_name} (already renamed or not found)")
                    
            except Exception as e:
                logger.error(f"Failed to rename {old_name}: {e}")
                self.migrations.append(f"✗ Failed to rename {old_name}")
    
    def activate_new_files(self):
        """Activate new implementation files"""
        files_to_activate = [
            ('database_new.py', 'database.py'),
            ('auth_new.py', 'auth.py'),
        ]
        
        for new_name, target_name in files_to_activate:
            try:
                new_path = Path(new_name)
                target_path = Path(target_name)
                
                if new_path.exists():
                    # Copy new implementation
                    shutil.copy2(new_path, target_path)
                    logger.info(f"Activated {new_name} as {target_name}")
                    self.migrations.append(f"✓ Activated {new_name} → {target_name}")
                else:
                    logger.warning(f"New file not found: {new_name}")
                    self.migrations.append(f"✗ File not found: {new_name}")
                    
            except Exception as e:
                logger.error(f"Failed to activate {new_name}: {e}")
                self.migrations.append(f"✗ Failed to activate {new_name}")
    
    def update_imports_in_file(self, filepath: str):
        """Update import statements in a file"""
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                return False
            
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Backup
            self.backup_file(filepath)
            
            # Update imports
            modified = content
            
            # Update common imports
            replacements = [
                ('from database import Database', 'from database_new import Database'),
                ('from auth import hash_password', 'from auth_new import PasswordHasher'),
                ('from auth import verify_password', 'from auth_new import PasswordHasher'),
            ]
            
            for old, new in replacements:
                if old in modified:
                    modified = modified.replace(old, new)
                    logger.info(f"Updated import in {filepath}: {old} → {new}")
            
            # Write back if modified
            if modified != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(modified)
                logger.info(f"Updated imports in {filepath}")
                self.migrations.append(f"✓ Updated imports in {filepath}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update imports in {filepath}: {e}")
            self.migrations.append(f"✗ Failed to update {filepath}")
            return False
    
    def create_env_file(self):
        """Create .env file template"""
        try:
            env_path = Path('.env')
            
            if env_path.exists():
                logger.info(".env file already exists, skipping")
                return
            
            env_template = """# Neural Eye Configuration
# Copy this file to .env and customize

# Application
DEBUG=False
SECRET_KEY=change-this-to-a-random-secret-key
HOST=0.0.0.0
PORT=5000

# Database
DATABASE_PATH=neural_eye.db
DATABASE_POOL_SIZE=10
DATABASE_TIMEOUT=30

# Camera
USE_MOCK_CAMERA=True
CAMERA_INDEX=0
CAMERA_WIDTH=1280
CAMERA_HEIGHT=720
CAMERA_FPS=30

# Face Recognition
FACE_DETECTION_MODEL=hog
FACE_RECOGNITION_TOLERANCE=0.5
PROCESS_EVERY_N_FRAMES=2

# Attendance
WORK_START_TIME=08:00:00
WORK_END_TIME=17:00:00
GRACE_PERIOD_MINUTES=15
RECOGNITION_COOLDOWN_SECONDS=10

# Security
PASSWORD_MIN_LENGTH=8
MAX_LOGIN_ATTEMPTS=5
LOGIN_ATTEMPT_WINDOW_MINUTES=15
SESSION_LIFETIME_HOURS=24

# Logging
LOG_LEVEL=INFO
LOG_FILE=neural_eye.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# SMTP (Optional - for notifications)
# SMTP_SERVER=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=your-email@gmail.com
# SMTP_PASSWORD=your-app-password
"""
            
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(env_template)
            
            logger.info("Created .env template file")
            self.migrations.append("✓ Created .env template")
            
        except Exception as e:
            logger.error(f"Failed to create .env file: {e}")
            self.migrations.append("✗ Failed to create .env")
    
    def verify_dependencies(self):
        """Verify all required dependencies are installed"""
        required_packages = [
            'flask',
            'flask-cors',
            'opencv-python',
            'face-recognition',
            'numpy',
            'bcrypt',
            'PyJWT',
            'python-dotenv'
        ]
        
        missing = []
        
        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
                logger.info(f"✓ {package} is installed")
            except ImportError:
                missing.append(package)
                logger.warning(f"✗ {package} is NOT installed")
        
        if missing:
            logger.warning(f"Missing packages: {', '.join(missing)}")
            logger.info("Run: pip install -r requirements.txt")
            self.migrations.append(f"⚠ Missing packages: {', '.join(missing)}")
        else:
            logger.info("All required packages are installed")
            self.migrations.append("✓ All dependencies installed")
        
        return len(missing) == 0
    
    def run_migration(self, dry_run: bool = False):
        """Run full migration process"""
        logger.info("=" * 60)
        logger.info("NEURAL EYE - MIGRATION TO IMPROVED ARCHITECTURE")
        logger.info("=" * 60)
        
        if dry_run:
            logger.info("DRY RUN MODE - No files will be modified")
        
        # Step 1: Verify dependencies
        logger.info("\n[1/5] Verifying dependencies...")
        deps_ok = self.verify_dependencies()
        
        if not deps_ok and not dry_run:
            logger.error("Please install missing dependencies first!")
            return False
        
        # Step 2: Create .env file
        logger.info("\n[2/5] Creating .env configuration...")
        if not dry_run:
            self.create_env_file()
        else:
            logger.info("Would create .env file")
        
        # Step 3: Backup and rename old files
        logger.info("\n[3/5] Backing up old implementation...")
        if not dry_run:
            self.rename_old_files()
        else:
            logger.info("Would rename: database.py → database_old.py")
            logger.info("Would rename: auth.py → auth_old.py")
        
        # Step 4: Activate new files
        logger.info("\n[4/5] Activating new implementation...")
        if not dry_run:
            self.activate_new_files()
        else:
            logger.info("Would activate: database_new.py → database.py")
            logger.info("Would activate: auth_new.py → auth.py")
        
        # Step 5: Summary
        logger.info("\n[5/5] Migration Summary:")
        logger.info("=" * 60)
        for migration in self.migrations:
            logger.info(migration)
        
        logger.info("=" * 60)
        
        if dry_run:
            logger.info("\nDry run complete. Run without --dry-run to apply changes.")
        else:
            logger.info(f"\nMigration complete! Backups stored in: {self.backup_dir}")
            logger.info("\nNext steps:")
            logger.info("1. Review and customize .env file")
            logger.info("2. Test the application: python bootstrap.py")
            logger.info("3. Run the main application: python app.py")
            logger.info("\nIf anything goes wrong, restore from: " + str(self.backup_dir))
        
        return True


def main():
    """Main migration entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate to improved Neural Eye architecture')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run migration without making changes')
    
    args = parser.parse_args()
    
    migrator = MigrationHelper()
    success = migrator.run_migration(dry_run=args.dry_run)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
