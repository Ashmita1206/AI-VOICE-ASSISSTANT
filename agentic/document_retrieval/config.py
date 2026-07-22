"""
Document Retrieval Configuration
================================

Central configuration settings for the document retrieval engine.
"""

import os
import sys

# ── Paths ──────────────────────────────────────────────────────────────────
_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data"
)
SQLITE_DB_PATH = os.path.join(_DB_DIR, "document_retrieval.db")
FAISS_INDEX_PATH = os.path.join(_DB_DIR, "faiss_index.bin")

# ── Embedding Models ───────────────────────────────────────────────────────
PRIMARY_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
FALLBACK_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
MAX_EMBED_CHARS = 1000

# ── Indexing Settings ──────────────────────────────────────────────────────
RESCAN_INTERVAL_SECONDS = 30 * 60  # 30 minutes
BATCH_SIZE = 50
MAX_WORKERS = 4
MAX_EXTRACT_CHARS = 20000

# 50 MB maximum file size to scan
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# ── Supported File Extensions ──────────────────────────────────────────────
HIGH_PRIORITY_DOC_EXTENSIONS = frozenset({
    "pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "txt", "md",
    "ipynb", "csv", "rtf", "odt", "ods", "odp", "png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "json"
})

SECOND_PRIORITY_CODE_EXTENSIONS = frozenset()

SUPPORTED_EXTENSIONS = HIGH_PRIORITY_DOC_EXTENSIONS

NEVER_INDEX_EXTENSIONS = frozenset({
    "dll", "exe", "sys", "cache", "log", "tmp", "pyc", "obj", "class", "so", "dylib", "shm", "wal",
    "py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h", "css", "html", "xml", "pyd"
})

# ── User Priority Folders (Metadata Boosted) ────────────────────────────────
USER_PRIORITY_FOLDERS = frozenset({
    "desktop", "documents", "downloads", "onedrive", "pictures", "projects",
    "workspaces", "dsmp", "college", "healthsphere", "voltguard", "research",
    "notes", "pdfs", "books", "ai voice assisstant"
})

# ── Excluded System Directories (Phase 6 Specification) ────────────────────
# ONLY skip system/environment/build artifacts. DO NOT skip user project subfolders!
SKIP_DIR_NAMES = frozenset({
    "node_modules", "venv", ".venv", "env", ".env", "__pycache__", ".git", ".idea", ".vscode",
    "dist", "build", "target", "out", ".cache", "tmp", "temp",
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "appdata", "local settings",
    "site-packages", "dist-packages", "dlls",
    "python37", "python38", "python39", "python310", "python311", "python312", "python313", "python314",
    "anaconda3", "miniconda3", "conda", "jdk", "gradle", "maven", "npm", "pip", "rust", "cargo", "go",
    "vs code", "visual studio", "pycharm", "jetbrains", "microsoft sdks", "intel", "nvidia", "amd",
    "xampp", "tomcat", "webapps", "apache"
})

SKIP_PATH_FRAGMENTS = (
    "\\appdata\\",
    "\\local settings\\",
    "\\temporary internet files\\",
    "\\windows\\",
    "\\program files",
    "\\site-packages\\",
    "\\dist-packages\\",
    "\\python3",
    "\\anaconda",
    "\\miniconda",
    "\\xampp\\",
    "\\tomcat\\",
    "\\webapps\\",
    "\\$recycle.bin\\",
    "\\node_modules\\",
)
