# Gujarati PDF Processor

A unified web application for processing Gujarati PDFs. Supports two modes:

1. **OCR Mode**: Convert scanned Gujarati PDFs to Word documents using Tesseract OCR
2. **Shrilipi Mode**: Extract and convert Shri Lipi font text to Unicode Gujarati

## Features

- Web-based interface with drag-and-drop file upload
- Mode selection (OCR or Shrilipi conversion)
- Real-time progress tracking
- DOCX output for easy editing

## Prerequisites

- Python 3.10+
- Node.js 22.12+ (for frontend)
- Redis server (for task queue)
- Tesseract OCR with Gujarati support (for OCR mode)
- Poppler (for PDF rendering)

### Install Dependencies

**macOS:**
```bash
brew install tesseract tesseract-lang poppler redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tesseract-ocr tesseract-ocr-guj poppler-utils redis-server
```

## Quick Start

### 1. Install Python dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install frontend dependencies
```bash
cd frontend
npm install
```

### 3. Start Redis
```bash
redis-server
```

### 4. Start Celery worker (new terminal)
```bash
celery -A worker worker --loglevel=info
```

### 5. Start API server (new terminal)
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 6. Start frontend (new terminal)
```bash
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

## CLI Usage

### OCR Mode (scanned PDFs)
```bash
python processor.py input.pdf --mode ocr
```

### Shrilipi Mode (legacy font PDFs)
```bash
python processor.py input.pdf --mode shrilipi
```

### Options
```
--output_docx   Output DOCX filename (optional)
--batch_size    Pages per batch for OCR (default: 5)
--dpi           DPI for image conversion (default: 300)
--lang          Tesseract language code (default: guj)
```

## API Endpoints

- `POST /upload` - Upload PDF with mode selection
- `GET /status/{task_id}` - Check processing status
- `GET /download/{task_id}/docx` - Download output DOCX

## Local files and credentials

Run tools from this directory. Source PDFs are in `inputs/` or `uploads/`, and generated files are in `outputs/`. Book-specific scripts may need their input paths adjusted. Temporary diagnostics were preserved in the root cleanup archive.

For Google Vision OCR, set `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of your local service-account JSON in `secrets/`. Credentials and working data are excluded from Git and Docker build context.
