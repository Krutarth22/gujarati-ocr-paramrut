# Swamini Vaat Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract full Swamini Vaat content from the Paramrut APK's bundled assets and save it as chapter-organised `.txt` files.

**Architecture:** Pull the APK from the Android emulator via ADB, unzip it, inspect bundled SQLite/JSON assets to locate Swamini Vaat content, then parse and write one `.txt` file per chapter plus an `index.json` manifest.

**Tech Stack:** Python 3, `subprocess` (ADB), `zipfile`, `sqlite3`, `json`, `pytest`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `config.py` | App package, paths, content source config |
| Create | `extract_apk.py` | Pull APK from emulator, unzip, print asset tree |
| Create | `inspect_assets.py` | Scan assets for DB/JSON, print schema/structure |
| Create | `parse_content.py` | Read source, group by chapter, write output files |
| Create | `tests/test_extract_apk.py` | Unit tests for extract/unzip logic |
| Create | `tests/test_inspect_assets.py` | Unit tests for asset inspection |
| Create | `tests/test_parse_content.py` | Unit tests for parsing and output writing |
| Delete | `scraper.py`, `ui_navigator.py`, `adb_manager.py`, `text_extractor.py`, `storage_manager.py`, `manual_navigation.py`, `install_xapk.sh`, `launch_emulator.sh`, `verify_setup.py`, `inspect_ui.py`, `EMULATOR_SETUP.md`, `QUICKSTART.md` | Replaced by new approach |

---

## Task 1: Clean up old files and update config

**Files:**
- Modify: `config.py`
- Delete: all files listed in the Delete row above

- [ ] **Step 1: Delete old files**

```bash
cd "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes"
rm scraper.py ui_navigator.py adb_manager.py text_extractor.py storage_manager.py \
   manual_navigation.py inspect_ui.py verify_setup.py \
   install_xapk.sh launch_emulator.sh \
   EMULATOR_SETUP.md QUICKSTART.md
```

- [ ] **Step 2: Replace config.py**

Replace the full contents of `config.py` with:

```python
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
```

- [ ] **Step 3: Create tests directory**

```bash
mkdir -p "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes/tests"
touch "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes/tests/__init__.py"
```

- [ ] **Step 4: Update requirements.txt**

Replace contents of `requirements.txt`:

```
pytest>=8.0.0
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes"
git init  # only if not already a git repo
git add config.py requirements.txt tests/
git commit -m "chore: reset project for APK-extraction approach"
```

---

## Task 2: extract_apk.py — pull and unzip APK from emulator

**Files:**
- Create: `extract_apk.py`
- Create: `tests/test_extract_apk.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extract_apk.py`:

```python
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent))
import extract_apk


def test_get_apk_path_returns_path_on_success():
    mock_result = MagicMock(returncode=0, stdout="package:/data/app/org.hariprabodham.swaminivato/base.apk\n")
    with patch("extract_apk.subprocess.run", return_value=mock_result):
        path = extract_apk.get_apk_path("org.hariprabodham.swaminivato")
    assert path == "/data/app/org.hariprabodham.swaminivato/base.apk"


def test_get_apk_path_exits_when_not_found():
    mock_result = MagicMock(returncode=1, stdout="")
    with patch("extract_apk.subprocess.run", return_value=mock_result):
        with pytest.raises(SystemExit):
            extract_apk.get_apk_path("org.hariprabodham.swaminivato")


def test_pull_apk_exits_on_failure(tmp_path):
    mock_result = MagicMock(returncode=1, stderr="error: device not found")
    with patch("extract_apk.subprocess.run", return_value=mock_result):
        with pytest.raises(SystemExit):
            extract_apk.pull_apk("/data/app/base.apk", tmp_path / "out.apk")


def test_extract_apk_unzips_contents(tmp_path):
    apk_path = tmp_path / "test.apk"
    extract_dir = tmp_path / "extracted"
    # Create a fake APK (ZIP with one file)
    with zipfile.ZipFile(apk_path, "w") as z:
        z.writestr("assets/data.db", b"fake db content")
    extract_apk.extract_apk(apk_path, extract_dir)
    assert (extract_dir / "assets" / "data.db").exists()


def test_print_asset_tree_lists_files(tmp_path, capsys):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "swamini.db").write_bytes(b"x" * 1024)
    (assets / "config.json").write_bytes(b"y" * 200)
    extract_apk.print_asset_tree(tmp_path)
    out = capsys.readouterr().out
    assert "swamini.db" in out
    assert "config.json" in out
    assert "1,024" in out


def test_print_asset_tree_warns_when_no_assets(tmp_path, capsys):
    extract_apk.print_asset_tree(tmp_path)
    out = capsys.readouterr().out
    assert "No assets/" in out
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes"
python -m pytest tests/test_extract_apk.py -v
```

