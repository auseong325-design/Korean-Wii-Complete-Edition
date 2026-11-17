"""Self-made Korean test pages for the Internet Channel local test build.

  .venv\\Scripts\\python.exe scripts\\make_internet_feed.py --revision 1

Writes workspace/channels/internet/local-feed-v1 (create-once): static HTML in
UTF-8 and EUC-KR, a fictional search result page for the redirected search
template, routes.tsv (method/path, file, Content-Type) and a fixture manifest.
No form, upload, order or posting endpoint exists; unknown paths return 404.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PANGRAM = '다람쥐 헌 쳇바퀴에 타고파.'
BODY = [
    ('h2', '1. 글자 크기와 굵기'),
    ('p', '<big>큰 글자: 인터넷 채널 한국어 시험</big><br>보통 글자: 인터넷 채널 한국어 시험<br><small>작은 글자: 인터넷 채널 한국어 시험</small>'),
    ('p', '<b>굵게</b>, <i>기울임</i>, <u>밑줄</u>, <a href="/">색인으로 돌아가기</a>'),
    ('h2', '2. 문장'),
    ('p', PANGRAM + ' 키스의 고유 조건은 입술끼리 만나야 하고 특별한 기술은 필요치 않다.'),
    ('p', '이 문장은 시험용으로 직접 만든 글입니다. 실제 기사나 서비스 내용이 아닙니다. 줄이 길어지면 화면 폭에 맞게 자동으로 바뀌는지, 띄어쓰기 단위로 자연스럽게 줄이 나뉘는지 확인해 주세요. Wii 리모컨의 + 버튼으로 확대하고 - 버튼으로 축소할 수 있습니다.'),
    ('h2', '3. 숫자, 영문, 기호'),
    ('p', '2026년 10월 28일 (수) 오전 9시 30분 · 가격 1,234원 · 영문 ABC abc 123 · 기호 ※ ★ ○ → ← “따옴표” ‘작은따옴표’ …'),
    ('h2', '4. 목록과 표'),
    ('ul', '<li>첫째 항목: 가나다라마바사</li><li>둘째 항목: 아자차카타파하</li><li>셋째 항목: 까꺄꺼껴꼬꾜꾸뀨끄끼</li>'),
    ('table', '<tr><th>분류</th><th>내용</th></tr><tr><td>자음</td><td>ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ</td></tr><tr><td>모음</td><td>ㅏ ㅑ ㅓ ㅕ ㅗ ㅛ ㅜ ㅠ ㅡ ㅣ</td></tr><tr><td>받침</td><td>값 닭 삶 앉 읽 흙 밟 핥</td></tr>'),
]
UTF8_ONLY = [
    ('h2', '5. 확장 음절과 한자 (알려진 한계 시험)'),
    ('p', 'KS X 1001 밖의 음절: 똠방각하 뷁 쀍 햏'),
    ('p', '한자: 大韓民國 漢字 — 한국어 글꼴에 한자가 없어 네모 또는 빈칸으로 보일 수 있습니다.'),
]


def page(title, blocks, *, charset=None, note='', font=False):
    meta = f'<meta http-equiv="Content-Type" content="text/html; charset={charset}">\n' if charset else ''
    # Opera's web content has no default Korean font; name the channel's Korean
    # web font exactly as the manual's main.css does so glyphs resolve (feed v2+).
    style = "<style type=\"text/css\">body{font-family:'Wii NTLG PGothic Regular',sans-serif;}</style>\n" if font else ''
    parts = [f'<{tag}>{html}</{tag}>' if tag != 'table' else f'<table border="1" cellpadding="4">{html}</table>' for tag, html in blocks]
    return ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">\n<html lang="ko">\n<head>\n' + meta + style +
            f'<title>{title}</title>\n</head>\n<body>\n<h1>{title}</h1>\n' + (f'<p>{note}</p>\n' if note else '') +
            '\n'.join(parts) + '\n<p><a href="/">KWCE 시험 색인</a></p>\n</body>\n</html>\n')


def files(font=False, error_links=False):
    # Revision 3 adds links whose targets make Opera draw its own error pages, so long
    # error headings (build-v7 line breaks) can be reviewed. Revisions 1/2 are unchanged.
    errors = ('<li><a href="telnet://127.0.0.2/">지원하지 않는 형식의 주소 (오류 제목 시험 1)</a></li>'
              '<li><a href="gopher://127.0.0.2/">지원하지 않는 형식의 주소 (오류 제목 시험 2)</a></li>'
              '<li><a href="http://127.0.0.2:99999/">잘못된 포트 번호 (오류 제목 시험 3)</a></li>'
              '<li><a href="https://127.0.0.3/">응답하지 않는 보안 주소 (오류 제목 시험 4)</a></li>') if error_links else ''
    index = page('KWCE 인터넷 채널 시험 색인', [
        ('p', '이 페이지들은 KWCE가 직접 만든 시험용 페이지이며 실제 서비스나 기사가 아닙니다. 주소 http://127.0.0.2 는 이 기기 안에서만 응답합니다.'),
        ('ul', '<li><a href="/utf8.html">한글 시험 (UTF-8)</a></li>'
               '<li><a href="/euckr.html">한글 시험 (EUC-KR, 문자 집합 선언 있음)</a></li>'
               '<li><a href="/euckr-nometa.html">한글 시험 (EUC-KR, 선언 없음)</a></li>'
               '<li><a href="/search/search?k=test">검색 결과 화면 시험 (가상 데이터)</a></li>'
               '<li><a href="/missing.html">없는 페이지 (404 오류 시험)</a></li>'
               '<li><a href="http://127.0.0.3/">응답하지 않는 주소 (연결 오류 시험)</a></li>' + errors),
    ], charset='utf-8', font=font)
    utf8 = page('한글 시험 (UTF-8)', BODY + UTF8_ONLY, charset='utf-8', note='문자 집합: UTF-8 (HTTP 헤더와 meta 모두 선언)', font=font)
    euc = page('한글 시험 (EUC-KR)', BODY, charset='euc-kr', note='문자 집합: EUC-KR (HTTP 헤더와 meta 모두 선언)', font=font)
    nometa = page('한글 시험 (EUC-KR, 선언 없음)', BODY, note='문자 집합 선언이 없습니다. 브라우저의 기본(자동) 인코딩 동작을 확인하는 페이지입니다.', font=font)
    search = page('검색 결과 (시험용 가상 데이터)', [
        ('p', '검색 서비스 주소가 이 시험 서버로 바뀐 로컬 빌드에서만 보이는 화면입니다. 아래 결과는 직접 만든 가상의 항목입니다.'),
        ('ol', '<li><a href="/utf8.html">한글 시험 페이지 (UTF-8)</a> — 가상의 검색 결과 1</li>'
               '<li><a href="/euckr.html">한글 시험 페이지 (EUC-KR)</a> — 가상의 검색 결과 2</li>'
               '<li><a href="/">KWCE 시험 색인</a> — 가상의 검색 결과 3</li>'),
    ], charset='utf-8', font=font)
    return {
        'index.html': (index.encode('utf-8'), 'text/html; charset=utf-8', ['/', '/index.html']),
        'utf8.html': (utf8.encode('utf-8'), 'text/html; charset=utf-8', ['/utf8.html']),
        'euckr.html': (euc.encode('euc_kr'), 'text/html; charset=EUC-KR', ['/euckr.html']),
        'euckr-nometa.html': (nometa.encode('euc_kr'), 'text/html', ['/euckr-nometa.html']),
        'search.html': (search.encode('utf-8'), 'text/html; charset=utf-8', ['/search/search', '/search']),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, choices=[1, 2, 3], default=2)
    args = ap.parse_args()
    out = ROOT / f'workspace/channels/internet/local-feed-v{args.revision}'
    if out.exists():
        raise SystemExit('Existing Internet Channel local feed preserved: ' + str(out))
    out.mkdir(parents=True)
    rows, records = [], []
    for name, (data, ctype, paths) in files(font=args.revision >= 2, error_links=args.revision >= 3).items():
        (out / name).write_bytes(data)
        records.append(dict(path=name, sha256=hashlib.sha256(data).hexdigest(), content_type=ctype, routes=paths))
        rows += [f'* {p}\t{name}\t{ctype}' for p in paths]
    (out / 'routes.tsv').write_text('\n'.join(rows) + '\n', encoding='ascii', newline='\n')
    manifest = dict(revision=args.revision, local_only=True, synthetic=True, fictional=True, external_network=False,
                    accepts_orders_uploads_or_posts=False, host='127.0.0.2', files=records,
                    routes_sha256=hashlib.sha256((out / 'routes.tsv').read_bytes()).hexdigest())
    (out / 'fixture-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('Wrote', out.relative_to(ROOT).as_posix(), len(records), 'pages,', len(rows), 'routes')


if __name__ == '__main__':
    main()
