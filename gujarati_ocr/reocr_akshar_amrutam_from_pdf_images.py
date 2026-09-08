import re
import subprocess
import tempfile
from pathlib import Path

from split_akshar_amrutam import OUTPUT_DIR, PDF_PATH, PRINTED_TO_PDF_OFFSET, TOC_ENTRIES, LAST_PRINTED_PAGE, sanitize_filename


RENDER_DPI = 200
HEADER_RE = re.compile(r"^\s*અક્ષર અમૃતમ્[\s‌.]*$")
PAGE_NUM_RE = re.compile(r"^\s*[-~]?\s*\d+\s*[-~]?\s*$")
TITLE_DIGITS_RE = re.compile(r"[૦-૯].*[૦-૯].*[૦-૯].*[૦-૯]")
SECTION_RE = re.compile(r"^\(\s*સત્ર\s*\d+[\s»)]*$")

GLOBAL_REPLACEMENTS = [
    ("ગોઝિ", "ગોષ્ઠિ"),
    ("ગોષિ", "ગોષ્ઠિ"),
    ("આભ્મીયસમાજની", "આર્યસમાજની"),
    ("આતભ્મીયસમાજની", "આર્યસમાજની"),
    ("આત્મીયસમાજની", "આર્યસમાજની"),
    ("આત્મીય સમાજની", "આર્યસમાજની"),
    ("આભ્મીય સમાજની", "આર્યસમાજની"),
    ("ગરુની", "ગુરુની"),
    ("ગ્રુજી", "ગુરુજી"),
    ("ગૂરુજી", "ગુરુજી"),
    ("ગૂજરાત", "ગુજરાત"),
    ("ગોઝ્ઠિ", "ગોષ્ઠિ"),
    ("જય જ્ય જય", "જય જય જય"),
    ("\"દિવાળીનો દિવસ'", "'દિવાળીનો દિવસ'"),
    ("\"અમારા અંબરીષો આવવાના.", "'અમારા અંબરીષો આવવાના.'"),
    ("\"અમારા અંબરીષો આવવાના !'", "'અમારા અંબરીષો આવવાના!'"),
    ("\"બસ, એક તું રાજી થા !'", "'બસ, એક તું રાજી થા!'"),
]


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def render_page(pdf_page_num: int, out_prefix: Path) -> Path:
    cmd = [
        "pdftoppm",
        "-f",
        str(pdf_page_num),
        "-l",
        str(pdf_page_num),
        "-r",
        str(RENDER_DPI),
        "-png",
        "-singlefile",
        str(PDF_PATH),
        str(out_prefix),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_prefix.with_suffix(".png")


def ocr_image(image_path: Path) -> str:
    return run(["tesseract", str(image_path), "stdout", "-l", "guj", "--psm", "6"])


def clean_lines(lines: list[str], first_page: bool, title: str) -> list[str]:
    cleaned: list[str] = []
    started = not first_page

    for raw in lines:
        line = raw.strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if HEADER_RE.fullmatch(line):
            continue
        if PAGE_NUM_RE.fullmatch(line):
            continue
        if SECTION_RE.fullmatch(line):
            continue
        if first_page and not started:
            # Skip image-caption noise before the actual title line on opening pages.
            if TITLE_DIGITS_RE.search(line):
                started = True
            continue
        if title in line:
            continue
        cleaned.append(line)

    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned


def normalize_text(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = text.replace("...", "...")
    for source, target in GLOBAL_REPLACEMENTS:
        text = text.replace(source, target)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?- ?\n", "-\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def section_page_ranges() -> list[tuple[int, int, str]]:
    ranges = []
    for index, (start_page, title) in enumerate(TOC_ENTRIES, start=1):
        next_start = TOC_ENTRIES[index][0] if index < len(TOC_ENTRIES) else LAST_PRINTED_PAGE + 1
        ranges.append((start_page, next_start - 1, f"{index:02d} - {title}"))
    return ranges


def build_section_text(start_page: int, end_page: int, file_stem: str) -> str:
    title = file_stem.split(" - ", 1)[1]
    page_blocks: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        for i, printed_page in enumerate(range(start_page, end_page + 1)):
            pdf_page_num = printed_page + PRINTED_TO_PDF_OFFSET
            image_path = render_page(pdf_page_num, tmpdir_path / f"page_{printed_page}")
            raw = ocr_image(image_path)
            lines = raw.splitlines()
            cleaned_lines = clean_lines(lines, first_page=(i == 0), title=title)
            if i == 0:
                cleaned_lines = [f"❖ {title}"] + cleaned_lines
            page_blocks.append("\n".join(cleaned_lines).strip())
    return normalize_text("\n\n".join(block for block in page_blocks if block))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for start_page, end_page, file_stem in section_page_ranges():
        text = build_section_text(start_page, end_page, file_stem)
        output_path = OUTPUT_DIR / f"{sanitize_filename(file_stem)}.txt"
        output_path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {output_path.name} from printed pages {start_page}-{end_page}")


if __name__ == "__main__":
    main()
