"""Second-pass cleanup for stray OCR artifacts in the final Gujarati TXT."""

from __future__ import annotations

import re
from pathlib import Path


INPUT = Path("outputs/Swamiji_na_Prasango_2_FINAL.txt")
BACKUP = Path("outputs/Swamiji_na_Prasango_2_FINAL.before_artifact_pass.bak")

PAGE_RE = re.compile(r"^\[Page \d+\]$")
GUJ = "\u0A80-\u0AFF"
ASCII_TO_GUJ_DIGITS = str.maketrans("0123456789", "૦૧૨૩૪૫૬૭૮૯")


def remove_isolated_artifact_digits(line: str) -> str:
    # Single ASCII digits floating in Gujarati prose are usually annotation/OCR
    # debris. Keep list markers like "1." for later digit conversion.
    line = re.sub(rf"(?<=[{GUJ}.,!?;:)\]”’])\s+[0-9](?=\s+[{GUJ}])", " ", line)
    line = re.sub(rf"(?<=[{GUJ}])\s+[0-9](?=\s*(?:$|[.?!,;:)\]”’]))", "", line)
    line = re.sub(rf"^[0-9]\s+(?=[{GUJ}])", "", line)
    return line


def remove_stray_latin(line: str) -> str:
    # The main cleanup removed words with 2+ Latin letters. Remove leftover
    # single Latin characters that sit in Gujarati prose.
    line = re.sub(rf"(?<=[{GUJ}.,!?;:)\]”’])\s+[A-Za-z](?=\s+[{GUJ}])", " ", line)
    line = re.sub(rf"(?<=[{GUJ}])\s+[A-Za-z](?=\s*(?:$|[.?!,;:)\]”’]))", "", line)
    line = re.sub(rf"^[A-Za-z]\s+(?=[{GUJ}])", "", line)
    return line


def clean_line(line: str) -> str:
    if PAGE_RE.match(line):
        return line

    line = remove_isolated_artifact_digits(line)
    line = remove_stray_latin(line)

    # Convert remaining ASCII digits to Gujarati numerals so real numbers remain
    # readable and visually consistent with the Gujarati text.
    line = line.translate(ASCII_TO_GUJ_DIGITS)

    line = re.sub(r"\s+([,.;:?!])", r"\1", line)
    line = re.sub(r"\s{2,}", " ", line).strip()
    line = re.sub(r"[,;:?!\-/ ]+$", "", line)
    return line


def main() -> int:
    original = INPUT.read_text(encoding="utf-8")
    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")

    cleaned = "\n".join(clean_line(line) for line in original.splitlines()).rstrip() + "\n"
    INPUT.write_text(cleaned, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
