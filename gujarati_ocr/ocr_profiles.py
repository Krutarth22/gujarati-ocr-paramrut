"""Explicit OCR settings for reproducible comparisons; no automatic winner selection."""
from pathlib import Path
import shlex
import numpy as np
from PIL import Image

PREPROCESSING = ('legacy', 'grayscale', 'sauvola')


def tesseract_config(psm=4, preprocessing='legacy', tessdata_dir=None):
    if preprocessing not in PREPROCESSING:
        raise ValueError('Unknown preprocessing profile.')
    if psm not in (3, 4, 6, 7):
        raise ValueError('Supported page segmentation modes: 3, 4, 6, 7.')
    config = f'--oem 1 --psm {psm} -c preserve_interword_spaces=1'
    if preprocessing == 'sauvola':
        config += ' -c thresholding_method=2'
    if tessdata_dir:
        config += ' --tessdata-dir ' + shlex.quote(str(Path(tessdata_dir).resolve()))
    return config


def deskew_image(image):
    """Correct small rotations only when horizontal projections improve clearly.

    Estimate on a thumbnail, retain the original resolution for the final image.
    This is opt-in: illustrations and unusual layouts can mislead projection scans.
    """
    gray = image.convert('L')
    sample = gray.copy()
    sample.thumbnail((900, 1200))
    if min(sample.size) < 20:
        return image
    mask = sample.point(lambda value: 255 if value < 160 else 0)

    def score(angle):
        rotated = mask.rotate(angle, resample=Image.Resampling.NEAREST, fillcolor=0)
        rows = np.asarray(rotated, dtype=np.float32).sum(axis=1)
        return float(np.square(np.diff(rows)).sum())

    baseline = score(0)
    angles = np.arange(-3.0, 3.01, 0.25)
    best_angle = max(angles, key=score)
    if abs(best_angle) < .25 or score(best_angle) <= baseline * 1.15:
        return image
    return image.rotate(float(best_angle), resample=Image.Resampling.BICUBIC,
                        expand=True, fillcolor='white')
