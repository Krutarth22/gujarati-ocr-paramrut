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