Expected: `ModuleNotFoundError: No module named 'extract_apk'` or multiple FAILs.

- [ ] **Step 3: Create extract_apk.py**

Create `extract_apk.py`:

```python
"""
Phase 1: Pull APK from emulator and unzip it.
Run this first. Requires the emulator to be running with the app installed.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import config


def get_apk_path(package: str) -> str:
    """Return on-device APK path for the given package name."""
    result = subprocess.run(
        ["adb", "shell", "pm", "path", package],
        capture_output=True, text=True
    )
    if result.returncode != 0 or "package:" not in result.stdout:
        print(f"✗ App '{package}' not found on device")
        print("  Make sure the emulator is running and the app is installed")
        sys.exit(1)
    return result.stdout.strip().split("package:")[1]


def pull_apk(device_path: str, local_path: Path) -> None:
    """Pull APK from device to local_path."""
    result = subprocess.run(
        ["adb", "pull", device_path, str(local_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"✗ Failed to pull APK: {result.stderr.strip()}")
        sys.exit(1)
    print(f"✓ APK pulled to {local_path}")


def extract_apk(apk_path: Path, extract_dir: Path) -> None:
    """Unzip APK into extract_dir."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk_path, "r") as z:
        z.extractall(extract_dir)
    print(f"✓ APK extracted to {extract_dir}")


def print_asset_tree(extract_dir: Path) -> None:
    """Print a file listing of the assets/ subdirectory."""
    assets_dir = extract_dir / "assets"
    if not assets_dir.exists():
        print("⚠ No assets/ directory found in APK")
        return
    print("\n=== ASSET INVENTORY ===")
    for path in sorted(assets_dir.rglob("*")):
        if path.is_file():
            size = path.stat().st_size
            rel = path.relative_to(extract_dir)
            print(f"  {rel}  ({size:,} bytes)")


def main():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    connected = [l for l in result.stdout.splitlines()[1:] if l.strip() and "offline" not in l]
    if not connected:
        print("✗ No Android emulator/device found")
        print("  Start the emulator and try again: adb devices")
        sys.exit(1)

    device_apk_path = get_apk_path(config.APP_PACKAGE)
    local_apk = Path("paramrut.apk")
    pull_apk(device_apk_path, local_apk)

    extract_dir = Path(config.APK_EXTRACT_DIR)
    extract_apk(local_apk, extract_dir)
    print_asset_tree(extract_dir)
    print(f"\nNext step: run inspect_assets.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes"
python -m pytest tests/test_extract_apk.py -v
```

Expected: 6 PASSed.

- [ ] **Step 5: Commit**

```bash
git add extract_apk.py tests/test_extract_apk.py
git commit -m "feat: add extract_apk - pull and unzip APK from emulator"
```

---

## Task 3: inspect_assets.py — scan assets and report schema

**Files:**
- Create: `inspect_assets.py`
- Create: `tests/test_inspect_assets.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_inspect_assets.py`:

