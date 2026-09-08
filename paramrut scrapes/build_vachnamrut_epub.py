from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from epub_builder import (
    EpubItem,
    NavPoint,
    build_epub,
    default_styles,
    make_xhtml_document,
    paragraphize,
    section_heading,
)


DEFAULT_SOURCE_DIR = Path("vachnamrut")
DEFAULT_OUTPUT = DEFAULT_SOURCE_DIR / "Vachnamrut.epub"
DEFAULT_COVER = DEFAULT_SOURCE_DIR / "cover.png"

HEADER_LINE_RE = re.compile(r"^=+$")
SEPARATOR_LINE_RE = re.compile(r"^-{5,}$")
ENTRY_HEADING_RE = re.compile(r"^[A-Za-z].+\d+:\s+")
META_LINE_RE = re.compile(r"^(તિથિ|તારીખ|દિવસ):\s+")
SPACE_RE = re.compile(r"\s+")

COVER_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def load_chapters(source_dir: Path) -> list[dict]:
    data = json.loads((source_dir / "index.json").read_text(encoding="utf-8"))
    return data["chapters"]


def parse_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush() -> None:
        if not paragraph_lines:
            return
        paragraph = SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
        if paragraph:
            blocks.append(("p", paragraph))
        paragraph_lines.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if HEADER_LINE_RE.match(line) or SEPARATOR_LINE_RE.match(line):
            continue
        if line.startswith("વચનામૃત - વિભાગ") or line.startswith("VACHNAMRUT - Section"):
            continue
        if META_LINE_RE.match(line):
            continue
        if ENTRY_HEADING_RE.match(line):
            flush()
            blocks.append(("h2", line))
            continue
        paragraph_lines.append(line)

    flush()
    return blocks


def blocks_to_html(blocks: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    pending_paragraphs: list[str] = []

    def flush_paragraphs() -> None:
        if pending_paragraphs:
            lines.append(paragraphize(pending_paragraphs))
            pending_paragraphs.clear()

    for kind, text in blocks:
        if kind == "h2":
            flush_paragraphs()
            lines.append(section_heading(2, text))
        else:
            pending_paragraphs.append(text)

    flush_paragraphs()
    return "\n".join(lines)


def build_chapter_xhtml(chapter: dict, blocks: list[tuple[str, str]]) -> str:
    body = "\n".join(
        [
            '    <section class="chapter-start">',
            section_heading(1, f"વિભાગ {chapter['number']}: {chapter['title_gujarati']}"),
            f'    <p class="subtitle">{html.escape(str(chapter["entry_count"]))} વચનામૃતો</p>',
            "    </section>",
            blocks_to_html(blocks),
        ]
    )
    return make_xhtml_document(chapter["title_gujarati"], body, language="gu")


def build_cover_xhtml(cover_href: str) -> str:
    body = "\n".join(
        [
            '    <section class="cover-page" epub:type="cover">',
            f'      <img src="{html.escape(cover_href)}" alt="વચનામૃત" />',
            "    </section>",
        ]
    )
    return make_xhtml_document("વચનામૃત", body, language="gu")


def custom_styles() -> str:
    return (
        default_styles()
        + """

.cover-page {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: 96vh;
  margin: 0;
  padding: 0;
  page-break-after: always;
}

.cover-page img {
  display: block;
  height: auto;
  max-height: 100vh;
  max-width: 100%;
  object-fit: contain;
}
"""
    )


def cover_items(cover: Path | None) -> list[EpubItem]:
    if cover is None:
        return []
    suffix = cover.suffix.lower()
    if suffix not in COVER_MEDIA_TYPES:
        raise ValueError(f"Unsupported cover image type: {cover.suffix}")
    if not cover.exists():
        raise FileNotFoundError(f"Cover image not found: {cover}")

    image_href = f"images/cover{suffix}"
    return [
        EpubItem(
            id="cover_image",
            href=image_href,
            media_type=COVER_MEDIA_TYPES[suffix],
            content=cover.read_bytes(),
            in_spine=False,
            properties=("cover-image",),
        ),
        EpubItem(
            id="cover",
            href="text/cover.xhtml",
            media_type="application/xhtml+xml",
            content=build_cover_xhtml(f"../{image_href}"),
        ),
    ]


def build_book(source_dir: Path, output: Path, cover: Path | None = None) -> None:
    chapters = load_chapters(source_dir)
    items: list[EpubItem] = cover_items(cover)
    nav_points: list[NavPoint] = []

    for chapter in chapters:
        href = f"text/chapter_{chapter['number']:03}.xhtml"
        title = f"વિભાગ {chapter['number']}: {chapter['title_gujarati']}"
        blocks = parse_blocks((source_dir / chapter["file"]).read_text(encoding="utf-8"))
        items.append(
            EpubItem(
                id=f"chapter_{chapter['number']:03}",
                href=href,
                media_type="application/xhtml+xml",
                content=build_chapter_xhtml(chapter, blocks),
            )
        )
        nav_points.append(NavPoint(label=title, href=href))

    build_epub(
        output,
        title="વચનામૃત",
        identifier_seed=str(output.resolve()),
        creators=["OpenAI Codex"],
        language="gu",
        items=items,
        nav_points=nav_points,
        styles_css=custom_styles(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a native EPUB from the Vachnamrut text files.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--cover",
        type=Path,
        default=None,
        help="Optional cover image path. Defaults to vachnamrut/cover.png when present.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cover = args.cover
    if cover is None and DEFAULT_COVER.exists():
        cover = DEFAULT_COVER
    build_book(args.source_dir, args.output, cover)
    print(f"Output EPUB: {args.output}")


if __name__ == "__main__":
    main()
