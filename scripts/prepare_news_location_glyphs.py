"""Collect Korean location glyphs from the existing local News replay only.

Only a sorted character inventory and source hashes leave the private feed;
article bodies, images, credentials and original strings are never printed.
"""
import json
import sys
from audit_sd import ROOT, sha256
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.news_data import strings


def main():
    load_library()
    from libWiiPy.archive import decompress_lz77
    root = ROOT / 'workspace/sandbox/news-v1/local-feed/news.wiilink.ca/v2/1/136'
    chars = set()
    rows = []
    count = 0
    for p in sorted(root.glob('news.bin.*')):
        for kind, _, _, text in strings(decompress_lz77(p.read_bytes()[320:])):
            if kind == 'location':
                chars.update(text)
                count += 1
        rows.append(dict(file=p.name, sha256=sha256(p)))
    if len(rows) != 24:
        raise SystemExit('Expected all 24 local News files')
    path = ROOT / 'configs/news-location-glyphs-ko.json'
    if path.exists():
        raise SystemExit('Existing glyph inventory preserved')
    record = dict(glyphs=''.join(sorted(chars)), files=rows,
                  location_references=count, purpose='glyph coverage, not translation review')
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(files=len(rows), location_references=count, unique_characters=len(chars))))


if __name__ == '__main__':
    main()
