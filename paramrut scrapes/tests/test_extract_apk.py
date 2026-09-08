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
