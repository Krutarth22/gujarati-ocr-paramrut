"""
Paravani Prasad scraper.

Fetches the entry index from the live API, downloads each HTML entry,
extracts Gujarati text, and writes output organised by year and date.

Output structure:
  paravani/
    index.json
    2020/
      2020-03-03_Title.txt
      ...
    2021/
      ...
    ...

API: http://dbphp.prabodhswamiji.in/dbjsonpravachan.php
HTML: http://prasang.prabodhswamiji.in/paravani/{PrvFile}
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

from bs4 import BeautifulSoup

INDEX_URL = "http://dbphp.prabodhswamiji.in/dbjsonpravachan.php"
HTML_BASE = "http://prasang.prabodhswamiji.in/paravani/"
OUTPUT = Path("paravani")
DELAY = 0.3   # seconds between requests — be polite to the server


def fetch(url: str, retries: int = 3) -> bytes:
    """Fetch URL with retries."""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=15) as r:
                return r.read()
        except URLError as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def fetch_index() -> list:
    """Fetch and return the full Paravani Prasad index sorted by date."""
    print("Fetching Paravani Prasad index...")
    data = json.loads(fetch(INDEX_URL))
    data.sort(key=lambda e: e["PrvDate"])
    print(f"  {len(data)} entries found ({min(e['PrvDate'] for e in data)} → {max(e['PrvDate'] for e in data)})")
    return data


def extract_text(html: bytes) -> str:
    """Extract Gujarati content from a Paravani HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_="vaat_ind")
    if not div:
        return ""
    for a in div.find_all("a"):
        a.replace_with(a.get_text())
    text = div.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def safe_filename(s: str) -> str:
    """Strip characters that are invalid in filenames."""
    return re.sub(r'[/\\:*?"<>|]', "_", s).strip()


def write_entry(entry: dict, text: str) -> Path:
    """Write one entry to its year folder. Returns the file path."""
    year = entry["PrvYear"]
    date = entry["PrvDate"]
    title = entry.get("PrvTitle", "").strip()
    place = entry.get("PrvPlace", "").strip()
    info = entry.get("PrvInfo", "").strip()

    year_dir = OUTPUT / year
    year_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{date}_{safe_filename(title)}.txt" if title else f"{date}.txt"

    lines = [
        "=" * 64,
        f"PARAVANI PRASAD",
        f"Date  : {date}",
        f"Title : {title}" if title else "",
        f"Place : {place}" if place else "",
        f"Info  : {info}" if info else "",
        "=" * 64,
        "",
        text,
    ]
    lines = [l for l in lines if l != ""]   # drop blank metadata lines

    (year_dir / filename).write_text("\n".join(lines), encoding="utf-8")
    return year_dir / filename


def main():
    entries = fetch_index()

    index = {
        "generated_at": datetime.now().isoformat(),
        "source": INDEX_URL,
        "total_entries": len(entries),
        "years": {},
    }

    failed = []

    print(f"\nDownloading {len(entries)} entries...\n")

    for i, entry in enumerate(entries, 1):
        prv_file = entry.get("PrvFile", "")
        date = entry["PrvDate"]
        year = entry["PrvYear"]
        title = entry.get("PrvTitle", "")

        if not prv_file:
            print(f"  [{i:03d}] SKIP {date} — no file")
            continue

        url = HTML_BASE + prv_file
        try:
            html = fetch(url)
            text = extract_text(html)
            if not text:
                print(f"  [{i:03d}] EMPTY {date} — no content div found")
                failed.append({"date": date, "url": url, "reason": "empty"})
                continue

            path = write_entry(entry, text)

            # Update year index
            if year not in index["years"]:
                index["years"][year] = {"entry_count": 0, "entries": []}
            index["years"][year]["entry_count"] += 1
            index["years"][year]["entries"].append({
                "date": date,
                "title": title,
                "place": entry.get("PrvPlace", ""),
                "file": str(path.relative_to(OUTPUT)),
            })

            print(f"  [{i:03d}] ✓ {date}  {title}")
            time.sleep(DELAY)

        except Exception as e:
            print(f"  [{i:03d}] ✗ {date}  {e}")
            failed.append({"date": date, "url": url, "reason": str(e)})

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n{'='*64}")
    print(f"Done.")
    print(f"  Total  : {len(entries)} entries")
    print(f"  Written: {len(entries) - len(failed)}")
    print(f"  Failed : {len(failed)}")
    print(f"  Output : {OUTPUT}/")
    for year, info in sorted(index["years"].items()):
        print(f"    {year}: {info['entry_count']} entries")
    if failed:
        print(f"\nFailed entries:")
        for f in failed:
            print(f"  {f['date']} — {f['reason']}")


if __name__ == "__main__":
    main()
