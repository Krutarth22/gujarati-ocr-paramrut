import os
import logging
from pathlib import Path
from job_limits import TASK_TIME_LIMIT, release_job
from celery import Celery
from processor import GujaratiPDFProcessor, ProcessingMode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery app
celery_app = Celery(
    "pdf_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=TASK_TIME_LIMIT,
    task_soft_time_limit=TASK_TIME_LIMIT - 30,
    worker_prefetch_multiplier=1,
    result_expires=24 * 3600,
    broker_connection_timeout=5,
    task_publish_retry=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

@celery_app.task(bind=True)
def process_task(
    self, 
    input_path: str, 
    output_docx_path: str, 
    output_pdf_path: str, 
    mode: str = "ocr",
    page_range: str = None,
    output_format: str = "pdf",
    output_txt_path: str = None,
    output_md_path: str = None
):
    """
    Celery task to run PDF processing (OCR or Shrilipi).
    
    Args:
        input_path: Path to input PDF file
        output_docx_path: Path where DOCX output will be saved
        output_pdf_path: Path where PDF output will be saved
        mode: Processing mode - 'ocr' or 'shrilipi'
        page_range: Page range to process (e.g., "1-5, 8")
        output_format: Output format - 'pdf', 'docx', 'txt', or 'md'
        output_txt_path: Path for .txt output (Shrilipi)
        output_md_path: Path for .md output (Shrilipi)
    """
    logger.info(f"Starting {mode.upper()} task for {input_path}")
    logger.info(f"Page range: {page_range}, Output format: {output_format}")
    
    # Progress helper
    reserve_pdf_conversion = mode == "shrilipi" and output_format == "pdf"

    def update_progress(pct, message):
        adjusted_pct = int(pct * 0.9) if reserve_pdf_conversion else pct
        self.update_state(
            state='PROCESSING',
            meta={
                'current': adjusted_pct,
                'total': 100,
                'status': message
            }
        )

    try:
        # Get configuration from environment
        batch_size = int(os.getenv("OCR_BATCH_SIZE", "5"))
        dpi = int(os.getenv("OCR_DPI", "300"))
        
        # Determine processing mode
        processing_mode = ProcessingMode.OCR if mode == "ocr" else ProcessingMode.SHRILIPI
        
        # Create and run processor
        processor = GujaratiPDFProcessor(
            input_pdf_path=input_path,
            output_docx_path=output_docx_path,
            mode=processing_mode,
            batch_size=batch_size,
            dpi=dpi,
            lang=os.getenv('OCR_LANG', 'guj+eng'),
            ocr_psm=int(os.getenv('OCR_PSM', '4')),
            preprocessing=os.getenv('OCR_PREPROCESSING', 'legacy'),
            tessdata_dir=os.getenv('OCR_TESSDATA_DIR') or None,
            deskew=os.getenv('OCR_DESKEW', '0') == '1',
            page_range=page_range,
            output_format=output_format,
            output_pdf_path=output_pdf_path,
            output_txt_path=output_txt_path,
            output_md_path=output_md_path,
            text_only=(mode == "ocr" and output_format != "pdf")
        )
        
        processor.process(progress_callback=update_progress)
        
        result = {
            'current': 100,
            'total': 100,
            'status': 'Task completed!',
            'docx_path': output_docx_path,
            'mode': mode
        }
        
        if output_pdf_path and os.path.exists(output_pdf_path):
             result['pdf_path'] = output_pdf_path
             result['pdf_generated'] = True
        else:
             result['pdf_generated'] = False
        
        # Add other output paths if generated
        if output_txt_path and os.path.exists(output_txt_path):
            result['txt_path'] = output_txt_path
        if output_md_path and os.path.exists(output_md_path):
            result['md_path'] = output_md_path
        
        return result
        
    except Exception as e:
        logger.error(f"Task failed: {e}")
        raise
    finally:
        # Retention starts after processing, not before a potentially long job.
        for folder in {Path(input_path).parent, Path(output_docx_path).parent}:
            if folder.exists():
                os.utime(folder, None)
        try:
            release_job(self.request.id)
        except Exception:
            logger.exception("Could not release job lease; it will expire automatically.")



# Keep backward compatibility alias
ocr_task = process_task
