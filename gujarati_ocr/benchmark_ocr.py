"""Compare OCR profiles against manually corrected, page-aligned references.

No engine output is treated as ground truth. Sample PDFs, reference text, model
files, and results belong under the ignored benchmarks/ and models/ directories.
"""
import argparse
import hashlib
import io
import json
import re
import subprocess
import time
import unicodedata
from pathlib import Path

from pdf2image import convert_from_path
import pytesseract
from PIL import Image, ImageOps
from rapidfuzz.distance import Levenshtein
from processor import GujaratiPDFProcessor


PROFILES = {
    'baseline': dict(preprocessing='legacy', ocr_psm=4, refine_metadata_lines=True),
    'best-legacy': dict(preprocessing='legacy', ocr_psm=4, refine_metadata_lines=True),
    'best-gray-3': dict(preprocessing='grayscale', ocr_psm=3, refine_metadata_lines=False),
    'best-gray-4': dict(preprocessing='grayscale', ocr_psm=4, refine_metadata_lines=False),
    'best-gray-6': dict(preprocessing='grayscale', ocr_psm=6, refine_metadata_lines=False),
    'best-sauvola-4': dict(preprocessing='sauvola', ocr_psm=4, refine_metadata_lines=False),
    'best-deskew-4': dict(preprocessing='grayscale', ocr_psm=4, deskew=True, refine_metadata_lines=False),
}


def normalize_text(text):
    # Keep vowel marks, punctuation, digits, and joiners. Ignore line wrapping.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def score_text(reference, prediction):
    reference, prediction = normalize_text(reference), normalize_text(prediction)
    if not reference:
        raise ValueError('Reference must contain text; blank pages are not accuracy samples.')
    words, predicted_words = reference.split(), prediction.split()
    edits = Levenshtein.distance(reference, prediction)
    word_edits = Levenshtein.distance(words, predicted_words)
    return dict(character_edits=edits, reference_characters=len(reference),
                cer=edits / len(reference), word_edits=word_edits,
                reference_words=len(words), wer=word_edits / len(words))


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def load_samples(manifest):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    samples = data.get('samples', [])
    if not 1 <= len(samples) <= 20:
        raise ValueError('Choose between 1 and 20 representative pages per run.')
    ids = set()
    for item in samples:
        sample_id = item.get('id', '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', sample_id) or sample_id in ids:
            raise ValueError('Sample IDs must be unique letters, digits, underscores, or hyphens.')
        ids.add(sample_id)
        if bool(item.get('pdf')) == bool(item.get('image')):
            raise ValueError('Each sample needs exactly one pdf or image source.')
        if item.get('image'):
            item['page'] = 1
        if not isinstance(item.get('page'), int) or item['page'] < 1:
            raise ValueError('Pages must be positive, one-based PDF page numbers.')
        if item.get('split', 'tune') not in ('tune', 'validation'):
            raise ValueError('Split must be tune or validation.')
        item['split'] = item.get('split', 'tune')
        item['source_type'] = 'image' if item.get('image') else 'pdf'
        item['pdf'] = (manifest.parent / (item.get('pdf') or item['image'])).resolve()
        if not item['pdf'].is_file():
            raise ValueError(f"Source document is missing for {sample_id}.")
        if item.get('reference'):
            if item.get('reference_kind') not in ('manual', 'ocr'):
                raise ValueError('References must be explicitly labeled manual or ocr.')
            item['reference'] = (manifest.parent / item['reference']).resolve()
            if not item['reference'].is_file():
                raise ValueError(f"Reference text is missing for {sample_id}.")
            if not normalize_text(item['reference'].read_text(encoding='utf-8')):
                raise ValueError(f"Reference text is empty for {sample_id}.")
    return samples


def summarize(rows):
    summary = []
    for split in sorted({row['split'] for row in rows}):
        for profile in sorted({row['profile'] for row in rows}):
            group = [r for r in rows if r['profile'] == profile and r['split'] == split]
            measured = [r for r in group if 'accuracy' in r]
            failed = [r for r in group if 'error' in r]
            characters = sum(r['accuracy']['reference_characters'] for r in measured)
            summary.append(dict(split=split, profile=profile, pages=len(group),
                                failed_pages=len(failed), scored_pages=len(measured),
                                seconds=sum(r['seconds'] for r in group),
                                cer=(sum(r['accuracy']['character_edits'] for r in measured) / characters
                                     if characters else None)))
    return summary


