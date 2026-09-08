"""Download pinned official Tesseract best models into an explicit local folder."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True, help='Full commit SHA from tesseract-ocr/tessdata_best')
    parser.add_argument('--output', type=Path, default=Path('models/tessdata_best'))
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        parser.error('Use a full Git commit SHA, not a moving branch name.')
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'repository': 'tesseract-ocr/tessdata_best', 'revision': args.revision, 'files': {}}
    for language in ('guj', 'eng'):
        target = args.output / f'{language}.traineddata'
        if target.exists():
            parser.error(f'{target} already exists; choose an empty model directory.')
    for language in ('guj', 'eng'):
        filename = f'{language}.traineddata'
        url = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{args.revision}/{filename}'
        with urlopen(url, timeout=60) as response:
            data = response.read()
        (args.output / filename).write_bytes(data)
        manifest['files'][filename] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        print(f'Downloaded {filename} ({len(data)} bytes)')
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
