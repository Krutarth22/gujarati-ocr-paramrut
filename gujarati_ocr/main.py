import os
import sys
import gc
import logging
import io
from typing import List, Optional


try:
    import pytesseract
    from pdf2image import convert_from_path, pdfinfo_from_path
    from pypdf import PdfWriter, PdfReader
    from docx import Document
    from tqdm import tqdm
    from PIL import Image
except ImportError as e:
    print(f"Error: Missing dependency. Please run 'pip install -r requirements.txt'. Details: {e}")
    sys.exit(1)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ocr_process.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GujaratiOCRProcessor:
    def __init__(self, input_pdf_path: str, output_pdf_path: str, output_docx_path: str, batch_size: int = 5, lang: str = 'guj', dpi: int = 300, quality: int = 0):
        """
        Initialize the OCR processor.
        
        Args:
            input_pdf_path: Path to the source PDF.
            output_pdf_path: Path where the searchable PDF will be saved.
            output_docx_path: Path where the DOCX file will be saved.
            batch_size: Number of pages to process in memory at once.
            lang: Tesseract language code (default 'guj' for Gujarati).
            dpi: Resolution for PDF to Image conversion (default 300).
            quality: JPEG Quality 1-100 (0 = Lossless/Default).
        """
        self.input_pdf_path = input_pdf_path
        self.output_pdf_path = output_pdf_path
        self.output_docx_path = output_docx_path
        self.batch_size = batch_size
        self.lang = lang
        self.dpi = dpi
        self.quality = quality
        
        if not os.path.exists(input_pdf_path):
            raise FileNotFoundError(f"Input file not found: {input_pdf_path}")
            
    # ... (get_total_pages and process methods remain same structurally) ...

    def process(self, progress_callback=None):
        # same as before
        logger.info(f"Starting OCR processing for: {self.input_pdf_path} at {self.dpi} DPI")
        # ... logic ...
        # Need to make sure we don't accidentally clip the whole middle of the file in this replace block if I don't include it.
        # But wait, replace_file_content requires me to provide exact TargetContent for the block I'm replacing.
        # If I replace the whole class, it's huge.
        # I should use multi_replace for surgical edits.
        pass

# Wait, I am inside the tool call. I cannot write comments like this.
# I will cancel this bad tool call and use multi_replace.


    def get_total_pages(self) -> int:
        """Get total page count without loading the whole PDF."""
        try:
            info = pdfinfo_from_path(self.input_pdf_path)
            return info["Pages"]
        except Exception as e:
            logger.error(f"Could not get page count from poppler: {e}")
            # Fallback to pypdf
            try:
                reader = PdfReader(self.input_pdf_path)
                return len(reader.pages)
            except Exception as e2:
                logger.error(f"Could not get page count from pypdf: {e2}")
                raise

    def process(self, progress_callback=None):
        """
        Main processing loop.
        Converts PDF to images in batches, performs OCR, and incrementally saves outputs.
        
        Args:
            progress_callback: Optional function to call with progress updates (percentage, message).
        """
        logger.info(f"Starting OCR processing for: {self.input_pdf_path}")
        total_pages = self.get_total_pages()
        logger.info(f"Total pages to process: {total_pages}")

        # Initialize output containers
        pdf_writer = PdfWriter()
        doc = Document()
        
        try:
            with tqdm(total=total_pages, unit="page", desc="Processing") as pbar:
                for start_page in range(1, total_pages + 1, self.batch_size):
                    end_page = min(start_page + self.batch_size - 1, total_pages)
                    
                    self._process_batch(start_page, end_page, pdf_writer, doc)
                    
                    # Update progress bar
                    pbar.update(end_page - start_page + 1)
                    
                    # Calculate progress percentage
                    progress_pct = int(end_page / total_pages * 100)
                    
                    # Log progress to file
                    logger.info(f"Progress: {end_page}/{total_pages} pages processed ({progress_pct}%)")
                    
                    # Call callback if provided
                    if progress_callback:
                        progress_callback(progress_pct, f"Processed {end_page}/{total_pages} pages")
                    
                    # Force garbage collection
                    gc.collect()

            # Save final outputs
            self._save_outputs(pdf_writer, doc)
            logger.info("Processing completed successfully.")
            
            if progress_callback:
                progress_callback(100, "Processing completed successfully.")

        except KeyboardInterrupt:
            logger.warning("Processing interrupted by user. Saving partial results...")
            self._save_outputs(pdf_writer, doc)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Critical error during processing: {e}", exc_info=True)
            raise

    def _process_batch(self, start_page: int, end_page: int, pdf_writer: PdfWriter, doc: Document):
        """
        Process a single batch of pages.
        """
        logger.debug(f"Processing batch: pages {start_page} to {end_page}")
        
        try:
            # Convert PDF pages to images
            # thread_count=4 speeds up conversion
            images = convert_from_path(
                self.input_pdf_path,
                first_page=start_page,
                last_page=end_page,
                thread_count=4,
                dpi=self.dpi
            )
        except Exception as e:
            logger.error(f"Failed to convert pages {start_page}-{end_page} to images: {e}")
            return

        import uuid
        
        for i, image in enumerate(images):
            try:
                # 1. Generate Searchable PDF Page
                # Configure compression if quality is set
                tess_config = ''
                if self.quality > 0:
                    tess_config = f'-c pdf_jpeg_quality={self.quality}'
                    
                    # Optimize: Convert to Grayscale
                    if image.mode != 'L':
                        logger.debug(f"Converting page {start_page + i} to Grayscale for optimization")
                        image = image.convert('L')

                # Pass PIL image directly + config
                # This is more efficient than saving/reading temp files (verified via debug script)
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                    image, 
                    lang=self.lang, 
                    extension='pdf',
                    config=tess_config
                )
                
                # Read these bytes into a temporary reader and add to our main writer
                batch_pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
                for page in batch_pdf_reader.pages:
                    pdf_writer.add_page(page)

                # 2. Extract Text for DOCX
                text = pytesseract.image_to_string(image, lang=self.lang)
                
                # Add to DOCX with a page break marker or just paragraphs
                doc.add_paragraph(text)
                doc.add_page_break()

            except Exception as e:
                logger.error(f"Error performing OCR on page {start_page + i}: {e}")
                # Continue to next page in batch rather than crashing
                continue
        
        # Clean up images explicitly
        del images

    def _save_outputs(self, pdf_writer: PdfWriter, doc: Document):
        """Save the accumulated results to disk."""
        logger.info("Saving output files...")
        
        # Save PDF
        try:
            with open(self.output_pdf_path, "wb") as f:
                pdf_writer.write(f)
            logger.info(f"Searchable PDF saved to: {self.output_pdf_path}")
        except Exception as e:
            logger.error(f"Failed to save PDF: {e}")

        # Save DOCX
        try:
            doc.save(self.output_docx_path)
            logger.info(f"Word document saved to: {self.output_docx_path}")
        except Exception as e:
            logger.error(f"Failed to save DOCX: {e}")

