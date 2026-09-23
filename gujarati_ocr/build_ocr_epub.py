from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARAMRUT_TOOLS = PROJECT_ROOT / "paramrut scrapes"
sys.path.insert(0, str(PARAMRUT_TOOLS))

from epub_builder import EpubItem, NavPoint, build_epub, make_xhtml_document  # noqa: E402


DEFAULT_PAGE_MARKER = r"^\[Page (?P<page>\d+)\]$"
GUJARATI_PAGE_NUMBER_RE = re.compile(r"^[૦-૯]{1,4}[.।]?$")
LATIN_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}[.]?$")
ORNAMENT_RE = re.compile(r"^[\s=*_.—–-]+$")
SPACE_RE = re.compile(r"\s+")
LIST_ITEM_RE = re.compile(r"^(?:[૦-૯0-9]+[.)]|[→•])\s*")


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    start_page: int
    end_page: int
    date: str = ""
    note: str = ""
    headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BookConfig:
    title: str
    display_title: str
    subtitle: str
    authors: tuple[str, ...]
    language: str
    identifier: str
    contents_title: str
    page_marker_regex: str
    running_headers: tuple[str, ...]
    running_header_prefixes: tuple[str, ...]
    header_scan_lines: int
    chapters: tuple[Chapter, ...]


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

.title-page, .chapter-start {
  break-before: page;
  page-break-before: always;
  padding-top: 18vh;
  text-align: center;
}

.book-title {
  font-size: 1.8em;
}

