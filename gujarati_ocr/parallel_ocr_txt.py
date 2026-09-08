"""Parallel TXT-only OCR runner for annotation-heavy scanned Gujarati PDFs."""

import argparse
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path
from tqdm import tqdm

from processor import GujaratiPDFProcessor, ProcessingMode


def parse_crop_box(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = tuple(float(part.strip()) for part in value.split(","))
    if len(parts) != 4 or any(part < 0 or part > 1 for part in parts):
        raise argparse.ArgumentTypeError("crop box must be left,top,right,bottom ratios")
    if parts[0] >= parts[2] or parts[1] >= parts[3]:
        raise argparse.ArgumentTypeError("crop box left/top must be smaller than right/bottom")
    return parts


def process_page(args: tuple) -> tuple[int, str, str | None]:
    pdf_path, page_num, dpi, lang, psm, crop_box = args
    processor = GujaratiPDFProcessor(
        input_pdf_path=pdf_path,
        output_docx_path=os.devnull,
        mode=ProcessingMode.OCR,
        lang=lang,
        dpi=dpi,
        text_only=True,
        refine_metadata_lines=False,
        ocr_psm=psm,
        crop_box=crop_box,
    )

    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            thread_count=1,
            dpi=dpi,
        )
        if not images:
            return page_num, "", "no image rendered"

        processed = processor._preprocess_image(images[0])
        fd, temp_img_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            processed.save(temp_img_path)
            config = f"--psm {psm} -c preserve_interword_spaces=1"
            raw_text = pytesseract.image_to_string(temp_img_path, lang=lang, config=config)
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

        text = processor._clean_text(raw_text)
        text = processor._clean_ocr_text_for_export(text)
        return page_num, text, None
    except Exception as exc:
        return page_num, "", str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel TXT-only OCR")
    parser.add_argument("input_pdf")
    parser.add_argument("output_txt")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--lang", default="guj+eng")
    parser.add_argument("--ocr_psm", type=int, default=6)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--crop_box", type=parse_crop_box)
    args = parser.parse_args()

    total_pages = pdfinfo_from_path(args.input_pdf)["Pages"]
    work = [
        (args.input_pdf, page_num, args.dpi, args.lang, args.ocr_psm, args.crop_box)
        for page_num in range(1, total_pages + 1)
    ]

    results: dict[int, tuple[str, str | None]] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process_page, item) for item in work]
        with tqdm(total=total_pages, unit="page", desc="Parallel OCR") as pbar:
            for future in as_completed(futures):
                page_num, text, error = future.result()
                results[page_num] = (text, error)
                pbar.update(1)

    blocks = []
    errors = []
    for page_num in range(1, total_pages + 1):
        text, error = results.get(page_num, ("", "missing result"))
        if error:
            errors.append(f"Page {page_num}: {error}")
        blocks.append(f"[Page {page_num}]\n{text}".rstrip())

    with open(args.output_txt, "w", encoding="utf-8") as output:
        output.write("\n\n".join(blocks).rstrip() + "\n")

    if errors:
        error_path = args.output_txt.replace(".txt", "_errors.txt")
        with open(error_path, "w", encoding="utf-8") as output:
            output.write("\n".join(errors) + "\n")
        print(f"OCR completed with {len(errors)} page errors. See {error_path}")
    else:
        print(f"OCR completed without page errors: {args.output_txt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
