import os
import shutil
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from worker import process_task
from pdf2image import pdfinfo_from_path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directories
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def cleanup_old_files():
    """Delete files older than 24 hours."""
    logger.info("Running cleanup task...")
    now = time.time()
    cutoff = now - (24 * 3600) # 24 hours in seconds
    
    count = 0
    for folder in [UPLOAD_DIR, OUTPUT_DIR]:
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if os.path.isfile(path):
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        count += 1
                        logger.info(f"Deleted old file: {path}")
                except Exception as e:
                    logger.error(f"Error deleting {path}: {e}")
    
    if count > 0:
        logger.info(f"Cleanup complete. Deleted {count} files.")
    else:
        logger.info("Cleanup complete. No old files found.")

async def periodic_cleanup():
    """Run cleanup every hour."""
    while True:
        cleanup_old_files()
        await asyncio.sleep(3600) # Sleep for 1 hour

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background task
    task = asyncio.create_task(periodic_cleanup())
    yield
    # Shutdown: Cancel task
    task.cancel()

app = FastAPI(title="Gujarati PDF Processor API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/pdf-info")
async def get_pdf_info(file: UploadFile = File(...)):
    """Get metadata about uploaded PDF before processing."""
    try:
        # Save temporarily
        temp_path = os.path.join(UPLOAD_DIR, f"temp_{file.filename}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Get PDF info
        info = pdfinfo_from_path(temp_path)
        
        # Delete temp file
        os.remove(temp_path)
        
        return {
            "filename": file.filename,
            "pages": info.get("Pages", 0),
            "size_mb": round(file.size / (1024 * 1024), 1) if file.size else 0
        }
    except Exception as e:
        logger.error(f"Error getting PDF info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    mode: str = Form(default="ocr"),
    page_range: str = Form(default=""),
    output_format: str = Form(default="pdf")
):
    """
    Upload a PDF file and start processing.
    
    Args:
        file: PDF file to upload
        mode: Processing mode - 'ocr' or 'shrilipi'
        page_range: Page range (e.g., "1-5, 8")
        output_format: Output format - 'pdf', 'docx', 'txt', or 'md'
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    # Validate mode
    if mode not in ["ocr", "shrilipi"]:
        raise HTTPException(status_code=400, detail="Mode must be 'ocr' or 'shrilipi'.")

    allowed_output_formats = {
        "ocr": {"pdf", "docx", "txt"},
        "shrilipi": {"pdf", "docx", "txt", "md"},
    }
    if output_format not in allowed_output_formats[mode]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid output format for {mode}. Allowed: {sorted(allowed_output_formats[mode])}."
        )

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    # Save uploaded file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Define output paths
    base_name = os.path.splitext(file.filename)[0]
    suffix = "_ocr" if mode == "ocr" else "_unicode"
    
    output_docx_path = os.path.join(OUTPUT_DIR, f"{base_name}{suffix}.docx")
    output_pdf_path = os.path.join(OUTPUT_DIR, f"{base_name}{suffix}.pdf")
    output_txt_path = os.path.join(OUTPUT_DIR, f"{base_name}{suffix}.txt")
    output_md_path = os.path.join(OUTPUT_DIR, f"{base_name}{suffix}.md")

    # Clean page range
    page_range = page_range.strip() if page_range else None

    # Start Celery task
    task = process_task.delay(
        file_path, 
        output_docx_path, 
        output_pdf_path, 
        mode,
        page_range,
        output_format,
        output_txt_path if output_format == 'txt' else None,
        output_md_path if output_format == 'md' else None
    )

    return {
        "task_id": task.id, 
        "filename": file.filename,
        "mode": mode,
        "page_range": page_range,
        "output_format": output_format
    }

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Get the status of a processing task.
    """
    task_result = AsyncResult(task_id)
    
    if task_result.state == 'PENDING':
        response = {
            'state': task_result.state,
            'current': 0,
            'total': 100,
            'status': 'Pending...'
        }
    elif task_result.state != 'FAILURE':
        response = {
            'state': task_result.state,
            'current': task_result.info.get('current', 0) if isinstance(task_result.info, dict) else 0,
            'total': task_result.info.get('total', 100) if isinstance(task_result.info, dict) else 100,
            'status': task_result.info.get('status', '') if isinstance(task_result.info, dict) else str(task_result.info)
        }
        if isinstance(task_result.info, dict):
            response['result'] = task_result.info
    else:
        # something went wrong in the background job
        response = {
            'state': task_result.state,
            'current': 100,
            'total': 100,
            'status': str(task_result.info),
        }
        
    return response

@app.get("/download/{task_id}/{file_type}")
async def download_file(task_id: str, file_type: str):
    """
    Download the generated file (docx, pdf, txt, or md).
    """
    task_result = AsyncResult(task_id)
    
    if task_result.state != 'SUCCESS':
         raise HTTPException(status_code=400, detail="Task not completed yet.")
         
    result = task_result.result
    
    if file_type == 'docx':
        path = result.get('docx_path')
        media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif file_type == 'pdf':
        if not result.get('pdf_generated'):
            raise HTTPException(status_code=404, detail="PDF conversion failed. Only DOCX is available.")
        path = result.get('pdf_path')
        media_type = 'application/pdf'
    elif file_type == 'txt':
        path = result.get('txt_path')
        if not path:
            raise HTTPException(status_code=404, detail="TXT output not generated.")
        media_type = 'text/plain'
    elif file_type == 'md':
        path = result.get('md_path')
        if not path:
            raise HTTPException(status_code=404, detail="Markdown output not generated.")
        media_type = 'text/markdown'
    else:
        raise HTTPException(status_code=400, detail="Invalid file type. Use 'docx', 'pdf', 'txt', or 'md'.")
    
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found.")
    
    filename = os.path.basename(path)
    return FileResponse(path, media_type=media_type, filename=filename)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
