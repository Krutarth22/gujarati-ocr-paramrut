"""
Vachnamrut extractor — reads text entries from the APK assets and writes
one .txt file per section plus an index.json manifest.

Data sources (inside apk_extracted/assets/flutter_assets/assets/):
  vachanall.json       — index of 274 entries
  textvachan/{KEY}.txt — Gujarati entry text with Paramrut app markup
"""
import json
import re
from datetime import datetime
from pathlib import Path


ASSETS = Path("apk_extracted/assets/flutter_assets/assets")
TEXT_SOURCE = ASSETS / "textvachan"
INDEX_SOURCE = ASSETS / "vachanall.json"
OUTPUT = Path("vachnamrut")

SPACE_RE = re.compile(r"[ \t]+")
INVALID_FILENAME_RE = re.compile(r'[/\\:*?"<>|]')
TRAILING_NUMBER_RE = re.compile(r"\s+\d+\s*$")

SECTION_TITLES = {
    "GP": ("Gadhada Pratham", "ગઢડા પ્રથમ"),
    "S": ("Sarangpur", "સારંગપુર"),
    "K": ("Kariyani", "કારિયાણી"),
    "L": ("Loya", "લોયા"),
    "P": ("Panchala", "પંચાળા"),
    "GM": ("Gadhada Madhya", "ગઢડા મધ્ય"),
    "V": ("Vadtal", "વરતાલ"),
    "A": ("Ahmedabad", "અમદાવાદ"),
    "GA": ("Gadhada Antya", "ગઢડા અંત્ય"),
    "Ash": ("Aslali", "અશ્લાલી"),
    "J": ("Jetalpur", "જેતલપુર"),
    "KB": ("Khagol Bhugol", "ભૂગોળ-ખગોળ"),
}


def text_file_for(entry: dict) -> Path:
    return TEXT_SOURCE / entry["File"].replace(".html", ".txt")


def entry_key(entry: dict) -> str:
    return entry["File"].rsplit(".", 1)[0].rsplit("-", 1)[0]


def section_title_for(key: str, first_entry: dict) -> tuple[str, str]:
    if key in SECTION_TITLES:
        return SECTION_TITLES[key]

    english = TRAILING_NUMBER_RE.sub("", first_entry["VachanName"]).strip()
    return english, english


def safe_filename_title(title: str) -> str:
    clean = INVALID_FILENAME_RE.sub("_", title)
    return clean[:50].strip().replace(" ", "_")


def clean_segment(segment: str) -> str:
    segment = segment.replace("@@TITLE@@", "")
    segment = segment.replace("*#", "")
    segment = segment.replace("#*", "")
    segment = SPACE_RE.sub(" ", segment)
    return segment.strip()


def extract_paragraphs(raw_text: str, metadata_title: str) -> list[str]:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("${Title}", "\n@@TITLE@@")
    text = text.replace("${Slok}", "\n")
    paragraphs: list[str] = []

    for segment in text.split("$"):
        if "@@TITLE@@" in segment:
            continue
        paragraph = clean_segment(segment)
        if not paragraph:
            continue
        if paragraph == metadata_title:
            continue
        paragraphs.append(paragraph)

    return paragraphs


def load_entries() -> list[dict]:
    with INDEX_SOURCE.open(encoding="utf-8") as f:
        return json.load(f)


def group_entries(entries: list[dict]) -> list[dict]:
    """
    Preserve the app/book order. Ahmedabad appears in two separate blocks in
    the source index, so consecutive blocks are kept separate.
    """
    sections: list[dict] = []
    current: dict | None = None

    for entry in entries:
        key = entry_key(entry)
        if current is None or current["key"] != key:
            title_english, title_gujarati = section_title_for(key, entry)
            current = {
                "key": key,
                "title_english": title_english,
                "title_gujarati": title_gujarati,
                "entries": [],
            }
            sections.append(current)
        current["entries"].append(entry)

    return sections


def write_section(section: dict, section_number: int) -> tuple[str, int]:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    title_gujarati = section["title_gujarati"]
    title_english = section["title_english"]
    filename = f"chapter_{section_number:03d}_{safe_filename_title(title_gujarati)}.txt"

    lines = [
        "=" * 64,
        f"વચનામૃત - વિભાગ {section_number}: {title_gujarati}",
        f"VACHNAMRUT - Section {section_number}: {title_english}",
        "=" * 64,
        "",
    ]

    written = 0
    for entry in section["entries"]:
        text_path = text_file_for(entry)
        if not text_path.exists():
            continue

        paragraphs = extract_paragraphs(
            text_path.read_text(encoding="utf-8"),
            metadata_title=entry["NameGuj"],
        )
        if not paragraphs:
            continue

        heading = f"{entry['VachanName']}: {entry['NameGuj']}"
        lines += [
            heading,
            "-" * 64,
            f"તિથિ: {entry['Tithi'].strip()}",
            f"તારીખ: {entry['Panchang'].strip()}",
            f"દિવસ: {entry['Day'].strip()}",
            "",
            *paragraphs,
            "",
        ]
        written += 1

    (OUTPUT / filename).write_text("\n\n".join(lines), encoding="utf-8")
    return filename, written


def main():
    if not INDEX_SOURCE.exists() or not TEXT_SOURCE.exists():
        print(f"✗ Vachnamrut assets not found under {ASSETS}.")
        print("  Run: python3 -c \"import zipfile; zipfile.ZipFile('paramrut.apk').extractall('apk_extracted')\"")
        return

    print("Loading Vachnamrut index...")
    entries = load_entries()
    sections = group_entries(entries)

    index = {
        "generated_at": datetime.now().isoformat(),
        "total_chapters": len(sections),
        "total_entries": 0,
        "chapters": [],
    }

    print(f"\nExtracting {len(entries)} entries across {len(sections)} sections...\n")

    for section_number, section in enumerate(sections, 1):
        filename, count = write_section(section, section_number)
        index["total_entries"] += count
        index["chapters"].append(
            {
                "number": section_number,
                "section_key": section["key"],
                "title_gujarati": section["title_gujarati"],
                "title_english": section["title_english"],
                "entry_count": count,
                "file": filename,
            }
        )
        print(f"  ✓ {filename}  ({count} entries)")

    (OUTPUT / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n✓ Done.")
    print(f"  Sections : {index['total_chapters']}")
    print(f"  Entries  : {index['total_entries']}")
    print(f"  Output   : {OUTPUT}/")


if __name__ == "__main__":
    main()
