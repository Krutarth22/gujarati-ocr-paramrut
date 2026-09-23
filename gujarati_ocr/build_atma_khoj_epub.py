from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARAMRUT_TOOLS = PROJECT_ROOT / "paramrut scrapes"
sys.path.insert(0, str(PARAMRUT_TOOLS))

from epub_builder import EpubItem, NavPoint, build_epub, make_xhtml_document  # noqa: E402


DEFAULT_SOURCE = Path("outputs/atma_koch_full/Atma_Koch_Shibir_2000_ocr.txt")
DEFAULT_OUTPUT = Path("outputs/atma_koch_full/Atma_Khoj_Shibir_2000.epub")

PAGE_MARKER_RE = re.compile(r"^\[Page (\d+)\]$")
GUJARATI_PAGE_NUMBER_RE = re.compile(r"^[૦-૯]{1,3}[.।]?$")
LATIN_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}[.]?$")
ORNAMENT_RE = re.compile(r"^[\s=*_.—–-]+$")
SPACE_RE = re.compile(r"\s+")
LIST_ITEM_RE = re.compile(r"^(?:[૦-૯0-9]+[.)]|[→•])\s*")


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    date: str
    start_page: int
    end_page: int
    header_variants: tuple[str, ...]
    note: str = ""


CHAPTERS = (
    Chapter(1, "સંબંધયોગ", "૭ ઑક્ટોબર ૨૦૦૦", 2, 16, ("સંબંધયોગ",)),
    Chapter(2, "ધ્યેયનિષ્ઠા", "૭ ઑક્ટોબર ૨૦૦૦", 17, 28, ("ધ્યેયનિષ્ઠા",)),
    Chapter(
        3,
        "માન ટળે ભાવે સેવા…",
        "૮ ઑક્ટોબર ૨૦૦૦",
        29,
        49,
        ("‘માન ટળે ભાવે સેવા...’", "‘માન ટળે ભાવે સેવા..'", "‘માન ટળે ભાવે સેવા…’"),
    ),
    Chapter(
        4,
        "વચનામૃત ગઢડા પ્રથમ-૩૨",
        "૯ ઑક્ટોબર ૨૦૦૦",
        50,
        66,
        ("વચનામૃત ગઢડા પ્રથમ-૩૨", "વચનામૃત ગઢડા પ્રથમ-૩૨: નિરૂપણ"),
    ),
    Chapter(5, "ગુણના પ્રવાહ", "૧૦ ઑક્ટોબર ૨૦૦૦", 67, 86, ("ગુણના પ્રવાહ",)),
    Chapter(6, "રસાસ્વાદ", "૧૧ ઑક્ટોબર ૨૦૦૦", 87, 119, ("રસાસ્વાદ", "રસસ્વાદ",)),
    Chapter(
        7,
        "નિત્ય લાખ રૂપિયા લાવે…",
        "૧૩ ઑક્ટોબર ૨૦૦૦",
        120,
        132,
        ("‘નિત્ય લાખ રૂપિયા લાવે...’", "‘નિત્ય લાખ રૂપિયા લાવે…’", "‘નિત્ય લાખ રૂપિયા લાવે’"),
        "શરદ પૂર્ણિમા",
    ),
)


BOOK_CSS = """html, body {
  margin: 0;
  padding: 0;
}

body {
  font-family: serif;
  line-height: 1.65;
  padding: 0 4%;
  text-align: left;
  widows: 2;
  orphans: 2;
}

h1, h2 {
  break-after: avoid;
  page-break-after: avoid;
  text-align: center;
}

h1 {
  font-size: 1.55em;
  margin: 0 0 0.65em;
}

h2 {
  font-size: 1.2em;
  margin: 1.4em 0 0.7em;
}

.title-page, .chapter-start {
  break-before: page;
  page-break-before: always;
  padding-top: 18vh;
  text-align: center;
}

.book-title {
  font-size: 1.8em;
}

.subtitle, .meta {
  color: #444;
  text-align: center;
}

.para {
  margin: 0 0 0.9em;
  text-indent: 1.4em;
}

.contents ol {
  list-style: none;
  padding-left: 0;
}

.contents li {
  border-bottom: 1px solid #ddd;
  margin: 0.55em 0;
  padding-bottom: 0.45em;
}

.contents a {
  color: inherit;
  text-decoration: none;
}

.chapter-date {
  color: #555;
  margin: 0.2em 0;
  text-align: center;
}

.pagebreak {
  display: block;
  height: 0;
  margin: 0;
}
"""


def split_pages(text: str) -> dict[int, list[str]]:
    pages: dict[int, list[str]] = {}
    page_number: int | None = None
    for raw_line in text.splitlines():
        marker = PAGE_MARKER_RE.fullmatch(raw_line.strip())
        if marker:
            page_number = int(marker.group(1))
            if page_number in pages:
                raise ValueError(f"Duplicate OCR page marker: {page_number}")
            pages[page_number] = []
        elif page_number is not None:
            pages[page_number].append(raw_line)
    expected = set(range(1, 133))
    if set(pages) != expected:
        missing = sorted(expected - set(pages))
        extra = sorted(set(pages) - expected)
        raise ValueError(f"Unexpected OCR pages; missing={missing}, extra={extra}")
    return pages


