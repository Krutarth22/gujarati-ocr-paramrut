"""Clean OCR debris from the final Swamiji TXT while preserving Gujarati text."""

from __future__ import annotations

import re
from pathlib import Path


INPUT = Path("outputs/Swamiji_na_Prasango_2_FINAL.txt")
BACKUP = Path("outputs/Swamiji_na_Prasango_2_FINAL.raw.bak")


GUJ_RE = re.compile(r"[\u0A80-\u0AFF]")
PAGE_RE = re.compile(r"^\[Page \d+\]$")


def clean_line(line: str) -> str:
    if PAGE_RE.match(line.strip()):
        return line.strip()

    line = line.replace("\u200c", "").replace("\u200d", "")
    line = line.replace("।", ".").replace("॥", ".")
    line = line.replace("—", "-")

    # Remove OCR fragments from handwritten English annotations and random Latin
    # guesses. The source is Gujarati; page markers are handled above.
    line = re.sub(r"\b[A-Za-z]{1,}\b", " ", line)

    # Drop common symbol debris that does not belong in the Gujarati prose.
    line = re.sub(r"[|_@#$%^&*=+<>€~`₹£¥©°«»{}]", " ", line)

    # Remove isolated punctuation or single non-Gujarati OCR leftovers at ends.
    line = re.sub(r"\s+([,.;:?!])", r"\1", line)
    line = re.sub(r"([“‘(\[])\s+", r"\1", line)
    line = re.sub(r"\s+([”’)\]])", r"\1", line)
    line = re.sub(r"\s{2,}", " ", line).strip()
    line = re.sub(r"^[,.;:?!\-/ ]+", "", line)
    line = re.sub(r"[,.;:?!\-/ ]+$", "", line)

    return line


def should_keep(line: str) -> bool:
    if not line:
        return False
    if PAGE_RE.match(line):
        return True
    return bool(GUJ_RE.search(line))


def main() -> int:
    original = INPUT.read_text(encoding="utf-8")
    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")

    cleaned_lines = []
    previous_blank = False

    for raw_line in original.splitlines():
        if not raw_line.strip():
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue

        line = clean_line(raw_line)
        if not should_keep(line):
            continue

        cleaned_lines.append(line)
        previous_blank = False

    cleaned = "\n".join(cleaned_lines).rstrip() + "\n"
    INPUT.write_text(cleaned, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
