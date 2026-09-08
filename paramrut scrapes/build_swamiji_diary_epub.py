from __future__ import annotations

import argparse
import html
import re
import subprocess
from pathlib import Path

import fitz

from epub_builder import EpubItem, NavPoint, build_epub, make_xhtml_document, paragraphize, section_heading


DEFAULT_SOURCE_PDF = Path("Swamishree diary.pdf")
DEFAULT_SOURCE_DIR = Path("swamiji_diary")
DEFAULT_OUTPUT = DEFAULT_SOURCE_DIR / "Swamiji_Diary.epub"
DEFAULT_FONT_PATH = Path("apk_extracted/assets/flutter_assets/assets/bhajan/css/Lohit-Gujarati.ttf")

GUJARATI_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
PAGE_NUMBER_RE = re.compile(r"^\s*[0-9૦-૯પ]+\s*$")
PRASANG_HEADING_RE = re.compile(
    r"^\s*(?:[0-9૦-૯]+\s+)?પ્રસંગ\s*(?:[-–—:ઃ]|\s+૬)?\s*[0-9૦-૯પરપ]+"
)
DATE_LINE_RE = re.compile(r"[0-9૦-૯]{1,2}\s*/\s*[0-9૦-૯]{1,2}\s*/\s*[0-9૦-૯]{2,4}")
SPACE_RE = re.compile(r"\s+")
NUMERIC_TOKEN_RE = re.compile(r"(?<![\u0A80-\u0AFF])([0-9૦-૯પર]+(?:\s*[-/:ઃ.]\s*[0-9૦-૯પર]+)*)(?![\u0A80-\u0AFF])")
GARBAGE_SYMBOL_RE = re.compile(r"[€#_£]")

TEXT_REPLACEMENTS = {
    "હને ઠાકર": "હું ને મારા ઠાકર",
    "સુષી": "સુધી",
    "જક્ટ": "જરૂર",
    "જક્#": "જરૂર",
    "જશ્ક": "જરૂર",
    "શશ્ન્આત": "શરૂઆત",
    "શશ્નઆત": "શરૂઆત",
    "શશ્ન": "શરૂ",
    "શશ્ચ": "શરૂ",
    "શર્‌": "શરૂ",
    "બધ્રા": "બધા",
    "બધ્યા": "બધા",
    "બધ્યાને": "બધાને",
    "બધ્યાના": "બધાના",
    "ન્હોતો": "નહોતો",
    "ન્હોતી": "નહોતી",
    "ન્હોતા": "નહોતા",
    "ન્હોતું": "નહોતું",
    "સાધ્વસ્વામી": "માધવસ્વામી",
    "અહોયાં": "અહીંયાં",
    "પડોયા": "પડીયા",
    "નદોમાંથી": "નદીમાંથી",
    "ધ્રોઈને": "ધોઈને",
}


def ocr_pdf_pages(
    pdf_path: Path,
    source_dir: Path,
    *,
    force: bool = False,
    zoom: float = 3.0,
) -> list[Path]:
    page_dir = source_dir / "ocr_pages"
    page_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    output_paths: list[Path] = []
    tmp_image = source_dir / ".ocr_page.png"

    for page_index in range(doc.page_count):
        text_path = page_dir / f"page_{page_index + 1:03}.txt"
        output_paths.append(text_path)
        if text_path.exists() and not force:
            continue

        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(tmp_image)
        result = subprocess.run(
            ["tesseract", str(tmp_image), "stdout", "-l", "guj", "--psm", "6"],
            check=True,
            capture_output=True,
            text=True,
        )
        text_path.write_text(result.stdout, encoding="utf-8")
        tmp_image.unlink(missing_ok=True)
        print(f"OCR page {page_index + 1}/{doc.page_count}: {text_path}")

    return output_paths


def clean_ocr_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if PAGE_NUMBER_RE.match(line):
            continue
        if line == "સ્વામિશ્રીજી":
            continue
        line = normalize_ocr_line(line)
        if not line:
            continue
        lines.append(line)
    return lines


def normalize_ocr_line(line: str) -> str:
    line = re.sub(r"^\s*૦\s+", "• ", line)

    for source, target in TEXT_REPLACEMENTS.items():
        line = line.replace(source, target)

    if PRASANG_HEADING_RE.match(line):
        return line
    if GARBAGE_SYMBOL_RE.search(line):
        return ""

    def normalize_numeric_token(match: re.Match[str]) -> str:
        token = match.group(1)
        if not re.search(r"[0-9૦-૯]", token) and not re.search(r"[-/:ઃ.]", token):
            return token
        return token.replace("પ", "૫").replace("ર", "૨")

    return NUMERIC_TOKEN_RE.sub(normalize_numeric_token, line)


def load_ocr_text(page_paths: list[Path]) -> str:
    pages: list[str] = []
    for page_path in page_paths:
        pages.append("\n".join(clean_ocr_lines(page_path.read_text(encoding="utf-8"))))
    return "\n\n".join(pages)


def gujarati_number_to_int(value: str) -> int:
    return int(value.translate(GUJARATI_DIGITS))


