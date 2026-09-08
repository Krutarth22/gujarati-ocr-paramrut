"""
Swamini Vaat extractor — reads HTML entries from the APK assets and
writes one .txt file per chapter plus an index.json manifest.

Data sources (all inside apk_extracted/assets/flutter_assets/assets/):
  chapter.json  — 16 chapters with Gujarati titles
  vato.json     — index of 3,825 entries (ChId, VatNo, VatFile, VatNameGuj)
  html/chapter{N}/ch{N}{NNN}.html — actual entry text
"""
import json
import re
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

ASSETS = Path("apk_extracted/assets/flutter_assets/assets")
OUTPUT = Path("swamini_vaat")


def extract_text(html_path: Path) -> str:
    """
    Parse one entry HTML file and return clean Gujarati text.
    The content lives in <div class="vaat_ind">; footnotes in <div id="ex1">.
    Anchor tags are kept as plain text (their href attributes are stripped).
    """
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    vaat_div = soup.find("div", class_="vaat_ind")
    if not vaat_div:
        return ""

    # Remove <a> tags but keep their inner text
    for a in vaat_div.find_all("a"):
        a.replace_with(a.get_text())

    text = vaat_div.get_text(separator=" ", strip=True)
    # Collapse multiple spaces/newlines
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_chapters() -> dict:
    """Return {ChId: {"name": str, "name_guj": str}}"""
    with open(ASSETS / "chapter.json", encoding="utf-8") as f:
        data = json.load(f)
    return {ch["ChId"]: {"name": ch["ChName"], "name_guj": ch["ChNameGuj"]} for ch in data}


def load_index() -> list:
    """Return sorted list of entry dicts from vato.json."""
    with open(ASSETS / "vato.json", encoding="utf-8") as f:
        data = json.load(f)
    return sorted(data, key=lambda e: (e["ChId"], e["VatNo"]))


def write_chapter(ch_id: int, ch_info: dict, entries: list, ch_num: int) -> tuple:
    """
    Write one chapter .txt file. Returns (filename, entry_count).
    entries: list of dicts from vato.json for this chapter.
    """
    OUTPUT.mkdir(parents=True, exist_ok=True)

    title_guj = ch_info["name_guj"]
    safe_title = re.sub(r'[/\\:*?"<>|]', "_", title_guj)[:50].strip().replace(" ", "_")
    filename = f"chapter_{ch_num:03d}_{safe_title}.txt"

    lines = [
        "=" * 64,
        f"સ્વામીની વાત - પ્રકરણ {ch_num}: {title_guj}",
        f"SWAMINI VAAT - Chapter {ch_num}: {ch_info['name']}",
        "=" * 64,
        "",
    ]

    html_dir = ASSETS / "html" / f"chapter{ch_id}"
    written = 0

    for entry in entries:
        vat_file = entry["VatFile"]
        html_path = html_dir / vat_file

        if not html_path.exists():
            continue

        text = extract_text(html_path)
        if not text:
            continue

        vat_no = entry["VatNo"]
        name_guj = entry.get("VatNameGuj", "")
        lines += [
            f"વાત {vat_no}" + (f": {name_guj}" if name_guj else ""),
            "-" * 64,
            text,
            "",
        ]
        written += 1

    (OUTPUT / filename).write_text("\n".join(lines), encoding="utf-8")
    return filename, written


def main():
    if not ASSETS.exists():
        print(f"✗ {ASSETS} not found.")
        print("  Run: python3 -c \"import zipfile,pathlib; zipfile.ZipFile('paramrut.apk').extractall('apk_extracted')\"")
        return

    print("Loading chapter index...")
    chapters = load_chapters()

    print("Loading entry index (vato.json)...")
    all_entries = load_index()

    # Group entries by chapter
    by_chapter: dict = {}
    for entry in all_entries:
        ch_id = entry["ChId"]
        by_chapter.setdefault(ch_id, []).append(entry)

    index = {
        "generated_at": datetime.now().isoformat(),
        "total_chapters": len(chapters),
        "total_entries": 0,
        "chapters": [],
    }

    print(f"\nExtracting {len(all_entries)} entries across {len(chapters)} chapters...\n")

    for ch_num, ch_id in enumerate(sorted(chapters.keys()), 1):
        ch_info = chapters[ch_id]
        entries = by_chapter.get(ch_id, [])
        filename, count = write_chapter(ch_id, ch_info, entries, ch_num)

        index["total_entries"] += count
        index["chapters"].append({
            "number": ch_num,
            "chapter_id": ch_id,
            "title_gujarati": ch_info["name_guj"],
            "title_english": ch_info["name"],
            "entry_count": count,
            "file": filename,
        })
        print(f"  ✓ {filename}  ({count} entries)")

    (OUTPUT / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n✓ Done.")
    print(f"  Chapters : {index['total_chapters']}")
    print(f"  Entries  : {index['total_entries']}")
    print(f"  Output   : {OUTPUT}/")


if __name__ == "__main__":
    main()
