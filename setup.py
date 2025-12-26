"""
NEURAL EYE - Setup Script
Automatically install and verify all dependencies
"""

import subprocess
import sys
import os
from pathlib import Path


def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def check_python_version():
    """Check if Python version is compatible"""
    print_header("Checking Python Version")
    
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required!")
        return False
    
    print("✅ Python version is compatible")
    return True


def install_package(package_name):
    """Install a single package"""
    try:
        print(f"Installing {package_name}...", end=" ")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("✅")
        return True
    except subprocess.CalledProcessError:
        print("❌")
        return False


def install_requirements():
    """Install all requirements from requirements.txt"""
    print_header("Installing Dependencies")
    
    requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print("❌ requirements.txt not found!")
        return False
    
    print("Reading requirements.txt...")
    
    with open(requirements_file, 'r') as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"Found {len(packages)} packages to install\n")
    
    failed = []
    
    for package in packages:
        if not install_package(package):
            failed.append(package)
    
    if failed:
        print(f"\n❌ Failed to install: {', '.join(failed)}")
        return False
    
    print("\n✅ All packages installed successfully!")
    return True


def verify_imports():
    """Verify all critical imports work"""
    print_header("Verifying Imports")
    
    imports_to_check = {
        'flask': 'Flask',
        'flask_cors': 'Flask-CORS',
        'cv2': 'OpenCV',
        'face_recognition': 'Face Recognition',
        'numpy': 'NumPy',
        'bcrypt': 'Bcrypt',
        'jwt': 'PyJWT',
        'dotenv': 'python-dotenv',
        'sqlite3': 'SQLite3 (built-in)'
    }
    
    failed = []
    
    for module, name in imports_to_check.items():
        try:
            print(f"Checking {name}...", end=" ")
            __import__(module)
            print("✅")
        except ImportError:
            print("❌")
            failed.append(name)
    
    if failed:
        print(f"\n❌ Failed to import: {', '.join(failed)}")
        print("\nTry installing manually:")
        for name in failed:
            print(f"  pip install {name.lower().replace(' ', '-')}")
        return False
    
    print("\n✅ All imports verified!")
    return True


def create_env_file():
    """Create .env file if it doesn't exist"""
    print_header("Setting Up Configuration")
    
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    if not env_example.exists():
        print("❌ .env.example not found!")
        return False
    
    print("Creating .env file from template...", end=" ")
    
    try:
        import shutil
        shutil.copy(env_example, env_file)
        print("✅")
        print("\n⚠️  IMPORTANT: Edit .env and set your SECRET_KEY!")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def verify_file_structure():
    """Verify all required files exist"""
    print_header("Verifying File Structure")
    
    required_files = [
        'config.py',
        'database_new.py',
        'auth_new.py',
        'services.py',
        'utils.py',
        'bootstrap.py',
        'requirements.txt',
        '.env.example'
    ]
    
    missing = []
    
    for file in required_files:
        path = Path(file)
        print(f"Checking {file}...", end=" ")
        if path.exists():
            print("✅")
        else:
            print("❌")
            missing.append(file)
    
    if missing:
        print(f"\n❌ Missing files: {', '.join(missing)}")
        return False
    
    print("\n✅ All required files present!")
    return True


def create_directories():
    """Create required directories"""
    print_header("Creating Directories")
    
    directories = [
        'face_data',
        'frontend/static',
        'backups'
    ]
    
    for directory in directories:
        path = Path(directory)
        print(f"Creating {directory}...", end=" ")
        try:
            path.mkdir(parents=True, exist_ok=True)
            print("✅")
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    print("\n✅ All directories created!")
    return True


def test_database_connection():
    """Test database initialization"""
    print_header("Testing Database")
    
    try:
        print("Initializing database...", end=" ")
        from database_new import Database
        db = Database()
        print("✅")
        
        print("Testing connection...", end=" ")
        count = db.employees.count()
        print(f"✅ ({count} employees)")
        
        db.close()
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def run_setup():
    """Run complete setup process"""
    print("\n" + "=" * 60)
    print("  NEURAL EYE - Automated Setup")
    print("=" * 60)
    
    steps = [
        ("Check Python Version", check_python_version),
        ("Verify File Structure", verify_file_structure),
        ("Install Dependencies", install_requirements),
        ("Verify Imports", verify_imports),
        ("Create Directories", create_directories),
        ("Setup Configuration", create_env_file),
        ("Test Database", test_database_connection),
    ]
    
    results = []
    
    for step_name, step_func in steps:
        try:
            success = step_func()
            results.append((step_name, success))
            
            if not success:
                print(f"\n⚠️  Setup incomplete due to error in: {step_name}")
                break
        except Exception as e:
            print(f"\n❌ Error in {step_name}: {e}")
            results.append((step_name, False))
            break
    
    # Print summary
    print_header("Setup Summary")
    
    for step_name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {step_name}")
    
    all_success = all(success for _, success in results)
    
    if all_success:
        print_header("Setup Complete! 🎉")
        print("Next steps:")
        print("  1. Edit .env file (set SECRET_KEY)")
        print("  2. Run: python bootstrap.py (to test)")
        print("  3. Run: python app.py (to start)")
        print("\nFor more info, read: IMPLEMENTATION_GUIDE.md")
    else:
        print_header("Setup Incomplete")
        print("Please resolve the errors above and run setup.py again.")
        return 1
    
    return 0


if __name__ == '__main__':
    try:
        exit_code = run_setup()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)