def int_to_gujarati_number(value: int) -> str:
    return str(value).translate(str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯"))


def parse_prasangs(text: str) -> list[dict]:
    prasangs: list[dict] = []
    current: dict | None = None
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if current is None or not paragraph_lines:
            paragraph_lines.clear()
            return
        paragraph = SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
        if paragraph:
            current["paragraphs"].append(paragraph)
        paragraph_lines.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if PRASANG_HEADING_RE.match(stripped):
            flush_paragraph()
            number = len(prasangs) + 1
            current = {
                "number": number,
                "title": f"પ્રસંગ - {int_to_gujarati_number(number)}",
                "meta": "",
                "paragraphs": [],
            }
            prasangs.append(current)
            continue

        if current is None:
            continue
        if not stripped:
            flush_paragraph()
            continue
        if not current["meta"] and not current["paragraphs"] and not paragraph_lines and DATE_LINE_RE.search(stripped):
            current["meta"] = SPACE_RE.sub(" ", stripped).strip()
            continue
        paragraph_lines.append(stripped)

    flush_paragraph()
    return prasangs


def write_prasang_texts(prasangs: list[dict], source_dir: Path) -> None:
    text_dir = source_dir / "prasangs"
    text_dir.mkdir(parents=True, exist_ok=True)

    for prasang in prasangs:
        parts = [prasang["title"]]
        if prasang["meta"]:
            parts.append(prasang["meta"])
        parts.extend(prasang["paragraphs"])
        text = "\n\n".join(parts).strip() + "\n"
        (text_dir / f"prasang_{prasang['number']:03}.txt").write_text(text, encoding="utf-8")


def build_prasang_xhtml(prasang: dict) -> str:
    meta_html = ""
    if prasang["meta"]:
        meta_html = "\n".join(
            [
                '    <div class="meta-block">',
                f'      <p class="meta">{html.escape(prasang["meta"])}</p>',
                "    </div>",
            ]
        )
    body = "\n".join(
        [
            '    <section class="entry-start">',
            section_heading(1, prasang["title"]),
            meta_html,
            "    </section>",
            paragraphize(prasang["paragraphs"]),
        ]
    )
    return make_xhtml_document(prasang["title"], body, language="gu")


def diary_styles() -> str:
    return """@font-face {
  font-family: "Lohit Gujarati";
  font-style: normal;
  font-weight: 400;
  src: url("../fonts/Lohit-Gujarati.ttf");
}

html, body {
  margin: 0;
  padding: 0;
}

body {
  font-family: "Lohit Gujarati", serif;
  line-height: 1.7;
  widows: 2;
  orphans: 2;
  margin: 0;
  padding: 0 4%;
  text-align: left;
}

h1 {
  break-after: avoid;
  font-size: 1.45em;
  margin: 0 0 0.8em;
  page-break-after: avoid;
  text-align: center;
}

.para {
  margin: 0 0 0.9em;
  text-indent: 1.4em;
}

.meta-block {
  border-top: 1px solid #ddd;
  border-bottom: 1px solid #ddd;
  color: #444;
  font-size: 0.96em;
  margin: 0 0 1.2em;
  padding: 0.8em 0;
}

.meta {
  margin: 0.25em 0;
  text-align: center;
}

.entry-start {
  margin-top: 18vh;
}

nav#toc ol {
  list-style: none;
  margin: 0;
  padding-left: 0;
}

nav#toc li {
  margin: 0.35em 0;
}
"""


def build_book(pdf_path: Path, source_dir: Path, output: Path, *, force_ocr: bool = False) -> None:
    page_paths = ocr_pdf_pages(pdf_path, source_dir, force=force_ocr)
    prasangs = parse_prasangs(load_ocr_text(page_paths))
    if not prasangs:
        raise RuntimeError("No prasangs found in OCR output.")

    write_prasang_texts(prasangs, source_dir)

    items: list[EpubItem] = []
    nav_points: list[NavPoint] = []
    for prasang in prasangs:
        href = f"text/prasang_{prasang['number']:03}.xhtml"
        items.append(
            EpubItem(
                id=f"prasang_{prasang['number']:03}",
                href=href,
                media_type="application/xhtml+xml",
                content=build_prasang_xhtml(prasang),
            )
        )
        nav_points.append(NavPoint(label=prasang["title"], href=href))

    if not DEFAULT_FONT_PATH.exists():
        raise RuntimeError(f"Embedded font not found: {DEFAULT_FONT_PATH}")

    build_epub(
        output,
        title="સ્વામિશ્રીજીની ડાયરી",
        identifier_seed=str(output.resolve()),
        creators=["OpenAI Codex"],
        language="gu",
        items=items,
        nav_points=nav_points,
        styles_css=diary_styles(),
        package_prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/",
        metadata_properties=[("ibooks:specified-fonts", "true")],
        extra_items=[
            EpubItem(
                id="font_lohit_gujarati",
                href="fonts/Lohit-Gujarati.ttf",
                media_type="font/ttf",
                content=DEFAULT_FONT_PATH.read_bytes(),
                in_spine=False,
            )
        ],
    )
    print(f"Parsed prasangs: {len(prasangs)}")
    print(f"Output EPUB: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a native EPUB from the Gujarati Swamiji Diary PDF.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_SOURCE_PDF)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force-ocr", action="store_true", help="Re-run OCR even when cached page text exists.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_book(args.pdf, args.source_dir, args.output, force_ocr=args.force_ocr)


if __name__ == "__main__":
    main()