```python
import sqlite3
import json
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import inspect_assets


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE swamini_vaat (id INTEGER, chapter INTEGER, content TEXT)")
    conn.execute("INSERT INTO swamini_vaat VALUES (1, 1, 'test content')")
    conn.execute("CREATE TABLE chapters (id INTEGER, title TEXT)")
    conn.commit()
    conn.close()


def test_inspect_sqlite_prints_table_names(tmp_path, capsys):
    db = tmp_path / "test.db"
    make_db(db)
    inspect_assets.inspect_sqlite(db)
    out = capsys.readouterr().out
    assert "swamini_vaat" in out
    assert "chapters" in out


def test_inspect_sqlite_prints_row_counts(tmp_path, capsys):
    db = tmp_path / "test.db"
    make_db(db)
    inspect_assets.inspect_sqlite(db)
    out = capsys.readouterr().out
    assert "1 row" in out or "1)" in out or "(1" in out or "1 rows" in out


def test_inspect_sqlite_prints_column_names(tmp_path, capsys):
    db = tmp_path / "test.db"
    make_db(db)
    inspect_assets.inspect_sqlite(db)
    out = capsys.readouterr().out
    assert "chapter" in out
    assert "content" in out


def test_inspect_json_dict_prints_keys(tmp_path, capsys):
    jf = tmp_path / "data.json"
    jf.write_text(json.dumps({"swaminiVaat": [{"chapter": 1, "text": "a"}] * 5}), encoding="utf-8")
    inspect_assets.inspect_json(jf)
    out = capsys.readouterr().out
    assert "swaminiVaat" in out
    assert "5" in out


def test_inspect_json_array_reports_length(tmp_path, capsys):
    jf = tmp_path / "data.json"
    jf.write_text(json.dumps([{"ch": 1}] * 3), encoding="utf-8")
    inspect_assets.inspect_json(jf)
    out = capsys.readouterr().out
    assert "3" in out


def test_main_reports_no_assets_when_dir_missing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("inspect_assets.config.APK_EXTRACT_DIR", str(tmp_path / "empty"))
    inspect_assets.main()
    out = capsys.readouterr().out
    assert "not found" in out or "Run extract_apk" in out
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_inspect_assets.py -v
```

Expected: `ModuleNotFoundError: No module named 'inspect_assets'`

- [ ] **Step 3: Create inspect_assets.py**

Create `inspect_assets.py`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_inspect_assets.py -v
```

Expected: 6 PASSed.

- [ ] **Step 5: Commit**

```bash
git add inspect_assets.py tests/test_inspect_assets.py
git commit -m "feat: add inspect_assets - report schema of APK asset files"
```

---

## Task 4: parse_content.py — extract chapters and write output files

**Files:**
- Create: `parse_content.py`
- Create: `tests/test_parse_content.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_parse_content.py`:

```python
import sqlite3
import json
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import parse_content


# ── helpers ──────────────────────────────────────────────────────────────────

