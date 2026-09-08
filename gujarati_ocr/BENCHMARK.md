# Gujarati OCR accuracy comparison

A better model or preprocessing setting is a candidate, not a proven upgrade.
Measure on the actual books before changing the service defaults. The initial
matrix compares the deployed text pipeline with official tessdata_best models,
grayscale, Sauvola binarization, page segmentation 3/4/6, and optional deskew.

## Prepare a representative sample

Choose 15-20 pages from the original PDFs: clean body text, small text, faint
printing, skewed scans, headings/dates, and complex layouts. Use PDF page numbers,
not printed page numbers. Reserve at least five pages as `validation` and avoid
using those pages to select parameters. If evaluating multiple books, represent
each book in both splits.

Put private inputs and references in the ignored `benchmarks/` directory.
Create a UTF-8 transcript for each page, matching its entire visible printed text
and reading order, including headers, footers, and page numbers. Have a Gujarati
reader verify it. Do not call unreviewed Vision or other OCR output ground truth.
OCR references can be used provisionally with `reference_kind: "ocr"`; the report
labels their differences as disagreement and excludes them from accuracy scores.
Without references the tool saves outputs and timings, but accuracy is unmeasured.

Example local `benchmarks/books/samples.json`:

```json
{
  "samples": [
    {
      "id": "book1-page10",
      "pdf": "book1.pdf",
      "page": 10,
      "reference": "book1-page10.txt",
      "reference_kind": "manual",
      "split": "tune"
    },
    {
      "id": "book1-page25",
      "pdf": "book1.pdf",
      "page": 25,
      "reference": "book1-page25.txt",
      "reference_kind": "manual",
      "split": "validation"
    }
  ]
}
```

Paths resolve relative to the manifest. For an individual scan use `image`
instead of `pdf` and omit `page`. Images retain their native pixel dimensions;
`--dpi` controls PDF rasterization only. Keep validation samples in a separate
manifest while tuning to avoid repeatedly looking at validation results.

## Install and run

From `gujarati_ocr/`:

```bash
pip install -r requirements-benchmark.txt
python download_best_models.py \
  --revision e12c65a915945e4c28e237a9b52bc4a8f39a0cec \
  --output models/tessdata_best
python benchmark_ocr.py benchmarks/books/samples.json \
  --best-model-dir models/tessdata_best \
  --output benchmarks/run-01
```

Model downloads come from the pinned official `tesseract-ocr/tessdata_best`
commit, not a third-party model source. A model manifest records file hashes.
Do not replace your system Tesseract model files: candidates use an explicit
model directory. Tesseract 5 is required for Sauvola binarization.

Use `--profiles baseline,best-gray-4` for a narrow comparison and `--lang guj`
to compare Gujarati-only recognition with the default `guj+eng`. Run alternative
DPI values in separate output directories. Defaults match the web worker's
300 DPI and language setting. Avoid changing language, DPI, preprocessing, and
model together without comparing intermediate candidates.

Outputs include a Markdown report, JSON metrics, source/preprocessed images,
and per-page predicted text. Each run records Tesseract version, model hashes,
source hashes, profile settings, and reference hashes. Use a new output directory
for every run. Timing includes preprocessing, recognition, and any metadata
refinement, but excludes PDF rendering. The baseline includes the existing
metadata refinement; experimental grayscale profiles disable it explicitly.
Deskew disables metadata crop refinement because rotations change coordinates.

Character error rate is edit distance divided by reference character count,
after NFC normalization and whitespace normalization. Gujarati vowel marks,
digits, punctuation, and joiners are preserved. Results also contain word error
rate. Failed pages stay visible and are not silently scored as successful.
A profile with low CER and failed pages is not a winner. No references means no
accuracy claim. Synthetic test inputs establish execution only, not real-book
quality. Visually check omitted lines, religious names, dates, and vowel marks.

## Optional Google Vision comparison

Use your own Google credentials and explicitly opt in:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/local-key.json
python benchmark_ocr.py benchmarks/books/samples.json \
  --best-model-dir models/tessdata_best \
  --output benchmarks/run-with-vision --vision
```

This uploads selected page images to Google and makes one billable OCR request
per sample (at most 20 per run; SDK retries are disabled). It never sends entire
books. Vision is scored against the same manual references as Tesseract. Without
`--vision`, this benchmark sends no documents to any cloud service. Mistral/Azure
are not automatically contacted. Avoid automatic cloud fallback until a labeled
sample establishes a useful failure-detection rule; Tesseract confidence alone
is not calibrated accuracy.

## Apply a measured profile

The service stays on `legacy` unless you explicitly configure a candidate:

```bash
export OCR_PREPROCESSING=grayscale
export OCR_PSM=4
export OCR_LANG=guj+eng
export OCR_TESSDATA_DIR="$PWD/models/tessdata_best"
export OCR_DESKEW=0
```

Restart the worker after changing settings. For Compose the host's `./models`
folder is mounted read-only at `/app/models`; set `OCR_TESSDATA_DIR` to the
container path `/app/models/tessdata_best`. CLI equivalents are `--preprocessing`,
`--ocr_psm`, `--lang`, `--tessdata_dir`, and `--deskew`. PDF text layers and text
extraction now receive the same model/segmentation/threshold settings; subsequent
text-only cleanup can still change DOCX/TXT content.

Sources: [Tesseract quality guide](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
and [official model documentation](https://tesseract-ocr.github.io/tessdoc/Data-Files.html).