def check_dependencies():
    """Check if external dependencies (Tesseract, Poppler) are available."""
    # Check Tesseract
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract is not found or not in your PATH. Please install Tesseract-OCR.")
        print("\nCRITICAL: Tesseract-OCR is missing.")
        print("Mac: brew install tesseract tesseract-lang")
        print("Windows: Download installer from UB-Mannheim/tesseract")
        print("Linux: sudo apt install tesseract-ocr tesseract-ocr-guj\n")
        sys.exit(1)

    # Check Poppler (implicitly checked by pdf2image, but good to warn)
    # pdf2image usually raises a clear error if poppler is missing.

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert Gujarati Scanned PDF to Searchable PDF and DOCX.")
    parser.add_argument("input_file", help="Path to input PDF file")
    parser.add_argument("--output_pdf", help="Output PDF filename (default: {input}_ocr.pdf)")
    parser.add_argument("--output_docx", help="Output DOCX filename (default: {input}_ocr.docx)")
    parser.add_argument("--batch_size", type=int, default=5, help="Number of pages to process at once (default: 5)")
    parser.add_argument("--lang", default="guj", help="Tesseract language code (default: guj)")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for rasterization (default: 300)")

    args = parser.parse_args()
    
    # Determine output filenames if not specific
    base_name = os.path.splitext(os.path.basename(args.input_file))[0]
    output_dir = os.path.dirname(args.input_file) # Default to same dir as input
    
    if not args.output_pdf:
        args.output_pdf = os.path.join(output_dir, f"{base_name}_ocr.pdf")
        
    if not args.output_docx:
        args.output_docx = os.path.join(output_dir, f"{base_name}_ocr.docx")

    check_dependencies()
    
    from utils import split_pdf_output

    
    # 1. Run Standard Processor
    processor = GujaratiOCRProcessor(
        input_pdf_path=args.input_file,
        output_pdf_path=args.output_pdf,
        output_docx_path=args.output_docx,
        batch_size=args.batch_size,
        lang=args.lang,
        dpi=args.dpi
    )
    
    # Run OCR (single pass)
    try:
        processor.process()
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        sys.exit(1)

    # 2. Check Output Size & Split
    max_size = int(os.getenv("MAX_PDF_SIZE_MB", "175"))
    
    # Determine base prefix
    # User wants format: input_ocr1.pdf
    input_base = os.path.splitext(os.path.basename(args.input_file))[0]
    output_dir = os.path.dirname(args.output_pdf) if os.path.dirname(args.output_pdf) else "."
    prefix_name = f"{input_base}_ocr"
    prefix_full = os.path.join(output_dir, prefix_name)

    split_files = split_pdf_output(args.output_pdf, max_size_mb=max_size, output_prefix=prefix_full)
    
    if len(split_files) > 1:
        print("\nNote: The output PDF was split into multiple parts because it exceeded the size limit:")
        for p in split_files:
            print(f"- {p}")
