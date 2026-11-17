"""Korean Internet Channel error messages: line breaks that fit the error dialog (revision 8).

The lead's build-v7 review showed that 240019 (unknown or unsupported address type) and
240016 (unsupported protocol) are not error pages: Opera opens them in the common dialog
(content 2 dialog.html + dialog.js, styles/dialog16x9.css or styles/dialog.css,
styles/[stylesWideScreen/]wii.css). dialog.js turns every line feed of the message into
its own <p>, so the v7 '\\n' escape works there, but the text column is the #message box
minus the floated warning icon: 425 - 2 - (30 + 64 + 22) = 307 px at 22 px bold (16:9)
and 567 - 3 - (40 + 85 + 30) = 409 px at 30 px bold (4:3), about 13.6 em, much narrower
than the error page h1 the v7 model assumed. '지원하지 않는 주소 형식입니다.' (14.7 em)
therefore still ended a line inside a word.

Width model: a line is accepted when its advance sum in the content-4 'Wii NTLG PGothic'
face (the face wii.css names), times BOLD_FACTOR, fits SAFETY times the narrower column.
BOLD_FACTOR covers synthetic bold and rounding: on the v7 captures the measured ink width
was 1.3-4.3 % above the advance sum, and '240016: telnet 프로토콜은' (13.31 em) fitted the
13.95 em 16:9 column, so the real factor is at most 1.049. Lines that fit the dialog also
fit the error page h1 (v7 limit, 17.4 em), so one break set serves both.
Breaks replace single spaces only, are chosen at phrase boundaries (penalties below) and
never split '-ㄹ 수 없다', '-지 않다/못하다', '-어 주세요', '더 이상' or a determiner and
its noun. '%s' (a protocol or MIME type) is measured as PLACEHOLDER.
"""
import itertools
import re

from . import internet_error_headings as eh

CODE = re.compile(r'^\d{6}: ')
BREAK = eh.BREAK
PLACEHOLDER = eh.PLACEHOLDER
BOLD_FACTOR = 1.05
SAFETY = 0.98
# dialog text column per screen layout (content 2); verified against the shipped CSS by layouts()
LAYOUTS = {
    '16:9': dict(css='styles/dialog16x9.css', font_px=22, message_px=425, p_margin_px=2,
                 icon_margin_left=30, icon_width=64, icon_margin_right=22),
    '4:3': dict(css='styles/dialog.css', font_px=30, message_px=567, p_margin_px=3,
                icon_margin_left=40, icon_width=85, icon_margin_right=30),
}
FONT_CSS = ('styles/wii.css', 'styles/stylesWideScreen/wii.css')
FONT_RULE = "font-family: 'Wii NTLG PGothic Regular', sans-serif;"

HARD, DETERMINER, STRONG, ADVERB, NOUN, CODE_ALONE = 100, 50, 50, 30, 30, 15
DETERMINERS = {'이', '그', '저', '새', '다른', '모든'}
ADVERBS = {'다시', '더', '너무', '잘', '이미', '모두', '아직', '잠시', '또는', '및', '혹은'}
MODIFIER_NOUNS = {'HTTP', 'Flash', 'SSL', '인터넷'}  # 인터넷 채널 is the product name
# bare nouns (no particle) that modify the next noun: 주소 형식, 응답 시간, 서버 인증서 ...
BARE_NOUNS = {'서버', '주소', '응답', '통신', '내부', '전제', '내용', '요청', '기존', '파일', '보안', '인터넷',
              '게이트웨이', '호스트', '사용자', '프록시'}
# '-어/-아/-해' + auxiliary verb (들어 있는, 불러와 주세요) and '-려고 합니다'
AUXILIARY_LEAD = ('어', '아', '여', '와', '해')
AUXILIARY = ('있', '주', '보', '두', '놓')


def column_em(layout):
    icon = layout['icon_margin_left'] + layout['icon_width'] + layout['icon_margin_right']
    return (layout['message_px'] - layout['p_margin_px'] - icon) / layout['font_px']


def limit():
    """Largest accepted advance sum (em) of one dialog line."""
    return min(column_em(v) for v in LAYOUTS.values()) * SAFETY / BOLD_FACTOR


def _rule(css, selector):
    m = re.search(r'(?:^|\n)\s*' + re.escape(selector) + r'\s*\{([^}]*)\}', css)
    if not m:
        raise ValueError(f'dialog CSS: no {selector} rule')
    return m.group(1)


