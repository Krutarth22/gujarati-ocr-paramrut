#!/usr/bin/env python3
"""Repair chapter headings and OCR hard line breaks in the Avirat EPUB."""

from __future__ import annotations

import argparse
import re
import tempfile
import zipfile
from pathlib import Path


CHAPTER_PATH = "EPUB/text/ch001.xhtml"
CSS_PATH = "EPUB/styles/stylesheet1.css"

CHAPTER_RE = re.compile(
    r'<p id="(?P<id>page-\d+)" class="chapter-start" '
    r'epub:type="pagebreak" title="(?P<page>\d+)">(?P<body>.*?)</p>',
    re.DOTALL,
)
BREAK_RE = re.compile(r"\s*<br\s*/>\s*")
DATE_RE = re.compile(r"^તા\s*[.:]?\s*[૦-૯0-9]{2}-[૦-૯0-9]{2}-[૦-૯0-9]{4}\s*[,]?$", re.I)
SEPARATOR_RE = re.compile(r"^[-–—]$")
SENTENCE_END_RE = re.compile(r"[.!?।॥…](?:[”’\"']|</em>|</strong>){0,2}\s+")

# This OCR page contains the location but dropped the event name from its heading.
TITLE_OVERRIDES = {
    "page-79": "સંતો અને સાધકોને ગોષ્ઠી, આઇલ ઓફ વ્હાઇટ, નીડલ પોઈન્ટ, યુ.કે.",
}

CHAPTER_CSS = r"""

/* Chapter openings use a distinct Gujarati display treatment. */
.chapter-start {
  display: block;
  break-before: page;
  page-break-before: always;
}
.chapter-title {
  font-family: "Noto Sans Gujarati", "Nirmala UI", Shruti, sans-serif;
  font-size: 1.7em;
  font-weight: 700;
  line-height: 1.3;
  margin: 2.25em 0 0.25em;
  text-align: center;
  text-indent: 0;
  break-after: avoid;
  page-break-after: avoid;
}
.chapter-date {
  font-family: "Noto Sans Gujarati", "Nirmala UI", Shruti, sans-serif;
  font-size: 1em;
  font-weight: 600;
  margin: 0 0 1.5em;
  text-align: center;
  text-indent: 0;
  break-after: avoid;
  page-break-after: avoid;
}
"""


def join_source_lines(parts: list[str]) -> str:
    """Join OCR lines, retaining markup and closing line-end hyphens."""
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not result:
            result = part
        elif re.search(r"[-‐‑‒–—]\s*$", result):
            result += part
        else:
            result += " " + part
    return result


def visible_length(fragment: str) -> int:
    return len(re.sub(r"<[^>]+>", "", fragment))


def paragraphize(fragment: str, target_length: int = 460, minimum_tail: int = 150) -> str:
    """Group complete sentences into readable paragraphs without losing inline markup."""
    fragment = fragment.strip()
    if visible_length(fragment) <= target_length:
        return fragment

    boundaries = [match.end() for match in SENTENCE_END_RE.finditer(fragment)]
    if not boundaries:
        return fragment

    chunks: list[str] = []
    start = 0
    for boundary in boundaries:
        if visible_length(fragment[start:boundary]) >= target_length:
            chunks.append(fragment[start:boundary].strip())
            start = boundary

    tail = fragment[start:].strip()
    if tail:
        if chunks and visible_length(tail) < minimum_tail:
            chunks[-1] = chunks[-1] + " " + tail
        else:
            chunks.append(tail)

    return "</p>\n<p>".join(chunks) if chunks else fragment


def rewrite_chapter(match: re.Match[str], titles: list[tuple[str, str]]) -> str:
    lines = BREAK_RE.split(match.group("body"))
    if len(lines) < 3:
        raise ValueError(f"Chapter at {match.group('id')} has fewer than three lines")

    header_limit = min(4, len(lines))
    date_index = next(
        (index for index, line in enumerate(lines[:header_limit]) if DATE_RE.match(line.strip())),
        None,
    )
    if date_index is None:
        raise ValueError(f"No chapter date found near {match.group('id')}")

    title_index = next(
        (
            index
            for index, line in enumerate(lines[:header_limit])
            if index != date_index and line.strip() and not SEPARATOR_RE.match(line.strip())
        ),
        None,
    )
    if title_index is None:
        raise ValueError(f"No chapter title found near {match.group('id')}")

    chapter_id = match.group("id")
    title = TITLE_OVERRIDES.get(chapter_id, lines[title_index].strip())
    date = lines[date_index].strip()
    body_start = max(title_index, date_index) + 1
    while body_start < len(lines) and SEPARATOR_RE.match(lines[body_start].strip()):
        body_start += 1
    body = join_source_lines(lines[body_start:])
    titles.append((chapter_id, title))

    return (
        f'<span id="{match.group("id")}" class="chapter-start" '
        f'epub:type="pagebreak" title="{match.group("page")}"></span>\n'
        f'<h2 class="chapter-title">{title}</h2>\n'
        f'<p class="chapter-date">{date}</p>\n'
        f'<p>{body}</p>'
    )


