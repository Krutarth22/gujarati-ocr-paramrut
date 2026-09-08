from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from epub_builder import EpubItem, NavPoint, build_epub, make_xhtml_document, paragraphize, section_heading


DEFAULT_SOURCE_DIR = Path("paravani")
DEFAULT_OUTPUT = DEFAULT_SOURCE_DIR / "Paravani_Prashad.epub"

HEADER_LINE_RE = re.compile(r"^=+$")
META_LINE_RE = re.compile(r"^(Date|Title|Place|Info)\s*:")
STAR_LINE_RE = re.compile(r"^[*]{3,5}$")
SPACE_RE = re.compile(r"\s+")


def load_year_groups(source_dir: Path) -> list[tuple[str, list[dict]]]:
    data = json.loads((source_dir / "index.json").read_text(encoding="utf-8"))
    groups: list[tuple[str, list[dict]]] = []
    for year in sorted(data["years"]):
        groups.append((year, data["years"][year]["entries"]))
    return groups


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
        if HEADER_LINE_RE.match(line) or STAR_LINE_RE.match(line):
            continue
        if line == "PARAVANI PRASAD":
            continue
        if META_LINE_RE.match(line):
            continue
        paragraph_lines.append(line)

    flush()
    return paragraphs


def build_entry_xhtml(entry: dict, paragraphs: list[str]) -> str:
    body = "\n".join(
        [
            '    <section class="entry-start">',
            section_heading(1, entry["title"], css_class="entry-title"),
            '    <div class="meta-block">',
            f'      <p class="meta"><strong>Date:</strong> {html.escape(entry["date"])}</p>',
            f'      <p class="meta"><strong>Place:</strong> {html.escape(entry["place"])}</p>',
            "    </div>",
            "    </section>",
            paragraphize(paragraphs),
        ]
    )
    return make_xhtml_document(entry["title"], body, language="gu")


def build_book(source_dir: Path, output: Path) -> None:
    year_groups = load_year_groups(source_dir)
    items: list[EpubItem] = []
    nav_points: list[NavPoint] = []

    for year, entries in year_groups:
        year_children: list[NavPoint] = []
        for index, entry in enumerate(entries, start=1):
            href = f"text/{year}_{index:03}.xhtml"
            title = f"{entry['date']} - {entry['title']}"
            paragraphs = parse_paragraphs((source_dir / entry["file"]).read_text(encoding="utf-8"))
            items.append(
                EpubItem(
                    id=f"{year}_{index:03}",
                    href=href,
                    media_type="application/xhtml+xml",
                    content=build_entry_xhtml(entry, paragraphs),
                )
            )
            year_children.append(NavPoint(label=title, href=href))
        if year_children:
            nav_points.append(NavPoint(label=year, href=year_children[0].href, children=tuple(year_children)))

    build_epub(
        output,
        title="પરાવાણી પ્રસાદ",
        identifier_seed=str(output.resolve()),
        creators=["OpenAI Codex"],
        language="gu",
        items=items,
        nav_points=nav_points,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a native EPUB from the Paravani text files.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_book(args.source_dir, args.output)
    print(f"Output EPUB: {args.output}")


if __name__ == "__main__":
    main()
