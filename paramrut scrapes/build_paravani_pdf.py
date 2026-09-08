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


DEFAULT_SOURCE_DIR = Path("paravani")
DEFAULT_OUTPUT_PDF = DEFAULT_SOURCE_DIR / "Paravani_Prashad_Compiled_Book.pdf"
DEFAULT_KINDLE_OUTPUT_PDF = DEFAULT_SOURCE_DIR / "Paravani_Prashad_Kindle_Scribe.pdf"

FONT_CANDIDATES = [
    (Path("/System/Library/Fonts/KohinoorGujarati.ttc"), 3),
    (Path("/System/Library/Fonts/Supplemental/Gujarati Sangam MN.ttc"), 0),
    (Path("/System/Library/Fonts/Supplemental/GujaratiMT.ttc"), 0),
]

LATIN_FONT_CANDIDATES = [
    (Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), 0),
    (Path("/Library/Fonts/Arial Unicode.ttf"), 0),
    (Path("/System/Library/Fonts/Helvetica.ttc"), 0),
    (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), 0),
]

GUJARATI_DIGITS = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")
HEADER_LINE_RE = re.compile(r"^=+$")
META_LINE_RE = re.compile(r"^(Date|Title|Place|Info)\s*:")
STAR_LINE_RE = re.compile(r"^[*]{3,5}$")
SPACE_RE = re.compile(r"\s+")
LATIN_CHAR_RE = re.compile(r"[A-Za-z0-9]")
TOKEN_RE = re.compile(r"\S+\s*")


@dataclass(frozen=True)
class EntryMeta:
    year: str
    date: str
    title: str
    place: str
    file: str


@dataclass(frozen=True)
class YearGroup:
    year: str
    entries: tuple[EntryMeta, ...]


@dataclass(frozen=True)
class TextBlock:
    style: str
    text: str
    target: str | None = None


@dataclass(frozen=True)
class LayoutPreset:
    dpi: int
    page_width_in: float
    page_height_in: float
    margin_left_px: int
    margin_right_px: int
    margin_top_px: int
    margin_bottom_px: int
    body_font_px: int
    body_leading_px: int
    small_font_px: int
    footer_font_px: int
    title_font_px: int
    chapter_font_px: int
    toc_year_font_px: int
    toc_entry_font_px: int
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
    font_family: str = "gujarati"
    align: str = "left"
    space_before_px: int = 0
    space_after_px: int = 0


@dataclass(frozen=True)
class TextElement:
    style_name: str
    lines: tuple[str, ...]
    x: int
    y: int
    target: str | None = None


@dataclass
class Page:
    kind: str
    page_number: int
    year: str | None = None
    entry: EntryMeta | None = None
    elements: list[TextElement] = field(default_factory=list)


class FontBook:
    def __init__(
        self,
        gujarati_font_path: Path,
        gujarati_font_index: int,
        latin_font_path: Path,
        latin_font_index: int,
    ):
        self._font_specs = {
            "gujarati": (gujarati_font_path, gujarati_font_index),
            "latin": (latin_font_path, latin_font_index),
        }
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        self._layout_kwargs = {}
        if hasattr(ImageFont, "Layout") and hasattr(ImageFont.Layout, "RAQM"):
            self._layout_kwargs["layout_engine"] = ImageFont.Layout.RAQM

    def get(self, size: int, family: str = "gujarati") -> ImageFont.FreeTypeFont:
        key = (family, size)
        if key not in self._cache:
            font_path, font_index = self._font_specs[family]
            self._cache[key] = ImageFont.truetype(
                str(font_path),
                size=size,
                index=font_index,
                **self._layout_kwargs,
            )
        return self._cache[key]


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
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines


def to_gujarati_digits(value: int | str) -> str:
    return str(value).translate(GUJARATI_DIGITS)


def choose_font() -> tuple[Path, int]:
    for path, index in FONT_CANDIDATES:
        if path.exists():
            return path, index
    raise FileNotFoundError("No Gujarati font found in the expected system locations.")


def choose_latin_font() -> tuple[Path, int]:
    for path, index in LATIN_FONT_CANDIDATES:
        if path.exists():
            return path, index
    raise FileNotFoundError("No Latin-capable font found in the expected system locations.")


def load_year_groups(source_dir: Path) -> list[YearGroup]:
    data = json.loads((source_dir / "index.json").read_text(encoding="utf-8"))
    groups: list[YearGroup] = []
    for year in sorted(data["years"]):
        entries = []
        for item in data["years"][year]["entries"]:
            entries.append(
                EntryMeta(
                    year=year,
                    date=item["date"],
                    title=item["title"].strip(),
                    place=item["place"].strip(),
                    file=item["file"],
                )
            )
        groups.append(YearGroup(year=year, entries=tuple(entries)))
    return groups


