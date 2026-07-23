import os
import subprocess
import sys
import ctypes
import traceback

path = r"D:\moneymentor content\MONEY MENTOR.pdf"

print("=" * 80)
print("AUDITING MONEY MENTOR FILE OPENING")
print(f"Absolute path: {os.path.abspath(path)}")
print(f"Exists: {os.path.exists(path)}")
print(f"Is file: {os.path.isfile(path)}")
print(f"Extension: {os.path.splitext(path)[1]}")
print("=" * 80)

if not os.path.exists(path):
    print("FILE DOES NOT EXIST! ABORTING.")
    sys.exit(1)

# Test 1: os.startfile
try:
    print("[TEST 1] os.startfile(path)...")
    os.startfile(path)
    print("  -> os.startfile() executed with no exception.")
except Exception as e:
    print(f"  -> os.startfile() EXCEPTION: {e}\n{traceback.format_exc()}")

# Test 2: ShellExecuteW
try:
    print("[TEST 2] ShellExecuteW...")
    res = ctypes.windll.shell32.ShellExecuteW(None, "open", path, None, None, 1)
    print(f"  -> ShellExecuteW returned code: {res} (codes > 32 mean success)")
except Exception as e:
    print(f"  -> ShellExecuteW EXCEPTION: {e}\n{traceback.format_exc()}")

# Test 3: subprocess Popen cmd /c start "" "path"
try:
    print("[TEST 3] subprocess cmd start...")
    p = subprocess.Popen(["cmd", "/c", "start", "", path], shell=True)
    print(f"  -> cmd start process spawned PID: {p.pid}")
except Exception as e:
    print(f"  -> cmd start EXCEPTION: {e}\n{traceback.format_exc()}")

# Test 4: subprocess Popen explorer.exe "path"
try:
    print("[TEST 4] subprocess explorer.exe...")
    p = subprocess.Popen(["explorer.exe", path])
    print(f"  -> explorer process spawned PID: {p.pid}")
except Exception as e:
    print(f"  -> explorer EXCEPTION: {e}\n{traceback.format_exc()}")

print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