def write_report(output, rows, metadata):
    summary = summarize(rows)
    (output / 'results.json').write_text(json.dumps(dict(metadata=metadata, summary=summary, pages=rows),
                                                   ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# OCR comparison', '',
             'Only manually corrected references contribute to character error rate (CER).',
             'OCR reference disagreement is diagnostic and is not accuracy. Lower CER is better;',
             'CER can exceed 100% when output adds substantial text. Failed pages are listed',
             'separately: never choose a profile by CER alone when it has failed pages.', '',
             '| Split | Profile | Pages | Failed | Scored | CER | Seconds |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in summary:
        cer = f"{row['cer']:.2%}" if row['cer'] is not None else 'Unmeasured'
        lines.append(f"| {row['split']} | {row['profile']} | {row['pages']} | {row['failed_pages']} | {row['scored_pages']} | {cer} | {row['seconds']:.1f} |")
    lines += ['', 'Choose candidates on the tuning split, then verify them on untouched validation',
              'pages. Review missing lines, names, dates, and Gujarati vowel marks visually.',
              'No production defaults are changed by this benchmark.', '',
              'Per-page predictions, review images, hashes, settings, and error details are in',
              '`results.json` and the sample folders. Cloud requests occur only with --vision.']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--best-model-dir', type=Path)
    parser.add_argument('--profiles', default=','.join(PROFILES))
    parser.add_argument('--lang', default='guj+eng')
    parser.add_argument('--dpi', type=int, default=300)
    parser.add_argument('--vision', action='store_true', help='Also send the selected pages to Google Vision (billable)')
    args = parser.parse_args()
    samples = load_samples(args.manifest.resolve())
    profiles = args.profiles.split(',')
    if any(profile not in PROFILES for profile in profiles) or len(set(profiles)) != len(profiles):
        parser.error('Choose unique known profiles: ' + ','.join(PROFILES))
    if not 150 <= args.dpi <= 600:
        parser.error('DPI must be between 150 and 600.')
    if any(p.startswith('best-') for p in profiles):
        if not args.best_model_dir:
            parser.error('--best-model-dir is required for best-* profiles.')
        for lang in args.lang.split('+'):
            if not (args.best_model_dir / f'{lang}.traineddata').is_file():
                parser.error(f'Missing best model for {lang}.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if list(output.iterdir()):
        parser.error('Use an empty output directory to preserve previous runs.')
    hashes = {}
    for sample in samples:
        path = str(sample['pdf'])
        if path not in hashes:
            hashes[path] = digest(path)
    model_hashes = {lang: digest(args.best_model_dir / f'{lang}.traineddata')
                    for lang in args.lang.split('+')} if args.best_model_dir else {}
    listing = subprocess.run([pytesseract.pytesseract.tesseract_cmd, '--list-langs'],
                             capture_output=True, text=True, check=True)
    match = re.search(r'"([^"\n]+)"', listing.stdout + listing.stderr)
    baseline_models = {}
    if match:
        for lang in args.lang.split('+'):
            candidate = Path(match[1]) / f'{lang}.traineddata'
            if candidate.is_file():
                baseline_models[lang] = digest(candidate)
    metadata = dict(baseline_model_sha256=baseline_models, tesseract=str(pytesseract.get_tesseract_version()), dpi=args.dpi,
                    lang=args.lang, profiles={p: PROFILES[p] for p in profiles},
                    source_sha256=hashes, best_model_sha256=model_hashes,
                    manifest_sha256=digest(args.manifest), vision_enabled=args.vision)
    # Validate credentials once; no cloud requests occur during client setup.
    vision_client = None
    if args.vision:
        from google.cloud import vision
        vision_client = vision.ImageAnnotatorClient()
    rows = []
    for sample in samples:
        directory = output / sample['id']
        directory.mkdir()
        if sample['source_type'] == 'image':
            with Image.open(sample['pdf']) as source:
                image = ImageOps.exif_transpose(source).convert('RGB')
        else:
            images = convert_from_path(str(sample['pdf']), dpi=args.dpi,
                                       first_page=sample['page'], last_page=sample['page'],
                                       thread_count=1, timeout=60)
            if len(images) != 1:
                raise ValueError(f"PDF page is missing for {sample['id']}.")
            image = images[0]
        image.save(directory / 'source.png')
        reference = sample['reference'].read_text(encoding='utf-8') if sample.get('reference') else None
        for profile in profiles + (['vision'] if args.vision else []):
            started = time.monotonic()
            row = dict(sample=sample['id'], split=sample['split'], page=sample['page'], profile=profile,
                       reference_kind=sample.get('reference_kind', 'none'))
            try:
                if profile == 'vision':
                    from google.cloud import vision
                    buf = io.BytesIO()
                    image.save(buf, format='PNG')
                    response = vision_client.document_text_detection(
                        image=vision.Image(content=buf.getvalue()), image_context={'language_hints': ['gu']},
                        timeout=120, retry=None)
                    if response.error.message:
                        raise RuntimeError('Google Vision request failed: ' + response.error.message)
                    prediction = response.full_text_annotation.text
                else:
                    processor = GujaratiPDFProcessor(str(sample['pdf']), str(directory / 'unused.docx'),
                        lang=args.lang, dpi=args.dpi, **PROFILES[profile],
                        tessdata_dir=str(args.best_model_dir) if profile.startswith('best-') else None)
                    prepared = processor._preprocess_image(image)
                    prepared_path = directory / f'{profile}.png'
                    prepared.save(prepared_path)
                    prediction = processor._extract_page_text(image, str(prepared_path))
                    row['tesseract_config'] = processor._tesseract_config()
                (directory / f'{profile}.txt').write_text(prediction, encoding='utf-8')
                row['output_characters'] = len(normalize_text(prediction))
                if reference is not None:
                    key = 'accuracy' if sample['reference_kind'] == 'manual' else 'ocr_reference_disagreement'
                    row[key] = score_text(reference, prediction)
                    row['reference_sha256'] = digest(sample['reference'])
            except Exception as exc:
                row['error'] = str(exc)
            row['seconds'] = round(time.monotonic() - started, 3)
            rows.append(row)
            write_report(output, rows, metadata)
            print(f"{sample['id']} / {profile}: {'FAILED' if 'error' in row else 'done'} ({row['seconds']}s)", flush=True)
        image.close()
    print(f'Report: {output / "REPORT.md"}')
    return 1 if any('error' in row for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
