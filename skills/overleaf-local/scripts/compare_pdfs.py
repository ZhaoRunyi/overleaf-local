#!/usr/bin/env python3
"""Compare word coordinates and page renders; requires Poppler and Pillow."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops


def layout(path):
    data = subprocess.check_output(['pdftotext', '-bbox', str(path), '-'])
    root = ET.fromstring(data)
    pages = []
    for page in root.iter():
        if page.tag.rsplit('}', 1)[-1] != 'page':
            continue
        words = [(word.attrib, word.text) for word in page
                 if word.tag.rsplit('}', 1)[-1] == 'word']
        pages.append((page.attrib, words))
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('local', type=Path)
    parser.add_argument('overleaf', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    local_layout, remote_layout = layout(args.local), layout(args.overleaf)
    report = {'pages': [len(local_layout), len(remote_layout)],
              'word_coordinates_and_page_sizes_equal': local_layout == remote_layout,
              'renders': {}}
    with tempfile.TemporaryDirectory(prefix='overleaf-pdf-compare-', dir='/tmp') as temporary:
        directory = Path(temporary)
        for dpi in [180, 300]:
            different = []
            count = max(len(local_layout), len(remote_layout))
            for number in range(1, count + 1):
                if number > min(len(local_layout), len(remote_layout)):
                    different.append(number)
                    continue
                for side, path in [('local', args.local), ('overleaf', args.overleaf)]:
                    subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number),
                                    '-singlefile', '-r', str(dpi), '-png', str(path),
                                    str(directory / side)], check=True, capture_output=True)
                with Image.open(directory/'local.png') as local, Image.open(directory/'overleaf.png') as remote:
                    if local.size != remote.size or ImageChops.difference(local.convert('RGB'), remote.convert('RGB')).getbbox():
                        different.append(number)
            report['renders'][str(dpi)] = {'equal': not different, 'different_pages': different}
    report['passed'] = report['word_coordinates_and_page_sizes_equal'] and all(
        result['equal'] for result in report['renders'].values())
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
