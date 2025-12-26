"""Verify camera and face_recognition status"""
import os, sys, json, urllib.request

# Ensure mock camera is OFF
os.environ['USE_MOCK_CAMERA'] = 'false'

# Fresh import - remove cached modules
for mod in list(sys.modules.keys()):
    if 'app' in mod or 'face' in mod.lower() or 'service' in mod.lower():
        del sys.modules[mod]

import app as a
import face_recognition_module as frm
import urllib.request

print("=== STATUS CHECK ===")
print(f"USE_MOCK_CAMERA: {os.environ.get('USE_MOCK_CAMERA', 'false')}")
print(f"face_recognition is None: {frm.face_recognition is None}")
print(f"App camera mode: {'real' if not a.USE_MOCK_CAMERA else 'mock'}")

# Test camera status endpoint
try:
    r = urllib.request.urlopen('http://localhost:5000/api/camera/status', timeout=10)
    data = json.loads(r.read().decode())
    print(f"\ncamera_is_opened: {data.get('camera_is_opened')}")
    print(f"runtime_use_mock: {data.get('runtime_use_mock')}")
    print(f"camera_type: {data.get('camera_type')}")
    print(f"camera_found_after_retry: {data.get('camera_found_after_retry')}")
except Exception as e:
    print(f"Camera status error: {e}")

# Test health endpoint
try:
    r = urllib.request.urlopen('http://localhost:5000/api/health', timeout=5)
    health = json.loads(r.read().decode())
    print(f"\nHealth camera_mode: {health.get('camera_mode')}")
except Exception as e:
    print(f"\nHealth error: {e}")

# Test if face_recognition library is available
try:
    import face_recognition
    print(f"\nface_recognition library: INSTALLED")
except ImportError:
    print(f"\nface_recognition library: NOT INSTALLED (graceful fallback active)")

print("\n=== END STATUS ===")