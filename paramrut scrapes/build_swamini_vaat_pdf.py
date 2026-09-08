from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


DEFAULT_SOURCE_DIR = Path("swamini_vaat")
DEFAULT_OUTPUT_PDF = DEFAULT_SOURCE_DIR / "Swamini_Vaat_Compiled_Book.pdf"
DEFAULT_KINDLE_OUTPUT_PDF = DEFAULT_SOURCE_DIR / "Swamini_Vaat_Kindle_Scribe.pdf"
TARGET_MIN_PAGES = 1000

FONT_CANDIDATES = [
    (Path("/System/Library/Fonts/KohinoorGujarati.ttc"), 3),
    (Path("/System/Library/Fonts/Supplemental/Gujarati Sangam MN.ttc"), 0),
    (Path("/System/Library/Fonts/Supplemental/GujaratiMT.ttc"), 0),
]

HEADER_LINE_RE = re.compile(r"^=+$")
ENTRY_HEADING_RE = re.compile(r"^વાત\s+\d+\s*:")
SEPARATOR_LINE_RE = re.compile(r"^-{5,}$")
SPACE_RE = re.compile(r"\s+")
GUJARATI_DIGITS = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")


@dataclass(frozen=True)
class ChapterMeta:
    number: int
    title_gujarati: str
    title_english: str
    entry_count: int
    file: str


@dataclass(frozen=True)
class TextBlock:
    style: str
    text: str
    target: str | None = None


@dataclass(frozen=True)
class LayoutPreset:
    name: str
    dpi: int
    page_width_in: float
    page_height_in: float
    margin_left_px: int
    margin_right_px: int
    margin_top_px: int
    margin_bottom_px: int
    body_font_px: int
    body_leading_px: int
    heading_font_px: int
    heading_leading_px: int
    small_font_px: int
    footer_font_px: int
    title_font_px: int
    chapter_font_px: int
    toc_font_px: int
    toc_leading_px: int

    @property
    def page_width_px(self) -> int:
        return int(round(self.page_width_in * self.dpi))

    @property
    def page_height_px(self) -> int:
        return int(round(self.page_height_in * self.dpi))

    @property
    def page_width_pt(self) -> float:
        return self.page_width_in * 72.0

    @property
    def page_height_pt(self) -> float:
        return self.page_height_in * 72.0

    @property
    def body_width_px(self) -> int:
        return self.page_width_px - self.margin_left_px - self.margin_right_px

    @property
    def body_top_px(self) -> int:
        return self.margin_top_px

    @property
    def body_bottom_px(self) -> int:
        return self.page_height_px - self.margin_bottom_px


@dataclass(frozen=True)
class TextStyle:
    font_px: int
    leading_px: int
    fill: tuple[int, int, int]
    align: str = "left"
    space_before_px: int = 0
    space_after_px: int = 0


@dataclass(frozen=True)
class TextElement:
    style_name: str
    lines: tuple[str, ...]
    x: int
    y: int
    max_width_px: int
    target: str | None = None


@dataclass
class Page:
    kind: str
    page_number: int
    chapter: ChapterMeta | None = None
    elements: list[TextElement] = field(default_factory=list)


