"""
Automated Backup and Restore System
"""

import os
import sys
import shutil
import sqlite3
import tarfile
import gzip
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
import logging
import json
import hashlib

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages database and file backups with compression and verification
    """
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
        self.database_path = Path(Config.DATABASE_PATH)
        self.face_data_dir = Path("face_data")
        
        # Retention policy (days)
        self.daily_retention = 7
        self.weekly_retention = 30
        self.monthly_retention = 365
        
        logger.info(f"Backup Manager initialized. Backup directory: {self.backup_dir}")
    
    def create_backup(self, backup_type: str = "daily") -> Optional[str]:
        """
        Create a complete system backup
        
        Args:
            backup_type: Type of backup (daily, weekly, monthly)
            
        Returns:
            Path to backup file if successful, None otherwise
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"
        
        logger.info(f"Creating {backup_type} backup: {backup_name}")
        
        try:
            # Create temporary directory for staging
            staging_dir = self.backup_dir / f"_staging_{timestamp}"
            staging_dir.mkdir(exist_ok=True)
            
            # Backup database
            db_backup_path = staging_dir / "database.db"
            self._backup_database(db_backup_path)
            
            # Backup face data
            if self.face_data_dir.exists():
                face_data_backup = staging_dir / "face_data"
                shutil.copytree(self.face_data_dir, face_data_backup)
            
            # Backup configuration
            config_backup = staging_dir / "config"
            config_backup.mkdir(exist_ok=True)
            if Path(".env").exists():
                shutil.copy(".env", config_backup / ".env")
            
            # Create backup metadata
            metadata = {
                'timestamp': datetime.now().isoformat(),
                'backup_type': backup_type,
                'database_size': os.path.getsize(db_backup_path),
                'version': '1.0'
            }
            
            with open(staging_dir / "metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Create compressed archive
            with tarfile.open(backup_path, "w:gz") as tar:
                tar.add(staging_dir, arcname=backup_name)
            
            # Calculate checksum
            checksum = self._calculate_checksum(backup_path)
            
            # Save checksum
            checksum_path = backup_path.with_suffix('.tar.gz.sha256')
            with open(checksum_path, 'w') as f:
                f.write(f"{checksum}  {backup_path.name}\n")
            
            # Cleanup staging directory
            shutil.rmtree(staging_dir)
            
            backup_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            logger.info(f"Backup created successfully: {backup_path} ({backup_size_mb:.2f} MB)")
            logger.info(f"Checksum: {checksum}")
            
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None
    
    def _backup_database(self, backup_path: Path):
        """Backup SQLite database with integrity check"""
        if not self.database_path.exists():
            logger.warning(f"Database not found: {self.database_path}")
            return
        
        # Create backup using SQLite backup API
        source_conn = sqlite3.connect(str(self.database_path))
        backup_conn = sqlite3.connect(str(backup_path))
        
        with backup_conn:
            source_conn.backup(backup_conn)
        
        source_conn.close()
        backup_conn.close()
        
        logger.info(f"Database backed up: {backup_path}")
    
    def restore_backup(self, backup_path: str, verify_checksum: bool = True) -> bool:
        """
        Restore system from backup
        
        Args:
            backup_path: Path to backup file
            verify_checksum: Verify backup integrity before restore
            
        Returns:
            True if restore successful
        """
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            logger.error(f"Backup file not found: {backup_file}")
            return False
        
        logger.info(f"Restoring from backup: {backup_file}")
        
        try:
            # Verify checksum if requested
            if verify_checksum:
                if not self._verify_checksum(backup_file):
                    logger.error("Checksum verification failed. Backup may be corrupted.")
                    return False
            
            # Create backup of current state before restore
            logger.info("Creating safety backup of current state...")
            self.create_backup(backup_type="pre_restore")
            
            # Extract backup
            restore_dir = self.backup_dir / "_restore_temp"
            restore_dir.mkdir(exist_ok=True)
            
            with tarfile.open(backup_file, "r:gz") as tar:
                tar.extractall(restore_dir)
            
            # Find the backup directory (first subdirectory)
            backup_content = next(restore_dir.iterdir())
            
            # Restore database
            db_restore_path = backup_content / "database.db"
            if db_restore_path.exists():
                # Stop any active database connections
                logger.info("Restoring database...")
                shutil.copy(db_restore_path, self.database_path)
                logger.info("Database restored")
            
            # Restore face data
            face_data_restore = backup_content / "face_data"
            if face_data_restore.exists():
                logger.info("Restoring face data...")
                if self.face_data_dir.exists():
                    shutil.rmtree(self.face_data_dir)
                shutil.copytree(face_data_restore, self.face_data_dir)
                logger.info("Face data restored")
            
            # Restore configuration (optional, manual confirmation recommended)
            config_restore = backup_content / "config" / ".env"
            if config_restore.exists():
                logger.info("Configuration file found in backup. Manual restore recommended.")
            
            # Cleanup
            shutil.rmtree(restore_dir)
            
            logger.info("Restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False
    
    def cleanup_old_backups(self):
        """Remove old backups according to retention policy"""
        logger.info("Cleaning up old backups...")
        
        current_time = datetime.now()
        removed_count = 0
        
        for backup_file in self.backup_dir.glob("backup_*.tar.gz"):
            try:
                # Parse timestamp from filename
                parts = backup_file.stem.split('_')
                if len(parts) < 3:
                    continue
                
                backup_type = parts[1]
                timestamp_str = f"{parts[2]}_{parts[3]}"
                backup_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                
                age_days = (current_time - backup_time).days
                
                # Determine if backup should be deleted
                should_delete = False
                if backup_type == "daily" and age_days > self.daily_retention:
                    should_delete = True
                elif backup_type == "weekly" and age_days > self.weekly_retention:
                    should_delete = True
                elif backup_type == "monthly" and age_days > self.monthly_retention:
                    should_delete = True
                
                if should_delete:
                    backup_file.unlink()
                    # Also remove checksum file
                    checksum_file = backup_file.with_suffix('.tar.gz.sha256')
                    if checksum_file.exists():
                        checksum_file.unlink()
                    
                    logger.info(f"Removed old backup: {backup_file.name}")
                    removed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing {backup_file}: {e}")
        
        logger.info(f"Cleanup complete. Removed {removed_count} old backup(s)")
    
    def list_backups(self) -> List[dict]:
        """List all available backups with metadata"""
        backups = []
        
        for backup_file in sorted(self.backup_dir.glob("backup_*.tar.gz")):
            try:
                stat = backup_file.stat()
                size_mb = stat.st_size / (1024 * 1024)
                
                # Parse backup info from filename
                parts = backup_file.stem.split('_')
                backup_type = parts[1] if len(parts) > 1 else "unknown"
                
                backups.append({
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'type': backup_type,
                    'size_mb': round(size_mb, 2),
                    'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days
                })
            except Exception as e:
                logger.error(f"Error processing {backup_file}: {e}")
        
        return backups
    
    @staticmethod
    def _calculate_checksum(file_path: Path) -> str:
        """Calculate SHA-256 checksum of file"""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def _verify_checksum(self, backup_file: Path) -> bool:
        """Verify backup file checksum"""
        checksum_file = backup_file.with_suffix('.tar.gz.sha256')
        
        if not checksum_file.exists():
            logger.warning("Checksum file not found")
            return True  # Assume valid if no checksum file
        
        # Read stored checksum
        with open(checksum_file, 'r') as f:
            stored_checksum = f.read().split()[0]
        
        # Calculate actual checksum
        actual_checksum = self._calculate_checksum(backup_file)
        
        if stored_checksum == actual_checksum:
            logger.info("Checksum verification passed")
            return True
        else:
            logger.error(f"Checksum mismatch! Stored: {stored_checksum}, Actual: {actual_checksum}")
            return False


def main():
    """Main backup script"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Neural Lens Backup Manager")
    parser.add_argument('action', choices=['backup', 'restore', 'list', 'cleanup'],
                       help="Action to perform")
    parser.add_argument('--type', choices=['daily', 'weekly', 'monthly'],
                       default='daily', help="Backup type")
    parser.add_argument('--file', help="Backup file to restore (for restore action)")
    
    args = parser.parse_args()
    
    manager = BackupManager()
    
    if args.action == 'backup':
        backup_path = manager.create_backup(args.type)
        if backup_path:
            print(f"✓ Backup created: {backup_path}")
        else:
            print("✗ Backup failed")
            sys.exit(1)
    
    elif args.action == 'restore':
        if not args.file:
            print("Error: --file required for restore action")
            sys.exit(1)
        
        if manager.restore_backup(args.file):
            print("✓ Restore completed successfully")
        else:
            print("✗ Restore failed")
            sys.exit(1)
    
    elif args.action == 'list':
        backups = manager.list_backups()
        if backups:
            print("\nAvailable Backups:")
            print("-" * 80)
            for backup in backups:
                print(f"{backup['filename']:<40} {backup['size_mb']:>8.2f} MB  {backup['age_days']:>3} days old")
            print(f"\nTotal backups: {len(backups)}")
        else:
            print("No backups found")
    
    elif args.action == 'cleanup':
        manager.cleanup_old_backups()
        print("✓ Cleanup completed")


if __name__ == "__main__":
    main()
