from __future__ import annotations

import html
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"


@dataclass(frozen=True)
class EpubItem:
    id: str
    href: str
    media_type: str
    content: str | bytes
    in_spine: bool = True
    properties: tuple[str, ...] = ()
    title: str | None = None


@dataclass(frozen=True)
class NavPoint:
    label: str
    href: str
    children: tuple["NavPoint", ...] = ()


def make_xhtml_document(title: str, body_html: str, language: str = "gu") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}" lang="{html.escape(language)}" xml:lang="{html.escape(language)}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="styles/book.css" />
  </head>
  <body>
{body_html}
  </body>
</html>
"""


def paragraphize(paragraphs: Iterable[str], css_class: str = "para") -> str:
    lines = [f'    <p class="{css_class}">{html.escape(paragraph)}</p>' for paragraph in paragraphs if paragraph.strip()]
    return "\n".join(lines)


def section_heading(level: int, text: str, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"    <h{level}{class_attr}>{html.escape(text)}</h{level}>"


def default_styles() -> str:
    return """html, body {
  margin: 0;
  padding: 0;
}

body {
  font-family: serif;
  line-height: 1.65;
  widows: 2;
  orphans: 2;
  margin: 0;
  padding: 0 4%;
  text-align: left;
}

h1, h2, h3 {
  page-break-after: avoid;
  break-after: avoid;
}

h1 {
  font-size: 1.55em;
  margin: 0 0 0.8em;
  text-align: center;
}

h2 {
  font-size: 1.2em;
  margin: 1.2em 0 0.7em;
}

.subtitle, .meta, .meta-block {
  color: #444;
}

.subtitle {
  font-size: 0.98em;
  margin: -0.2em 0 1.2em;
  text-align: center;
}

.meta-block {
  border-top: 1px solid #ddd;
  border-bottom: 1px solid #ddd;
  font-size: 0.96em;
  margin: 0 0 1.2em;
  padding: 0.8em 0;
}

.meta {
  margin: 0.25em 0;
}

.para {
  margin: 0 0 0.9em;
  text-indent: 1.4em;
}

.chapter-start, .entry-start, .year-start {
  margin-top: 18vh;
}

.chapter-start h1, .entry-start h1, .year-start h1 {
  margin-bottom: 0.5em;
}

nav#toc ol {
  list-style: none;
  margin: 0;
  padding-left: 0;
}

nav#toc li {
  margin: 0.35em 0;
}

