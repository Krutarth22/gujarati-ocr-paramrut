import re
from pathlib import Path

from pypdf import PdfReader


PDF_PATH = Path("uploads/Akshar Amrutam 2025.pdf")
OUTPUT_DIR = Path("outputs/Akshar Amrutam 2025 txt")
PRINTED_TO_PDF_OFFSET = 14
LAST_PRINTED_PAGE = 176

TOC_ENTRIES = [
    (1, "૦૮ ડિસેમ્બર ૨૦૨૪, અંબરીષ ઉત્થાન યાત્રા, બ્રેન્ટફોર્ડ"),
    (8, "૨૨ માર્ચ ૨૦૨૫, અંબરીષ ઉત્થાન યાત્રા, ટોરોન્ટો મંદિર"),
    (17, "૦૮ જુલાઈ ૨૦૨૫, ઉતારે, બ્રેમ્પ્ટન"),
    (23, "૦૯ જુલાઈ ૨૦૨૫, યુવકોને ગોષ્ઠી, બ્રેમ્પ્ટન"),
    (26, "૧૦ જુલાઈ ૨૦૨૫, ગુરુપૂર્ણિમા ઉત્સવ, ટોરોન્ટો મંદિર"),
    (34, "૧૧ જુલાઈ ૨૦૨૫, વિન્નિપેગ, મૂર્તિપ્રતિષ્ઠા મહાપૂજા"),
    (41, "૧૨ જુલાઈ ૨૦૨૫, વિન્નિપેગ, ગુરુપૂર્ણિમા સભા"),
    (51, "૧૨ જુલાઈ ૨૦૨૫, વિન્નિપેગ, મૂર્તિપ્રતિષ્ઠા ઉત્સવ"),
    (60, "૧૬ જુલાઈ ૨૦૨૫, એડમન્ટન, ખાતમુહૂર્ત સભા"),
    (65, "૧૬ જુલાઈ ૨૦૨૫, એડમન્ટન, દર્શન સભા"),
    (74, "૧૮ જુલાઈ ૨૦૨૫, હરિપ્રબોધમ્ પરિવાર શિબિર, કેનેડા (સત્ર ૧)"),
    (83, "૧૯ જુલાઈ ૨૦૨૫, હરિપ્રબોધમ્ પરિવાર શિબિર, કેનેડા (સત્ર ૩)"),
    (93, "૨૦ જુલાઈ ૨૦૨૫, હરિપ્રબોધમ્ પરિવાર શિબિર, કેનેડા (સત્ર ૪)"),
    (105, "૨૨ જુલાઈ ૨૦૨૫, પરિવાર સભા, કિચનર"),
    (114, "૨૩ જુલાઈ ૨૦૨૫, યુવકોને ગોષ્ઠી, લંડન"),
    (117, "૨૫ જુલાઈ ૨૦૨૫, યુવક સભા, જેકશન પોઈન્ટ"),
    (127, "૨૬ જુલાઈ ૨૦૨૫, પૂજા દર્શન, ટોરોન્ટો મંદિર"),
    (132, "૨૬ જુલાઈ ૨૦૨૫, સ્મૃતિદિન સભા, ટોરોન્ટો મંદિર"),
    (142, "૨૭ જુલાઈ ૨૦૨૫, અંબરીષ સભા, ટોરોન્ટો મંદિર"),
    (152, "૩૦ જુલાઈ ૨૦૨૫, અંબરીષ સભા, સ્કારબોરો"),
    (159, "૩૦ જુલાઈ ૨૦૨૫, યુવા સભા, સ્કારબોરો"),
    (164, "૩૧ જુલાઈ ૨૦૨૫, ગુરુહરિ પ્રાગટ્યદિન સભા, ટોરોન્ટો મંદિર"),
    (170, "૧ ઓગસ્ટ ૨૦૨૫, અંબરીષ દીક્ષા, ટોરોન્ટો મંદિર"),
]


def clean_page_text(text: str) -> str:
    text = text.replace("\x00", "")
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^~\s*[^~]+\s*~\s*", "", line)
        if not line:
            continue
        if line == "અક્ષર અમૃતમ્":
            continue
        if re.fullmatch(r"~\s*[^~]+\s*~", line):
            continue
        if line == "p":
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[/:*?\"<>|]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_printed_pages(reader: PdfReader) -> dict[int, str]:
    printed_pages = {}
    for printed_page in range(1, LAST_PRINTED_PAGE + 1):
        pdf_index = printed_page + PRINTED_TO_PDF_OFFSET - 1
        if pdf_index >= len(reader.pages):
            break
        text = reader.pages[pdf_index].extract_text() or ""
        printed_pages[printed_page] = clean_page_text(text)
    return printed_pages


def build_sections(printed_pages: dict[int, str]) -> list[tuple[str, str]]:
    sections = []
    for index, (start_page, title) in enumerate(TOC_ENTRIES, start=1):
        next_start = (
            TOC_ENTRIES[index][0] if index < len(TOC_ENTRIES) else LAST_PRINTED_PAGE + 1
        )
        page_texts = []
        for page_num in range(start_page, next_start):
            text = printed_pages.get(page_num, "").strip()
            if text:
                page_texts.append(text)

        body = "\n\n".join(page_texts).strip()
        sections.append((f"{index:02d} - {title}", body))
    return sections


def main() -> None:
    reader = PdfReader(str(PDF_PATH))
    printed_pages = extract_printed_pages(reader)
    sections = build_sections(printed_pages)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for file_stem, body in sections:
        output_path = OUTPUT_DIR / f"{sanitize_filename(file_stem)}.txt"
        output_path.write_text(body + "\n", encoding="utf-8")

    print(f"Created {len(sections)} files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
