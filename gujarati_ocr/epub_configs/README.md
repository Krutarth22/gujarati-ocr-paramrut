# OCR EPUB builder

`build_ocr_epub.py` turns UTF-8 OCR text with page markers into an EPUB with a
title page, visible contents page, reader navigation, separate chapter files,
and original page-break locations.

Use the Aatma Khoj preset from the `gujarati_ocr` directory:

```bash
python build_ocr_epub.py --config epub_configs/atma_khoj_2000.json
```

For another book, either copy the JSON preset and change its metadata, paths,
and chapter page ranges, or supply everything on the command line:

```bash
python build_ocr_epub.py \
  --source outputs/book_ocr.txt \
  --output outputs/Book.epub \
  --title "Book title" \
  --author "Author" \
  --language gu \
  --chapter "1-10|First chapter|Date|Optional note" \
  --chapter "11-20|Second chapter"
```

Repeat `--author` for multiple creators. Use
`--chapter-header NUMBER=ALTERNATE_TEXT` when an OCR running header differs
from its chapter title. `--chapter-date` and `--chapter-note` can override
chapter metadata from a JSON config. Run `python build_ocr_epub.py --help` for
all options.

The default page marker is `[Page N]`. For another OCR format, pass
`--page-marker-regex` with either a named `page` capture group or a first
numeric capture group.