nav#toc ol ol {
  padding-left: 1.1em;
}
"""


def build_epub(
    output_path: Path,
    *,
    title: str,
    identifier_seed: str,
    creators: list[str],
    language: str,
    items: list[EpubItem],
    nav_points: list[NavPoint],
    styles_css: str | None = None,
    extra_items: list[EpubItem] | None = None,
    package_prefix: str | None = None,
    metadata_properties: list[tuple[str, str]] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    book_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identifier_seed))
    modified = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    styles_item = EpubItem(
        id="styles",
        href="styles/book.css",
        media_type="text/css",
        content=styles_css or default_styles(),
        in_spine=False,
    )
    nav_item = EpubItem(
        id="nav",
        href="nav.xhtml",
        media_type="application/xhtml+xml",
        content=_build_nav_xhtml(title, nav_points, language),
        in_spine=False,
        properties=("nav",),
    )
    ncx_item = EpubItem(
        id="ncx",
        href="toc.ncx",
        media_type="application/x-dtbncx+xml",
        content=_build_ncx(title, book_id, nav_points),
        in_spine=False,
    )
    full_items = [styles_item, nav_item, ncx_item, *(extra_items or []), *items]
    package_opf = _build_package_opf(
        title=title,
        book_id=book_id,
        creators=creators,
        language=language,
        modified=modified,
        items=full_items,
        package_prefix=package_prefix,
        metadata_properties=metadata_properties or [],
    )

    with zipfile.ZipFile(output_path, "w") as zf:
        mimetype_info = zipfile.ZipInfo("mimetype")
        mimetype_info.compress_type = zipfile.ZIP_STORED
        zf.writestr(mimetype_info, "application/epub+zip")
        zf.writestr("META-INF/container.xml", _container_xml())
        zf.writestr("OEBPS/package.opf", package_opf)
        for item in full_items:
            zf.writestr(f"OEBPS/{item.href}", item.content)


def _container_xml() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _build_package_opf(
    *,
    title: str,
    book_id: str,
    creators: list[str],
    language: str,
    modified: str,
    items: list[EpubItem],
    package_prefix: str | None,
    metadata_properties: list[tuple[str, str]],
) -> str:
    manifest_lines = []
    spine_lines = []
    for item in items:
        properties_attr = f' properties="{" ".join(item.properties)}"' if item.properties else ""
        manifest_lines.append(
            f'    <item id="{escape(item.id)}" href="{escape(item.href)}" media-type="{escape(item.media_type)}"{properties_attr}/>'
        )
        if item.in_spine:
            spine_lines.append(f'    <itemref idref="{escape(item.id)}"/>')

    creator_tags = "\n".join(
        f'    <dc:creator>{escape(creator)}</dc:creator>' for creator in creators
    )
    metadata_property_tags = "\n".join(
        f'    <meta property="{escape(prop)}">{escape(value)}</meta>' for prop, value in metadata_properties
    )
    package_prefix_attr = f' prefix="{escape(package_prefix)}"' if package_prefix else ""
    extra_metadata_block = f"\n{metadata_property_tags}" if metadata_property_tags else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf"{package_prefix_attr}>
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:{escape(book_id)}</dc:identifier>
    <dc:title>{escape(title)}</dc:title>
    <dc:language>{escape(language)}</dc:language>
{creator_tags}
    <meta property="dcterms:modified">{escape(modified)}</meta>{extra_metadata_block}
  </metadata>
  <manifest>
{chr(10).join(manifest_lines)}
  </manifest>
  <spine toc="ncx">
{chr(10).join(spine_lines)}
  </spine>
</package>
"""


def _build_nav_xhtml(title: str, nav_points: list[NavPoint], language: str) -> str:
    return make_xhtml_document(
        f"{title} - TOC",
        "\n".join(
            [
                '    <nav id="toc" epub:type="toc">',
                f"      <h1>{html.escape(title)}</h1>",
                "      <ol>",
                _render_nav_html(nav_points, indent=8),
                "      </ol>",
                "    </nav>",
            ]
        ),
        language=language,
    )


def _render_nav_html(points: list[NavPoint], indent: int) -> str:
    lines: list[str] = []
    pad = " " * indent
    for point in points:
        lines.append(f'{pad}<li><a href="{html.escape(point.href)}">{html.escape(point.label)}</a>')
        if point.children:
            lines.append(f"{pad}  <ol>")
            lines.append(_render_nav_html(list(point.children), indent + 4))
            lines.append(f"{pad}  </ol>")
        lines.append(f"{pad}</li>")
    return "\n".join(lines)


def _build_ncx(title: str, book_id: str, nav_points: list[NavPoint]) -> str:
    body, _ = _render_ncx_points(nav_points, 1)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{escape(book_id)}"/>
    <meta name="dtb:depth" content="2"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{escape(title)}</text>
  </docTitle>
  <navMap>
{body}
  </navMap>
</ncx>
"""


def _render_ncx_points(points: list[NavPoint], play_order: int, depth: int = 1) -> tuple[str, int]:
    lines: list[str] = []
    current_order = play_order
    indent = "  " * (depth + 1)
    for idx, point in enumerate(points, start=1):
        point_id = f"navPoint-{current_order}"
        lines.append(f'{indent}<navPoint id="{point_id}" playOrder="{current_order}">')
        lines.append(f"{indent}  <navLabel><text>{escape(point.label)}</text></navLabel>")
        lines.append(f'{indent}  <content src="{escape(point.href)}"/>')
        current_order += 1
        if point.children:
            child_xml, current_order = _render_ncx_points(list(point.children), current_order, depth + 1)
            lines.append(child_xml)
        lines.append(f"{indent}</navPoint>")
    return "\n".join(lines), current_order