def normalized_header(line: str) -> str:
    return re.sub(r"[^\w\u0A80-\u0AFF]+", "", line).casefold()


def is_running_header(line: str, chapter: Chapter) -> bool:
    candidate = normalized_header(line)
    return any(candidate == normalized_header(header) for header in chapter.header_variants)


def clean_page_lines(lines: list[str], chapter: Chapter) -> list[str]:
    cleaned: list[str] = []
    for index, raw_line in enumerate(lines):
        line = SPACE_RE.sub(" ", raw_line).strip()
        if not line:
            cleaned.append("")
            continue
        if is_running_header(line, chapter):
            continue
        if index < 8 and (GUJARATI_PAGE_NUMBER_RE.fullmatch(line) or LATIN_PAGE_NUMBER_RE.fullmatch(line)):
            continue
        if index < 8 and (
            line in {"સ્વામીશ્રીજી", "અંબરીષ હૉલ.", "અંબરિય હોલ"}
            or line.startswith("તા.")
        ):
            continue
        if ORNAMENT_RE.fullmatch(line):
            cleaned.append("")
            continue
        cleaned.append(line)
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return cleaned


def lines_to_paragraphs(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            paragraphs.append(SPACE_RE.sub(" ", " ".join(current)).strip())
            current.clear()

    for line in lines:
        if not line:
            flush()
            continue
        if LIST_ITEM_RE.match(line):
            flush()
            paragraphs.append(line)
            continue
        current.append(line)
        if line.endswith((".", "!", "?", "।", ":", "…", "...", "!’", "?’", ".’", "!”", "?”")):
            flush()
    flush()
    return [paragraph for paragraph in paragraphs if paragraph]


def xhtml_document(title: str, body: str) -> str:
    document = make_xhtml_document(title, body, language="gu")
    return document.replace('href="styles/book.css"', 'href="../styles/book.css"')


def build_title_page() -> str:
    body = "\n".join(
        [
            '    <section class="title-page" epub:type="titlepage">',
            '      <h1 class="book-title">આત્મખોજ શિબિર</h1>',
            '      <p class="subtitle">૨૦૦૦</p>',
            '      <p class="meta">સ્વામીશ્રીજી</p>',
            "    </section>",
        ]
    )
    return xhtml_document("આત્મખોજ શિબિર", body)


def build_contents_page() -> str:
    entries = []
    for chapter in CHAPTERS:
        note = f" — {html.escape(chapter.note)}" if chapter.note else ""
        entries.append(
            f'        <li><a href="chapter_{chapter.number:02}.xhtml">'
            f'{chapter.number}. {html.escape(chapter.title)}</a>'
            f'<br /><span class="meta">{html.escape(chapter.date)}{note}</span></li>'
        )
    body = "\n".join(
        [
            '    <section class="contents" epub:type="toc">',
            "      <h1>અનુક્રમણિકા</h1>",
            "      <ol>",
            *entries,
            "      </ol>",
            "    </section>",
        ]
    )
    return xhtml_document("અનુક્રમણિકા", body)


def build_chapter_page(chapter: Chapter, pages: dict[int, list[str]]) -> str:
    parts = [
        '    <section class="chapter-start">',
        f"      <h1>{chapter.number}. {html.escape(chapter.title)}</h1>",
        f'      <p class="chapter-date">{html.escape(chapter.date)}</p>',
    ]
    if chapter.note:
        parts.append(f'      <p class="chapter-date">{html.escape(chapter.note)}</p>')
    parts.append("    </section>")

    for page_number in range(chapter.start_page, chapter.end_page + 1):
        parts.append(
            f'    <span class="pagebreak" epub:type="pagebreak" id="page-{page_number}" '
            f'title="{page_number}" aria-label="Page {page_number}"></span>'
        )
        for paragraph in lines_to_paragraphs(clean_page_lines(pages[page_number], chapter)):
            parts.append(f'    <p class="para">{html.escape(paragraph)}</p>')
    return xhtml_document(chapter.title, "\n".join(parts))


def build_book(source: Path, output: Path) -> None:
    pages = split_pages(source.read_text(encoding="utf-8"))
    items = [
        EpubItem("title_page", "text/title_page.xhtml", "application/xhtml+xml", build_title_page()),
        EpubItem("contents", "text/contents.xhtml", "application/xhtml+xml", build_contents_page()),
    ]
    nav_points = [NavPoint("અનુક્રમણિકા", "text/contents.xhtml")]

    for chapter in CHAPTERS:
        href = f"text/chapter_{chapter.number:02}.xhtml"
        items.append(
            EpubItem(
                id=f"chapter_{chapter.number:02}",
                href=href,
                media_type="application/xhtml+xml",
                content=build_chapter_page(chapter, pages),
            )
        )
        nav_points.append(NavPoint(f"{chapter.number}. {chapter.title}", href))

    build_epub(
        output,
        title="આત્મખોજ શિબિર ૨૦૦૦",
        identifier_seed="urn:atma-khoj-shibir:2000",
        creators=["સ્વામીશ્રીજી"],
        language="gu",
        items=items,
        nav_points=nav_points,
        styles_css=BOOK_CSS,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a structured EPUB from the Aatma Khoj OCR text.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_book(args.source, args.output)
    print(f"Output EPUB: {args.output}")


if __name__ == "__main__":
    main()
