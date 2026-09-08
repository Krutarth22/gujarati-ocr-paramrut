from unittest.mock import Mock
import pytest
from PIL import Image
from pypdf import PdfWriter
import processor
from page_ranges import parse_page_range


@pytest.mark.parametrize('value', ['0-2', '-1', '2-1', '1,', '99999999999', '1-9999999999', 'x'])
def test_invalid_page_range(value):
    with pytest.raises(ValueError):
        parse_page_range(value, 3)


def test_page_range():
    assert parse_page_range('1-2, 2, 3', 3) == [1, 2, 3]


@pytest.mark.parametrize('failure', [RuntimeError('render failed'), []])
def test_ocr_failure_is_not_success(tmp_path, monkeypatch, failure):
    source = tmp_path / 'input.pdf'
    source.write_bytes(b'%PDF-')
    output = tmp_path / 'result.docx'
    job = processor.GujaratiPDFProcessor(str(source), str(output), text_only=True)
    monkeypatch.setattr(job, 'get_total_pages', lambda: 1)
    renderer = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
    monkeypatch.setattr(processor, 'convert_from_path', renderer)
    progress = Mock()
    with pytest.raises(RuntimeError, match='page 1'):
        job.process(progress)
    assert not output.exists()
    assert not any(call.args[0] == 100 for call in progress.call_args_list)


def test_later_page_failure_does_not_publish_partial_document(tmp_path, monkeypatch):
    source = tmp_path / 'input.pdf'
    source.write_bytes(b'%PDF-')
    output = tmp_path / 'result.docx'
    job = processor.GujaratiPDFProcessor(str(source), str(output), text_only=True)
    monkeypatch.setattr(job, 'get_total_pages', lambda: 2)
    monkeypatch.setattr(processor, 'convert_from_path', Mock(side_effect=[[Image.new('RGB', (10, 10))], RuntimeError('bad page')]))
    monkeypatch.setattr(job, '_extract_page_text', lambda **_: 'Gujarati text')
    with pytest.raises(RuntimeError, match='page 2'):
        job.process()
    assert not output.exists()


def test_shrilipi_txt_pipeline(tmp_path):
    source = tmp_path / 'input.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(str(source))
    job = processor.GujaratiPDFProcessor(str(source), str(tmp_path / 'result.docx'),
        mode=processor.ProcessingMode.SHRILIPI, output_format='txt')
    job.process()
    assert (tmp_path / 'result.docx').exists()
    assert (tmp_path / 'result.txt').exists()
