import io
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import app as api

TOKEN = 'test-token-' + 'x' * 32


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('OCR_API_TOKEN', TOKEN)
    monkeypatch.setattr(api, 'UPLOAD_DIR', tmp_path / 'uploads')
    monkeypatch.setattr(api, 'OUTPUT_DIR', tmp_path / 'outputs')
    monkeypatch.setattr(api, 'reserve_job', Mock(return_value=True))
    monkeypatch.setattr(api, 'release_job', Mock())
    monkeypatch.setattr(api.process_task, 'apply_async', Mock())
    monkeypatch.setattr(api, 'pdfinfo_from_path', Mock(return_value={'Pages': 3}))
    with TestClient(api.app, headers={'Authorization': f'Bearer {TOKEN}'}) as client:
        yield client


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def upload(client, name='book.pdf', **options):
    return client.post('/upload', files={'file': (name, pdf(), 'application/pdf')}, data=options)


def test_auth_before_body(client):
    response = client.post('/upload', content=b'invalid', headers={'Authorization': ''})
    assert response.status_code == 401
    assert not list(api.UPLOAD_DIR.iterdir())


def test_missing_token_fails_startup(monkeypatch):
    monkeypatch.delenv('OCR_API_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='OCR_API_TOKEN'):
        with TestClient(api.app):
            pass


def test_traversal_and_same_name_jobs_are_isolated(client, tmp_path):
    responses = [upload(client, '../escaped.pdf') for _ in range(2)]
    assert all(r.status_code == 200 for r in responses)
    ids = [r.json()['task_id'] for r in responses]
    assert ids[0] != ids[1]
    assert not (tmp_path / 'escaped.pdf').exists()
    for task_id in ids:
        assert (api.UPLOAD_DIR / task_id / 'input.pdf').read_bytes() == pdf()
    for call in api.process_task.apply_async.call_args_list:
        for path in call.kwargs['args'][:3]:
            assert Path(path).resolve().is_relative_to(tmp_path)


def test_options_forwarded(client):
    response = upload(client, mode='shrilipi', output_format='md', page_range='1-2')
    assert response.status_code == 200
    args = api.process_task.apply_async.call_args.kwargs['args']
    assert args[3:6] == ['shrilipi', '1-2', 'md']
    assert args[7].endswith('/result.md')


@pytest.mark.parametrize('options', [dict(page_range='0-2'), dict(page_range='9'), dict(page_range='3-1'), dict(output_format='exe')])
def test_invalid_options_do_not_queue(client, options):
    assert upload(client, **options).status_code == 400
    api.process_task.apply_async.assert_not_called()
    assert not list(api.UPLOAD_DIR.iterdir())


def test_oversized_file_is_removed(client, monkeypatch):
    monkeypatch.setattr(api, 'MAX_UPLOAD_BYTES', 10)
    assert upload(client).status_code == 413
    assert not list(api.UPLOAD_DIR.iterdir())
    api.release_job.assert_called_once()


def test_oversized_request_rejected_before_parse(client):
    response = client.post('/upload', content=b'x', headers={'Content-Length': str(api.MAX_UPLOAD_BYTES + 2 * 1024**2)})
    assert response.status_code == 413


def test_queue_full(client):
    api.reserve_job.return_value = False
    assert upload(client).status_code == 429
    api.process_task.apply_async.assert_not_called()


def test_invalid_pdf_and_metadata_cleanup(client):
    api.pdfinfo_from_path.side_effect = RuntimeError('sensitive internal path')
    for endpoint in ('/upload', '/pdf-info'):
        response = client.post(endpoint, files={'file': ('test.pdf', pdf())})
        assert response.status_code == 400
        assert 'sensitive' not in response.text
    assert not list(api.UPLOAD_DIR.iterdir())
    assert not list(api.OUTPUT_DIR.iterdir())


def test_page_limit(client, monkeypatch):
    monkeypatch.setattr(api, 'MAX_PAGES', 2)
    assert upload(client).status_code == 400
    api.process_task.apply_async.assert_not_called()


@pytest.mark.parametrize('ext', ['txt', 'md', 'docx', 'pdf'])
def test_authenticated_downloads_and_formats(client, monkeypatch, ext):
    task_id = upload(client).json()['task_id']
    (api.OUTPUT_DIR / task_id / f'result.{ext}').write_bytes(b'output')
    monkeypatch.setattr(api.celery_app, 'AsyncResult', lambda _: SimpleNamespace(state='SUCCESS', info={}))
    response = client.get(f'/status/{task_id}')
    assert response.json()['result']['formats'] == [ext]
    assert client.get(f'/download/{task_id}/{ext}').content == b'output'
    assert client.get(f'/download/{task_id}/{ext}', headers={'Authorization': ''}).status_code == 401


def test_failed_job_cannot_download(client, monkeypatch):
    task_id = upload(client).json()['task_id']
    monkeypatch.setattr(api.celery_app, 'AsyncResult', lambda _: SimpleNamespace(state='FAILURE'))
    assert client.get(f'/download/{task_id}/docx').status_code == 400
    assert client.get(f'/status/{task_id}').json()['state'] == 'FAILURE'


def test_cleanup_expired_nested_jobs_only(client):
    old = api.OUTPUT_DIR / str(uuid4())
    old.mkdir()
    (old / 'result.txt').write_text('old')
    os.utime(old, (time.time() - 90000,) * 2)
    recent = api.OUTPUT_DIR / str(uuid4())
    recent.mkdir()
    legacy = api.UPLOAD_DIR / 'legacy.pdf'
    legacy.write_bytes(b'old')
    os.utime(legacy, (time.time() - 90000,) * 2)
    api.cleanup_old_files()
    assert not old.exists()
    assert not legacy.exists()
    assert recent.exists()


def test_forged_content_length_still_bounded(client, monkeypatch):
    monkeypatch.setattr(api, 'MAX_UPLOAD_BYTES', 10)
    response = client.post('/upload', files={'file': ('huge.pdf', b'%PDF-' + b'x' * (2 * 1024**2))}, headers={'Content-Length': '1'})
    assert response.status_code == 413
    api.process_task.apply_async.assert_not_called()


def test_download_symlink_rejected(client, monkeypatch, tmp_path):
    task_id = upload(client).json()['task_id']
    outside = tmp_path / 'private.txt'
    outside.write_text('private')
    (api.OUTPUT_DIR / task_id / 'result.txt').symlink_to(outside)
    monkeypatch.setattr(api.celery_app, 'AsyncResult', lambda _: SimpleNamespace(state='SUCCESS', info={}))
    assert client.get(f'/download/{task_id}/txt').status_code == 404
