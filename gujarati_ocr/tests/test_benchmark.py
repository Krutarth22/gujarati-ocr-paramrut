import json
from pathlib import Path
import pytest
from PIL import Image
from benchmark_ocr import score_text, summarize, load_samples, normalize_text
from ocr_profiles import tesseract_config, deskew_image
from processor import GujaratiPDFProcessor


def test_vowel_marks_count_as_errors():
    score = score_text('કિ', 'ક')
    assert score['character_edits'] == 1
    assert score['cer'] == .5


def test_whitespace_normalization():
    assert score_text('એક\nબે', 'એક બે')['cer'] == 0
    assert normalize_text('કિ') != normalize_text('કી')


def test_insertions_can_exceed_one_hundred_percent():
    assert score_text('ક', 'કખગઘ')['cer'] == 3


def test_ocr_reference_is_not_accuracy():
    rows = [dict(profile='baseline', split='tune', seconds=1,
                 ocr_reference_disagreement=score_text('ક', 'ક'))]
    result = summarize(rows)[0]
    assert result['scored_pages'] == 0
    assert result['cer'] is None


def test_failed_pages_and_validation_are_separate():
    rows = [dict(profile='best', split='tune', seconds=1, accuracy=score_text('ક', 'ક')),
            dict(profile='best', split='validation', seconds=1, error='OCR failed')]
    results = {r['split']: r for r in summarize(rows)}
    assert results['tune']['cer'] == 0
    assert results['validation']['cer'] is None
    assert results['validation']['failed_pages'] == 1


def test_invalid_reference_label_rejected(tmp_path):
    (tmp_path / 'book.pdf').write_bytes(b'pdf')
    manifest = tmp_path / 'samples.json'
    manifest.write_text(json.dumps({'samples': [dict(id='test', pdf='book.pdf', page=1,
        reference='text.txt')]}))
    with pytest.raises(ValueError, match='explicitly labeled'):
        load_samples(manifest)


def test_profile_preserves_faint_pixels(tmp_path):
    source = tmp_path / 'source.pdf'
    source.touch()
    job = GujaratiPDFProcessor(str(source), str(tmp_path / 'out.docx'), preprocessing='grayscale')
    img = Image.new('RGB', (20, 20), (200, 200, 200))
    prepared = job._preprocess_image(img)
    assert prepared.getpixel((0, 0)) == 200
    assert prepared.size == img.size


def test_model_config_quotes_spaces(tmp_path):
    config = tesseract_config(6, 'sauvola', tmp_path / 'model files')
    import shlex
    tokens = shlex.split(config)
    assert tokens[tokens.index('--tessdata-dir') + 1] == str(tmp_path / 'model files')
    assert 'thresholding_method=2' in tokens
    assert '--oem 1' in config


def test_blank_deskew_is_unchanged():
    img = Image.new('RGB', (200, 200), 'white')
    assert deskew_image(img) is img


def test_missing_model_fails_early(tmp_path):
    source = tmp_path / 'source.pdf'
    source.touch()
    with pytest.raises(ValueError, match='Missing traineddata'):
        GujaratiPDFProcessor(str(source), str(tmp_path / 'out.docx'), tessdata_dir=str(tmp_path))
