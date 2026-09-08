"""
Process Pardarshi Paravani PDF: extract all 223 discourses and convert
Shri Lipi text to Unicode Gujarati.

The source PDF is a combined scan/export of discourses 1-223. Its extracted
text is inconsistent: some headers say "(â-35)", some say "(âhQ‚-35)",
some are truncated, and a few are visibly mislabeled. This script therefore
uses explicit header numbers as anchors and falls back to printed page-reset
boundaries to keep the physical sequence at exactly 223 files.

Output layout:
  outputs/Pardarshi Paravani/001.txt
  outputs/Pardarshi Paravani/002.txt
  ...
  outputs/Pardarshi Paravani/223.txt
"""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

from shri_lipi_converter import convert_shri_lipi_to_unicode, remove_bold_duplicates


PDF_PATH = Path("uploads/Pardarshi Paravani 1-223 combined.pdf")
OUTPUT_DIR = Path("outputs/Pardarshi Paravani")
EXPECTED_DISCOURSE_COUNT = 223

DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{1,2}"
    r"|\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{2,4}"
)
DISCOURSE_RE = (
    re.compile(r"\(\s*â\s*-?\s*(\d{1,3})\s*\)"),
    re.compile(r"\(\s*âhQ‚\s*-?\s*(\d{1,3})\s*\)"),
)


def clean_body(text: str) -> str:
    text = text.replace("\x00", "")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def page_window(text: str, max_lines: int = 18) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ⏎ ".join(lines[:max_lines])


def is_printed_page_one(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    first = lines[0]
    second = lines[1] if len(lines) > 1 else ""

    # Common forms:
    #   "25-12-78 ... 1"
    #   "25-12-78, topic" / "1"
    #   "6-2-83,  1 1983-02-06, title ..."
    return (
        re.search(r"(?<!\d)1\s*$", first) is not None
        or second == "1"
        or (DATE_RE.search(first) and re.search(r"(^|\s)1(\s|$)", first))
        is not None
    )


def discourse_numbers_in_window(window: str) -> list[int]:
    numbers = []
    for regex in DISCOURSE_RE:
        for match in regex.finditer(window):
            number = int(match.group(1))
            before = window[max(0, match.start() - 260):match.start()]
            if 1 <= number <= EXPECTED_DISCOURSE_COUNT and DATE_RE.search(before):
                numbers.append(number)
    return numbers


def detect_discourse_starts(raw_pages: list[str]) -> dict[int, int]:
    """Return discourse number -> 0-based start page index."""
    windows = [page_window(text) for text in raw_pages]
    page_one_pages = [
        page_number
        for page_number, text in enumerate(raw_pages, start=1)
        if is_printed_page_one(text)
    ]

    occurrences: list[tuple[int, int]] = []
    for page_number, window in enumerate(windows, start=1):
        numbers = discourse_numbers_in_window(window)
        if not numbers:
            continue

        nearby_page_ones = [
            candidate
            for candidate in page_one_pages
            if candidate <= page_number and page_number - candidate <= 4
        ]
        start_page = nearby_page_ones[-1] if nearby_page_ones else page_number
        occurrences.append((start_page, numbers[-1]))

    deduped_occurrences = []
    seen = set()
    for occurrence in occurrences:
        if occurrence in seen:
            continue
        seen.add(occurrence)
        deduped_occurrences.append(occurrence)

    by_number: dict[int, list[int]] = defaultdict(list)
    for start_page, number in deduped_occurrences:
        by_number[number].append(start_page)

    starts: dict[int, int] = {}
    previous_page = 0
    used_pages = set()

    for expected_number in range(1, EXPECTED_DISCOURSE_COUNT + 1):
        exact = [
            page
            for page in by_number.get(expected_number, [])
            if page > previous_page and page not in used_pages
        ]
        if exact:
            chosen = exact[0]
        else:
            next_exact = []
            limit = len(raw_pages) + 1
            for future_number in range(expected_number + 1, EXPECTED_DISCOURSE_COUNT + 1):
                future_pages = [
                    page
                    for page in by_number.get(future_number, [])
                    if page > previous_page and page not in used_pages
                ]
                if future_pages:
                    next_exact = future_pages
                    limit = future_pages[0]
                    break

            fallback = [
                page
                for page in page_one_pages
                if previous_page < page < limit and page not in used_pages
            ]
            if fallback:
                chosen = fallback[0]
            elif next_exact:
                # Some source headers are mislabeled/truncated. Keep sequence.
                chosen = next_exact[0]
            else:
                remaining = [
                    page
                    for page in page_one_pages
                    if page > previous_page and page not in used_pages
                ]
                if not remaining:
                    raise RuntimeError(
                        f"Could not infer start page for discourse {expected_number}"
                    )
                chosen = remaining[0]

        starts[expected_number] = chosen - 1
        used_pages.add(chosen)
        previous_page = chosen

    if len(starts) != EXPECTED_DISCOURSE_COUNT:
        raise RuntimeError(f"Detected {len(starts)} starts, expected 223")

    return starts


def main() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    reader = PdfReader(str(PDF_PATH))
    raw_pages = [
        remove_bold_duplicates(reader.pages[index].extract_text() or "")
        for index in range(len(reader.pages))
    ]
    print(f"Processing {len(raw_pages)} PDF pages...")

    starts = detect_discourse_starts(raw_pages)
    start_items = sorted(starts.items())
    written = 0

    for idx, (number, start_page) in enumerate(start_items):
        end_page = (
            start_items[idx + 1][1]
            if idx + 1 < len(start_items)
            else len(raw_pages)
        )
        raw_text = "\n\n".join(raw_pages[start_page:end_page])
        body = clean_body(raw_text)
        unicode_text = convert_shri_lipi_to_unicode(body)
        out_path = OUTPUT_DIR / f"{number:03d}.txt"
        out_path.write_text(unicode_text.rstrip() + "\n", encoding="utf-8")
        written += 1

    txt_count = len(list(OUTPUT_DIR.glob("*.txt")))
    if written != EXPECTED_DISCOURSE_COUNT or txt_count != EXPECTED_DISCOURSE_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_DISCOURSE_COUNT} files, wrote {written}, "
            f"found {txt_count}"
        )

    print(f"Written {written} discourse files to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
