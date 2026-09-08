# Swamini Vaat Scraper — Design Spec

**Date:** 2026-04-15  
**App:** Paramrut (`org.hariprabodham.swaminivato`)  
**Target:** Swamini Vaat section — full text of every entry, organized by chapter  
**Environment:** Android emulator (no physical device)

---

## Problem Statement

The previous scraping approach used `uiautomator2` UI automation against an Android emulator. It failed because the Paramrut app is a Flutter application — Flutter renders its UI on a Skia/Impeller canvas, not native Android views. `uiautomator2` sees a blank frame with no queryable elements.

The correct approach is to bypass the UI entirely and extract content directly from the APK's bundled assets.

---

## Approach: APK Asset Extraction

Flutter offline content apps bundle their data as assets inside the APK (typically a SQLite database or JSON files in the `assets/` directory). By pulling the APK from the emulator and inspecting its contents, we can extract all Swamini Vaat content without any UI automation.

This approach is:
- **Reliable** — no timing, no UI fragility, no OCR
- **Complete** — gets all content in one pass, not scroll-by-scroll
- **Emulator-compatible** — works without a physical device

---

## Architecture

Two-phase pipeline with a diagnostic step between them:

```
Phase 1 — Extract
  extract_apk.py
    → adb pull APK from emulator
    → unzip to temp working directory
    → print asset inventory (file tree of assets/)

Phase 2 — Inspect (diagnostic)
  inspect_assets.py
    → scan assets/ for .db, .json, .txt files
    → if SQLite: print table names and row counts
    → if JSON: print top-level keys and array lengths
    → identify which file contains Swamini Vaat content

Phase 3 — Parse & Export
  parse_content.py
    → read identified source (SQLite or JSON)
    → find Swamini Vaat table/key
    → group entries by chapter, preserve order
    → write one .txt file per chapter
    → write index.json
```

Phases 1 and 2 are intentionally separate diagnostic steps — if the asset structure is unexpected, the user can inspect the output and adapt before running Phase 3.

---

## Components

### `extract_apk.py`
- Connects to the running emulator via ADB
- Finds the installed APK path for `org.hariprabodham.swaminivato`
- Pulls APK to local disk
- Unzips into `apk_extracted/` directory
- Prints a file tree of `apk_extracted/assets/`
- Exits with clear error if emulator not running or app not installed

### `inspect_assets.py`
- Scans `apk_extracted/assets/` recursively
- For each `.db` file: opens with `sqlite3`, lists tables and row counts
- For each `.json` file: loads and prints top-level structure
- For each `.txt` / other file: prints size and first 200 bytes
- Outputs a clear report so the correct source file can be identified

### `parse_content.py`
- Reads from the identified content source (SQLite or JSON)
- Extracts all Swamini Vaat entries
- Groups by chapter (using chapter number/title from the data)
- Within each chapter, preserves entry order
- Writes output to `swamini_vaat/` directory

### `config.py` (updated)
- `APP_PACKAGE = "org.hariprabodham.swaminivato"`
- `APK_EXTRACT_DIR = "apk_extracted"`
- `OUTPUT_DIR = "swamini_vaat"`
- `CONTENT_SOURCE = None` — set by user after running `inspect_assets.py`

---

## Output Format

### Directory structure
```
swamini_vaat/
  index.json
  chapter_001_<title>.txt
  chapter_002_<title>.txt
  ...
```

### Per-chapter file
```
================================================================
SWAMINI VAAT - Chapter 1: <title>
================================================================

Entry 1
----------------------------------------------------------------
[Gujarati text content]

Entry 2
----------------------------------------------------------------
[Gujarati text content]
```

### index.json
```json
{
  "generated_at": "2026-04-15T...",
  "total_chapters": 42,
  "total_entries": 1234,
  "chapters": [
    { "number": 1, "title": "...", "entry_count": 30, "file": "chapter_001_....txt" }
  ]
}
```

---

## Data Flow: SQLite path (expected)

```
apk_extracted/assets/<name>.db
  → sqlite3.connect()
  → PRAGMA table_info on all tables
  → identify Swamini Vaat table (by name or column inspection)
  → SELECT * ORDER BY chapter, entry_number
  → group by chapter
  → format and write
```

## Data Flow: JSON path (fallback)

```
apk_extracted/assets/<name>.json
  → json.load()
  → traverse to Swamini Vaat key
  → iterate chapters → entries
  → format and write
```

---

## Error Handling

| Situation | Behaviour |
|-----------|-----------|
| Emulator not running | `extract_apk.py` exits with `adb devices` hint |
| App not installed | `extract_apk.py` exits with install hint |
| No `.db` or `.json` in assets | `inspect_assets.py` prints full file tree for manual review |
| Swamini Vaat table/key not found | `parse_content.py` prints all available tables/keys and exits |
| Binary/protobuf format | `inspect_assets.py` reports unknown format — manual intervention needed |

---

## Verification

1. `extract_apk.py` — succeeds when `apk_extracted/assets/` exists and contains files
2. `inspect_assets.py` — succeeds when it prints table names or JSON keys from the content
3. `parse_content.py` — succeeds when `swamini_vaat/` contains at least one non-empty `.txt` file
4. Manual spot-check — open one chapter file and confirm Gujarati text is correct

---

## Files To Remove

The following files from the previous approach are no longer needed and should be deleted:
- `scraper.py`
- `ui_navigator.py`
- `adb_manager.py`
- `text_extractor.py`
- `storage_manager.py`
- `manual_navigation.py`
- `install_xapk.sh`
- `launch_emulator.sh`
- `verify_setup.py`
- `EMULATOR_SETUP.md`
- `QUICKSTART.md`

`inspect_ui.py` and `config.py` are replaced by the new scripts above.

---

## Out of Scope

- Other app sections (Paravani, etc.) — Swamini Vaat only for now
- Incremental/delta scraping — full extraction each time
- Any UI automation fallback
