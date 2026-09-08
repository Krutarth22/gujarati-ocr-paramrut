"""
Unified Gujarati PDF Processor

Supports two modes:
1. OCR Mode: Convert scanned Gujarati PDFs to DOCX using Tesseract OCR
2. Shrilipi Mode: Extract and convert Shri Lipi font text to Unicode Gujarati
"""

import os
import shutil
import sys
import gc
import logging
import io
import re
import tempfile
from difflib import SequenceMatcher
from typing import Optional, Callable
from enum import Enum

try:
    import numpy as np
    import pytesseract
    from pdf2image import convert_from_path, pdfinfo_from_path
    from pypdf import PdfReader, PdfWriter
    from docx import Document
    from tqdm import tqdm
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError as e:
    print(f"Error: Missing dependency. Please run 'pip install -r requirements.txt'. Details: {e}")
    sys.exit(1)

from shri_lipi_converter import convert_shri_lipi_to_unicode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("process.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

METADATA_LINE_KEYWORDS = (
    "તા.",
    "વાર",
    "સવારે",
    "બપોરે",
    "સાંજે",
    "રાત્રે",
    "સભા",
    "આરતી",
    "વચ.",
    "ગઢડા",
    "સોખડા",
    "ઉભરાટ",
    "ગોંડલ",
    "જૂનાગઢ",
    "વડોદરા",
)


class ProcessingMode(Enum):
    OCR = "ocr"
    SHRILIPI = "shrilipi"


class OCREngine(Enum):
    TESSERACT = "tesseract"
    VISION = "vision"


class GujaratiPDFProcessor:
    """Unified processor for Gujarati PDFs supporting OCR and Shrilipi modes."""
    
    def __init__(
        self,
        input_pdf_path: str,
        output_docx_path: str,
        mode: ProcessingMode = ProcessingMode.OCR,
        batch_size: int = 5,
        lang: str = 'guj+eng',
        dpi: int = 600,
        page_range: str = None,
        output_format: str = 'docx',
        output_pdf_path: str = None,
        output_txt_path: str = None,
        output_md_path: str = None,
        text_only: bool = False,
        refine_metadata_lines: bool = True,
        ocr_psm: int = 4,
        crop_box: tuple[float, float, float, float] = None,
        ocr_engine: OCREngine = OCREngine.TESSERACT,
        google_credentials_path: str = None,
    ):
        """
        Initialize the processor.

        Args:
            input_pdf_path: Path to the source PDF.
            output_docx_path: Path where the DOCX file will be saved.
            mode: Processing mode (OCR or SHRILIPI).
            batch_size: Number of pages to process in memory at once (OCR only).
            lang: Tesseract language code (default 'guj' for Gujarati).
            dpi: Resolution for PDF to Image conversion (default 300).
            page_range: Page range to process (e.g., "1-5, 8, 10-12"). If None, all pages.
            output_format: Output format - 'docx', 'txt', or 'md'.
            output_txt_path: Path for .txt output (Shrilipi mode).
            output_md_path: Path for .md output (Shrilipi mode).
            ocr_engine: OCR engine to use for OCR mode (TESSERACT or VISION).
            google_credentials_path: Path to a Google Cloud service-account JSON key
                (required when ocr_engine is VISION; falls back to
                GOOGLE_APPLICATION_CREDENTIALS env var if not given).
        """
        self.input_pdf_path = input_pdf_path
        self.output_docx_path = output_docx_path
        self.output_pdf_path = output_pdf_path
        self.mode = mode
        self.batch_size = batch_size
        self.lang = lang
        self.dpi = dpi
        self.page_range = page_range
        self.output_format = output_format
        self.output_txt_path = output_txt_path
        self.output_md_path = output_md_path
        self.text_only = text_only
        self.refine_metadata_lines = refine_metadata_lines
        self.ocr_psm = ocr_psm
        self.crop_box = crop_box
        self.ocr_engine = ocr_engine
        self.google_credentials_path = google_credentials_path
        self._vision_client = None

        if not os.path.exists(input_pdf_path):
            raise FileNotFoundError(f"Input file not found: {input_pdf_path}")

        if self.ocr_engine == OCREngine.VISION:
            self._vision_client = self._build_vision_client()

    def _build_vision_client(self):
        """Create a Google Cloud Vision client from a service-account key or ADC."""
        try:
            from google.cloud import vision
            from google.oauth2 import service_account
        except ImportError as e:
            raise ImportError(
                "google-cloud-vision is required for the 'vision' OCR engine. "
                "Install it with: pip install google-cloud-vision"
            ) from e

        creds_path = self.google_credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path:
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            return vision.ImageAnnotatorClient(credentials=credentials)

        # Fall back to Application Default Credentials.
        return vision.ImageAnnotatorClient()

    def get_total_pages(self) -> int:
        """Get total page count without loading the whole PDF."""
        try:
            if self.mode == ProcessingMode.OCR:
                info = pdfinfo_from_path(self.input_pdf_path)
                return info["Pages"]
            else:
                reader = PdfReader(self.input_pdf_path)
                return len(reader.pages)
        except Exception as e:
            logger.error(f"Could not get page count: {e}")
            # Fallback to pypdf
            try:
                reader = PdfReader(self.input_pdf_path)
                return len(reader.pages)
            except Exception as e2:
                logger.error(f"Could not get page count from pypdf: {e2}")
                raise

    def _parse_page_range(self, total_pages: int) -> list:
        """
        Parse page range string into list of page numbers.
        Examples: "1-5" -> [1,2,3,4,5], "1-3,5,7-9" -> [1,2,3,5,7,8,9]
        """
        if not self.page_range:
            return list(range(1, total_pages + 1))
        
        pages = set()
        parts = self.page_range.replace(' ', '').split(',')
        
        for part in parts:
            if '-' in part:
                start, end = part.split('-')
                start = int(start)
                end = int(end)
                pages.update(range(start, min(end + 1, total_pages + 1)))
            else:
                page = int(part)
                if 1 <= page <= total_pages:
                    pages.add(page)
        
        return sorted(list(pages))

    def process(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        Main processing method. Routes to appropriate handler based on mode.
        
        Args:
            progress_callback: Optional function to call with progress updates (percentage, message).
        """
        if self.mode == ProcessingMode.OCR:
            self._process_ocr(progress_callback)
        else:
            self._process_shrilipi(progress_callback)

    def _process_ocr(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        OCR processing - converts scanned images to text.
        Always saves DOCX, optionally saves searchable PDF, and can export a cleaner TXT.
        """
        logger.info(f"Starting OCR processing for: {self.input_pdf_path}")
        total_pages = self.get_total_pages()
        pages_to_process = self._parse_page_range(total_pages)
        logger.info(f"Total pages in PDF: {total_pages}, Processing: {len(pages_to_process)} pages")

        doc = Document()
        pdf_writer = PdfWriter()
        cleaned_txt_pages = []
        
        try:
            with tqdm(total=len(pages_to_process), unit="page", desc="OCR Processing") as pbar:
                # Process pages in batches, but only selected pages
                processed = 0
                for i in range(0, len(pages_to_process), self.batch_size):
                    batch_pages = pages_to_process[i:i + self.batch_size]
                    
                    # For each page in batch, extract individually
                    for page_num in batch_pages:
                        try:
                            # Convert single page to image
                            images = convert_from_path(
                                self.input_pdf_path,
                                first_page=page_num,
                                last_page=page_num,
                                thread_count=4,
                                dpi=self.dpi
                            )
                            
                            if images:
                                if self.ocr_engine == OCREngine.VISION:
                                    text = self._extract_page_text_vision(images[0])
                                else:
                                    # Preprocess image
                                    processed_image = self._preprocess_image(images[0])

                                    # Save to temp file to avoid pytesseract PIL passing bug
                                    fd, temp_img_path = tempfile.mkstemp(suffix='.png')
                                    os.close(fd)

                                    try:
                                        processed_image.save(temp_img_path)

                                        # 1. PDF Generation
                                        if not self.text_only:
                                            pdf_bytes = pytesseract.image_to_pdf_or_hocr(temp_img_path, extension='pdf', lang=self.lang)
                                            pdf_page_reader = PdfReader(io.BytesIO(pdf_bytes))
                                            if len(pdf_page_reader.pages) > 0:
                                                pdf_writer.add_page(pdf_page_reader.pages[0])

                                        # 2. Extract Text for DOCX
                                        text = self._extract_page_text(
                                            source_image=images[0],
                                            processed_image_path=temp_img_path
                                        )
                                    finally:
                                        if os.path.exists(temp_img_path):
                                            os.remove(temp_img_path)
                                
                                doc.add_paragraph(f"[Page {page_num}]")
                                doc.add_paragraph(text)
                                doc.add_page_break()
                                cleaned_txt_pages.append((page_num, self._clean_ocr_text_for_export(text)))
                                
                            del images
                        except Exception as e:
                            logger.error(f"Error processing page {page_num}: {e}")
                            continue
                        
                        processed += 1
                        pbar.update(1)
                        
                    progress_pct = int(processed / len(pages_to_process) * 100)
                    logger.info(f"Progress: {processed}/{len(pages_to_process)} pages processed ({progress_pct}%)")
                    
                    if progress_callback:
                        progress_callback(progress_pct, f"OCR: Processed {processed}/{len(pages_to_process)} pages")
                    
                    gc.collect()

            # Save DOCX
            doc.save(self.output_docx_path)
            logger.info(f"DOCX saved to: {self.output_docx_path}")

            # Optionally save text file too if requested (often useful in text_only mode)
            if self.text_only or self.output_txt_path:
                txt_path = self.output_txt_path or self.output_docx_path.replace('.docx', '.txt')
                full_text = self._build_clean_ocr_txt_output(cleaned_txt_pages)
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                logger.info(f"TXT saved to: {txt_path}")

            # Save Searchable PDF (Tesseract engine only; Vision doesn't produce a text-overlay PDF)
            if not self.text_only and self.ocr_engine != OCREngine.VISION:
                pdf_path = self.output_pdf_path or self.output_docx_path.replace('.docx', '.pdf')
                with open(pdf_path, "wb") as f:
                    pdf_writer.write(f)
                logger.info(f"Searchable PDF saved to: {pdf_path}")
                
                # Check for splitting
                self._split_pdf_if_large(pdf_path)


            
            if progress_callback:
                progress_callback(100, "OCR processing completed successfully.")

        except KeyboardInterrupt:
            logger.warning("Processing interrupted by user. Saving partial results...")
            doc.save(self.output_docx_path)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Critical error during OCR processing: {e}", exc_info=True)
            raise

    def _split_pdf_if_large(self, output_path: str):
        """
        Check if PDF exceeds 175MB limit. If so, split into parts.
        """
        try:
            if not os.path.exists(output_path):
                return
            
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            if file_size_mb <= 175:
                # No split needed
                return

            logger.info(f"PDF size {file_size_mb:.2f}MB exceeds 175MB limit. Splitting...")
            
            reader = PdfReader(output_path)
            total_pages = len(reader.pages)
            
            # Estimate pages per chunk (assuming roughly equal size per page)
            # Target 150MB to be safe
            pages_per_chunk = int(total_pages * (150 / file_size_mb))
            
            if pages_per_chunk < 1:
                pages_per_chunk = 1
            
            chunk_num = 1
            for start in range(0, total_pages, pages_per_chunk):
                writer = PdfWriter()
                end = min(start + pages_per_chunk, total_pages)
                
                for i in range(start, end):
                    writer.add_page(reader.pages[i])
                
                # output_path is like "foo.pdf"
                # part_path should be "foo_part1.pdf"
                base, ext = os.path.splitext(output_path)
                part_path = f"{base}_part{chunk_num}{ext}"
                
                with open(part_path, "wb") as f:
                    writer.write(f)
                
                logger.info(f"Saved split part: {part_path} (Pages {start+1}-{end})")
                chunk_num += 1
            
            # Optional: Remove original giant file? 
            # Ideally yes to save space, but let's keep it for now or rename it.
            # os.remove(output_path) 
            
        except Exception as e:
            logger.error(f"Failed to split large PDF: {e}")

    def _extract_page_text(self, source_image: Image.Image, processed_image_path: str) -> str:
        """Run the main OCR pass and then repair likely metadata header lines."""
        custom_config = f'--psm {self.ocr_psm} -c preserve_interword_spaces=1'
        raw_text = pytesseract.image_to_string(processed_image_path, lang=self.lang, config=custom_config)
        text = self._clean_text(raw_text)
        if not self.refine_metadata_lines:
            return text
        return self._refine_metadata_lines(source_image, processed_image_path, text)

    def _extract_page_text_vision(self, source_image: Image.Image) -> str:
        """Run OCR via Google Cloud Vision's document_text_detection."""
        from google.cloud import vision

        if self.crop_box:
            source_image = self._crop_by_ratios(source_image, self.crop_box)

        buf = io.BytesIO()
        source_image.save(buf, format="PNG")
        vimg = vision.Image(content=buf.getvalue())

        # Gujarati is 'gu' in Vision's language hints, English text is auto-detected.
        response = self._vision_client.document_text_detection(
            image=vimg, image_context={"language_hints": ["gu"]}
        )
        if response.error.message:
            logger.error(f"Vision API error: {response.error.message}")
            return ""

        text = response.full_text_annotation.text
        return self._clean_text(text)

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image to improve OCR accuracy.
        Applies grayscale, contrast enhancement, sharpening and binary thresholding.
        """
        try:
            if self.crop_box:
                image = self._crop_by_ratios(image, self.crop_box)

            image = self._remove_colored_annotations(image)

            # 1. Convert to grayscale
            img = image.convert('L')
            
            # 2. Increase contrast significantly
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)  # Increased from 2.0 to make text darker
            
            # 3. Sharpen more
            img = img.filter(ImageFilter.SHARPEN)
            
            # 4. Resize if too small (improves character recognition for small fonts)
            width, height = img.size
            if width < 3000:
                new_size = (width * 2, height * 2)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 5. Binary Thresholding
            # Using 180 as threshold (slightly darker cutoff) keeps more text detail
            img = img.point(lambda p: 255 if p > 180 else 0)
            
            return img
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}. Using original image.")
            return image

    def _crop_by_ratios(
        self,
        image: Image.Image,
        crop_box: tuple[float, float, float, float]
    ) -> Image.Image:
        """Crop by left, top, right, bottom ratios in the range 0.0-1.0."""
        left_ratio, top_ratio, right_ratio, bottom_ratio = crop_box
        width, height = image.size
        left = max(0, min(width - 1, int(width * left_ratio)))
        top = max(0, min(height - 1, int(height * top_ratio)))
        right = max(left + 1, min(width, int(width * right_ratio)))
        bottom = max(top + 1, min(height, int(height * bottom_ratio)))
        return image.crop((left, top, right, bottom))

    def _remove_colored_annotations(self, image: Image.Image) -> Image.Image:
        """
        Remove bright colored markup before OCR while preserving dark printed text.

        The Swamiji Prasango scan has red handwritten annotations/underlines and
        yellow highlights baked into the page image. Whiten saturated bright
        pixels so Tesseract sees the printed black text, not the markup.
        """
        rgb = image.convert('RGB')
        arr = np.array(rgb)

        channels_max = arr.max(axis=2)
        channels_min = arr.min(axis=2)
        saturation_delta = channels_max - channels_min

        colored_markup = (saturation_delta > 35) & (channels_max > 120)
        arr[colored_markup] = [255, 255, 255]

        return Image.fromarray(arr, mode='RGB')

    def _clean_text(self, text: str) -> str:
        """
        Clean up common OCR artifacts.
        - Replaces weird dotted line interpretations (e.g. '.. . .', '.-.-') with clean dotted lines.
        - Removes common isolated garbage characters.
        """
        try:
            # 1. Normalize dotted lines
            # Matches any sequence of 4+ dots/spaces/hyphens mixed together
            text = re.sub(r'(?:[\.\-]\s*){4,}', '.......... ', text)
            
            # 2. Fix potential broken dotted lines that look like underscores
            text = re.sub(r'_{4,}', '.......... ', text)

            return text
        except Exception as e:
            logger.warning(f"Text cleaning failed: {e}")
            return text

    def _refine_metadata_lines(self, source_image: Image.Image, processed_image_path: str, text: str) -> str:
        """
        Re-run OCR on short bold date/time/location lines using line-oriented segmentation.
        Those lines are disproportionately error-prone in the full-page OCR pass.
        """
        try:
            candidates = self._detect_metadata_line_candidates(processed_image_path, source_image.size)
            if not candidates:
                return text

            lines = text.splitlines()
            search_start = 0
            replacements = 0

            for candidate in candidates:
                refined = self._ocr_metadata_line_crop(source_image, candidate["bbox"])
                if not refined:
                    continue

                match_idx = self._find_best_metadata_line_match(lines, candidate["text"], search_start)
                if match_idx is None:
                    continue

                if not self._should_replace_metadata_line(lines[match_idx], refined):
                    continue

                lines[match_idx] = refined
                search_start = match_idx + 1
                replacements += 1

            if replacements:
                logger.info(f"Refined {replacements} metadata lines with line-level OCR")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Metadata line refinement failed: {e}")
            return text

    def _detect_metadata_line_candidates(self, processed_image_path: str, image_size: tuple[int, int]) -> list[dict]:
        """Find OCR line boxes that likely contain date/time/location metadata."""
        data = pytesseract.image_to_data(
            processed_image_path,
            lang=self.lang,
            config='--psm 3',
            output_type=pytesseract.Output.DICT
        )

        grouped_lines: dict[tuple[int, int, int], dict] = {}
        for i, raw_word in enumerate(data["text"]):
            word = re.sub(r'\s+', ' ', (raw_word or '').strip())
            conf = self._safe_float(data["conf"][i])
            if not word or conf < 0:
                continue

            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            line = grouped_lines.setdefault(key, {
                "words": [],
                "left": data["left"][i],
                "top": data["top"][i],
                "right": data["left"][i] + data["width"][i],
                "bottom": data["top"][i] + data["height"][i],
            })
            line["words"].append(word)
            line["left"] = min(line["left"], data["left"][i])
            line["top"] = min(line["top"], data["top"][i])
            line["right"] = max(line["right"], data["left"][i] + data["width"][i])
            line["bottom"] = max(line["bottom"], data["top"][i] + data["height"][i])

        page_width, page_height = image_size
        candidates = []
        for line in grouped_lines.values():
            text_line = " ".join(line["words"]).strip()
            bbox = (line["left"], line["top"], line["right"], line["bottom"])
            if not self._is_metadata_line_candidate(text_line, bbox, page_width, page_height):
                continue
            candidates.append({"text": text_line, "bbox": bbox})

        candidates.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        return candidates

    def _is_metadata_line_candidate(
        self,
        text: str,
        bbox: tuple[int, int, int, int],
        page_width: int,
        page_height: int
    ) -> bool:
        normalized = self._normalize_metadata_line(text)
        if not normalized:
            return False

        digits = self._count_digit_chars(normalized)
        keywords = sum(keyword in normalized for keyword in METADATA_LINE_KEYWORDS)
        left, top, right, bottom = bbox
        box_width = max(1, right - left)
        box_height = max(1, bottom - top)
        guj = self._count_gujarati_chars(normalized)

        if keywords == 0:
            return False
        if digits < 4 and "તા." not in normalized and "સભા" not in normalized:
            return False
        if len(normalized) < 10 or len(normalized) > 120:
            return False
        if guj < 8:
            return False
        if left > page_width * 0.45:
            return False
        if box_width < page_width * 0.22:
            return False
        if box_height > page_height * 0.09:
            return False

        return True

    def _ocr_metadata_line_crop(self, source_image: Image.Image, bbox: tuple[int, int, int, int]) -> str:
        """OCR a cropped metadata line with milder preprocessing and line-based PSMs."""
        left, top, right, bottom = bbox
        x_pad = max(24, int((right - left) * 0.08))
        y_pad = max(14, int((bottom - top) * 0.35))
        crop_box = (
            max(0, left - x_pad),
            max(0, top - y_pad),
            min(source_image.width, right + x_pad),
            min(source_image.height, bottom + y_pad),
        )
        crop = source_image.crop(crop_box)

        variants = self._build_metadata_crop_variants(crop)
        configs = (
            '--psm 7 -c preserve_interword_spaces=1',
            '--psm 6 -c preserve_interword_spaces=1',
        )

        best_line = ""
        best_score = float("-inf")
        for variant in variants:
            for config in configs:
                candidate = self._ocr_image_with_tempfile(variant, config)
                normalized = self._normalize_metadata_line(candidate)
                score = self._metadata_line_score(normalized)
                if score > best_score:
                    best_line = normalized
                    best_score = score

        return best_line

    def _build_metadata_crop_variants(self, crop: Image.Image) -> list[Image.Image]:
        """Use softer variants than the full-page thresholding pass for bold metadata lines."""
        gray = crop.convert('L')
        width, height = gray.size
        if width < 1800:
            scale = max(2, int(1800 / max(1, width)) + 1)
            gray = gray.resize((width * scale, height * scale), Image.Resampling.LANCZOS)

        autocontrast = ImageOps.autocontrast(gray)
        enhanced = ImageEnhance.Contrast(autocontrast).enhance(1.6)
        return [gray, autocontrast, enhanced]

    def _ocr_image_with_tempfile(self, image: Image.Image, config: str) -> str:
        """Persist a PIL image briefly so pytesseract sees a stable file input."""
        fd, temp_img_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        try:
            image.save(temp_img_path)
            return pytesseract.image_to_string(temp_img_path, lang=self.lang, config=config)
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

    def _find_best_metadata_line_match(
        self,
        lines: list[str],
        candidate_text: str,
        start_index: int = 0
    ) -> Optional[int]:
        """Find the page-text line that best matches the detected OCR line box."""
        normalized_candidate = self._normalize_match_text(candidate_text)
        if not normalized_candidate:
            return None

        best_idx = None
        best_score = 0.0
        search_ranges = (range(start_index, len(lines)), range(0, start_index))

        for indexes in search_ranges:
            for idx in indexes:
                normalized_line = self._normalize_match_text(lines[idx])
                if not normalized_line:
                    continue

                score = SequenceMatcher(None, normalized_candidate, normalized_line).ratio()
                if normalized_candidate in normalized_line or normalized_line in normalized_candidate:
                    score += 0.15

                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_score >= 0.6:
                break

        if best_score < 0.6:
            return None
        return best_idx

    def _should_replace_metadata_line(self, existing_line: str, refined_line: str) -> bool:
        existing = self._normalize_metadata_line(existing_line)
        refined = self._normalize_metadata_line(refined_line)
        if not refined:
            return False

        similarity = SequenceMatcher(
            None,
            self._normalize_match_text(existing),
            self._normalize_match_text(refined)
        ).ratio()
        if similarity < 0.45:
            return False

        return self._metadata_line_score(refined) >= self._metadata_line_score(existing) - 2

    def _normalize_metadata_line(self, text: str) -> str:
        line = re.sub(r'\s+', ' ', (text or '').strip())
        if not line:
            return ""

        if 'તા.' in line:
            prefix, suffix = line.split('તા.', 1)
            if len(prefix.strip()) <= 4:
                line = 'તા.' + suffix

        line = re.sub(r'\s+([,.:])', r'\1', line)
        line = re.sub(r'([,])(?=\S)', r'\1 ', line)
        line = re.sub(r'([:])(?=\S)', r'\1 ', line)
        line = re.sub(r'^\W+', '', line)
        return line.strip(' -"“”‘’*%₹~|[]{}<>')

    def _normalize_match_text(self, text: str) -> str:
        line = self._normalize_metadata_line(text)
        line = line.replace(' ', '')
        return re.sub(r'[^\u0A80-\u0AFF0-9\u0AE6-\u0AEF:.,-]', '', line)

    def _metadata_line_score(self, text: str) -> float:
        if not text:
            return float("-inf")

        guj = self._count_gujarati_chars(text)
        digits = self._count_digit_chars(text)
        latin = sum(1 for ch in text if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))
        symbols = sum(1 for ch in text if not ch.isalnum() and not ch.isspace() and ch not in '.,:-')
        keywords = sum(keyword in text for keyword in METADATA_LINE_KEYWORDS)
        has_date = bool(re.search(r'તા\.\s*[\d૦૧૨૩૪૫૬૭૮૯]+[-/][\d૦૧૨૩૪૫૬૭૮૯]+[-/][\d૦૧૨૩૪૫૬૭૮૯]+', text))

        score = guj + (digits * 1.5) + (keywords * 8)
        if has_date:
            score += 20
        score -= latin * 4
        score -= symbols * 3
        if len(text) < 12:
            score -= 12
        return score

    def _safe_float(self, value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return -1.0

    def _count_digit_chars(self, text: str) -> int:
        return sum(1 for ch in text if ch.isdigit() or '\u0AE6' <= ch <= '\u0AEF')

    def _clean_ocr_text_for_export(self, text: str) -> str:
        """Filter obvious OCR noise while preserving readable Gujarati lines for TXT export."""
        lines = []
        for raw_line in text.splitlines():
            line = self._normalize_ocr_line(raw_line)
            if not line or self._is_probably_noise_line(line):
                continue
            lines.append(line)

        if not lines:
            return ""

        total_chars = sum(len(line) for line in lines)
        if total_chars < 25 and len(lines) <= 2:
            return ""

        return "\n".join(lines)

    def _normalize_ocr_line(self, line: str) -> str:
        line = re.sub(r'\s+', ' ', line.strip())
        line = self._normalize_metadata_line(line)
        return line.strip(' -|/,:;.')

    def _count_gujarati_chars(self, text: str) -> int:
        return sum(1 for ch in text if '\u0A80' <= ch <= '\u0AFF')

    def _is_probably_noise_line(self, line: str) -> bool:
        guj = self._count_gujarati_chars(line)
        nonspace = sum(1 for ch in line if not ch.isspace())
        digits = sum(1 for ch in line if ch.isdigit())
        latin = sum(1 for ch in line if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))
        symbols = sum(1 for ch in line if ch in '[]{}<>|_/*€%#@\\~=+^`')
        words = [word for word in line.split() if word]
        short_ratio = sum(len(word) <= 2 for word in words) / len(words) if words else 1.0
        guj_ratio = (guj / nonspace) if nonspace else 0.0

        if nonspace < 4:
            return True
        if guj == 0:
            return True
        if guj_ratio < 0.45:
            return True
        if digits >= 3 and digits > guj:
            return True
        if latin >= 4 and latin >= guj:
            return True
        if symbols >= 3 and guj < 12:
            return True
        if len(words) >= 3 and short_ratio > 0.75 and guj < 24:
            return True
        return False

    def _build_clean_ocr_txt_output(self, cleaned_txt_pages: list[tuple[int, str]]) -> str:
        blocks = []
        for page_num, page_text in cleaned_txt_pages:
            if page_text:
                blocks.append(f"[Page {page_num}]\n{page_text}")
            else:
                blocks.append(f"[Page {page_num}]")
        return "\n\n".join(blocks) + "\n"

    def _process_ocr_batch(self, start_page: int, end_page: int, doc: Document, pdf_writer: PdfWriter):
        """Process a single batch of pages for OCR."""
        logger.debug(f"Processing OCR batch: pages {start_page} to {end_page}")
        
        try:
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

        for i, image in enumerate(images):
            try:
                # Preprocess image for better OCR
                processed_image = self._preprocess_image(image)
                
                fd, temp_img_path = tempfile.mkstemp(suffix='.png')
                os.close(fd)
                
                try:
                    processed_image.save(temp_img_path)
                    
                    # 1. Generate Searchable PDF Page
                    if not self.text_only:
                        pdf_bytes = pytesseract.image_to_pdf_or_hocr(temp_img_path, extension='pdf', lang=self.lang)
                        pdf_page_reader = PdfReader(io.BytesIO(pdf_bytes))
                        if len(pdf_page_reader.pages) > 0:
                            pdf_writer.add_page(pdf_page_reader.pages[0])
    
                    # 2. Extract Text for DOCX
                    text = self._extract_page_text(
                        source_image=image,
                        processed_image_path=temp_img_path
                    )
                finally:
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
                
                doc.add_paragraph(text)
                doc.add_page_break()

            except Exception as e:
                logger.error(f"Error performing OCR on page {start_page + i}: {e}")
                continue
        
        del images

    def _process_shrilipi(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        """
        Shrilipi processing - extracts text and converts to Unicode Gujarati.
        Supports .pdf, .txt, .md, and .docx output formats.
        """
        logger.info(f"Starting Shrilipi processing for: {self.input_pdf_path}")
        
        reader = PdfReader(self.input_pdf_path)
        total_pages = len(reader.pages)
        pages_to_process = self._parse_page_range(total_pages)
        logger.info(f"Total pages in PDF: {total_pages}, Processing: {len(pages_to_process)} pages")

        all_text = []
        
        try:
            with tqdm(total=len(pages_to_process), unit="page", desc="Shrilipi Processing") as pbar:
                for idx, page_num in enumerate(pages_to_process):
                    # Extract text (in Shri Lipi encoding) from specific page
                    page = reader.pages[page_num - 1]  # Convert to 0-indexed
                    shri_lipi_text = page.extract_text() or ""
                    
                    # Convert to Unicode
                    unicode_text = convert_shri_lipi_to_unicode(shri_lipi_text)
                    all_text.append(unicode_text)
                    
                    pbar.update(1)
                    
                    progress_pct = int((idx + 1) / len(pages_to_process) * 100)
                    
                    if progress_callback:
                        progress_callback(progress_pct, f"Shrilipi: Processed {idx + 1}/{len(pages_to_process)} pages")

            # Save outputs based on format
            full_text = '\n\n'.join(all_text)
            
            # Always save DOCX
            doc = Document()
            for page_text in all_text:
                doc.add_paragraph(page_text)
                doc.add_page_break()
            doc.save(self.output_docx_path)
            logger.info(f"DOCX saved to: {self.output_docx_path}")

            if self.output_format == 'pdf':
                pdf_path = self.output_pdf_path or self.output_docx_path.replace('.docx', '.pdf')
                if progress_callback:
                    progress_callback(95, "Shrilipi: Converting DOCX to PDF")
                convert_docx_to_pdf(self.output_docx_path, pdf_path)
                logger.info(f"PDF saved to: {pdf_path}")
            
            # Save .txt if requested
            if self.output_txt_path or self.output_format == 'txt':
                txt_path = self.output_txt_path or self.output_docx_path.replace('.docx', '.txt')
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                logger.info(f"TXT saved to: {txt_path}")
            
            # Save .md if requested
            if self.output_md_path or self.output_format == 'md':
                md_path = self.output_md_path or self.output_docx_path.replace('.docx', '.md')
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Converted Document\n\n")
                    f.write(full_text)
                logger.info(f"MD saved to: {md_path}")
            
            if progress_callback:
                progress_callback(100, "Shrilipi processing completed successfully.")

        except Exception as e:
            logger.error(f"Critical error during Shrilipi processing: {e}", exc_info=True)
            raise


def convert_docx_to_pdf(docx_path: str, pdf_path: str = None) -> str:
    """
    Convert a DOCX file to PDF.
    
    The resulting PDF will be fully searchable because it contains actual text,
    not images with text overlays like OCR-generated searchable PDFs.
    
    Args:
        docx_path: Path to input DOCX file
        pdf_path: Optional path for output PDF (default: same name with .pdf extension)
        
    Returns:
        Path to the generated PDF file
    """
    if not os.path.exists(docx_path):
        raise FileNotFoundError(f"DOCX file not found: {docx_path}")
    
    if pdf_path is None:
        pdf_path = docx_path.replace('.docx', '.pdf')
    
    # Try LibreOffice FIRST (more reliable for background tasks)
    try:
        import subprocess
        
        # Check standard macOS path for LibreOffice
        soffice_cmd = 'soffice'
        if not shutil.which('soffice'):
            if os.path.exists('/Applications/LibreOffice.app/Contents/MacOS/soffice'):
                soffice_cmd = '/Applications/LibreOffice.app/Contents/MacOS/soffice'
        
        output_dir = os.path.dirname(pdf_path) or "."
        
        logger.info(f"Attempting PDF conversion with LibreOffice...")
        result = subprocess.run([
            soffice_cmd, '--headless', '--convert-to', 'pdf',
            '--outdir', output_dir, docx_path
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            # LibreOffice outputs to same basename with .pdf
            generated_pdf = os.path.join(output_dir, os.path.basename(docx_path).replace('.docx', '.pdf'))
            
            # Rename if necessary/ensure correct path
            if generated_pdf != pdf_path and os.path.exists(generated_pdf):
                os.rename(generated_pdf, pdf_path)
                
            if os.path.exists(pdf_path):
                logger.info(f"PDF saved via LibreOffice to: {pdf_path}")
                return pdf_path
            else:
                 logger.warning("LibreOffice reported success but file not found. Trying docx2pdf...")
        else:
            logger.warning(f"LibreOffice conversion failed: {result.stderr}. Trying docx2pdf...")
            
    except Exception as e:
        logger.warning(f"LibreOffice conversion error: {e}")

    # Fallback to docx2pdf - DISABLED due to stability issues on macOS
    # try:
    #     from docx2pdf import convert
    #     logger.info("Attempting PDF conversion with docx2pdf (MS Word)...")
    #     convert(docx_path, pdf_path)
    #     logger.info(f"PDF saved via docx2pdf to: {pdf_path}")
    #     return pdf_path
    # except ImportError:
    #     logger.error("docx2pdf not installed. Run: pip install docx2pdf")
    #     raise
    # except Exception as e:
    #     logger.error(f"Failed to convert DOCX to PDF with both methods: {e}")
    #     raise Exception("PDF conversion failed. Please ensure LibreOffice is installed.")
    
    raise Exception("PDF conversion failed. LibreOffice conversion unsuccessful.")


def check_dependencies():
    """Check if external dependencies (Tesseract, Poppler) are available."""
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract is not found or not in your PATH.")
        print("\nCRITICAL: Tesseract-OCR is missing.")
        print("Mac: brew install tesseract tesseract-lang")
        print("Windows: Download installer from UB-Mannheim/tesseract")
        print("Linux: sudo apt install tesseract-ocr tesseract-ocr-guj\n")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unified Gujarati PDF Processor")
    parser.add_argument("input_file", help="Path to input PDF file")
    parser.add_argument("--mode", choices=["ocr", "shrilipi"], default="ocr",
                        help="Processing mode: 'ocr' for scanned PDFs, 'shrilipi' for Shri Lipi font PDFs")
    parser.add_argument("--engine", choices=["tesseract", "vision"], default="tesseract",
                        help="OCR engine for 'ocr' mode: 'tesseract' (free, offline) or "
                             "'vision' (Google Cloud Vision, higher accuracy, needs credentials)")
    parser.add_argument("--google_credentials",
                        help="Path to Google Cloud service-account JSON key (required for --engine vision "
                             "unless GOOGLE_APPLICATION_CREDENTIALS is set)")
    parser.add_argument("--output_docx", help="Output DOCX filename")
    parser.add_argument("--batch_size", type=int, default=5, 
                        help="Number of pages to process at once (OCR only, default: 5)")
    parser.add_argument("--lang", default="guj", help="Tesseract language code (default: guj)")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for rasterization (default: 300)")
    parser.add_argument("--page_range", help="Pages to process, e.g. '1-5,8,10-12'")
    parser.add_argument("--ocr_psm", type=int, default=4, help="Tesseract page segmentation mode for main OCR (default: 4)")
    parser.add_argument(
        "--crop_box",
        help="Crop ratios as left,top,right,bottom before OCR, e.g. '0.16,0.06,0.74,0.96'"
    )
    parser.add_argument("--text_only", action="store_true", help="Skip searchable PDF generation, output only text files")
    parser.add_argument(
        "--no_refine_metadata_lines",
        action="store_true",
        help="Skip slower line-level metadata OCR refinement"
    )

    args = parser.parse_args()
    
    # Determine output filename
    base_name = os.path.splitext(os.path.basename(args.input_file))[0]
    output_dir = os.path.dirname(args.input_file) or "."
    
    if not args.output_docx:
        suffix = "_ocr.docx" if args.mode == "ocr" else "_unicode.docx"
        args.output_docx = os.path.join(output_dir, f"{base_name}{suffix}")

    # Check dependencies for OCR mode
    if args.mode == "ocr" and args.engine == "tesseract":
        check_dependencies()

    crop_box = None
    if args.crop_box:
        try:
            crop_box = tuple(float(part.strip()) for part in args.crop_box.split(','))
            if len(crop_box) != 4 or any(part < 0 or part > 1 for part in crop_box):
                raise ValueError
            if crop_box[0] >= crop_box[2] or crop_box[1] >= crop_box[3]:
                raise ValueError
        except ValueError:
            parser.error("--crop_box must be four ratios in order: left,top,right,bottom")
    
    # Create processor
    mode = ProcessingMode.OCR if args.mode == "ocr" else ProcessingMode.SHRILIPI
    
    processor = GujaratiPDFProcessor(
        input_pdf_path=args.input_file,
        output_docx_path=args.output_docx,
        mode=mode,
        batch_size=args.batch_size,
        lang=args.lang,
        dpi=args.dpi,
        page_range=args.page_range,
        text_only=args.text_only,
        refine_metadata_lines=not args.no_refine_metadata_lines,
        ocr_psm=args.ocr_psm,
        crop_box=crop_box,
        ocr_engine=OCREngine.VISION if args.engine == "vision" else OCREngine.TESSERACT,
        google_credentials_path=args.google_credentials,
    )
    
    try:
        processor.process()
        print(f"\nOutput saved to: {args.output_docx}")
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        sys.exit(1)