def repair_xhtml(xhtml: str) -> tuple[str, list[tuple[str, str]], int, int]:
    titles: list[tuple[str, str]] = []
    rewritten = CHAPTER_RE.sub(lambda match: rewrite_chapter(match, titles), xhtml)
    first_chapter = rewritten.find('<span id="page-5" class="chapter-start"')
    if first_chapter < 0:
        raise ValueError("Could not locate the first repaired chapter")
    front_matter = rewritten[:first_chapter]
    chapter_text = rewritten[first_chapter:]
    break_count = len(re.findall(r"<br\s*/>", chapter_text))

    # Remaining chapter breaks are PDF line endings on ordinary and continuation pages.
    # The five intentional display lines in the reproduced front matter are preserved.
    chapter_text = re.sub(r"([-‐‑‒–—])\s*<br\s*/>\s*", r"\1", chapter_text)
    chapter_text = re.sub(r"\s*<br\s*/>\s*", " ", chapter_text)

    # Source-page boundaries should remain navigable but must not create a
    # visible paragraph break in the middle of a sentence.
    chapter_text = re.sub(
        r"</p>\s*(<span id=\"page-\d+\" epub:type=\"pagebreak\" title=\"\d+\"></span>)\s*<p>",
        r" \1",
        chapter_text,
    )

    # The OCR supplied physical lines rather than logical paragraphs. Once the
    # lines and pages are reflowed, group complete sentences into readable blocks.
    chapter_text = re.sub(
        r"<p>(.*?)</p>",
        lambda match: "<p>" + paragraphize(match.group(1)) + "</p>",
        chapter_text,
        flags=re.DOTALL,
    )
    paragraph_count = chapter_text.count("<p>")
    rewritten = front_matter + chapter_text
    return rewritten, titles, break_count, paragraph_count


def repair_css(css: str) -> str:
    # Remove the old duplicate chapter rule before installing the complete rule.
    css = re.sub(
        r"\n/\* Begin every indexed section.*?\n\.chapter-start\s*\{.*?\}\s*",
        "\n",
        css,
        flags=re.DOTALL,
    )
    return css.rstrip() + CHAPTER_CSS + "\n"


def write_repaired_epub(source: Path, destination: Path) -> tuple[list[tuple[str, str]], int, int]:
    with zipfile.ZipFile(source, "r") as src:
        names = src.namelist()
        if not names or names[0] != "mimetype":
            raise ValueError("Invalid EPUB: mimetype is not the first archive entry")
        if CHAPTER_PATH not in names or CSS_PATH not in names:
            raise ValueError("Expected chapter or stylesheet is missing from EPUB")

        xhtml = src.read(CHAPTER_PATH).decode("utf-8")
        css = src.read(CSS_PATH).decode("utf-8")
        repaired_xhtml, titles, remaining_breaks, paragraph_count = repair_xhtml(xhtml)
        repaired_css = repair_css(css)

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=destination.stem + ".", suffix=".tmp", dir=destination.parent, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            with zipfile.ZipFile(temp_path, "w") as dst:
                for name in names:
                    info = src.getinfo(name)
                    data = src.read(name)
                    if name == CHAPTER_PATH:
                        data = repaired_xhtml.encode("utf-8")
                    elif name == CSS_PATH:
                        data = repaired_css.encode("utf-8")

                    copied_info = zipfile.ZipInfo(name, date_time=info.date_time)
                    copied_info.comment = info.comment
                    copied_info.extra = info.extra
                    copied_info.internal_attr = info.internal_attr
                    copied_info.external_attr = info.external_attr
                    copied_info.create_system = info.create_system
                    copied_info.compress_type = (
                        zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
                    )
                    dst.writestr(copied_info, data)
            temp_path.replace(destination)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    return titles, remaining_breaks, paragraph_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    titles, remaining_breaks, paragraph_count = write_repaired_epub(args.source, args.destination)
    print(f"Wrote {args.destination}")
    print(f"Converted {len(titles)} chapter openings to styled headings")
    print(f"Removed {remaining_breaks} remaining OCR hard line breaks")
    print(f"Created {paragraph_count} readable body paragraphs")
    for chapter_id, title in titles:
        print(f"  {chapter_id}: {title}")


if __name__ == "__main__":
    main()