def _px(body, prop):
    m = re.search(r'(?:^|[;\s{])' + re.escape(prop) + r'\s*:\s*(\d+)px', body)
    if not m:
        raise ValueError(f'dialog CSS: no {prop} in px')
    return int(m.group(1))


def layouts(c2):
    """Re-read the dialog geometry and font from content 2; refuse a stylesheet that differs."""
    js = c2.get('dialog.js').decode('utf-8', 'replace')
    for needle in ('text.split("\\n")', 'loadCSS("styles/dialog16x9")', 'loadCSS("styles/dialog")',
                   'loadCSS("styles/stylesWideScreen/wii")', 'loadCSS("styles/wii")'):
        if needle not in js:
            raise ValueError(f'dialog.js: {needle!r} missing')
    for name in FONT_CSS:
        if FONT_RULE not in _rule(c2.get(name).decode('utf-8'), 'html, body'):
            raise ValueError(f'{name}: dialog font differs')
    found = {}
    for key, layout in LAYOUTS.items():
        css = c2.get(layout['css']).decode('utf-8')
        icon = _rule(css, '#notificationImg')
        got = dict(css=layout['css'], font_px=_px(_rule(css, '.dialog'), 'font-size'),
                   message_px=_px(_rule(css, '#message'), 'width'), p_margin_px=_px(_rule(css, 'p'), 'margin'),
                   icon_margin_left=_px(icon, 'margin-left'), icon_width=_px(icon, 'width'),
                   icon_margin_right=_px(icon, 'margin-right'))
        if 'float: left' not in icon or 'font-weight:bold' not in _rule(css, '.dialog').replace(' ', ''):
            raise ValueError(f'{layout["css"]}: icon float or bold text differs')
        if got != layout:
            raise ValueError(f'{layout["css"]}: dialog geometry differs {got}')
        found[key] = dict(column_px=round(column_em(layout) * layout['font_px']), font_px=layout['font_px'],
                          column_em=round(column_em(layout), 4))
    return found


def penalty(a, b, code_word):
    """Cost of ending a line after word a when word b starts the next line."""
    if b == '수' or a == '수' or (a, b) == ('더', '이상') or b.startswith('주세요'):
        return HARD
    if a.endswith('지') and b.startswith(('않', '못')):
        return HARD
    if (a.endswith(AUXILIARY_LEAD) and b.startswith(AUXILIARY)) or (a.endswith('려고') and b.startswith('합니다')):
        return HARD
    if a in DETERMINERS:
        return DETERMINER
    if a in MODIFIER_NOUNS:
        return STRONG
    if a in ADVERBS:
        return ADVERB
    if a in BARE_NOUNS:
        return NOUN
    if a == code_word:
        return CODE_ALONE
    return 0


def break_points(segment):
    """Indexes of single spaces between two non-space characters."""
    return [i for i, ch in enumerate(segment)
            if ch == ' ' and 0 < i < len(segment) - 1 and segment[i - 1] != ' ' and segment[i + 1] != ' ']


def split_segment(segment, metrics, width, code_word):
    """Best phrase-aware split of one segment: fewest lines, then penalty, then evenness."""
    if metrics.em(segment) <= width:
        return [segment], 0
    spaces = break_points(segment)
    best = None
    for count in range(1, len(spaces) + 1):
        for chosen in itertools.combinations(spaces, count):
            cuts = [-1, *chosen, len(segment)]
            lines = [segment[cuts[i] + 1:cuts[i + 1]] for i in range(len(cuts) - 1)]
            widths = [metrics.em(ln) for ln in lines]
            if max(widths) > width:
                continue
            cost = sum(penalty(segment[:c].rsplit(' ', 1)[-1], segment[c + 1:].split(' ', 1)[0], code_word) for c in chosen)
            key = (count * 10 + cost, cost, max(widths) - min(widths))
            if best is None or key < best[0]:
                best = (key, lines, cost)
        if best is not None and best[0][0] <= (count + 1) * 10:
            break  # one more line cannot be cheaper
    if best is None:
        raise ValueError(f'No word-boundary split fits {width:.3f} em: {segment!r}')
    return best[1], best[2]


