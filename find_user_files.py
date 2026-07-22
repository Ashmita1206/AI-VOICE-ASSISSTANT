"""
Find user document files on disk
"""

import os

user_home = os.path.expanduser("~")
print(f"User Home: {user_home}")

found_files = []
for root, dirs, files in os.walk(user_home):
    # skip appdata / hidden
    dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ["appdata", "local settings", "node_modules", "vendor", "cache"]]
    for f in files:
        ext = f.rsplit(".", 1)[-1].lower() if "." in f else ""
        if ext in ["pdf", "docx", "pptx", "ipynb", "xlsx"]:
            fp = os.path.join(root, f)
            found_files.append((ext, f, fp))

print(f"Total User Documents Found under {user_home}: {len(found_files)}\n")
for ext, f, fp in found_files[:40]:
    print(f"  [{ext:<5}] {f:<40} | Path: {fp}")
