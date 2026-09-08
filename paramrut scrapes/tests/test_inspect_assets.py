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
