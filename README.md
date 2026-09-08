# Gujarati OCR & Paramrut tools

Personal tools for Gujarati PDF OCR, legacy Shri Lipi conversion, Paramrut content extraction, and EPUB/PDF generation.

## Projects

| Directory | Purpose |
| --- | --- |
| `gujarati_ocr/` | FastAPI + Celery OCR backend, React interface, and document-processing scripts |
| `paramrut scrapes/` | APK content parsers, Paravani API scraper, and book builders |

See each project's README for setup. Run scripts from their project directory: existing tools use relative input and output paths.

## Local files

This repository tracks source code, dependency manifests, tests, and documentation. Source PDFs, APKs, extracted datasets, generated books, credentials, environments, and cleanup backups stay local and are ignored by Git.

- `gujarati_ocr/inputs/`: source PDFs moved out of the project root.
- `gujarati_ocr/uploads/`, `outputs/`: existing application inputs and generated documents.
- `gujarati_ocr/secrets/`: local Google Cloud key; set `GOOGLE_APPLICATION_CREDENTIALS` to its absolute path when using Vision OCR.
- `archive/cleanup-2026-09-08/`: preserved temporary images, diagnostic files, previous documentation, and a move manifest.
- Paramrut's `apk_extracted/`, `swamini_vaat/`, `swamiji_diary/`, and `vachnamrut/` remain at their expected paths.

Original working data is preserved. Nothing in the archive is needed for a fresh code checkout. Recreate virtual environments and install dependencies on a new machine; GitHub is a code backup, not a document backup.

## Verification

```bash
cd "paramrut scrapes"
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests -q
cd ../gujarati_ocr/frontend
npm ci
npm run build
```

Document-specific OCR scripts may require local input files and manual settings. Full OCR requires Tesseract/Poppler/Redis; Google Vision additionally requires your own credentials. PDF book builders use local Gujarati fonts. No OCR jobs or live scraping are run during repository verification.
