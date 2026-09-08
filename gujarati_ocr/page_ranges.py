"""Strict page selection shared by the API and CLI."""
import re


def parse_page_range(value, total_pages):
    if total_pages < 1:
        raise ValueError('PDF must contain at least one page.')
    if not value or not value.strip():
        return list(range(1, total_pages + 1))
    pages = set()
    for part in value.split(','):
        match = re.fullmatch(r'\s*(\d+)\s*(?:-\s*(\d+)\s*)?', part)
        if not match:
            raise ValueError('Use page ranges such as 1-5, 8.')
        start = int(match[1])
        end = int(match[2] or match[1])
        if not 1 <= start <= end <= total_pages:
            raise ValueError(f'Page range must be between 1 and {total_pages}.')
        pages.update(range(start, end + 1))
    return sorted(pages)
