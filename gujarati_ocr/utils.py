import os
import math
import logging
from typing import List
from pypdf import PdfReader, PdfWriter
from docx import Document
from docx.opc.constants import CONTENT_TYPE as CT

logger = logging.getLogger(__name__)

def split_pdf_output(file_path: str, max_size_mb: int = 175, output_prefix: str = "") -> List[str]:
    """
    Split an EXISTING output PDF into chunks if it exceeds the max_size_mb.
    Naming pattern: {output_prefix}{index}.pdf (e.g. input_ocr1.pdf)
    
    Args:
        file_path: Path to the large PDF.
        max_size_mb: Max size in MB.
        output_prefix: Base name for split files (e.g. "my_doc_ocr").
    
    Returns:
        List of paths to the final files (split parts or original if no split).
    """
    if not os.path.exists(file_path):
        return []

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    logger.info(f"Checking output file size: {file_size_mb:.2f} MB")

    if file_size_mb <= max_size_mb:
        logger.info("Output file is under the limit.")
        return [file_path]

    logger.info(f"Output exceeds {max_size_mb} MB. Splitting...")
    
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        
        # Approximate number of chunks needed
        num_chunks = math.ceil(file_size_mb / max_size_mb)
        
        # We can't strictly trust page count / chunks because images might be concentrated.
        # But for OCR output, it's roughly uniform.
        pages_per_chunk = math.ceil(total_pages / num_chunks)
        
        chunk_paths = []
        
        for i in range(num_chunks):
            start_page = i * pages_per_chunk
            end_page = min((i + 1) * pages_per_chunk, total_pages)
            
            if start_page >= total_pages:
                break
                
            writer = PdfWriter()
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
            
            # Pattern: prefix + index + .pdf
            # User example: input_ocr1.pdf
            chunk_path = f"{output_prefix}{i+1}.pdf"
            
            with open(chunk_path, "wb") as f_out:
                writer.write(f_out)
            
            chunk_paths.append(chunk_path)
            logger.info(f"Created split part {i+1}: {chunk_path}")
            
        # Optional: Delete the original large file
        # os.remove(file_path)
        
        return chunk_paths

    except Exception as e:
        logger.error(f"Error splitting Output PDF: {e}")
        # Return original if split fails so user at least gets something
        return [file_path]

def merge_pdfs(pdf_paths: List[str], output_path: str):
    """
    Merge multiple PDFs into a single file.
    """
    logger.info(f"Merging {len(pdf_paths)} PDFs into {output_path}")
    writer = PdfWriter()
    
    for path in pdf_paths:
        try:
            reader = PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            logger.error(f"Error reading {path} for merge: {e}")
            raise

    with open(output_path, "wb") as f_out:
        writer.write(f_out)
    logger.info("PDF merge complete.")

def merge_docxs(docx_paths: List[str], output_path: str):
    """
    Merge multiple DOCX files into a single file.
    Note: 'python-docx' doesn't support easy merging of full documents with formatting perfectly.
    This implementation appends content from subsequent docs to the first one.
    """
    logger.info(f"Merging {len(docx_paths)} DOCX files into {output_path}")
    
    if not docx_paths:
        return

    # Load the first document as the master
    master_doc = Document(docx_paths[0])
    
    # Append the rest
    # Using a simple composer approach is tricky with python-docx.
    # We will iterate through body elements and append them.
    # This is a naive implementation but sufficient for simple text extraction results.
    
    for path in docx_paths[1:]:
        sub_doc = Document(path)
        
        # Add a page break before appending new document content
        master_doc.add_page_break()
        
        for element in sub_doc.element.body:
             master_doc.element.body.append(element)

    master_doc.save(output_path)
    logger.info("DOCX merge complete.")
