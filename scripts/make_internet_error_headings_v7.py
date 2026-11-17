"""Write configs/internet-v7-ko.json: word-boundary breaks for long Korean error headings.

  .venv\\Scripts\\python.exe scripts\\make_internet_error_headings_v7.py

Reads the v1 lng translations and the Korean Opera font that the build puts in
content 4 (kwce.internet_opera_font from the pinned USA original), plans breaks with
kwce.internet_error_headings and writes the config once. If the config already
exists it is compared, never overwritten.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import internet_error_headings as eh  # noqa: E402
from kwce.channels import load_library  # noqa: E402
from kwce.internet_build import ORIGINAL, ORIGINAL_SHA256  # noqa: E402
from kwce.internet_opera_font import korean_opera_font  # noqa: E402

OUT = ROOT / 'configs/internet-v7-ko.json'
LNG = 'configs/internet-lng-v1-ko.json'
# Phrase-aware first lines where the greedy (keep-all) fill would split a unit such as
# '~할 수 없습니다', '지원하지 않는', '더 이상', '너무 깁니다' or '응답 시간이'.
# Each must still fit the width limit (checked below); everything else uses the greedy fill.
PREFERRED_FIRST_LINE = {
    '24': '240019: 알 수 없거나',
    '28': '243500: 서버 또는 파일을',
    '35': '243410: 이 주소는',
    '38': '243413: HTTP 요청 데이터가',
    '45': '243504: HTTP 게이트웨이',
    '51': '240007: 이 파일에',
    '182': '240021: 인터넷 채널에서는',
    '313': '244002: 보안 처리를',
}


def preferred(rows):
    for index, first in PREFERRED_FIRST_LINE.items():
        text = rows[index]['v6']
        if not text.startswith(first + ' '):
            raise SystemExit(f'Preferred first line for entry {index} is not a word prefix')
        rows[index] = dict(v6=text, ko=first + eh.BREAK + text[len(first) + 1:])
    return rows


def main():
    raw = ORIGINAL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA256:
        raise SystemExit('USA Internet Channel original differs')
    lib = load_library()
    t = lib.title.Title()
    t.load_wad(raw)
    c4, _ = korean_opera_font(t.get_content_by_index(4))
    metrics = eh.Metrics(eh.opera_face(c4))
    lng_raw = (ROOT / LNG).read_bytes()
    translations = json.loads(lng_raw.decode('utf-8'))['translations']
    rows = preferred(eh.plan(translations, metrics))
    report = eh.check(rows, translations, metrics)
    two_sentence = sorted(int(k) for k, v in translations.items() if eh.HEADING.match(v) and not eh.single_sentence(v))
    cfg = dict(
        schema=1,
        purpose='Revision 7: long Korean error-page headings get a line break at a word boundary (english.lng \\n escape) '
                'and the error page h1 gets white-space: pre-line, so Opera no longer ends a line inside a word.',
        source=dict(lng=LNG, lng_sha256=hashlib.sha256(lng_raw).hexdigest()),
        error_heading_css=dict(file='styles/error.css', selector='h1', old='font-size: 110%;',
                               new='font-size: 110%;\n\twhite-space: pre-line;'),
        error_heading_css_reason='Opera 9.30 for Wii has no word-break/word-wrap property; pre-line honours the line feed '
                                 'and still wraps a line that is too long, so a narrower layout behaves like v6.',
        model=dict(observed_fits=eh.OBSERVED_FITS, observed_wraps=eh.OBSERVED_WRAPS, observed_scale=eh.OBSERVED_SCALE,
                   target_scale=eh.TARGET_SCALE, safety=eh.SAFETY, placeholder=eh.PLACEHOLDER,
                   observation='lead Dolphin review of build-v5 (h1 130%, 16:9 profile): first line ended at 없습니, second line 다.',
                   limit_em=report['limit_em'], bounds_em=report['bounds_em']),
        error_heading_breaks={k: rows[k] for k in sorted(rows, key=int)},
        kept_two_sentence=two_sentence,
        kept_two_sentence_reason='two-sentence entries may be dialog texts (certificate question, Flash memory); unchanged',
    )
    text = json.dumps(cfg, ensure_ascii=False, indent=1) + '\n'
    if OUT.exists():
        same = OUT.read_text(encoding='utf-8') == text
        print(('PASS: ' if same else 'DIFF: ') + f'{OUT.relative_to(ROOT).as_posix()} already exists (not overwritten)')
        if not same:
            raise SystemExit(1)
        return
    OUT.write_text(text, encoding='utf-8')
    print(f'Wrote {OUT.relative_to(ROOT).as_posix()}: {len(rows)} headings, limit {report["limit_em"]} em, '
          f'max {report["max_lines"]} lines, kept two-sentence {two_sentence}')


if __name__ == '__main__':
    main()
