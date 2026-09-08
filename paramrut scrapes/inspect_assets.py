"""
Phase 2: Inspect APK assets and report schema.
Run after extract_apk.py. Identifies SQLite/JSON files and prints their structure
so you can set CONTENT_SOURCE, CONTENT_TABLE, CHAPTER_COLUMN, ENTRY_COLUMN in config.py.
"""
import sqlite3
import json
from pathlib import Path

import config


def inspect_sqlite(db_path: Path) -> None:
    """Print table names, column names, and row counts for a SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\n  [SQLite] {db_path.name}")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM '{table}'")
        count = cursor.fetchone()[0]
        cursor.execute(f"PRAGMA table_info('{table}')")
        cols = [row[1] for row in cursor.fetchall()]
        print(f"    Table: {table!r}  ({count} rows)")
        print(f"    Columns: {', '.join(cols)}")
        if count > 0:
            cursor.execute(f"SELECT * FROM '{table}' LIMIT 1")
            row = dict(zip(cols, cursor.fetchone()))
            sample = {k: str(v)[:60] for k, v in row.items()}
            print(f"    Sample: {sample}")
    conn.close()


def inspect_json(json_path: Path) -> None:
    """Print top-level structure of a JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n  [JSON] {json_path.name}")
    if isinstance(data, list):
        print(f"    Bare array with {len(data)} items")
        if data and isinstance(data[0], dict):
            print(f"    Item keys: {list(data[0].keys())}")
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                print(f"    Key {key!r}: array({len(val)})")
                if val and isinstance(val[0], dict):
                    print(f"      Item keys: {list(val[0].keys())}")
            else:
                print(f"    Key {key!r}: {type(val).__name__} = {str(val)[:60]}")


def main():
    assets_dir = Path(config.APK_EXTRACT_DIR) / "assets"
    if not assets_dir.exists():
        print(f"✗ {assets_dir} not found. Run extract_apk.py first.")
        return

    found = False
    for path in sorted(assets_dir.rglob("*.db")):
        inspect_sqlite(path)
        found = True
    for path in sorted(assets_dir.rglob("*.json")):
        inspect_json(path)
        found = True

    if not found:
        print("No .db or .json files found in assets/. Full listing:")
        for path in sorted(assets_dir.rglob("*")):
            if path.is_file():
                size = path.stat().st_size
                print(f"  {path.relative_to(assets_dir)}  ({size:,} bytes)")

    print("\n--- Next step ---")
    print("Set in config.py:")
    print("  CONTENT_SOURCE  = path to the file above")
    print("  CONTENT_TABLE   = table name (SQLite) or omit for JSON")
    print("  CHAPTER_COLUMN  = column/key that identifies the chapter")
    print("  ENTRY_COLUMN    = column/key that holds the Swamini Vaat text")
    print("  TITLE_COLUMN    = column/key for chapter title (optional)")


if __name__ == "__main__":
    main()