.subtitle, .meta, .chapter-meta {
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

.chapter-meta {
  margin: 0.2em 0;
}

.pagebreak {
  display: block;
  height: 0;
  margin: 0;
}
"""


def parse_chapter_argument(value: str, number: int) -> Chapter:
    parts = value.split("|", 3)
    if len(parts) < 2:
        raise argparse.ArgumentTypeError(
            "chapter must be START-END|TITLE, optionally followed by |DATE|NOTE"
        )
    page_range, title = parts[0].strip(), parts[1].strip()
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", page_range)
    if not match or not title:
        raise argparse.ArgumentTypeError(
            "chapter must use START-END|TITLE, for example 2-16|સંબંધયોગ"
        )
    date = parts[2].strip() if len(parts) >= 3 else ""
    note = parts[3].strip() if len(parts) >= 4 else ""
    return Chapter(
        number=number,
        title=title,
        start_page=int(match.group(1)),
        end_page=int(match.group(2)),
        date=date,
        note=note,
        headers=(title,),
    )


def parse_numbered_value(value: str, option: str) -> tuple[int, str]:
    number, separator, text = value.partition("=")
    if not separator or not number.isdigit() or not text.strip():
        raise argparse.ArgumentTypeError(f"{option} must use CHAPTER_NUMBER=TEXT")
    return int(number), text.strip()


def load_json_config(path: Path | None) -> dict:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("The EPUB config must be a JSON object")
    return data


def chapters_from_json(raw_chapters: object) -> list[Chapter]:
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raise ValueError("Config must contain a non-empty 'chapters' array")
    chapters: list[Chapter] = []
    for index, raw in enumerate(raw_chapters, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Chapter {index} must be a JSON object")
        title = str(raw.get("title", "")).strip()
        if not title:
            raise ValueError(f"Chapter {index} is missing a title")
        headers = raw.get("headers", [title])
        if not isinstance(headers, list):
            raise ValueError(f"Chapter {index} 'headers' must be an array")
        chapters.append(
            Chapter(
                number=index,
                title=title,
                start_page=int(raw["start_page"]),
                end_page=int(raw["end_page"]),
                date=str(raw.get("date", "")).strip(),
                note=str(raw.get("note", "")).strip(),
                headers=tuple(str(header) for header in headers if str(header).strip()),
            )
        )
    return chapters


def apply_chapter_metadata(
    chapters: list[Chapter],
    header_arguments: list[str] | None,
    date_arguments: list[str] | None,
    note_arguments: list[str] | None,
) -> list[Chapter]:
    headers_by_chapter: dict[int, list[str]] = {}
    dates: dict[int, str] = {}
    notes: dict[int, str] = {}
    for value in header_arguments or []:
        number, text = parse_numbered_value(value, "--chapter-header")
        headers_by_chapter.setdefault(number, []).append(text)
    for value in date_arguments or []:
        number, text = parse_numbered_value(value, "--chapter-date")
        dates[number] = text
    for value in note_arguments or []:
        number, text = parse_numbered_value(value, "--chapter-note")
        notes[number] = text

    known_numbers = {chapter.number for chapter in chapters}
    referenced_numbers = set(headers_by_chapter) | set(dates) | set(notes)
    unknown = sorted(referenced_numbers - known_numbers)
    if unknown:
        raise ValueError(f"Chapter metadata references unknown chapters: {unknown}")

    result = []
    for chapter in chapters:
        extra_headers = headers_by_chapter.get(chapter.number, [])
        result.append(
            Chapter(
                number=chapter.number,
                title=chapter.title,
                start_page=chapter.start_page,
                end_page=chapter.end_page,
                date=dates.get(chapter.number, chapter.date),
                note=notes.get(chapter.number, chapter.note),
                headers=tuple(dict.fromkeys((*chapter.headers, *extra_headers, chapter.title))),
            )
        )
    return result


def resolve_config(args: argparse.Namespace) -> tuple[Path, Path, BookConfig]:
    raw = load_json_config(args.config)
    source_value = args.source or raw.get("source")
    output_value = args.output or raw.get("output")
    title = args.title or raw.get("title")
    if not source_value or not output_value or not title:
        raise ValueError("source, output, and title are required through arguments or --config")

    if args.chapter:
        chapters = [parse_chapter_argument(value, index) for index, value in enumerate(args.chapter, start=1)]
    else:
        chapters = chapters_from_json(raw.get("chapters"))
    chapters = apply_chapter_metadata(
        chapters,
        args.chapter_header,
        args.chapter_date,
        args.chapter_note,
    )

    raw_authors = raw.get("authors") or ([raw["author"]] if raw.get("author") else [])
    authors = tuple(args.author or raw_authors)
    if not authors:
        raise ValueError("At least one author is required through --author or --config")

    config = BookConfig(
        title=str(title),
        display_title=str(args.display_title or raw.get("display_title") or title),
        subtitle=str(args.subtitle if args.subtitle is not None else raw.get("subtitle", "")),
        authors=tuple(str(author) for author in authors),
        language=str(args.language or raw.get("language", "gu")),
        identifier=str(args.identifier or raw.get("identifier") or Path(output_value).resolve()),
        contents_title=str(args.contents_title or raw.get("contents_title", "Contents")),
        page_marker_regex=str(args.page_marker_regex or raw.get("page_marker_regex", DEFAULT_PAGE_MARKER)),
        running_headers=tuple(args.running_header or raw.get("running_headers", [])),
        running_header_prefixes=tuple(
            args.running_header_prefix or raw.get("running_header_prefixes", [])
        ),
        header_scan_lines=int(args.header_scan_lines or raw.get("header_scan_lines", 8)),
        chapters=tuple(chapters),
    )
    validate_chapters(config.chapters)
    return Path(source_value), Path(output_value), config


def validate_chapters(chapters: tuple[Chapter, ...]) -> None:
    covered: set[int] = set()
    for chapter in chapters:
        if chapter.start_page < 1 or chapter.end_page < chapter.start_page:
            raise ValueError(f"Invalid page range for chapter {chapter.number}: {chapter.start_page}-{chapter.end_page}")
        chapter_pages = set(range(chapter.start_page, chapter.end_page + 1))
        overlap = sorted(covered & chapter_pages)
        if overlap:
            raise ValueError(f"Overlapping chapter pages: {overlap}")
        covered.update(chapter_pages)


def split_pages(text: str, marker_pattern: str) -> dict[int, list[str]]:
    marker_re = re.compile(marker_pattern)
    if marker_re.groups < 1:
        raise ValueError("Page marker regex must contain a capture group or a named 'page' group")
    pages: dict[int, list[str]] = {}
    page_number: int | None = None
    for raw_line in text.splitlines():
        marker = marker_re.fullmatch(raw_line.strip())
        if marker:
            captured = marker.groupdict().get("page") or marker.group(1)
            page_number = int(captured)
            if page_number in pages:
                raise ValueError(f"Duplicate OCR page marker: {page_number}")
            pages[page_number] = []
        elif page_number is not None:
            pages[page_number].append(raw_line)
    if not pages:
        raise ValueError("No page markers matched the source text")
    return pages


def normalized_header(line: str) -> str:
    return re.sub(r"[^\w\u0A80-\u0AFF]+", "", line).casefold()


def is_header(line: str, headers: tuple[str, ...]) -> bool:
    candidate = normalized_header(line)
    return any(candidate == normalized_header(header) for header in headers)


def clean_page_lines(lines: list[str], chapter: Chapter, config: BookConfig) -> list[str]:
    cleaned: list[str] = []
    all_headers = tuple(dict.fromkeys((*chapter.headers, chapter.title, *config.running_headers)))
    for index, raw_line in enumerate(lines):
        line = SPACE_RE.sub(" ", raw_line).strip()
        if not line:
            cleaned.append("")
            continue
        in_header_area = index < config.header_scan_lines
        if in_header_area and is_header(line, all_headers):
            continue
        if in_header_area and (
            GUJARATI_PAGE_NUMBER_RE.fullmatch(line) or LATIN_PAGE_NUMBER_RE.fullmatch(line)
        ):
            continue
        if in_header_area and any(line.startswith(prefix) for prefix in config.running_header_prefixes):
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


def xhtml_document(title: str, body: str, language: str) -> str:
    document = make_xhtml_document(title, body, language=language)
    return document.replace('href="styles/book.css"', 'href="../styles/book.css"')


def build_title_page(config: BookConfig) -> str:
    parts = [
        '    <section class="title-page" epub:type="titlepage">',
        f'      <h1 class="book-title">{html.escape(config.display_title)}</h1>',
    ]
    if config.subtitle:
        parts.append(f'      <p class="subtitle">{html.escape(config.subtitle)}</p>')
    for author in config.authors:
        parts.append(f'      <p class="meta">{html.escape(author)}</p>')
    parts.append("    </section>")
    return xhtml_document(config.display_title, "\n".join(parts), config.language)


def build_contents_page(config: BookConfig) -> str:
    entries = []
    for chapter in config.chapters:
        metadata = " — ".join(value for value in (chapter.date, chapter.note) if value)
        metadata_html = (
            f'<br /><span class="meta">{html.escape(metadata)}</span>' if metadata else ""
        )
        entries.append(
            f'        <li><a href="chapter_{chapter.number:03}.xhtml">'
            f'{chapter.number}. {html.escape(chapter.title)}</a>{metadata_html}</li>'
        )
    body = "\n".join(
        [
            '    <section class="contents" epub:type="toc">',
            f"      <h1>{html.escape(config.contents_title)}</h1>",
            "      <ol>",
            *entries,
            "      </ol>",
            "    </section>",
        ]
    )
    return xhtml_document(config.contents_title, body, config.language)


def build_chapter_page(
    chapter: Chapter,
    pages: dict[int, list[str]],
    config: BookConfig,
) -> str:
    parts = [
        '    <section class="chapter-start">',
        f"      <h1>{chapter.number}. {html.escape(chapter.title)}</h1>",
    ]
    for metadata in (chapter.date, chapter.note):
        if metadata:
            parts.append(f'      <p class="chapter-meta">{html.escape(metadata)}</p>')
    parts.append("    </section>")

    for page_number in range(chapter.start_page, chapter.end_page + 1):
        parts.append(
            f'    <span class="pagebreak" epub:type="pagebreak" id="page-{page_number}" '
            f'title="{page_number}" aria-label="Page {page_number}"></span>'
        )
        for paragraph in lines_to_paragraphs(clean_page_lines(pages[page_number], chapter, config)):
            parts.append(f'    <p class="para">{html.escape(paragraph)}</p>')
    return xhtml_document(chapter.title, "\n".join(parts), config.language)


def build_book(source: Path, output: Path, config: BookConfig) -> None:
    pages = split_pages(source.read_text(encoding="utf-8"), config.page_marker_regex)
    required_pages = {
        page
        for chapter in config.chapters
        for page in range(chapter.start_page, chapter.end_page + 1)
    }
    missing = sorted(required_pages - set(pages))
    if missing:
        raise ValueError(f"Chapter definitions reference missing source pages: {missing}")

    items = [
        EpubItem(
            "title_page",
            "text/title_page.xhtml",
            "application/xhtml+xml",
            build_title_page(config),
        ),
        EpubItem(
            "contents",
            "text/contents.xhtml",
            "application/xhtml+xml",
            build_contents_page(config),
        ),
    ]
    nav_points = [NavPoint(config.contents_title, "text/contents.xhtml")]

    for chapter in config.chapters:
        href = f"text/chapter_{chapter.number:03}.xhtml"
        items.append(
            EpubItem(
                id=f"chapter_{chapter.number:03}",
                href=href,
                media_type="application/xhtml+xml",
                content=build_chapter_page(chapter, pages, config),
            )
        )
        nav_points.append(NavPoint(f"{chapter.number}. {chapter.title}", href))

    build_epub(
        output,
        title=config.title,
        identifier_seed=config.identifier,
        creators=list(config.authors),
        language=config.language,
        items=items,
        nav_points=nav_points,
        styles_css=BOOK_CSS,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a structured EPUB from page-marked OCR text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python build_ocr_epub.py --config epub_configs/atma_khoj_2000.json

  python build_ocr_epub.py --source book.txt --output book.epub \\
    --title "Book title" --author "Author" \\
    --chapter "1-10|First chapter" --chapter "11-20|Second chapter"

Chapter syntax: START-END|TITLE[|DATE[|NOTE]]
Use --chapter-header NUMBER=TEXT for alternate running headers.
""",
    )
    parser.add_argument("--config", type=Path, help="JSON file containing book metadata and chapters")
    parser.add_argument("--source", type=Path, help="UTF-8 OCR text containing page markers")
    parser.add_argument("--output", type=Path, help="Output .epub path")
    parser.add_argument("--title", help="EPUB metadata title")
    parser.add_argument("--display-title", help="Title shown on the title page")
    parser.add_argument("--subtitle", help="Subtitle shown on the title page")
    parser.add_argument("--author", action="append", help="Author/creator; repeat for multiple authors")
    parser.add_argument("--language", help="BCP 47 language code, such as gu or en")
    parser.add_argument("--identifier", help="Stable identifier seed for the EPUB UUID")
    parser.add_argument("--contents-title", help="Visible and navigational contents-page title")
    parser.add_argument(
        "--chapter",
        action="append",
        help="Chapter as START-END|TITLE[|DATE[|NOTE]]; repeat in reading order",
    )
    parser.add_argument(
        "--chapter-header",
        action="append",
        help="Alternate running header as CHAPTER_NUMBER=TEXT; repeat as needed",
    )
    parser.add_argument("--chapter-date", action="append", help="Override as CHAPTER_NUMBER=TEXT")
    parser.add_argument("--chapter-note", action="append", help="Override as CHAPTER_NUMBER=TEXT")
    parser.add_argument("--running-header", action="append", help="Book-wide running header to remove")
    parser.add_argument(
        "--running-header-prefix",
        action="append",
        help="Prefix for header-area lines to remove, such as 'Date:'",
    )
    parser.add_argument("--header-scan-lines", type=int, help="Number of lines treated as page headers")
    parser.add_argument(
        "--page-marker-regex",
        help="Regex with a named 'page' group or first capture group",
    )
    return parser.parse_args()


def main() -> None:
    try:
        source, output, config = resolve_config(parse_args())
        build_book(source, output, config)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, re.error) as error:
        raise SystemExit(f"error: {error}") from error
    print(f"Output EPUB: {output}")


if __name__ == "__main__":
    main()
