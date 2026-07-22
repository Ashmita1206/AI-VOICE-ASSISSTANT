"""
Phase 1-10 Empirical Inspection of SQLite Database & Disk Folders
===================================================================
Inspects actual data/document_retrieval.db and local disk paths.
"""

import os
import sys
import sqlite3
import time
from pathlib import Path
from collections import Counter

from agentic.document_retrieval import config, scanner, metadata, retriever, search, ranking

def main():
    db_path = config.SQLITE_DB_PATH
    print(f"[DB INSPECTION] Target Database Path: {os.path.abspath(db_path)}")
    
    if not os.path.exists(db_path):
        print(f"[DB ERROR] Database file does not exist at {db_path}!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── PHASE 1: INDEX BREAKDOWN ─────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM docs")
    total_docs = cursor.fetchone()[0]
    print(f"\n========== PHASE 1: INDEX BREAKDOWN ==========")
    print(f"Total indexed files in SQLite DB: {total_docs}\n")

    cursor.execute("SELECT extension, COUNT(*) FROM docs GROUP BY extension ORDER BY COUNT(*) DESC")
    ext_counts = cursor.fetchall()
    print("Extension Breakdown:")
    for ext, count in ext_counts:
        print(f"  .{ext:<8}: {count} files")

    # Path Breakdown
    cursor.execute("SELECT path, filename, folder, extension FROM docs")
    all_rows = cursor.fetchall()

    folder_categories = Counter()
    system_python_count = 0
    
    for path, filename, folder, ext in all_rows:
        path_lower = path.lower()
        if any(sp in path_lower for sp in ["site-packages", "python", "lib", "appdata", "windows", "program files"]):
            system_python_count += 1
            
        for key in ["desktop", "downloads", "documents", "projects", "college", "dsmp", "healthsphere", "voltguard", "work"]:
            if key in path_lower or key in folder.lower():
                folder_categories[key] += 1

    print(f"\nSystem / Python / Lib files count in DB : {system_python_count} / {total_docs} ({system_python_count/max(1, total_docs)*100:.1f}%)")
    print("User Folder Category Counts in DB:")
    for cat, count in folder_categories.most_common():
        print(f"  - {cat:<15}: {count} files")

    # ── PHASE 6: REAL FILE EXISTENCE CHECK IN INDEX ──────────────────────────
    print("\n========== PHASE 6: REAL FILE EXISTENCE CHECK IN DB ==========")
    keywords = [
        "data", "science", "ds", "healthsphere", "healthcare", "voltguard",
        "research", "resume", "project", "presentation", "ai", "ml", "rag", "notebook"
    ]
    
    matching_files = []
    for kw in keywords:
        cursor.execute("SELECT id, path, filename, folder, extension FROM docs WHERE lower(filename) LIKE ? OR lower(folder) LIKE ? OR lower(summary) LIKE ?", (f"%{kw}%", f"%{kw}%", f"%{kw}%"))
        rows = cursor.fetchall()
        for r in rows:
            matching_files.append((kw, r))
            
    print(f"Total User Keyword DB Matches Found: {len(matching_files)}")
    seen = set()
    for kw, (doc_id, path, filename, folder, ext) in matching_files:
        if doc_id not in seen:
            seen.add(doc_id)
            print(f"  [MATCH: {kw:<12}] ID={doc_id:<3} | {filename:<35} | Ext: {ext:<5} | Path: {path}")

    if not seen:
        print("  WARNING: ZERO user document matches found in SQLite database!")

    # ── PHASE 8 & 9: CHECK USER DIRECTORIES ON DISK ─────────────────────────
    print("\n========== PHASE 8 & 9: USER DIRECTORIES CHECK ON DISK ==========")
    user_home = os.path.expanduser("~")
    target_dirs = [
        ("Desktop", os.path.join(user_home, "Desktop")),
        ("Downloads", os.path.join(user_home, "Downloads")),
        ("Documents", os.path.join(user_home, "Documents")),
        ("OneDrive", os.path.join(user_home, "OneDrive")),
        ("Projects", os.path.join(user_home, "Projects")),
        ("DSMP", os.path.join(user_home, "Documents", "DSMP")),
        ("HealthSphere", os.path.join(user_home, "Documents", "HealthSphere")),
        ("VoltGuard", os.path.join(user_home, "Documents", "VoltGuard")),
        ("College", os.path.join(user_home, "Documents", "College")),
        ("Research", os.path.join(user_home, "Documents", "Research")),
    ]

    for name, dpath in target_dirs:
        exists = os.path.exists(dpath)
        visited = False
        skipped = False
        reason = "N/A"
        indexed_in_db = 0
        
        if exists:
            visited = not scanner._should_skip_dir(os.path.dirname(dpath), os.path.basename(dpath))
            skipped = not visited
            if skipped:
                reason = f"Excluded by SKIP_DIR_NAMES or SKIP_PATH_FRAGMENTS"
            else:
                reason = "Visited by scanner"
                # Count docs in DB matching this path
                norm_d = dpath.lower().replace("/", "\\")
                cursor.execute("SELECT COUNT(*) FROM docs WHERE lower(path) LIKE ?", (f"{norm_d}%",))
                indexed_in_db = cursor.fetchone()[0]
        else:
            reason = "Path does not exist on this machine"
            
        print(f"Folder: {name:<14} | Path: {dpath}")
        print(f"  Exists: {exists} | Visited: {visited} | Skipped: {skipped} | DB Records: {indexed_in_db} | Reason: {reason}\n")

    conn.close()

if __name__ == "__main__":
    main()
