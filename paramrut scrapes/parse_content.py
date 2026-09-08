"""
Phase 3: Parse Swamini Vaat from APK assets and write chapter files.
Run after inspect_assets.py and after setting config.py values.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

import config


def parse_sqlite(source: Path) -> dict:
    """
    Read Swamini Vaat entries from a SQLite database.
    Returns {chapter_key: {"title": str, "entries": [str]}}
    Returns {} and prints guidance if config is incomplete.
    """
    conn = sqlite3.connect(source)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if not config.CONTENT_TABLE:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        print("✗ CONTENT_TABLE not set in config.py")
        print(f"  Available tables: {tables}")
        conn.close()
        return {}

    cursor.execute(f"SELECT * FROM '{config.CONTENT_TABLE}' ORDER BY {config.CHAPTER_COLUMN}")
    rows = cursor.fetchall()
    conn.close()

    chapters = {}
    for row in rows:
        ch = row[config.CHAPTER_COLUMN]
        if ch not in chapters:
            title = (
                row[config.TITLE_COLUMN]
                if config.TITLE_COLUMN and config.TITLE_COLUMN in row.keys()
                else f"Chapter {ch}"
            )
            chapters[ch] = {"title": title, "entries": []}
        chapters[ch]["entries"].append(row[config.ENTRY_COLUMN])
    return chapters


def parse_json(source: Path) -> dict:
    """
    Read Swamini Vaat entries from a JSON file.
    Returns {chapter_key: {"title": str, "entries": [str]}}
    Returns {} and prints guidance if config is incomplete.
    """
    with open(source, "r", encoding="utf-8") as f:
        data = json.load(f)

    if config.CONTENT_KEY is None and isinstance(data, dict):
        print("✗ CONTENT_KEY not set in config.py")
        print(f"  Available keys: {list(data.keys())}")
        return {}

    items = data[config.CONTENT_KEY] if isinstance(data, dict) else data

    if not config.CHAPTER_COLUMN or not config.ENTRY_COLUMN:
        if items and isinstance(items[0], dict):
            print("✗ CHAPTER_COLUMN / ENTRY_COLUMN not set in config.py")
            print(f"  Available item keys: {list(items[0].keys())}")
        return {}

    chapters = {}
    for item in items:
        ch = item.get(config.CHAPTER_COLUMN, 1)
        if ch not in chapters:
            title = (
                item.get(config.TITLE_COLUMN, f"Chapter {ch}")
                if config.TITLE_COLUMN
                else f"Chapter {ch}"
            )
            chapters[ch] = {"title": title, "entries": []}
        chapters[ch]["entries"].append(item[config.ENTRY_COLUMN])
    return chapters


def write_output(chapters: dict, output_dir: Path) -> None:
    """Write one .txt file per chapter and an index.json manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)

    index = {
        "generated_at": datetime.now().isoformat(),
        "total_chapters": len(chapters),
        "total_entries": 0,
        "chapters": [],
    }

    for i, ch_key in enumerate(sorted(chapters.keys()), 1):
        ch = chapters[ch_key]
        title = ch["title"]
        entries = ch["entries"]

        safe_title = "".join(
            c if (c.isalnum() or c in " _-") else "_"
            for c in str(title)
        )[:50].strip().replace(" ", "_")
        filename = f"chapter_{i:03d}_{safe_title}.txt"

        lines = [
            "=" * 64,
            f"SWAMINI VAAT - Chapter {i}: {title}",
            "=" * 64,
            "",
        ]
        for j, entry in enumerate(entries, 1):
            lines += [f"Entry {j}", "-" * 64, entry, ""]

        (output_dir / filename).write_text("\n".join(lines), encoding="utf-8")
        print(f"✓ {filename}  ({len(entries)} entries)")

        index["total_entries"] += len(entries)
        index["chapters"].append({
            "number": i,
            "title": title,
            "entry_count": len(entries),
            "file": filename,
        })

    (output_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n✓ index.json written")
    print(f"Total: {index['total_chapters']} chapters, {index['total_entries']} entries")


def main():
    if not config.CONTENT_SOURCE:
        print("✗ CONTENT_SOURCE not set in config.py")
        print("  Run inspect_assets.py first to identify the right file")
        return

    source = Path(config.CONTENT_SOURCE)
    if not source.exists():
        print(f"✗ {source} not found")
        return

    if source.suffix == ".db":
        chapters = parse_sqlite(source)
    elif source.suffix == ".json":
        chapters = parse_json(source)
    else:
        print(f"✗ Unknown format: {source.suffix!r}  (expected .db or .json)")
        return

    if not chapters:
        return

    write_output(chapters, Path(config.OUTPUT_DIR))


if __name__ == "__main__":
    main()
