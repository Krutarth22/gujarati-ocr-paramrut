import re
import shutil
from pathlib import Path


ORIGINAL = Path("outputs/Swamiji_na_Prasango_ocr.txt")
GUJ_ONLY = Path("outputs/Swamiji_na_Prasango_guj_only.txt")
FINAL = Path("outputs/Swamiji_na_Prasango_FINAL_REVIEW.txt")
REPORT = Path("outputs/Swamiji_na_Prasango_FINAL_REVIEW_report.txt")


def split_pages(text: str) -> dict[int, list[str]]:
    pages: dict[int, list[str]] = {}
    current_page = None
    for line in text.splitlines():
        match = re.fullmatch(r"\[Page (\d+)\]", line.strip())
        if match:
            current_page = int(match.group(1))
            pages[current_page] = [line]
            continue
        if current_page is not None:
            pages[current_page].append(line)
    return pages


def count_gujarati(text: str) -> int:
    return sum(1 for ch in text if "\u0A80" <= ch <= "\u0AFF")


def count_latin(text: str) -> int:
    return sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def obvious_debris(line: str) -> bool:
    s = line.strip()
    if not s or re.fullmatch(r"\[Page \d+\]", s):
        return False
    guj = count_gujarati(s)
    latin = count_latin(s)
    symbols = sum(1 for ch in s if ch in "#@€$~`\\|[]_")

    if "Swamiji-prasango" in s or "copy-A5" in s:
        return True
    if "#" in s:
        return True
    if re.fullmatch(r"[%.,:;|_#@€$~`\\/-]+", s):
        return True
    if re.search(r"[A-Za-z]{2,}[-\]\[]", s) and guj < 5:
        return True
    if re.search(r"(?:0\[|૦0|00|€0|%5|45-|45-|A5|AS|-[a-zA-Z0-9]{2,})", s) and guj < 35:
        return True
    if symbols >= 2 and guj < 35:
        return True
    if latin >= 8 and guj < 20:
        return True
    if re.search(r"(?:\s[કખગઘચછજઝટઠડઢતથદધનપફબભમયરલવશષસહ]\s){3,}", s) and len(s) < 90:
        return True
    if len(s) < 18 and re.search(r"[0-9A-Za-z#@€$~`\\|_[\]]", s):
        return True
    return False


def junk_score_line(line: str) -> float:
    s = line.strip()
    if not s or re.fullmatch(r"\[Page \d+\]", s):
        return 0

    guj = count_gujarati(s)
    latin = count_latin(s)
    nonspace = sum(1 for ch in s if not ch.isspace())
    guj_ratio = guj / nonspace if nonspace else 0

    score = 0.0
    if obvious_debris(s):
        score += 200
    score += latin * 3
    score += sum(1 for ch in s if ch in "#@€$~`\\|[]_") * 8
    score += sum(1 for ch in s if ch == "%") * 5
    if nonspace >= 10 and guj_ratio < 0.35:
        score += 40
    if re.search(r"(?:\s[કખગઘચછજઝટઠડઢતથદધનપફબભમયરલવશષસહ]\s){4,}", s):
        score += 60
    if re.search(r"[A-Za-z]{3,}", s):
        score += 25
    if len(re.findall(r"\d|[૦-૯]", s)) >= 8 and guj < 20:
        score += 25
    if len(s) > 120 and (latin or re.search(r"[#@€$~`\\|_]", s)):
        score += 50
    return score


def page_score(lines: list[str]) -> float:
    score = sum(junk_score_line(line) for line in lines)
    text_lines = [line for line in lines if line.strip() and not re.fullmatch(r"\[Page \d+\]", line.strip())]
    guj_chars = sum(count_gujarati(line) for line in text_lines)
    if guj_chars < 80:
        score += 100
    return score


def clean_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    cleaned = []
    removed = []
    for line in lines:
        if obvious_debris(line):
            removed.append(line)
            continue
        cleaned.append(line.rstrip())
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned, removed


def main() -> None:
    original_pages = split_pages(ORIGINAL.read_text(encoding="utf-8"))
    guj_pages = split_pages(GUJ_ONLY.read_text(encoding="utf-8"))

    final_lines = []
    report = [
        "Swamiji na Prasango final review hybrid report",
        f"Original OCR: {ORIGINAL}",
        f"Gujarati-only OCR: {GUJ_ONLY}",
        f"Final review TXT: {FINAL}",
        "",
    ]

    used = {"original": 0, "guj_only": 0}
    removed_count = 0

    for page in range(1, max(max(original_pages), max(guj_pages)) + 1):
        original = original_pages.get(page, [f"[Page {page}]"])
        guj = guj_pages.get(page, [f"[Page {page}]"])
        original_score = page_score(original)
        guj_score = page_score(guj)

        if guj_score + 20 < original_score:
            choice = "guj_only"
            chosen = guj
        else:
            choice = "original"
            chosen = original

        cleaned, removed = clean_lines(chosen)
        if final_lines:
            final_lines.append("")
        final_lines.extend(cleaned)

        used[choice] += 1
        removed_count += len(removed)
        report.append(
            f"Page {page}: {choice} "
            f"(original_score={original_score:.1f}, guj_only_score={guj_score:.1f}, removed={len(removed)})"
        )
        for line in removed:
            report.append(f"  removed: {line}")

    FINAL.write_text("\n".join(final_lines).rstrip() + "\n", encoding="utf-8")
    REPORT.write_text("\n".join(report).rstrip() + "\n", encoding="utf-8")

    print(f"Wrote {FINAL}")
    print(f"Wrote {REPORT}")
    print(f"Pages from original: {used['original']}")
    print(f"Pages from guj_only: {used['guj_only']}")
    print(f"Removed debris lines: {removed_count}")

    # Keep an explicit backup of the prior file name if it exists and is different.
    backup = FINAL.with_name("Swamiji_na_Prasango_FINAL_REVIEW_previous_backup.txt")
    if not backup.exists() and ORIGINAL.exists():
        shutil.copyfile(ORIGINAL, backup)


if __name__ == "__main__":
    main()
