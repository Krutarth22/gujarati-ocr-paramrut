import re
from pathlib import Path


SRC = Path("outputs/Swamiji_na_Prasango_ocr.txt")
AUDIT = Path("outputs/Swamiji_na_Prasango_numbering_audit.txt")
OUT = Path("outputs/Swamiji_na_Prasango_ocr_clean_review.txt")
REPORT = Path("outputs/Swamiji_na_Prasango_cleaning_report.txt")


def count_gujarati(text: str) -> int:
    return sum(1 for ch in text if "\u0A80" <= ch <= "\u0AFF")


def count_latin(text: str) -> int:
    return sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def count_symbols(text: str) -> int:
    return sum(1 for ch in text if ch in '|_#@%^~`€$\\')


def is_page_marker(line: str) -> bool:
    return bool(re.fullmatch(r"\[Page \d+\]", line.strip()))


def is_probable_footer_or_header(line: str) -> bool:
    normalized = line.strip()
    if "Swamiji-prasango" in normalized or "copy-A5" in normalized:
        return True
    if re.fullmatch(r"[%.,:;|_ -]+", normalized):
        return True
    return False


def is_high_confidence_junk(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if is_page_marker(stripped):
        return False
    if is_probable_footer_or_header(stripped):
        return True

    guj = count_gujarati(stripped)
    latin = count_latin(stripped)
    symbols = count_symbols(stripped)
    nonspace = sum(1 for ch in stripped if not ch.isspace())

    if nonspace < 3:
        return True

    guj_ratio = guj / nonspace if nonspace else 0
    latin_ratio = latin / nonspace if nonspace else 0

    # Remove lines that are overwhelmingly OCR debris. This intentionally keeps
    # mixed Gujarati/English lines because some English words are legitimate.
    if guj == 0 and (latin >= 8 or symbols >= 2):
        return True
    if guj_ratio < 0.18 and latin_ratio > 0.45 and nonspace >= 12:
        return True
    if guj_ratio < 0.12 and symbols >= 3 and nonspace >= 10:
        return True
    if re.search(r"(?:[A-Z]{3,}\s+){2,}[A-Z]{3,}", stripped):
        return True

    return False


def parse_audit_markers(audit_text: str) -> dict[int, list[str]]:
    markers: dict[int, list[str]] = {}
    current_missing = None
    for raw_line in audit_text.splitlines():
        missing = re.match(r"Missing between \d+ and \d+: (.+)", raw_line)
        if missing:
            current_missing = missing.group(1)
            continue

        next_line = re.match(r"\s+next:\s+page\s+(\d+),\s+txt line\s+(\d+):\s+(.+)", raw_line)
        if next_line and current_missing:
            page = next_line.group(1)
            line_no = int(next_line.group(2))
            preview = next_line.group(3)
            marker = (
                f"[[REVIEW NUMBERING: expected {current_missing} before this marker "
                f"(page {page}); next detected: {preview}]]"
            )
            markers.setdefault(line_no, []).append(marker)
            current_missing = None
    return markers


def main() -> None:
    source_lines = SRC.read_text(encoding="utf-8").splitlines()
    audit_text = AUDIT.read_text(encoding="utf-8")
    markers_by_line = parse_audit_markers(audit_text)

    output_lines = []
    removed_lines = []
    inserted_markers = 0

    for original_line_no, line in enumerate(source_lines, start=1):
        for marker in markers_by_line.get(original_line_no, []):
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            output_lines.append(marker)
            inserted_markers += 1

        if is_high_confidence_junk(line):
            removed_lines.append((original_line_no, line))
            continue

        output_lines.append(line.rstrip())

    OUT.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")

    report_lines = [
        "Swamiji na Prasango TXT cleanup report",
        f"Source: {SRC}",
        f"Output: {OUT}",
        f"Review markers inserted: {inserted_markers}",
        f"High-confidence junk/header/footer lines removed: {len(removed_lines)}",
        "",
        "Removed lines:",
    ]
    for line_no, line in removed_lines:
        report_lines.append(f"{line_no}: {line}")
    REPORT.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")

    print(f"Wrote {OUT}")
    print(f"Wrote {REPORT}")
    print(f"Review markers inserted: {inserted_markers}")
    print(f"Removed lines: {len(removed_lines)}")


if __name__ == "__main__":
    main()
