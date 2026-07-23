import os
import subprocess
import sys
import time

file_path = r"D:\healthsphere content\Healthsphere.pdf"

print("=" * 80)
print(f"TESTING NATIVE WINDOWS OPEN FOR: {file_path!r}")
print(f"Exists: {os.path.exists(file_path)}")
print("=" * 80)

methods = []

# Method 1: os.startfile(path)
try:
    print("[1] Executing os.startfile(file_path)...")
    os.startfile(file_path)
    print("    -> os.startfile() returned without exception")
    methods.append("os.startfile")
except Exception as e:
    print(f"    -> os.startfile() failed: {e}")

time.sleep(2)

# Method 2: os.startfile(path, 'open')
try:
    print("[2] Executing os.startfile(file_path, 'open')...")
    os.startfile(file_path, 'open')
    print("    -> os.startfile('open') returned without exception")
    methods.append("os.startfile_open")
except Exception as e:
    print(f"    -> os.startfile('open') failed: {e}")

time.sleep(2)

# Method 3: cmd /c start "" "path"
try:
    print("[3] Executing cmd /c start...")
    subprocess.Popen(f'cmd /c start "" "{file_path}"', shell=True)
    print("    -> cmd start process spawned")
    methods.append("cmd_start")
except Exception as e:
    print(f"    -> cmd start failed: {e}")

time.sleep(2)

# Method 4: explorer.exe "path"
try:
    print("[4] Executing explorer.exe...")
    subprocess.Popen(["explorer.exe", file_path])
    print("    -> explorer process spawned")
    methods.append("explorer")
except Exception as e:
    print(f"    -> explorer failed: {e}")

time.sleep(2)

# Method 5: powershell Start-Process
try:
    print("[5] Executing powershell Start-Process...")
    subprocess.Popen(["powershell", "-NoProfile", "-Command", f'Start-Process -FilePath "{file_path}"'])
    print("    -> powershell Start-Process spawned")
    methods.append("powershell_start_process")
except Exception as e:
    print(f"    -> powershell failed: {e}")

print("=" * 80)
print(f"ALL METHODS EXECUTED. Successful methods: {methods}")
print("=" * 80)
