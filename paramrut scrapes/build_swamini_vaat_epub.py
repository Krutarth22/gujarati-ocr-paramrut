from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from epub_builder import EpubItem, NavPoint, build_epub, make_xhtml_document, paragraphize, section_heading


DEFAULT_SOURCE_DIR = Path("swamini_vaat")
DEFAULT_OUTPUT = DEFAULT_SOURCE_DIR / "Swamini_Vaat.epub"

HEADER_LINE_RE = re.compile(r"^=+$")
ENTRY_HEADING_RE = re.compile(r"^વાત\s+\d+\s*:")
SEPARATOR_LINE_RE = re.compile(r"^-{5,}$")
SPACE_RE = re.compile(r"\s+")


def load_chapters(source_dir: Path) -> list[dict]:
    data = json.loads((source_dir / "index.json").read_text(encoding="utf-8"))
    return data["chapters"]


def parse_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    paragraph_lines: list[str] = []

    def flush() -> None:
        if not paragraph_lines:
            return
        paragraph = SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
        if paragraph:
            paragraphs.append(paragraph)
        paragraph_lines.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if HEADER_LINE_RE.match(line):
            continue
        if line.startswith("સ્વામીની વાત - પ્રકરણ"):
            continue
        if line.startswith("SWAMINI VAAT - Chapter"):
            continue
        if SEPARATOR_LINE_RE.match(line):
            continue
        if ENTRY_HEADING_RE.match(line):
            flush()
            continue
        paragraph_lines.append(line)

    flush()
    return paragraphs


def build_chapter_xhtml(chapter: dict, paragraphs: list[str]) -> str:
    body = "\n".join(
        [
            '    <section class="chapter-start">',
            section_heading(1, f"પ્રકરણ {chapter['number']}: {chapter['title_gujarati']}"),
            f'    <p class="subtitle">{html.escape(str(chapter["entry_count"]))} વાતો</p>',
            "    </section>",
            paragraphize(paragraphs),
        ]
    )
    return make_xhtml_document(chapter["title_gujarati"], body, language="gu")


def build_book(source_dir: Path, output: Path) -> None:
    chapters = load_chapters(source_dir)
    items: list[EpubItem] = []
    nav_points: list[NavPoint] = []

    for chapter in chapters:
        href = f"text/chapter_{chapter['number']:03}.xhtml"
        title = f"પ્રકરણ {chapter['number']}: {chapter['title_gujarati']}"
        paragraphs = parse_paragraphs((source_dir / chapter["file"]).read_text(encoding="utf-8"))
        items.append(
            EpubItem(
                id=f"chapter_{chapter['number']:03}",
                href=href,
                media_type="application/xhtml+xml",
                content=build_chapter_xhtml(chapter, paragraphs),
            )
        )
        nav_points.append(NavPoint(label=title, href=href))

    build_epub(
        output,
        title="સ્વામીની વાત",
        identifier_seed=str(output.resolve()),
        creators=["OpenAI Codex"],
        language="gu",
        items=items,
        nav_points=nav_points,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a native EPUB from the Swamini Vaat text files.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_book(args.source_dir, args.output)
    print(f"Output EPUB: {args.output}")


if __name__ == "__main__":
    main()
