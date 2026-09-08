"""
Audit converted Pardarshi Paravani text for Shri Lipi residue.

Usage:
  python audit_pardarshi_paravani.py
  python audit_pardarshi_paravani.py --root "outputs/Pardarshi Paravani"
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_ROOT = Path("outputs/Pardarshi Paravani")

ALLOWED_ASCII = set(" \n\t\r.,;:!?(){}'\"-/\\%–—+*=…")
ALLOWED_EXTRA = {"।"}  # old half marker emitted from Shri Lipi &&/&.

CHECKS = {
    "latin_letters": re.compile(r"[A-Za-z]"),
    "private_use": re.compile(r"[\ue000-\uf8ff]"),
    "replacement_char": re.compile("\ufffd"),
    "ascii_digits": re.compile(r"[0-9]"),
    "dangling_virama_space": re.compile(
        r"્[ \t]+(?=[\u0a85-\u0ab9\u0ae0-\u0ae1\u0abe-\u0ac5\u0ac7-\u0ac9\u0acb-\u0acc])"
    ),
    "space_before_matra": re.compile(
        r"[\u0a85-\u0ab9\u0ae0-\u0ae1][ \t]+"
        r"[\u0abe-\u0ac5\u0ac7-\u0ac9\u0acb-\u0acd]"
    ),
    "double_virama": re.compile(r"્{2,}"),
}


def is_allowed_char(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        0x0A80 <= codepoint <= 0x0AFF
        or ch in ALLOWED_ASCII
        or ch in ALLOWED_EXTRA
    )


def snippet(text: str, start: int, end: int) -> str:
    return text[max(0, start - 35): min(len(text), end + 35)].replace("\n", "⏎")


def audit(root: Path) -> int:
    files = sorted(root.rglob("*.txt"))
    suspicious_chars: Counter[str] = Counter()
    char_locations: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    check_counts: Counter[str] = Counter()
    check_locations: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for path in files:
        text = path.read_text(encoding="utf-8")
        for index, ch in enumerate(text):
            if is_allowed_char(ch):
                continue
            suspicious_chars[ch] += 1
            if len(char_locations[ch]) < 5:
                line = text.count("\n", 0, index) + 1
                char_locations[ch].append((str(path), line, snippet(text, index, index + 1)))

        for name, regex in CHECKS.items():
            for match in regex.finditer(text):
                check_counts[name] += 1
                if len(check_locations[name]) < 5:
                    line = text.count("\n", 0, match.start()) + 1
                    check_locations[name].append(
                        (str(path), line, snippet(text, match.start(), match.end()))
                    )

    print(f"Files audited: {len(files)}")

    if suspicious_chars:
        print("\nSuspicious characters:")
        for ch, count in suspicious_chars.most_common():
            name = unicodedata.name(ch, "UNKNOWN")
            print(f"  {ch!r} U+{ord(ch):04X} {name}: {count}")
            for path, line, sample in char_locations[ch]:
                print(f"    {path}:{line}: {sample}")
    else:
        print("Suspicious characters: 0")

    failing_checks = {name: count for name, count in check_counts.items() if count}
    if failing_checks:
        print("\nPattern failures:")
        for name, count in sorted(failing_checks.items()):
            print(f"  {name}: {count}")
            for path, line, sample in check_locations[name]:
                print(f"    {path}:{line}: {sample}")
    else:
        print("Pattern failures: 0")

    return 1 if suspicious_chars or failing_checks else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    return audit(args.root)


if __name__ == "__main__":
    sys.exit(main())
