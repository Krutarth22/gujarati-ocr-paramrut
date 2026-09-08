# Paramrut extraction and book tools

Extract bundled Gujarati content from the Paramrut Android APK, fetch Paravani entries through its HTTP API, and build EPUB/PDF books.

## Setup

Use Python 3.10+ and run commands from this directory.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# For tests:
pip install -r requirements-dev.txt
```

## APK extraction

`extract_apk.py` uses ADB to pull the installed app configured in `config.py` (`org.hariprabodham.swaminivato`) and extract `paramrut.apk` into `apk_extracted/`. Install Android platform tools and connect a device with USB debugging enabled before running it.

```bash
python extract_apk.py
python inspect_assets.py
python parse_swamini_vaat.py
python parse_vachnamrut.py
```

For other SQLite/JSON assets, set `CONTENT_SOURCE` and the relevant table/key fields in `config.py`, then run `python parse_content.py`.

## Paravani API scraper

```bash
python scrape_paravani.py
```

This fetches the remote entry index and HTML pages, then writes `paravani/index.json` and text files grouped by year. It uses urllib and BeautifulSoup; it does not require Android UI automation. Running it performs network requests and writes local output.

## Build books

```bash
python build_swamini_vaat_epub.py --help
python build_swamini_vaat_pdf.py --help
python build_vachnamrut_epub.py --help
python build_paravani_epub.py --help
python build_paravani_pdf.py --help
python build_swamiji_diary_epub.py --help
```

Builders consume the corresponding local dataset directories. PDF generation requires Pillow, ReportLab, and suitable Gujarati fonts; default font candidates include macOS system fonts. EPUB utilities are shared in `epub_builder.py`.

## Tests and data

```bash
python -m pytest tests -q
```

Tests cover APK extraction helpers, asset inspection, and generic content parsing. APK files, extracted assets, datasets, screenshots, and generated books are intentionally excluded from Git. Historical plans are in `docs/`; the previous README is preserved in the local cleanup archive.
