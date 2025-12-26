"""
Diagnostic Tool for System Health and Troubleshooting
"""

import sys
import os
from pathlib import Path
import logging
import json
from datetime import datetime
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.monitoring.watchdog import WatchdogMonitor
from src.core.logging_system import get_log_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiagnosticTool:
    """
    System diagnostic and troubleshooting tool
    """
    
    def __init__(self):
        self.results = {}
        self.watchdog = WatchdogMonitor(check_interval=1)
    
    def run_all_diagnostics(self) -> Dict:
        """Run all diagnostic checks"""
        print("=" * 60)
        print("NEURAL LENS - SYSTEM DIAGNOSTICS")
        print("=" * 60)
        print()
        
        self.check_python_version()
        self.check_dependencies()
        self.check_database()
        self.check_camera()
        self.check_face_data()
        self.check_system_health()
        self.check_disk_space()
        self.check_permissions()
        self.check_configuration()
        self.check_logs()
        
        return self.results
    
    def check_python_version(self):
        """Check Python version"""
        print("Checking Python version...")
        import sys
        version = sys.version_info
        
        if version.major == 3 and version.minor >= 8:
            status = "✓ PASS"
            self.results['python_version'] = {"status": "pass", "version": f"{version.major}.{version.minor}.{version.micro}"}
        else:
            status = "✗ FAIL"
            self.results['python_version'] = {"status": "fail", "version": f"{version.major}.{version.minor}.{version.micro}"}
        
        print(f"  {status} - Python {version.major}.{version.minor}.{version.micro}")
        print()
    
    def check_dependencies(self):
        """Check required dependencies"""
        print("Checking dependencies...")
        
        required = [
            'flask', 'opencv-python', 'face_recognition', 'numpy',
            'bcrypt', 'jwt', 'cryptography', 'psutil'
        ]
        
        missing = []
        for module in required:
            try:
                __import__(module)
                print(f"  ✓ {module}")
            except ImportError:
                print(f"  ✗ {module} - MISSING")
                missing.append(module)
        
        self.results['dependencies'] = {
            "status": "pass" if not missing else "fail",
            "missing": missing
        }
        print()
    
    def check_database(self):
        """Check database status"""
        print("Checking database...")
        
        from config import Config
        db_path = Path(Config.DATABASE_PATH)
        
        if db_path.exists():
            size_mb = db_path.stat().st_size / (1024 * 1024)
            print(f"  ✓ Database exists: {db_path}")
            print(f"    Size: {size_mb:.2f} MB")
            
            # Try to connect
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                print(f"    Tables: {', '.join(tables)}")
                self.results['database'] = {"status": "pass", "tables": tables, "size_mb": size_mb}
            except Exception as e:
                print(f"  ✗ Database error: {e}")
                self.results['database'] = {"status": "fail", "error": str(e)}
        else:
            print(f"  ✗ Database not found: {db_path}")
            self.results['database'] = {"status": "fail", "error": "not found"}
        
        print()
    
    def check_camera(self):
        """Check camera availability"""
        print("Checking camera...")
        
        try:
            import cv2
            camera = cv2.VideoCapture(0)
            
            if camera.isOpened():
                ret, frame = camera.read()
                if ret:
                    h, w = frame.shape[:2]
                    print(f"  ✓ Camera accessible")
                    print(f"    Resolution: {w}x{h}")
                    self.results['camera'] = {"status": "pass", "resolution": f"{w}x{h}"}
                else:
                    print(f"  ⚠ Camera opened but failed to read frame")
                    self.results['camera'] = {"status": "warning", "error": "no frame"}
            else:
                print(f"  ⚠ No camera detected (mock mode available)")
                self.results['camera'] = {"status": "warning", "note": "using mock mode"}
            
            camera.release()
        except Exception as e:
            print(f"  ✗ Camera check failed: {e}")
            self.results['camera'] = {"status": "fail", "error": str(e)}
        
        print()
    
    def check_face_data(self):
        """Check face data directory"""
        print("Checking face data...")
        
        face_data_dir = Path("face_data")
        
        if face_data_dir.exists():
            files = list(face_data_dir.glob("*.jpg")) + list(face_data_dir.glob("*.png"))
            print(f"  ✓ Face data directory exists")
            print(f"    Images: {len(files)}")
            self.results['face_data'] = {"status": "pass", "images": len(files)}
        else:
            print(f"  ⚠ Face data directory not found (will be created)")
            self.results['face_data'] = {"status": "warning", "note": "directory missing"}
        
        print()
    
    def check_system_health(self):
        """Check system resources"""
        print("Checking system health...")
        
        metrics = self.watchdog.get_system_metrics()
        
        print(f"  CPU Usage: {metrics.cpu_percent:.1f}%")
        print(f"  Memory Usage: {metrics.memory_percent:.1f}% ({metrics.memory_available_mb:.0f} MB available)")
        print(f"  Disk Usage: {metrics.disk_percent:.1f}% ({metrics.disk_free_gb:.2f} GB free)")
        
        if metrics.temperature:
            print(f"  Temperature: {metrics.temperature:.1f}°C")
        
        print(f"  Status: {metrics.status.value.upper()}")
        
        self.results['system_health'] = {
            "status": "pass" if metrics.status.value == "healthy" else "warning",
            "cpu": metrics.cpu_percent,
            "memory": metrics.memory_percent,
            "disk": metrics.disk_percent
        }
        print()
    
    def check_disk_space(self):
        """Check available disk space"""
        print("Checking disk space...")
        
        import shutil
        total, used, free = shutil.disk_usage("/")
        
        free_gb = free / (1024 ** 3)
        percent = (used / total) * 100
        
        if free_gb < 1.0:
            print(f"  ⚠ WARNING: Low disk space ({free_gb:.2f} GB free)")
            status = "warning"
        else:
            print(f"  ✓ Disk space OK ({free_gb:.2f} GB free)")
            status = "pass"
        
        self.results['disk_space'] = {"status": status, "free_gb": free_gb}
        print()
    
    def check_permissions(self):
        """Check file permissions"""
        print("Checking permissions...")
        
        paths_to_check = [
            Path("."),
            Path("logs"),
            Path("backups"),
            Path("face_data")
        ]
        
        all_ok = True
        for path in paths_to_check:
            if path.exists():
                if os.access(path, os.R_OK | os.W_OK):
                    print(f"  ✓ {path}")
                else:
                    print(f"  ✗ {path} - No read/write permission")
                    all_ok = False
            else:
                print(f"  ⚠ {path} - Does not exist")
        
        self.results['permissions'] = {"status": "pass" if all_ok else "fail"}
        print()
    
    def check_configuration(self):
        """Check configuration"""
        print("Checking configuration...")
        
        try:
            from config import Config
            
            print(f"  ✓ Configuration loaded")
            print(f"    Debug: {Config.DEBUG}")
            print(f"    Host: {Config.HOST}")
            print(f"    Port: {Config.PORT}")
            print(f"    Database: {Config.DATABASE_PATH}")
            
            self.results['configuration'] = {"status": "pass"}
        except Exception as e:
            print(f"  ✗ Configuration error: {e}")
            self.results['configuration'] = {"status": "fail", "error": str(e)}
        
        print()
    
    def check_logs(self):
        """Check log files"""
        print("Checking logs...")
        
        log_dir = Path("logs")
        
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))
            total_size = sum(f.stat().st_size for f in log_files) / (1024 * 1024)
            
            print(f"  ✓ Log directory exists")
            print(f"    Files: {len(log_files)}")
            print(f"    Total size: {total_size:.2f} MB")
            
            self.results['logs'] = {"status": "pass", "files": len(log_files), "size_mb": total_size}
        else:
            print(f"  ⚠ Log directory not found (will be created)")
            self.results['logs'] = {"status": "warning", "note": "directory missing"}
        
        print()
    
    def generate_report(self) -> str:
        """Generate diagnostic report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'system': 'Neural Lens',
            'diagnostics': self.results
        }
        
        report_path = Path("diagnostic_report.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return str(report_path)
    
    def print_summary(self):
        """Print diagnostic summary"""
        print("=" * 60)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 60)
        
        total = len(self.results)
        passed = sum(1 for r in self.results.values() if r.get('status') == 'pass')
        warnings = sum(1 for r in self.results.values() if r.get('status') == 'warning')
        failed = sum(1 for r in self.results.values() if r.get('status') == 'fail')
        
        print(f"Total Checks: {total}")
        print(f"  ✓ Passed: {passed}")
        print(f"  ⚠ Warnings: {warnings}")
        print(f"  ✗ Failed: {failed}")
        print()
        
        if failed == 0 and warnings == 0:
            print("✓ System is healthy and ready for operation")
        elif failed > 0:
            print("✗ System has critical issues that need attention")
        else:
            print("⚠ System has warnings but is operational")
        
        print("=" * 60)


def main():
    """Main diagnostic script"""
    tool = DiagnosticTool()
    tool.run_all_diagnostics()
    tool.print_summary()
    
    report_path = tool.generate_report()
    print(f"\nDiagnostic report saved to: {report_path}")


if __name__ == "__main__":
    main()
