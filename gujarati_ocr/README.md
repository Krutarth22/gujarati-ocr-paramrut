# Gujarati PDF Processor

FastAPI + Celery + React tools for Gujarati OCR and Shri Lipi conversion.
OCR supports searchable PDF, DOCX, and TXT through the API; the UI offers PDF
and DOCX. Shri Lipi supports PDF, DOCX, TXT, and Markdown through the API;
the UI offers TXT and Markdown. The UI sends the selected format and OCR page
range to the backend and displays downloads for generated files.

## Local setup

Use Python 3.10+ and Node.js 22.12+. On macOS:

```bash
brew install tesseract tesseract-lang poppler redis
brew install --cask libreoffice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
(cd frontend && npm ci)
export OCR_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
./start_app.sh
```

Keep `OCR_API_TOKEN` in your shell or a local secret manager. Enter the same
value in the interface at http://localhost:5173. The UI keeps it in memory only;
it is not embedded in the frontend bundle or placed in download URLs.
The server refuses to start without a token of at least 32 characters.
Export the same token in any separate API terminal.

On Ubuntu/Debian install `tesseract-ocr`, `tesseract-ocr-guj`, `poppler-utils`,
`redis-server`, `libreoffice-writer`, and `fonts-noto-core`.

To start services manually, run these in separate terminals from this directory:

```bash
redis-server --bind 127.0.0.1 --protected-mode yes
celery -A worker.celery_app worker --loglevel=info --concurrency=2
uvicorn app:app --host 127.0.0.1 --port 8000
# Frontend terminal:
cd frontend
npm run dev
```

## Docker

Export `OCR_API_TOKEN` as above, then run `docker compose up --build`.
Redis is internal to the Compose network. API and frontend ports bind to
localhost. LibreOffice and Gujarati-capable Noto fonts are installed in the
backend/worker image. Only upload and output folders are mounted, not the
source tree or local credentials. The frontend proxy uses the backend service.

## Access and limits

All API requests require `Authorization: Bearer <OCR_API_TOKEN>`. This is a
single-operator application: anyone with that token can access its jobs. For
remote use, configure an HTTPS reverse proxy with request timeouts and body
limits; preserve authentication and keep Redis private. Do not expose the Vite
development server. A production frontend uses `/api` by default; route that
prefix to the API with the prefix stripped, or set `VITE_API_URL` at build time.

Defaults:

| Setting | Default |
| --- | --- |
| `MAX_UPLOAD_MB` | 50 MB per PDF |
| `MAX_PDF_PAGES` | 500 pages |
| `MAX_ACTIVE_JOBS` | 8 admitted jobs across API processes |
| Queue wait | 10 minutes before expiration |
| Worker execution | 30 minutes maximum (prefork worker) |
| `OCR_ALLOWED_ORIGINS` | localhost:5173 and 127.0.0.1:5173 |
| File retention | 24 hours after processing, checked hourly |

API uploads must include Content-Length. The full multipart request is capped
at the upload limit plus 1 MB overhead; the saved file has its own byte limit.
Metadata requests share admission limits. PDF headers, page counts, and page
ranges are validated before queueing. Each job gets generated UUID directories
under `uploads/` and `outputs/`; original filenames are display-only. Failed OCR
pages fail the job and do not expose an incomplete document as a successful
result. Failed or expired jobs also retain files until cleanup. Cleanup runs
while the API is running, including at startup, and supports old flat files.

## API

- `POST /pdf-info`: PDF metadata.
- `POST /upload`: multipart `file`, `mode`, `output_format`, `page_range`.
- `GET /status/{task_id}`: progress; success includes `result.formats`.
- `GET /download/{task_id}/{file_type}`: authenticated generated file.

```bash
curl -H "Authorization: Bearer $OCR_API_TOKEN" \
  -F 'file=@input.pdf' -F 'mode=ocr' -F 'output_format=docx' \
  -F 'page_range=1-5, 8' http://127.0.0.1:8000/upload
```

## CLI and tests

```bash
python processor.py input.pdf --mode ocr --output_format docx --page_range '1-5'
python processor.py input.pdf --mode shrilipi --output_format txt
pip install -r requirements-dev.txt
python -m pytest tests -q
(cd frontend && npm test && npm run lint && npm run build)
```

The API tests mock the queue and PDF metadata tool; processor tests cover page
failures, selection, and a real blank-PDF Shri Lipi conversion. Full OCR needs
Tesseract and Poppler. Google Vision additionally needs your own credentials:
set `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of the local service
account JSON in `secrets/`. Credentials and working documents are ignored by
Git and Docker. Book-specific scripts may need local input paths adjusted.

## Accuracy experiments

See [BENCHMARK.md](BENCHMARK.md) for reproducible model/preprocessing comparisons,
manual-reference scoring, and optional Google Vision evaluation. The existing
profile remains the default until representative books establish a better one.
