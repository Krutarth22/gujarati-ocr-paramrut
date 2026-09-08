"""Build the Swamiji na Prasango EPUB from the cleaned TXT file."""

from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path


TITLE = "Swamiji na Prasango"
AUTHOR = "Swamiji"
INPUT_TXT = Path("outputs/Swamiji_na_Prasango_2_FINAL.txt")
COVER = Path("uploads/epub_cover.jpeg")
BUILD_DIR = Path("outputs/epub_build")
SOURCE_MD = BUILD_DIR / "Swamiji na Prasango.md"
EPUB_CSS = BUILD_DIR / "epub.css"
OUTPUT_EPUB = Path("outputs/Swamiji na Prasango.epub")


GUJ_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
ASCII_TO_GUJ_DIGITS = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")
PRASANG_RE = re.compile(r"^([૦-૯0-9]{1,4})(.*)$")
PAGE_RE = re.compile(r"^\[Page (\d+)\]$")
FINAL_PRINTED_MARKER_RE = re.compile(r"^૩૨૪\s*[.:]")


def prasang_number(raw_number: str) -> int:
    return int(raw_number.translate(GUJ_DIGITS))


def is_prasang_heading(line: str) -> re.Match[str] | None:
    match = PRASANG_RE.match(line)
    if not match:
        return None

    number = prasang_number(match.group(1))
    rest = match.group(2).strip()

    # Dates/times, years, and numbered sub-list items should not become chapters.
    if number <= 0 or number > 500:
        return None
    if re.match(r"^[./:-][૦-૯0-9]", rest):
        return None
    if rest.startswith(")"):
        return None
    if 1900 <= number <= 2099 and not rest.startswith((".", ":")):
        return None
    if len(match.group(1)) >= 4 and number > 600:
        return None
    if len(line.strip()) < 8:
        return None
    if sum("\u0A80" <= ch <= "\u0AFF" for ch in line) < 5:
        return None
    return match


def strip_ocr_number_prefix(line: str) -> str:
    match = PRASANG_RE.match(line)
    if not match:
        return line
    rest = match.group(2).strip()
    rest = re.sub(r"^[.:।,)\s-]+", "", rest).strip()
    return rest or line


def gujarati_number(number: int) -> str:
    return str(number).translate(ASCII_TO_GUJ_DIGITS)


def txt_to_markdown(text: str) -> str:
    lines = [
        "---",
        f"title: {TITLE}",
        f"author: {AUTHOR}",
        "language: gu",
        "---",
        "",
    ]

    for raw_line in text.splitlines():
        line = raw_line.strip()
        page_match = PAGE_RE.match(line)
        if page_match:
            continue

        heading_match = is_prasang_heading(line)
        if heading_match:
            raw_number = heading_match.group(1)
            title = strip_ocr_number_prefix(line)
            lines.extend(["", f"## પ્રસંગ {raw_number}", ""])
            lines.append(html.escape(title, quote=False))
        elif line:
            lines.append(html.escape(line, quote=False))
        else:
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if not INPUT_TXT.exists():
        raise FileNotFoundError(INPUT_TXT)
    if not COVER.exists():
        raise FileNotFoundError(COVER)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_MD.write_text(txt_to_markdown(INPUT_TXT.read_text(encoding="utf-8")), encoding="utf-8")
    EPUB_CSS.write_text(
        """
body {
  font-family: "Gujarati Sangam MN", "Gujarati MT", serif;
  line-height: 1.55;
}
h1, h2 {
  font-family: "Gujarati Sangam MN", "Gujarati MT", serif;
}
.page-ref {
  color: #777;
  font-size: 0.85em;
  font-style: italic;
}
""".strip() + "\n",
        encoding="utf-8",
    )

    cmd = [
        "pandoc",
        str(SOURCE_MD),
        "-o",
        str(OUTPUT_EPUB),
        "--toc",
        "--toc-depth=2",
        "--css",
        str(EPUB_CSS),
        "--metadata",
        f"title={TITLE}",
        "--metadata",
        f"author={AUTHOR}",
        "--metadata",
        "lang=gu",
        "--epub-cover-image",
        str(COVER),
    ]
    subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