class FontBook:
    def __init__(self, font_path: Path, font_index: int):
        self.font_path = font_path
        self.font_index = font_index
        self._cache: dict[int, ImageFont.FreeTypeFont] = {}
        self._layout_kwargs = {}
        if hasattr(ImageFont, "Layout") and hasattr(ImageFont.Layout, "RAQM"):
            self._layout_kwargs["layout_engine"] = ImageFont.Layout.RAQM

    def get(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._cache:
            self._cache[size] = ImageFont.truetype(
                str(self.font_path),
                size=size,
                index=self.font_index,
                **self._layout_kwargs,
            )
        return self._cache[size]


class Measurer:
    def __init__(self):
        self._image = Image.new("L", (32, 32), 255)
        self._draw = ImageDraw.Draw(self._image)
        self._cache: dict[tuple[int, str], float] = {}

    def width(self, text: str, font: ImageFont.FreeTypeFont) -> float:
        if not text:
            return 0.0
        key = (font.size, text)
        if key not in self._cache:
            self._cache[key] = self._draw.textlength(text, font=font, language="gu")
        return self._cache[key]

    def wrap(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return []

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if self.width(candidate, font) <= max_width:
                current = candidate
                continue

            if self.width(word, font) > max_width:
                lines.extend(self._break_token(current, font, max_width))
                current = word
                continue

            lines.append(current)
            current = word

        if self.width(current, font) > max_width:
            lines.extend(self._break_token(current, font, max_width))
        else:
            lines.append(current)
        return lines

    def _break_token(self, token: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        pieces: list[str] = []
        current = ""
        for character in token:
            candidate = f"{current}{character}"
            if current and self.width(candidate, font) > max_width:
                pieces.append(current)
                current = character
            else:
                current = candidate
        if current:
            pieces.append(current)
        return pieces


def choose_font_path() -> tuple[Path, int]:
    for candidate, index in FONT_CANDIDATES:
        if candidate.exists():
            return candidate, index
    raise FileNotFoundError("No Gujarati font found in the expected system locations.")


def load_chapters(source_dir: Path) -> list[ChapterMeta]:
    index_path = source_dir / "index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    chapters = data["chapters"]
    return [
        ChapterMeta(
            number=item["number"],
            title_gujarati=item["title_gujarati"].strip(),
            title_english=item["title_english"].strip(),
            entry_count=item["entry_count"],
            file=item["file"],
        )
        for item in chapters
    ]


def to_gujarati_digits(value: int | str) -> str:
    return str(value).translate(GUJARATI_DIGITS)


def parse_chapter_blocks(text: str) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
        if paragraph:
            blocks.append(TextBlock(style="body", text=paragraph))
        paragraph_lines.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
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
            flush_paragraph()
            continue
        paragraph_lines.append(line)

    flush_paragraph()
    return blocks


def build_styles(layout: LayoutPreset) -> dict[str, TextStyle]:
    return {
        "body": TextStyle(
            font_px=layout.body_font_px,
            leading_px=layout.body_leading_px,
            fill=(28, 24, 22),
            space_after_px=14,
        ),
        "toc_heading": TextStyle(
            font_px=layout.chapter_font_px,
            leading_px=layout.chapter_font_px + 12,
            fill=(70, 40, 26),
            align="center",
            space_after_px=28,
        ),
        "toc_line": TextStyle(
            font_px=layout.toc_font_px,
            leading_px=layout.toc_leading_px,
            fill=(28, 24, 22),
            space_after_px=10,
        ),
    }


def layout_text_blocks(
    blocks: Iterable[TextBlock],
    page_kind: str,
    starting_page_number: int,
    layout: LayoutPreset,
    styles: dict[str, TextStyle],
    fonts: FontBook,
    measurer: Measurer,
    chapter: ChapterMeta | None = None,
) -> list[Page]:
    pages: list[Page] = []
    current_page = Page(kind=page_kind, page_number=starting_page_number, chapter=chapter)
    y_cursor = layout.body_top_px

    def finish_page() -> None:
        nonlocal current_page, y_cursor
        pages.append(current_page)
        current_page = Page(
            kind=page_kind,
            page_number=pages[-1].page_number + 1,
            chapter=chapter,
        )
        y_cursor = layout.body_top_px

    for block in blocks:
        style = styles[block.style]
        font = fonts.get(style.font_px)
        wrapped_lines = tuple(measurer.wrap(block.text, font, layout.body_width_px))
        if not wrapped_lines:
            continue

        first_segment = True
        pending_lines = list(wrapped_lines)
        while pending_lines:
            effective_before = style.space_before_px if first_segment else 0
            if y_cursor + effective_before > layout.body_bottom_px:
                finish_page()
                first_segment = False
                continue

            available_height = layout.body_bottom_px - (y_cursor + effective_before)
            fit_line_count = max(1, available_height // style.leading_px)
            segment_lines = tuple(pending_lines[:fit_line_count])
            segment_height = len(segment_lines) * style.leading_px
            is_last_segment = fit_line_count >= len(pending_lines)
            effective_after = style.space_after_px if is_last_segment else 0

            if y_cursor + effective_before + segment_height + effective_after > layout.body_bottom_px and current_page.elements:
                finish_page()
                first_segment = False
                continue

            current_page.elements.append(
                TextElement(
                    style_name=block.style,
                    lines=segment_lines,
                    x=layout.margin_left_px,
                    y=y_cursor + effective_before,
                    max_width_px=layout.body_width_px,
                    target=block.target if len(segment_lines) == len(wrapped_lines) else None,
                )
            )
            y_cursor += effective_before + segment_height + effective_after
            pending_lines = pending_lines[fit_line_count:]
            first_segment = False

            if pending_lines:
                finish_page()

    if current_page.elements:
        pages.append(current_page)
    return pages


def fit_text_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int, measurer: Measurer) -> str:
    if measurer.width(text, font) <= max_width:
        return text
    truncated = text.rstrip()
    ellipsis = "..."
    while truncated and measurer.width(f"{truncated}{ellipsis}", font) > max_width:
        truncated = truncated[:-1].rstrip()
    return f"{truncated}{ellipsis}" if truncated else ellipsis


def make_destination_name(kind: str, identifier: str) -> str:
    safe_identifier = identifier.replace("/", "_").replace(" ", "_")
    return f"{kind}:{safe_identifier}"


def format_toc_line(
    chapter: ChapterMeta,
    page_number: int,
    layout: LayoutPreset,
    fonts: FontBook,
    measurer: Measurer,
) -> str:
    font = fonts.get(layout.toc_font_px)
    page_label = to_gujarati_digits(page_number)
    left_prefix = f"પ્રકરણ {to_gujarati_digits(chapter.number)}  "
    title_text = chapter.title_gujarati
    left_text = f"{left_prefix}{title_text}"
    max_width = layout.body_width_px
    min_gap = "  "

    while True:
        leader = "." * 12
        candidate = f"{left_text}{min_gap}{leader} {page_label}"
        if measurer.width(candidate, font) <= max_width:
            break
        title_text = fit_text_to_width(title_text, font, max_width - measurer.width(f"{left_prefix}{min_gap}{leader} {page_label}", font), measurer)
        left_text = f"{left_prefix}{title_text}"
        break

    leader = "."
    candidate = f"{left_text}{min_gap}{leader} {page_label}"
    while measurer.width(candidate, font) <= max_width:
        leader += "."
        candidate = f"{left_text}{min_gap}{leader} {page_label}"

    leader = leader[:-1] if len(leader) > 1 else "."
    return f"{left_text}{min_gap}{leader} {page_label}"


def build_toc_blocks(
    chapters: list[ChapterMeta],
    chapter_start_pages: dict[int, int],
    layout: LayoutPreset,
    fonts: FontBook,
    measurer: Measurer,
) -> list[TextBlock]:
    blocks = [TextBlock(style="toc_heading", text="વિષય સૂચિ")]
    for chapter in chapters:
        page_number = chapter_start_pages.get(chapter.number, 0)
        line = format_toc_line(chapter, page_number, layout, fonts, measurer)
        blocks.append(
            TextBlock(
                style="toc_line",
                text=line,
                target=make_destination_name("chapter", str(chapter.number)),
            )
        )
    return blocks


def make_title_page(page_number: int) -> Page:
    return Page(kind="title", page_number=page_number)


def make_chapter_page(page_number: int, chapter: ChapterMeta) -> Page:
    return Page(kind="chapter", page_number=page_number, chapter=chapter)


def paginate_chapters(
    chapters: list[ChapterMeta],
    source_dir: Path,
    layout: LayoutPreset,
    styles: dict[str, TextStyle],
    fonts: FontBook,
    measurer: Measurer,
    starting_page_number: int,
) -> tuple[list[Page], dict[int, int]]:
    pages: list[Page] = []
    chapter_start_pages: dict[int, int] = {}
    next_page_number = starting_page_number

    for chapter in chapters:
        chapter_start_pages[chapter.number] = next_page_number
        pages.append(make_chapter_page(next_page_number, chapter))
        next_page_number += 1

        chapter_text = (source_dir / chapter.file).read_text(encoding="utf-8")
        chapter_blocks = parse_chapter_blocks(chapter_text)
        body_pages = layout_text_blocks(
            chapter_blocks,
            page_kind="body",
            starting_page_number=next_page_number,
            layout=layout,
            styles=styles,
            fonts=fonts,
            measurer=measurer,
            chapter=chapter,
        )
        pages.extend(body_pages)
        next_page_number = pages[-1].page_number + 1

    return pages, chapter_start_pages


def paginate_book(
    chapters: list[ChapterMeta],
    source_dir: Path,
    layout: LayoutPreset,
    fonts: FontBook,
    measurer: Measurer,
) -> list[Page]:
    styles = build_styles(layout)
    title_page = make_title_page(1)
    toc_page_count = len(
        layout_text_blocks(
            build_toc_blocks(chapters, {}, layout, fonts, measurer),
            page_kind="toc",
            starting_page_number=2,
            layout=layout,
            styles=styles,
            fonts=fonts,
            measurer=measurer,
        )
    )

    for _ in range(3):
        chapter_pages, chapter_start_pages = paginate_chapters(
            chapters,
            source_dir,
            layout,
            styles,
            fonts,
            measurer,
            starting_page_number=2 + toc_page_count,
        )
        toc_pages = layout_text_blocks(
            build_toc_blocks(chapters, chapter_start_pages, layout, fonts, measurer),
            page_kind="toc",
            starting_page_number=2,
            layout=layout,
            styles=styles,
            fonts=fonts,
            measurer=measurer,
        )
        if len(toc_pages) == toc_page_count:
            return [title_page, *toc_pages, *chapter_pages]
        toc_page_count = len(toc_pages)

    chapter_pages, chapter_start_pages = paginate_chapters(
        chapters,
        source_dir,
        layout,
        styles,
        fonts,
        measurer,
        starting_page_number=2 + toc_page_count,
    )
    toc_pages = layout_text_blocks(
        build_toc_blocks(chapters, chapter_start_pages, layout, fonts, measurer),
        page_kind="toc",
        starting_page_number=2,
        layout=layout,
        styles=styles,
        fonts=fonts,
        measurer=measurer,
    )
    return [title_page, *toc_pages, *chapter_pages]


def pick_layout(
    chapters: list[ChapterMeta],
    source_dir: Path,
    fonts: FontBook,
    measurer: Measurer,
    target_min_pages: int,
    kindle_scribe: bool = False,
) -> tuple[LayoutPreset, list[Page]]:
    if kindle_scribe:
        candidates = [
            LayoutPreset(
                name="kindle-balanced",
                dpi=175,
                page_width_in=7.5,
                page_height_in=10.0,
                margin_left_px=86,
                margin_right_px=86,
                margin_top_px=108,
                margin_bottom_px=108,
                body_font_px=31,
                body_leading_px=50,
                heading_font_px=35,
                heading_leading_px=54,
                small_font_px=22,
                footer_font_px=21,
                title_font_px=66,
                chapter_font_px=46,
                toc_font_px=28,
                toc_leading_px=40,
            ),
            LayoutPreset(
                name="kindle-roomier",
                dpi=175,
                page_width_in=7.5,
                page_height_in=10.0,
                margin_left_px=94,
                margin_right_px=94,
                margin_top_px=114,
                margin_bottom_px=114,
                body_font_px=32,
                body_leading_px=52,
                heading_font_px=36,
                heading_leading_px=56,
                small_font_px=22,
                footer_font_px=21,
                title_font_px=68,
                chapter_font_px=47,
                toc_font_px=29,
                toc_leading_px=42,
            ),
        ]
    else:
        candidates = [
            LayoutPreset(
                name="balanced",
                dpi=175,
                page_width_in=5.5,
                page_height_in=8.5,
                margin_left_px=95,
                margin_right_px=95,
                margin_top_px=110,
                margin_bottom_px=110,
                body_font_px=24,
                body_leading_px=39,
                heading_font_px=29,
                heading_leading_px=44,
                small_font_px=18,
                footer_font_px=19,
                title_font_px=54,
                chapter_font_px=38,
                toc_font_px=23,
                toc_leading_px=34,
            ),
            LayoutPreset(
                name="roomier",
                dpi=175,
                page_width_in=5.5,
                page_height_in=8.5,
                margin_left_px=100,
                margin_right_px=100,
                margin_top_px=116,
                margin_bottom_px=116,
                body_font_px=25,
                body_leading_px=41,
                heading_font_px=30,
                heading_leading_px=46,
                small_font_px=18,
                footer_font_px=19,
                title_font_px=56,
                chapter_font_px=39,
                toc_font_px=24,
                toc_leading_px=35,
            ),
            LayoutPreset(
                name="max-spacious",
                dpi=175,
                page_width_in=5.25,
                page_height_in=8.25,
                margin_left_px=104,
                margin_right_px=104,
                margin_top_px=120,
                margin_bottom_px=118,
                body_font_px=26,
                body_leading_px=43,
                heading_font_px=31,
                heading_leading_px=48,
                small_font_px=18,
                footer_font_px=19,
                title_font_px=58,
                chapter_font_px=40,
                toc_font_px=24,
                toc_leading_px=36,
            ),
        ]

    last_pages: list[Page] | None = None
    for candidate in candidates:
        candidate_pages = paginate_book(chapters, source_dir, candidate, fonts, measurer)
        last_pages = candidate_pages
        if candidate_pages[-1].page_number >= target_min_pages:
            return candidate, candidate_pages

    if last_pages is None:
        raise RuntimeError("Unable to paginate any pages from the supplied chapter files.")
    return candidates[-1], last_pages


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
    page_width_px: int,
    fill: tuple[int, int, int],
) -> None:
    draw.text(
        (page_width_px // 2, y),
        text,
        font=font,
        fill=fill,
        anchor="ma",
        language="gu",
    )


def draw_double_frame(draw: ImageDraw.ImageDraw, layout: LayoutPreset, inset_outer: int, inset_inner: int, fill: int) -> None:
    draw.rectangle(
        (inset_outer, inset_outer, layout.page_width_px - inset_outer, layout.page_height_px - inset_outer),
        outline=fill,
        width=2,
    )
    draw.rectangle(
        (inset_inner, inset_inner, layout.page_width_px - inset_inner, layout.page_height_px - inset_inner),
        outline=fill,
        width=1,
    )


def draw_divider(draw: ImageDraw.ImageDraw, y: int, layout: LayoutPreset, fill: int) -> None:
    left = layout.page_width_px // 2 - 150
    right = layout.page_width_px // 2 + 150
    draw.line((left, y, right, y), fill=fill, width=2)
    draw.rectangle((layout.page_width_px // 2 - 8, y - 8, layout.page_width_px // 2 + 8, y + 8), outline=fill, width=2)


def add_toc_links(
    pdf: canvas.Canvas,
    page: Page,
    layout: LayoutPreset,
    styles: dict[str, TextStyle],
    fonts: FontBook,
    measurer: Measurer,
) -> None:
    scale_x = layout.page_width_pt / layout.page_width_px
    scale_y = layout.page_height_pt / layout.page_height_px
    for element in page.elements:
        if not element.target or element.style_name != "toc_line":
            continue
        style = styles[element.style_name]
        font = fonts.get(style.font_px)
        line = element.lines[0]
        width_px = int(measurer.width(line, font))
        left = element.x * scale_x
        right = (element.x + width_px + 12) * scale_x
        top = layout.page_height_pt - (element.y - 4) * scale_y
        bottom = layout.page_height_pt - (element.y + style.leading_px) * scale_y
        pdf.linkAbsolute(
            "",
            destinationname=element.target,
            Rect=(left, bottom, right, top),
            thickness=0,
        )


def render_page(
    page: Page,
    total_pages: int,
    layout: LayoutPreset,
    styles: dict[str, TextStyle],
    fonts: FontBook,
    book_title: str,
) -> Image.Image:
    image = Image.new("L", (layout.page_width_px, layout.page_height_px), color=247)
    draw = ImageDraw.Draw(image)

    if page.kind == "title":
        title_font = fonts.get(layout.title_font_px)
        subtitle_font = fonts.get(layout.heading_font_px)
        small_font = fonts.get(layout.small_font_px)
        draw_double_frame(draw, layout, 28, 46, 125)
        draw_divider(draw, layout.page_height_px // 3 - 54, layout, 126)
        draw_centered_text(draw, "સ્વામીની વાત", title_font, layout.page_height_px // 3, layout.page_width_px, 24)
        draw_centered_text(
            draw,
            "અધ્યાયવાર સંકલિત આવૃત્તિ",
            subtitle_font,
            layout.page_height_px // 3 + 170,
            layout.page_width_px,
            52,
        )
        draw_centered_text(
            draw,
            "સોળ પ્રકરણોનું પુસ્તક સ્વરૂપ સંકલન",
            small_font,
            layout.page_height_px // 3 + 244,
            layout.page_width_px,
            72,
        )
        draw_divider(draw, layout.page_height_px // 3 + 316, layout, 126)
        draw_centered_text(
            draw,
            f"{to_gujarati_digits(16)} પ્રકરણો  |  સંકલિત પુસ્તક",
            small_font,
            layout.page_height_px - 180,
            layout.page_width_px,
            74,
        )
        return image

    if page.kind == "chapter" and page.chapter is not None:
        chapter_font = fonts.get(layout.chapter_font_px)
        heading_font = fonts.get(layout.heading_font_px)
        small_font = fonts.get(layout.small_font_px)
        chapter = page.chapter
        draw_double_frame(draw, layout, 36, 56, 132)
        draw_divider(draw, layout.page_height_px // 3 - 18, layout, 138)
        draw_centered_text(
            draw,
            f"પ્રકરણ {to_gujarati_digits(chapter.number)}",
            chapter_font,
            layout.page_height_px // 3,
            layout.page_width_px,
            36,
        )
        draw_centered_text(
            draw,
            chapter.title_gujarati,
            heading_font,
            layout.page_height_px // 3 + 92,
            layout.page_width_px,
            24,
        )
        draw_divider(draw, layout.page_height_px // 3 + 150, layout, 138)
        draw_centered_text(
            draw,
            f"{to_gujarati_digits(chapter.entry_count)} વાતો",
            small_font,
            layout.page_height_px // 3 + 170,
            layout.page_width_px,
            74,
        )
        return image

    header_font = fonts.get(layout.small_font_px)
    footer_font = fonts.get(layout.footer_font_px)
    draw.rectangle(
        (20, 20, layout.page_width_px - 20, layout.page_height_px - 20),
        outline=228,
        width=1,
    )
    draw.line(
        (
            layout.margin_left_px,
            layout.margin_top_px - 34,
            layout.page_width_px - layout.margin_right_px,
            layout.margin_top_px - 34,
        ),
        fill=170,
        width=2,
    )
    header_text = book_title if page.chapter is None else f"પ્રકરણ {to_gujarati_digits(page.chapter.number)}: {page.chapter.title_gujarati}"
    draw.text(
        (layout.margin_left_px, layout.margin_top_px - 72),
        header_text,
        font=header_font,
        fill=80,
        language="gu",
    )
    page_counter = f"Page {page.page_number} / {total_pages}"
    draw.text(
        (layout.page_width_px // 2, layout.page_height_px - 54),
        page_counter,
        font=footer_font,
        fill=96,
        anchor="ma",
    )

    for element in page.elements:
        style = styles[element.style_name]
        font = fonts.get(style.font_px)
        y = element.y
        for line in element.lines:
            if style.align == "center":
                draw.text(
                    (layout.page_width_px // 2, y),
                    line,
                    font=font,
                    fill=style.fill[0],
                    anchor="ma",
                    language="gu",
                )
            else:
                draw.text(
                    (element.x, y),
                    line,
                    font=font,
                    fill=style.fill[0],
                    language="gu",
                )
            y += style.leading_px

    return image


def write_pdf(
    output_path: Path,
    pages: list[Page],
    layout: LayoutPreset,
    fonts: FontBook,
    book_title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=(layout.page_width_pt, layout.page_height_pt))
    pdf.setTitle(book_title)
    pdf.setAuthor("OpenAI Codex")
    pdf.setSubject("Compiled Swamini Vaat chapters")
    pdf.setPageCompression(1)
    pdf.showOutline()
    styles = build_styles(layout)
    total_pages = pages[-1].page_number
    measurer = Measurer()
    toc_outline_added = False

    for page in pages:
        if page.kind == "title":
            destination = make_destination_name("title", "root")
            pdf.bookmarkPage(destination)
            pdf.addOutlineEntry(book_title, destination, 0, closed=False)
        elif page.kind == "toc" and not toc_outline_added:
            destination = make_destination_name("toc", "root")
            pdf.bookmarkPage(destination)
            pdf.addOutlineEntry("વિષય સૂચિ", destination, 1, closed=False)
            toc_outline_added = True
        elif page.kind == "chapter" and page.chapter is not None:
            destination = make_destination_name("chapter", str(page.chapter.number))
            pdf.bookmarkPage(destination)
            pdf.addOutlineEntry(f"પ્રકરણ {to_gujarati_digits(page.chapter.number)}: {page.chapter.title_gujarati}", destination, 1, closed=True)

        rendered = render_page(page, total_pages, layout, styles, fonts, book_title)
        pdf.drawImage(
            ImageReader(rendered),
            0,
            0,
            width=layout.page_width_pt,
            height=layout.page_height_pt,
        )
        if page.kind == "toc":
            add_toc_links(pdf, page, layout, styles, fonts, measurer)
        pdf.showPage()

    pdf.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a formatted PDF from the Swamini Vaat chapter text files.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="Directory containing the chapter .txt files and index.json.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PDF, help="Destination PDF path.")
    parser.add_argument("--min-pages", type=int, default=TARGET_MIN_PAGES, help="Minimum page count target.")
    parser.add_argument("--kindle-scribe", action="store_true", help="Use a page size and typography tuned for Kindle Scribe.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir
    if args.kindle_scribe and args.output == DEFAULT_OUTPUT_PDF:
        args.output = DEFAULT_KINDLE_OUTPUT_PDF
    font_path, font_index = choose_font_path()
    fonts = FontBook(font_path, font_index)
    measurer = Measurer()
    chapters = load_chapters(source_dir)
    layout, pages = pick_layout(chapters, source_dir, fonts, measurer, args.min_pages, kindle_scribe=args.kindle_scribe)
    write_pdf(args.output, pages, layout, fonts, "સ્વામીની વાત")
    print(f"Output PDF: {args.output}")
    print(f"Font used: {font_path} (index {font_index})")
    print(f"Layout preset: {layout.name}")
    print(f"Total pages: {pages[-1].page_number}")


if __name__ == "__main__":
    main()