def parse_body_blocks(text: str) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    paragraph_lines: list[str] = []

    def flush() -> None:
        if not paragraph_lines:
            return
        paragraph = SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
        if paragraph:
            blocks.append(TextBlock(style="body", text=paragraph))
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
    return blocks


def build_styles(layout: LayoutPreset) -> dict[str, TextStyle]:
    return {
        "toc_heading": TextStyle(
            font_px=layout.toc_year_font_px,
            leading_px=layout.toc_year_font_px + 10,
            fill=(70, 40, 26),
            font_family="gujarati",
            space_after_px=16,
        ),
        "body": TextStyle(
            font_px=layout.body_font_px,
            leading_px=layout.body_leading_px,
            fill=(28, 24, 22),
            space_after_px=14,
        ),
        "toc_year": TextStyle(
            font_px=layout.toc_year_font_px,
            leading_px=layout.toc_year_font_px + 10,
            fill=(70, 40, 26),
            font_family="latin",
            space_before_px=14,
            space_after_px=10,
        ),
        "toc_entry": TextStyle(
            font_px=layout.toc_entry_font_px,
            leading_px=layout.toc_leading_px,
            fill=(28, 24, 22),
            font_family="latin",
            space_after_px=6,
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
) -> list[Page]:
    pages: list[Page] = []
    current_page = Page(kind=page_kind, page_number=starting_page_number)
    y_cursor = layout.body_top_px

    def finish_page() -> None:
        nonlocal current_page, y_cursor
        pages.append(current_page)
        current_page = Page(kind=page_kind, page_number=pages[-1].page_number + 1)
        y_cursor = layout.body_top_px

    for block in blocks:
        style = styles[block.style]
        font = fonts.get(style.font_px, style.font_family)
        wrapped_lines = tuple(measurer.wrap(block.text, font, layout.body_width_px))
        if not wrapped_lines:
            continue

        first_segment = True
        pending_lines = list(wrapped_lines)
        while pending_lines:
            before = style.space_before_px if first_segment else 0
            available_height = layout.body_bottom_px - (y_cursor + before)
            if available_height <= 0:
                finish_page()
                first_segment = False
                continue

            fit_count = max(1, available_height // style.leading_px)
            segment_lines = tuple(pending_lines[:fit_count])
            segment_height = len(segment_lines) * style.leading_px
            after = style.space_after_px if fit_count >= len(pending_lines) else 0
            if y_cursor + before + segment_height + after > layout.body_bottom_px and current_page.elements:
                finish_page()
                first_segment = False
                continue

            current_page.elements.append(
                TextElement(
                    style_name=block.style,
                    lines=segment_lines,
                    x=layout.margin_left_px,
                    y=y_cursor + before,
                    target=block.target if len(segment_lines) == len(wrapped_lines) else None,
                )
            )
            y_cursor += before + segment_height + after
            pending_lines = pending_lines[fit_count:]
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
    while truncated and measurer.width(f"{truncated}...", font) > max_width:
        truncated = truncated[:-1].rstrip()
    return f"{truncated}..." if truncated else "..."


def make_destination_name(kind: str, identifier: str) -> str:
    safe_identifier = identifier.replace("/", "_").replace(" ", "_")
    return f"{kind}:{safe_identifier}"


def format_toc_entry(entry: EntryMeta, page_number: int, layout: LayoutPreset, fonts: FontBook, measurer: Measurer) -> str:
    font = fonts.get(layout.toc_entry_font_px, "latin")
    page_label = str(page_number)
    date_label = entry.date
    left_prefix = f"{date_label}  "
    title = entry.title
    reserved_width = int(measurer.width(f"{left_prefix}  .... {page_label}", font) + 24)
    title = fit_text_to_width(title, font, layout.body_width_px - reserved_width, measurer)
    left = f"{left_prefix}{title}"
    dots = "."
    candidate = f"{left}  {dots} {page_label}"
    while measurer.width(candidate, font) <= layout.body_width_px:
        dots += "."
        candidate = f"{left}  {dots} {page_label}"
    dots = dots[:-1] if len(dots) > 1 else "."
    return f"{left}  {dots} {page_label}"


def build_toc_blocks(
    groups: list[YearGroup],
    year_page_map: dict[str, int],
    entry_page_map: dict[str, int],
    layout: LayoutPreset,
    fonts: FontBook,
    measurer: Measurer,
) -> list[TextBlock]:
    blocks = [TextBlock(style="toc_heading", text="વિષય સૂચિ")]
    for group in groups:
        year_page = year_page_map.get(group.year, 0)
        year_label = f"{group.year}  ................................  {year_page}"
        blocks.append(
            TextBlock(
                style="toc_year",
                text=year_label,
                target=make_destination_name("year", group.year),
            )
        )
        for entry in group.entries:
            blocks.append(
                TextBlock(
                    style="toc_entry",
                    text=format_toc_entry(entry, entry_page_map[entry.file], layout, fonts, measurer),
                    target=make_destination_name("entry", entry.file),
                )
            )
    return blocks


def make_title_page(page_number: int) -> Page:
    return Page(kind="title", page_number=page_number)


def make_year_page(page_number: int, year: str) -> Page:
    return Page(kind="year", page_number=page_number, year=year)


def make_entry_page(page_number: int, entry: EntryMeta) -> Page:
    return Page(kind="entry", page_number=page_number, year=entry.year, entry=entry)


def paginate_entries(
    groups: list[YearGroup],
    source_dir: Path,
    layout: LayoutPreset,
    styles: dict[str, TextStyle],
    fonts: FontBook,
    measurer: Measurer,
    starting_page_number: int,
) -> tuple[list[Page], dict[str, int], dict[str, int]]:
    pages: list[Page] = []
    year_page_map: dict[str, int] = {}
    entry_page_map: dict[str, int] = {}
    page_number = starting_page_number

    for group in groups:
        year_page_map[group.year] = page_number
        pages.append(make_year_page(page_number, group.year))
        page_number += 1

        for entry in group.entries:
            entry_page_map[entry.file] = page_number
            pages.append(make_entry_page(page_number, entry))
            page_number += 1

            body_text = (source_dir / entry.file).read_text(encoding="utf-8")
            body_blocks = parse_body_blocks(body_text)
            body_pages = layout_text_blocks(
                body_blocks,
                page_kind="body",
                starting_page_number=page_number,
                layout=layout,
                styles=styles,
                fonts=fonts,
                measurer=measurer,
            )
            for page in body_pages:
                page.year = entry.year
                page.entry = entry
            pages.extend(body_pages)
            page_number = pages[-1].page_number + 1

    return pages, year_page_map, entry_page_map


def paginate_book(groups: list[YearGroup], source_dir: Path, layout: LayoutPreset, fonts: FontBook, measurer: Measurer) -> list[Page]:
    styles = build_styles(layout)
    title_page = make_title_page(1)

    toc_count = len(
        layout_text_blocks(
            [TextBlock(style="toc_year", text="વિષય સૂચિ")],
            page_kind="toc",
            starting_page_number=2,
            layout=layout,
            styles=styles,
            fonts=fonts,
            measurer=measurer,
        )
    )

    for _ in range(3):
        content_pages, year_page_map, entry_page_map = paginate_entries(
            groups, source_dir, layout, styles, fonts, measurer, starting_page_number=2 + toc_count
        )
        toc_pages = layout_text_blocks(
            build_toc_blocks(groups, year_page_map, entry_page_map, layout, fonts, measurer),
            page_kind="toc",
            starting_page_number=2,
            layout=layout,
            styles=styles,
            fonts=fonts,
            measurer=measurer,
        )
        if len(toc_pages) == toc_count:
            return [title_page, *toc_pages, *content_pages]
        toc_count = len(toc_pages)

    content_pages, year_page_map, entry_page_map = paginate_entries(
        groups, source_dir, layout, styles, fonts, measurer, starting_page_number=2 + toc_count
    )
    toc_pages = layout_text_blocks(
        build_toc_blocks(groups, year_page_map, entry_page_map, layout, fonts, measurer),
        page_kind="toc",
        starting_page_number=2,
        layout=layout,
        styles=styles,
        fonts=fonts,
        measurer=measurer,
    )
    return [title_page, *toc_pages, *content_pages]


def draw_centered_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, y: int, x_center: int, fill: int) -> None:
    draw.text((x_center, y), text, font=font, fill=fill, anchor="ma", language="gu")


def draw_double_frame(draw: ImageDraw.ImageDraw, layout: LayoutPreset, inset_outer: int, inset_inner: int, fill: int) -> None:
    draw.rectangle((inset_outer, inset_outer, layout.page_width_px - inset_outer, layout.page_height_px - inset_outer), outline=fill, width=2)
    draw.rectangle((inset_inner, inset_inner, layout.page_width_px - inset_inner, layout.page_height_px - inset_inner), outline=fill, width=1)


def draw_divider(draw: ImageDraw.ImageDraw, y: int, layout: LayoutPreset, fill: int) -> None:
    left = layout.page_width_px // 2 - 150
    right = layout.page_width_px // 2 + 150
    draw.line((left, y, right, y), fill=fill, width=2)
    draw.rectangle((layout.page_width_px // 2 - 8, y - 8, layout.page_width_px // 2 + 8, y + 8), outline=fill, width=2)


def draw_mixed_line(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font_px: int,
    fill: int,
    fonts: FontBook,
    measurer: Measurer,
) -> None:
    cursor_x = x
    tokens = TOKEN_RE.findall(text)
    if not tokens:
        return

    for token in tokens:
        family = "latin" if LATIN_CHAR_RE.search(token) else "gujarati"
        font = fonts.get(font_px, family)
        kwargs = {"font": font, "fill": fill}
        if family == "gujarati":
            kwargs["language"] = "gu"
        draw.text((cursor_x, y), token, **kwargs)
        cursor_x += int(round(measurer.width(token, font)))


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
        if not element.target or element.style_name not in {"toc_year", "toc_entry"}:
            continue
        style = styles[element.style_name]
        font = fonts.get(style.font_px, style.font_family)
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


def render_page(page: Page, total_pages: int, layout: LayoutPreset, styles: dict[str, TextStyle], fonts: FontBook) -> Image.Image:
    image = Image.new("L", (layout.page_width_px, layout.page_height_px), color=247)
    draw = ImageDraw.Draw(image)
    x_center = layout.page_width_px // 2
    measurer = Measurer()

    if page.kind == "title":
        title_font = fonts.get(layout.title_font_px, "gujarati")
        heading_font = fonts.get(layout.chapter_font_px, "gujarati")
        small_font = fonts.get(layout.small_font_px, "gujarati")
        draw_double_frame(draw, layout, 28, 46, 125)
        draw_divider(draw, layout.page_height_px // 3 - 52, layout, 126)
        draw_centered_text(draw, "પરાવાણી પ્રસાદ", title_font, layout.page_height_px // 3, x_center, 24)
        draw_centered_text(draw, "વર્ષવાર સંકલિત આવૃત્તિ", heading_font, layout.page_height_px // 3 + 160, x_center, 42)
        draw_divider(draw, layout.page_height_px // 3 + 228, layout, 126)
        draw_centered_text(draw, "૨૦૨૦ થી ૨૦૨૬ સુધીના પ્રવચનો", small_font, layout.page_height_px - 180, x_center, 74)
        return image

    if page.kind == "year" and page.year is not None:
        year_font = fonts.get(layout.title_font_px, "latin")
        heading_font = fonts.get(layout.chapter_font_px, "gujarati")
        draw_double_frame(draw, layout, 36, 56, 132)
        draw_divider(draw, layout.page_height_px // 3 - 20, layout, 138)
        draw_centered_text(draw, to_gujarati_digits(page.year), year_font, layout.page_height_px // 3, x_center, 36)
        draw_centered_text(draw, "વર્ષ વિભાગ", heading_font, layout.page_height_px // 3 + 120, x_center, 50)
        draw_divider(draw, layout.page_height_px // 3 + 182, layout, 138)
        return image

    if page.kind == "entry" and page.entry is not None:
        title_font = fonts.get(layout.chapter_font_px, "latin")
        meta_font = fonts.get(layout.small_font_px, "latin")
        draw_double_frame(draw, layout, 36, 56, 132)
        draw_divider(draw, layout.page_height_px // 3 - 24, layout, 138)
        title_lines = Measurer().wrap(page.entry.title, title_font, layout.body_width_px)
        y = layout.page_height_px // 3
        for line in title_lines:
            draw_centered_text(draw, line, title_font, y, x_center, 30)
            y += title_font.size + 20
        draw_divider(draw, y + 10, layout, 138)
        draw_centered_text(draw, f"Date: {page.entry.date}", meta_font, y + 56, x_center, 72)
        draw_centered_text(draw, f"Place: {page.entry.place}", meta_font, y + 112, x_center, 72)
        return image

    header_font = fonts.get(layout.small_font_px, "latin" if page.entry is not None else "gujarati")
    footer_font = fonts.get(layout.footer_font_px, "gujarati")
    draw.rectangle((20, 20, layout.page_width_px - 20, layout.page_height_px - 20), outline=228, width=1)
    draw.line(
        (layout.margin_left_px, layout.margin_top_px - 34, layout.page_width_px - layout.margin_right_px, layout.margin_top_px - 34),
        fill=170,
        width=2,
    )
    header_text = "પરાવાણી પ્રસાદ"
    if page.entry is not None:
        header_text = f"{page.entry.date}  {page.entry.title}"
    draw.text((layout.margin_left_px, layout.margin_top_px - 72), header_text, font=header_font, fill=80, language="gu")
    page_counter = f"Page {page.page_number} / {total_pages}"
    draw.text((x_center, layout.page_height_px - 54), page_counter, font=footer_font, fill=96, anchor="ma")

    for element in page.elements:
        style = styles[element.style_name]
        font = fonts.get(style.font_px, style.font_family)
        y = element.y
        for line in element.lines:
            if page.kind == "body" and element.style_name == "body":
                draw_mixed_line(draw, element.x, y, line, style.font_px, style.fill[0], fonts, measurer)
            else:
                kwargs = {"font": font, "fill": style.fill[0]}
                if style.font_family == "gujarati":
                    kwargs["language"] = "gu"
                draw.text((element.x, y), line, **kwargs)
            y += style.leading_px

    return image


def write_pdf(output_path: Path, pages: list[Page], layout: LayoutPreset, fonts: FontBook) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=(layout.page_width_pt, layout.page_height_pt))
    pdf.setTitle("પરાવાણી પ્રસાદ")
    pdf.setAuthor("OpenAI Codex")
    pdf.setSubject("Compiled Paravani Prashad talks")
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
            pdf.addOutlineEntry("પરાવાણી પ્રસાદ", destination, 0, closed=False)
        elif page.kind == "toc" and not toc_outline_added:
            destination = make_destination_name("toc", "root")
            pdf.bookmarkPage(destination)
            pdf.addOutlineEntry("વિષય સૂચિ", destination, 1, closed=False)
            toc_outline_added = True
        elif page.kind == "year" and page.year is not None:
            destination = make_destination_name("year", page.year)
            pdf.bookmarkPage(destination)
            pdf.addOutlineEntry(to_gujarati_digits(page.year), destination, 1, closed=False)
        elif page.kind == "entry" and page.entry is not None:
            destination = make_destination_name("entry", page.entry.file)
            outline_title = f"{to_gujarati_digits(page.entry.date)}  {page.entry.title}"
            pdf.bookmarkPage(destination)
            pdf.addOutlineEntry(outline_title, destination, 2, closed=True)

        rendered = render_page(page, total_pages, layout, styles, fonts)
        pdf.drawImage(ImageReader(rendered), 0, 0, width=layout.page_width_pt, height=layout.page_height_pt)
        if page.kind == "toc":
            add_toc_links(pdf, page, layout, styles, fonts, measurer)
        pdf.showPage()
    pdf.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a formatted PDF from the Paravani text files.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PDF)
    parser.add_argument("--kindle-scribe", action="store_true", help="Use a page size and typography tuned for Kindle Scribe.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    font_path, font_index = choose_font()
    latin_font_path, latin_font_index = choose_latin_font()
    fonts = FontBook(font_path, font_index, latin_font_path, latin_font_index)
    measurer = Measurer()
    if args.kindle_scribe and args.output == DEFAULT_OUTPUT_PDF:
        args.output = DEFAULT_KINDLE_OUTPUT_PDF
    if args.kindle_scribe:
        layout = LayoutPreset(
            dpi=175,
            page_width_in=7.5,
            page_height_in=10.0,
            margin_left_px=88,
            margin_right_px=88,
            margin_top_px=108,
            margin_bottom_px=108,
            body_font_px=29,
            body_leading_px=47,
            small_font_px=21,
            footer_font_px=21,
            title_font_px=64,
            chapter_font_px=44,
            toc_year_font_px=38,
            toc_entry_font_px=27,
            toc_leading_px=40,
        )
    else:
        layout = LayoutPreset(
            dpi=175,
            page_width_in=5.5,
            page_height_in=8.5,
            margin_left_px=100,
            margin_right_px=100,
            margin_top_px=116,
            margin_bottom_px=116,
            body_font_px=25,
            body_leading_px=41,
            small_font_px=18,
            footer_font_px=19,
            title_font_px=56,
            chapter_font_px=39,
            toc_year_font_px=34,
            toc_entry_font_px=24,
            toc_leading_px=36,
        )
    groups = load_year_groups(args.source_dir)
    pages = paginate_book(groups, args.source_dir, layout, fonts, measurer)
    write_pdf(args.output, pages, layout, fonts)
    print(f"Output PDF: {args.output}")
    print(f"Gujarati font used: {font_path} (index {font_index})")
    print(f"Latin font used: {latin_font_path} (index {latin_font_index})")
    print(f"Total pages: {pages[-1].page_number}")


if __name__ == "__main__":
    main()
