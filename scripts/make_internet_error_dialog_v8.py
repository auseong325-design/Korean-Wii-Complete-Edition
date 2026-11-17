"""Write configs/internet-v8-ko.json: line breaks that fit the Internet Channel error dialog.

  .venv\\Scripts\\python.exe scripts\\make_internet_error_dialog_v8.py [--plan]

Reads the v1 lng translations, the Korean Opera font the build puts in content 4 and the
dialog stylesheets of the pinned USA original (content 2, unchanged by every revision),
plans breaks with kwce.internet_error_dialog and writes the config once. If the config
already exists it is compared, never overwritten. --plan prints the lines only.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import internet_error_dialog as ed  # noqa: E402
from kwce import internet_error_headings as eh  # noqa: E402
from kwce.channels import ChannelArchive, load_library  # noqa: E402
from kwce.internet_build import ORIGINAL, ORIGINAL_SHA256  # noqa: E402
from kwce.internet_opera_font import korean_opera_font  # noqa: E402

OUT = ROOT / 'configs/internet-v8-ko.json'
LNG = 'configs/internet-lng-v1-ko.json'
B = ed.BREAK
# Hand-set lines where the penalty planner's choice reads worse. Each is re-checked
# (spaces only, width) like a planned row.
OVERRIDES = {
    # the substituted protocol / MIME type shares its line only with the code, so a long
    # name cannot push a Korean word over the edge
    '377': f'240016: %s{B}프로토콜은{B}지원하지 않습니다.',
    '376': f'240020: %s{B}파일 형식은{B}지원하지 않습니다.',
    # '더 이상' stays with its clause instead of standing alone
    '35': f'243410:{B}이 주소는 더 이상{B}사용할 수 없습니다.',
    # keep '응답 시간' (response time) together rather than '게이트웨이 응답'
    '45': f'243504:{B}HTTP 게이트웨이{B}응답 시간이{B}초과되었습니다.',
    # keep the cause clause '메모리가 부족해' whole
    '514': f'241001: 메모리가 부족해{B}Flash 내용을{B}표시할 수 없습니다.{B}페이지를{B}다시 불러와 주세요.',
}


def load():
    raw = ORIGINAL.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA256:
        raise SystemExit('USA Internet Channel original differs')
    lib = load_library()
    t = lib.title.Title()
    t.load_wad(raw)
    c4, _ = korean_opera_font(t.get_content_by_index(4))
    c2 = ChannelArchive(t.get_content_by_index(2))
    return eh.Metrics(eh.opera_face(c4)), c2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', action='store_true', help='print the planned lines, write nothing')
    args = ap.parse_args()
    metrics, c2 = load()
    lng_raw = (ROOT / LNG).read_bytes()
    translations = json.loads(lng_raw.decode('utf-8'))['translations']
    rows = ed.plan(translations, metrics, OVERRIDES)
    report = ed.check(rows, translations, metrics, c2)
    if args.plan:
        print('limit', report['limit_em'], 'em; layouts', report['layouts'])
        for index in sorted(rows, key=int):
            row = rows[index]
            lines = row['ko'].split(B)
            print(f'{index:>4} p={row["penalty"]} ' + ' / '.join(f'{ln} ({metrics.em(ln):.2f})' for ln in lines))
        unchanged = [r for r in report['rows'] if not r['changed']]
        print('unchanged coded:', [(r['index'], r['widest_em']) for r in unchanged])
        return
    cfg = dict(
        schema=1,
        purpose='Revision 8: every coded Korean error message is broken (english.lng \\n escape) at phrase boundaries '
                'so each line fits the error dialog text column next to the warning icon (dialog.html), which is '
                'narrower than the error page heading that revision 7 measured.',
        source=dict(lng=LNG, lng_sha256=hashlib.sha256(lng_raw).hexdigest()),
        supersedes='configs/internet-v7-ko.json error_heading_breaks (its error.css h1 white-space: pre-line stays)',
        observation='lead Dolphin review of build-v7 (2026-10-29, 16:9): 240019 and 240016 open the dialog, not the error '
                    'page; 240019 line 2 ended at 형식입니 / 다.; text column starts after the floated warning icon',
        model=dict(font='content 4 Wii NTLG PGothic (styles/wii.css font-family)', bold_factor=ed.BOLD_FACTOR,
                   safety=ed.SAFETY, placeholder=ed.PLACEHOLDER, limit_em=report['limit_em'],
                   page_limit_em=report['page_limit_em'], layouts=report['layouts'],
                   calibration='v7 captures: ink width 1.3-4.3 % above advance sums; 13.31 em fitted the 13.95 em column'),
        error_breaks={k: dict(v1=rows[k]['v1'], ko=rows[k]['ko']) for k in sorted(rows, key=int)},
        overrides=sorted(OVERRIDES, key=int),
        unchanged_coded=[r['index'] for r in report['rows'] if not r['changed']],
    )
    text = json.dumps(cfg, ensure_ascii=False, indent=1) + '\n'
    if OUT.exists():
        same = OUT.read_text(encoding='utf-8') == text
        print(('PASS: ' if same else 'DIFF: ') + f'{OUT.relative_to(ROOT).as_posix()} already exists (not overwritten)')
        if not same:
            raise SystemExit(1)
        return
    OUT.write_text(text, encoding='utf-8')
    print(f'Wrote {OUT.relative_to(ROOT).as_posix()}: {len(rows)} messages, limit {report["limit_em"]} em, '
          f'max {report["max_lines"]} lines, widest {report["widest_em"]} em')


if __name__ == '__main__':
    main()
