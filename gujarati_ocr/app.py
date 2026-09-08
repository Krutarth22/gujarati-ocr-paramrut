import asyncio
import contextlib
import logging
import os
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pdf2image import pdfinfo_from_path
from redis.exceptions import RedisError

from job_limits import QUEUE_WAIT_SECONDS, reserve_job, release_job
from page_ranges import parse_page_range
from worker import celery_app, process_task

logger = logging.getLogger(__name__)
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', 'uploads'))
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', 'outputs'))
MAX_UPLOAD_BYTES = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024 * 1024
MAX_PAGES = int(os.getenv('MAX_PDF_PAGES', '500'))
RETENTION_SECONDS = 24 * 3600


def cleanup_old_files():
    """Remove expired job directories and legacy files; never follow symlinks."""
    cutoff = time.time() - RETENTION_SECONDS
    for folder in (UPLOAD_DIR, OUTPUT_DIR):
        for path in folder.iterdir():
            if path.is_symlink():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    if path.is_dir():
                        # Only delete generated UUID job directories.
                        if str(UUID(path.name)) != path.name:
                            continue
                        shutil.rmtree(path)
                    else:
                        path.unlink()
            except (OSError, ValueError):
                logger.exception('Cleanup failed for %s', path.name)


async def periodic_cleanup():
    while True:
        await asyncio.to_thread(cleanup_old_files)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app):
    if len(os.getenv('OCR_API_TOKEN', '')) < 32:
        raise RuntimeError('Set OCR_API_TOKEN to a random token of at least 32 characters.')
    for folder in (UPLOAD_DIR, OUTPUT_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(periodic_cleanup())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class AccessGuard:
    """Authenticate before parsing multipart bodies and cap request sizes."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        expected = os.getenv('OCR_API_TOKEN', '')
        supplied = headers.get(b'authorization', b'')
        if len(expected) < 32 or not secrets.compare_digest(supplied, f'Bearer {expected}'.encode()):
            return await JSONResponse({'detail': 'Valid access token required.'}, 401)(scope, receive, send)
        if scope['method'] == 'POST':
            try:
                length = int(headers.get(b'content-length', b'-1'))
            except ValueError:
                length = -1
            if length < 0:
                return await JSONResponse({'detail': 'Content-Length is required.'}, 411)(scope, receive, send)
            if length > MAX_UPLOAD_BYTES + 1024 * 1024:
                return await JSONResponse({'detail': 'Upload exceeds the size limit.'}, 413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > MAX_UPLOAD_BYTES + 1024 * 1024:
                raise HTTPException(413, 'Upload exceeds the size limit.')
            return message

        await self.app(scope, limited_receive, send)


app = FastAPI(title='Gujarati PDF Processor API', lifespan=lifespan)
app.add_middleware(AccessGuard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('OCR_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
    allow_methods=['GET', 'POST'],
    allow_headers=['Authorization', 'Content-Type'],
)


def save_pdf(file, path):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, 'Only PDF files are allowed.')
    size = 0
    with path.open('xb') as target:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, 'Upload exceeds the size limit.')
            if size == len(chunk) and not chunk.startswith(b'%PDF-'):
                raise HTTPException(400, 'Invalid PDF file.')
            target.write(chunk)
    if not size:
        raise HTTPException(400, 'Empty PDF file.')
    try:
        pages = pdfinfo_from_path(str(path), timeout=30)['Pages']
    except Exception as exc:
        raise HTTPException(400, 'Cannot read this PDF. Check that it is valid and unencrypted.') from exc
    if not 1 <= pages <= MAX_PAGES:
        raise HTTPException(400, f'PDF must contain between 1 and {MAX_PAGES} pages.')
    return size, pages


def new_job_dirs(task_id):
    incoming, outgoing = UPLOAD_DIR / task_id, OUTPUT_DIR / task_id
    incoming.mkdir(parents=True)
    try:
        outgoing.mkdir(parents=True)
    except Exception:
        shutil.rmtree(incoming, ignore_errors=True)
        raise
    return incoming, outgoing


@app.post('/pdf-info')
def get_pdf_info(file: UploadFile = File(...)):
    task_id = str(uuid4())
    try:
        if not reserve_job(task_id):
            raise HTTPException(429, 'Processing queue is full. Try again later.')
    except RedisError as exc:
        raise HTTPException(503, 'Processing queue is unavailable.') from exc
    incoming = outgoing = None
    try:
        incoming, outgoing = new_job_dirs(task_id)
        size, pages = save_pdf(file, incoming / 'input.pdf')
        return {'filename': file.filename, 'pages': pages, 'size_mb': round(size / 1024**2, 1)}
    finally:
        for directory in (incoming, outgoing):
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
        with contextlib.suppress(RedisError):
            release_job(task_id)


@app.post('/upload')
def upload_file(file: UploadFile = File(...), mode: str = Form('ocr'),
                page_range: str = Form(''), output_format: str = Form('pdf')):
    allowed = {'ocr': {'pdf', 'docx', 'txt'}, 'shrilipi': {'pdf', 'docx', 'txt', 'md'}}
    if mode not in allowed or output_format not in allowed[mode]:
        raise HTTPException(400, 'Invalid processing mode or output format.')
    task_id = str(uuid4())
    try:
        if not reserve_job(task_id):
            raise HTTPException(429, 'Processing queue is full. Try again later.')
    except RedisError as exc:
        raise HTTPException(503, 'Processing queue is unavailable.') from exc
    incoming = outgoing = None
    try:
        incoming, outgoing = new_job_dirs(task_id)
        _, pages = save_pdf(file, incoming / 'input.pdf')
        try:
            parse_page_range(page_range, pages)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        process_task.apply_async(args=[
            str(incoming / 'input.pdf'), str(outgoing / 'result.docx'),
            str(outgoing / 'result.pdf'), mode, page_range.strip() or None,
            output_format, str(outgoing / 'result.txt') if output_format == 'txt' else None,
            str(outgoing / 'result.md') if output_format == 'md' else None,
        ], task_id=task_id, expires=QUEUE_WAIT_SECONDS)
    except Exception:
        for directory in (incoming, outgoing):
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
        with contextlib.suppress(RedisError):
            release_job(task_id)
        raise
    return {'task_id': task_id, 'filename': file.filename, 'mode': mode,
            'page_range': page_range, 'output_format': output_format}


def task_result(task_id):
    try:
        if str(UUID(task_id)) != task_id:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(404, 'Job not found.') from exc
    if not (OUTPUT_DIR / task_id).is_dir():
        raise HTTPException(404, 'Job not found or files expired.')
    return celery_app.AsyncResult(task_id)


@app.get('/status/{task_id}')
def get_status(task_id: str):
    result = task_result(task_id)
    if result.state in ('FAILURE', 'REVOKED'):
        return {'state': 'FAILURE', 'current': 0, 'total': 100,
                'status': 'Processing failed or expired. No complete document is available; check server logs.'}
    info = result.info if isinstance(result.info, dict) else {}
    response = {'state': result.state, 'current': info.get('current', 0), 'total': 100,
                'status': info.get('status', 'Pending...')}
    if result.state == 'SUCCESS':
        response['result'] = {'formats': [ext for ext in ('pdf', 'docx', 'txt', 'md')
                                         if (OUTPUT_DIR / task_id / f'result.{ext}').is_file()]}
    return response


@app.get('/download/{task_id}/{file_type}')
def download_file(task_id: str, file_type: str):
    types = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
             'pdf': 'application/pdf', 'txt': 'text/plain', 'md': 'text/markdown'}
    if file_type not in types:
        raise HTTPException(400, 'Invalid file type.')
    if task_result(task_id).state != 'SUCCESS':
        raise HTTPException(400, 'Job has not completed successfully.')
    directory = (OUTPUT_DIR / task_id).resolve()
    path = directory / f'result.{file_type}'
    if not path.is_file() or path.is_symlink() or path.resolve().parent != directory:
        raise HTTPException(404, 'Output not generated or expired.')
    return FileResponse(path, media_type=types[file_type], filename=f'result.{file_type}')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
