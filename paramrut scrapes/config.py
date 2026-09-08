# App
APP_PACKAGE = "org.hariprabodham.swaminivato"

# Directories
APK_EXTRACT_DIR = "apk_extracted"
OUTPUT_DIR = "swamini_vaat"

# Set these after running inspect_assets.py
CONTENT_SOURCE = None   # e.g. "apk_extracted/assets/swamini_vaat.db"

# For SQLite source
CONTENT_TABLE = None    # e.g. "swamini_vaat"
CHAPTER_COLUMN = None   # e.g. "chapter_no"
ENTRY_COLUMN = None     # e.g. "content"
TITLE_COLUMN = None     # e.g. "chapter_title" (optional, can stay None)

# For JSON source
CONTENT_KEY = None      # e.g. "swaminiVaat" (top-level key); None if JSON is a bare array