def plan(translations, metrics, overrides=None):
    """{index: {'v1': text, 'ko': text with breaks, 'penalty': n}} for coded error messages that need breaks.
    A first sentence that fits one line once the code is set apart stays whole under the code."""
    width = limit()
    out = {}
    for index, text in translations.items():
        if not CODE.match(text):
            continue
        if overrides and index in overrides:
            out[index] = dict(v1=text, ko=overrides[index], penalty=None)
            continue
        code_word = text.split(' ', 1)[0]
        lines, cost = [], 0
        for n, segment in enumerate(text.split(BREAK)):
            rest = segment[len(code_word) + 1:]
            if n == 0 and metrics.em(segment) > width and metrics.em(rest) <= width:
                got, c = [code_word, rest], 0
            else:
                got, c = split_segment(segment, metrics, width, code_word if n == 0 else None)
            lines += got
            cost += c
        ko = BREAK.join(lines)
        if ko != text:
            out[index] = dict(v1=text, ko=ko, penalty=cost)
    return out


def spaces_to_breaks(old, new):
    """Number of single spaces of old written as BREAK in new; ValueError for any other difference."""
    i = j = n = 0
    while i < len(old) or j < len(new):
        if i < len(old) and j < len(new) and old[i] == new[j] and not new.startswith(BREAK, j):
            i, j = i + 1, j + 1
        elif new.startswith(BREAK, j) and old.startswith(BREAK, i):
            i, j = i + len(BREAK), j + len(BREAK)
        elif new.startswith(BREAK, j) and i < len(old) and old[i] == ' ' and 0 < i < len(old) - 1 \
                and old[i - 1] != ' ' and old[i + 1] != ' ':
            i, j, n = i + 1, j + len(BREAK), n + 1
        else:
            raise ValueError(f'breaks must replace single spaces only: {old!r} -> {new!r}')
    return n


LNG_ENTRY = eh.LNG_ENTRY


def apply_breaks(lng, rows):
    """Rewrite the planned entries of the v1 Korean english.lng (entry index = file order)."""
    import hashlib
    lines = lng.decode('utf-8').split('\n')
    index, done = 0, []
    for n, line in enumerate(lines):
        m = LNG_ENTRY.match(line)
        if not m:
            continue
        row = rows.get(str(index))
        if row is not None:
            if m.group(2) != row['v1']:
                raise ValueError(f'lng entry {index}: expected the v1 translation')
            lines[n] = f'{m.group(1)}="{row["ko"]}"'
            done.append(index)
        index += 1
    if sorted(done) != sorted(int(k) for k in rows):
        raise ValueError('Not every planned error message was found in english.lng')
    data = '\n'.join(lines).encode('utf-8')
    return data, dict(entries=len(done), sha256=hashlib.sha256(data).hexdigest())


def check(rows, translations, metrics, c2=None):
    """Rows keep the v1 words (single spaces become breaks); every line of every coded error
    message fits the dialog column (and the v7 error page limit); nothing coded is left too wide."""
    width = limit()
    page = metrics.limit()
    report = []
    for index, text in sorted(translations.items(), key=lambda kv: int(kv[0])):
        if not CODE.match(text):
            continue
        row = rows.get(index)
        final = text
        if row is not None:
            if row['v1'] != text:
                raise ValueError(f'lng entry {index}: v1 text differs from the translation')
            if spaces_to_breaks(text, row['ko']) < 1:
                raise ValueError(f'lng entry {index}: no new break')
            final = row['ko']
        lines = final.split(BREAK)
        widest = max(metrics.em(ln) for ln in lines)
        if widest > width or widest > page:
            raise ValueError(f'lng entry {index}: line {widest:.3f} em exceeds {width:.3f} em')
        if any(ln != ln.strip() for ln in lines if ln.strip() and not ln.endswith('%s ')):
            raise ValueError(f'lng entry {index}: a line starts or ends with a space')
        report.append(dict(index=int(index), lines=len([ln for ln in lines if ln]), widest_em=round(widest, 4),
                           changed=row is not None))
    if sorted(int(k) for k in rows) != [r['index'] for r in report if r['changed']]:
        raise ValueError('Break rows must be coded error messages')
    out = dict(limit_em=round(width, 4), bold_factor=BOLD_FACTOR, safety=SAFETY, placeholder=PLACEHOLDER,
               page_limit_em=round(page, 4), coded_messages=len(report), changed=len(rows),
               max_lines=max(r['lines'] for r in report), widest_em=max(r['widest_em'] for r in report), rows=report)
    if c2 is not None:
        out['layouts'] = layouts(c2)
    return out