def make_sqlite_source(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE sv (
            id INTEGER PRIMARY KEY,
            chapter_no INTEGER,
            chapter_title TEXT,
            body TEXT
        )
    """)
    rows = [
        (1, 1, "Gadhada Pratham", "First entry text"),
        (2, 1, "Gadhada Pratham", "Second entry text"),
        (3, 2, "Sarangpur",       "Sarangpur entry"),
    ]
    conn.executemany("INSERT INTO sv VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()


def make_json_source(path: Path) -> None:
    data = {
        "swaminiVaat": [
            {"chapter_no": 1, "chapter_title": "Gadhada Pratham", "body": "First entry text"},
            {"chapter_no": 1, "chapter_title": "Gadhada Pratham", "body": "Second entry text"},
            {"chapter_no": 2, "chapter_title": "Sarangpur",       "body": "Sarangpur entry"},
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")


# ── parse_sqlite ──────────────────────────────────────────────────────────────

def test_parse_sqlite_returns_two_chapters(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    make_sqlite_source(db)
    monkeypatch.setattr("parse_content.config.CONTENT_TABLE", "sv")
    monkeypatch.setattr("parse_content.config.CHAPTER_COLUMN", "chapter_no")
    monkeypatch.setattr("parse_content.config.ENTRY_COLUMN", "body")
    monkeypatch.setattr("parse_content.config.TITLE_COLUMN", "chapter_title")
    chapters = parse_content.parse_sqlite(db)
    assert len(chapters) == 2


def test_parse_sqlite_chapter1_has_two_entries(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    make_sqlite_source(db)
    monkeypatch.setattr("parse_content.config.CONTENT_TABLE", "sv")
    monkeypatch.setattr("parse_content.config.CHAPTER_COLUMN", "chapter_no")
    monkeypatch.setattr("parse_content.config.ENTRY_COLUMN", "body")
    monkeypatch.setattr("parse_content.config.TITLE_COLUMN", "chapter_title")
    chapters = parse_content.parse_sqlite(db)
    assert len(chapters[1]["entries"]) == 2
    assert chapters[1]["entries"][0] == "First entry text"


def test_parse_sqlite_returns_empty_when_table_not_set(tmp_path, monkeypatch, capsys):
    db = tmp_path / "test.db"
    make_sqlite_source(db)
    monkeypatch.setattr("parse_content.config.CONTENT_TABLE", None)
    monkeypatch.setattr("parse_content.config.CHAPTER_COLUMN", None)
    monkeypatch.setattr("parse_content.config.ENTRY_COLUMN", None)
    monkeypatch.setattr("parse_content.config.TITLE_COLUMN", None)
    result = parse_content.parse_sqlite(db)
    assert result == {}
    out = capsys.readouterr().out
    assert "CONTENT_TABLE" in out


# ── parse_json ────────────────────────────────────────────────────────────────

def test_parse_json_returns_two_chapters(tmp_path, monkeypatch):
    jf = tmp_path / "data.json"
    make_json_source(jf)
    monkeypatch.setattr("parse_content.config.CONTENT_KEY", "swaminiVaat")
    monkeypatch.setattr("parse_content.config.CHAPTER_COLUMN", "chapter_no")
    monkeypatch.setattr("parse_content.config.ENTRY_COLUMN", "body")
    monkeypatch.setattr("parse_content.config.TITLE_COLUMN", "chapter_title")
    chapters = parse_content.parse_json(jf)
    assert len(chapters) == 2


def test_parse_json_chapter_title_preserved(tmp_path, monkeypatch):
    jf = tmp_path / "data.json"
    make_json_source(jf)
    monkeypatch.setattr("parse_content.config.CONTENT_KEY", "swaminiVaat")
    monkeypatch.setattr("parse_content.config.CHAPTER_COLUMN", "chapter_no")
    monkeypatch.setattr("parse_content.config.ENTRY_COLUMN", "body")
    monkeypatch.setattr("parse_content.config.TITLE_COLUMN", "chapter_title")
    chapters = parse_content.parse_json(jf)
    assert chapters[1]["title"] == "Gadhada Pratham"


def test_parse_json_returns_empty_when_key_not_set(tmp_path, monkeypatch, capsys):
    jf = tmp_path / "data.json"
    make_json_source(jf)
    monkeypatch.setattr("parse_content.config.CONTENT_KEY", None)
    monkeypatch.setattr("parse_content.config.CHAPTER_COLUMN", None)
    monkeypatch.setattr("parse_content.config.ENTRY_COLUMN", None)
    monkeypatch.setattr("parse_content.config.TITLE_COLUMN", None)
    result = parse_content.parse_json(jf)
    assert result == {}
    assert "CONTENT_KEY" in capsys.readouterr().out


# ── write_output ──────────────────────────────────────────────────────────────

def test_write_output_creates_chapter_files(tmp_path):
    chapters = {
        1: {"title": "Gadhada Pratham", "entries": ["Entry A", "Entry B"]},
        2: {"title": "Sarangpur",       "entries": ["Entry C"]},
    }
    parse_content.write_output(chapters, tmp_path)
    files = list(tmp_path.glob("chapter_*.txt"))
    assert len(files) == 2


def test_write_output_file_contains_entry_text(tmp_path):
    chapters = {1: {"title": "Test Chapter", "entries": ["Hello Gujarati text"]}}
    parse_content.write_output(chapters, tmp_path)
    txt = list(tmp_path.glob("chapter_*.txt"))[0].read_text(encoding="utf-8")
    assert "Hello Gujarati text" in txt
    assert "SWAMINI VAAT" in txt
    assert "Test Chapter" in txt


def test_write_output_creates_index_json(tmp_path):
    chapters = {1: {"title": "Ch1", "entries": ["e1", "e2"]}}
    parse_content.write_output(chapters, tmp_path)
    import json
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["total_chapters"] == 1
    assert index["total_entries"] == 2
    assert index["chapters"][0]["title"] == "Ch1"


def test_write_output_chapter_files_ordered(tmp_path):
    chapters = {
        3: {"title": "Third", "entries": ["c"]},
        1: {"title": "First", "entries": ["a"]},
        2: {"title": "Second", "entries": ["b"]},
    }
    parse_content.write_output(chapters, tmp_path)
    files = sorted(tmp_path.glob("chapter_*.txt"))
    names = [f.name for f in files]
    assert names[0].startswith("chapter_001")
    assert names[1].startswith("chapter_002")
    assert names[2].startswith("chapter_003")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_parse_content.py -v
```

Expected: `ModuleNotFoundError: No module named 'parse_content'`

- [ ] **Step 3: Create parse_content.py**

Create `parse_content.py`:

```python
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
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASSed (Task 2 + 3 + 4 tests).

- [ ] **Step 5: Commit**

```bash
git add parse_content.py tests/test_parse_content.py
git commit -m "feat: add parse_content - extract Swamini Vaat by chapter"
```

---

## Task 5: End-to-end smoke test on the emulator

This task runs the full pipeline against the real emulator and confirms actual content is extracted. No automated test — this is a manual verification step.

- [ ] **Step 1: Confirm emulator is running with the app installed**

```bash
adb devices
adb shell pm path org.hariprabodham.swaminivato
```

Expected: a device listed, and `package:/data/app/...` path printed.

- [ ] **Step 2: Run Phase 1 — extract APK**

```bash
cd "/Users/krutarthmajithia/Desktop/personal/paramrut scrapes"
python extract_apk.py
```

Expected: `paramrut.apk` created, `apk_extracted/assets/` populated, file listing printed.

- [ ] **Step 3: Run Phase 2 — inspect assets**

```bash
python inspect_assets.py
```

Expected: table names / JSON keys printed. Identify the Swamini Vaat source file, table, chapter column, and entry column.

- [ ] **Step 4: Update config.py with findings**

Based on `inspect_assets.py` output, set in `config.py` (example values — use what was actually printed):

```python
CONTENT_SOURCE = "apk_extracted/assets/<actual_filename>.db"
CONTENT_TABLE  = "<actual_table_name>"
CHAPTER_COLUMN = "<actual_chapter_column>"
ENTRY_COLUMN   = "<actual_entry_text_column>"
TITLE_COLUMN   = "<actual_title_column_or_None>"
```

- [ ] **Step 5: Run Phase 3 — parse and export**

```bash
python parse_content.py
```

Expected: `swamini_vaat/` directory created with `chapter_001_*.txt` ... and `index.json`.

- [ ] **Step 6: Verify output**

```bash
ls swamini_vaat/
cat "swamini_vaat/$(ls swamini_vaat/ | grep chapter | head -1)"
```

Confirm the file contains Gujarati text structured as chapters with numbered entries.

- [ ] **Step 7: Final commit**

```bash
git add config.py
git commit -m "chore: set content source config after asset inspection"
```
