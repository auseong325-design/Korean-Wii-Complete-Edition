"""Korean Internet Channel error-page headings: explicit word-boundary line breaks (revision 7).

Opera 9.30 for Wii breaks lines between any two Hangul syllables and has no
`word-break`/`word-wrap` property (neither name is in its CSS tables), so a long
Korean error heading such as '240007: 이 파일에 접근할 수 없습니다.' can end a line
inside a word ('없습니/다.'). Revision 7 writes the break position into the heading
text (the `\\n` escape in english.lng, a line feed for Opera) and sets
`white-space: pre-line` on the error page h1: the forced break is honoured and any
remaining overflow still wraps, so a narrower layout degrades to the v6 behaviour.

Width model (no viewport or base size needed): the lead's build-v5 review (h1 130%,
16:9) showed '240023: 서버를 찾을 수 없습니' on the first line and '다.' on the
second. With advances scaled linearly,
    1.30 * em('240023: 서버를 찾을 수 없습니') <= W/S < 1.30 * em('240023: 서버를 찾을 수 없습니다.')
where em() sums advances of the Opera 'Wii NTLG PGothic' face (the Korean TTC in
content 4) and W/S is the h1 line width over the base font size. One line at h1 110%
is accepted when 1.10 * em(line) <= SAFETY * lower bound. '%s' is measured as
PLACEHOLDER (a protocol or MIME type is substituted there).
Only single-sentence headings are changed: two-sentence entries (244004 certificate
question, 241001 Flash memory) may be dialog texts, so they keep the v6 text.
"""
import io
import re

from .channels import ChannelArchive, load_library

HEADING = re.compile(r'^2\d{5}: ')
OBSERVED_FITS = '240023: 서버를 찾을 수 없습니'
OBSERVED_WRAPS = '240023: 서버를 찾을 수 없습니다.'
OBSERVED_SCALE = 1.30
TARGET_SCALE = 1.10
SAFETY = 0.975
PLACEHOLDER = 'application'
BREAK = '\\n'  # english.lng escape; Opera's language loader turns it into a line feed


def opera_face(content4):
    """'Wii NTLG PGothic' face of the content-4 TTC (U8 archive or bare TTC)."""
    load_library()
    from fontTools.ttLib import TTCollection
    data = content4
    if content4[:4] == b'\x55\xaa\x38\x2d':
        arc = ChannelArchive(content4)
        data = arc.get([n for n in arc.files if n.lower().endswith('.ttc')][0])
    for face in TTCollection(io.BytesIO(data)).fonts:
        if 'PGothic' in face['name'].getDebugName(1):
            return face
    raise ValueError('Opera font has no PGothic face')


class Metrics:
    def __init__(self, face):
        self.cmap = face.getBestCmap()
        self.hmtx = face['hmtx']
        self.upm = face['head'].unitsPerEm

    def em(self, text):
        text = text.replace('%s', PLACEHOLDER)
        missing = sorted({c for c in text if ord(c) not in self.cmap})
        if missing:
            raise ValueError(f'Opera font lacks {missing!r}')
        return sum(self.hmtx[self.cmap[ord(c)]][0] for c in text) / self.upm

    def bounds(self):
        """(lower, upper) bound of the h1 line width W/S in base-size em."""
        return OBSERVED_SCALE * self.em(OBSERVED_FITS), OBSERVED_SCALE * self.em(OBSERVED_WRAPS)

    def limit(self):
        """Largest accepted em() of one heading line at h1 110%."""
        return SAFETY * self.bounds()[0] / TARGET_SCALE


def single_sentence(text):
    body = text[len('000000: '):]
    return not re.search(r'[.?!] \S', body)


def keep_all_lines(text, metrics, limit):
    """Greedy fill breaking only at spaces (what CSS 'word-break: keep-all' would give)."""
    lines, cur = [], ''
    for word in text.split(' '):
        trial = f'{cur} {word}' if cur else word
        if cur and metrics.em(trial) > limit:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    return lines


def plan(translations, metrics):
    """{index: {'v6': one-line text, 'ko': text with breaks}} for headings that may not fit one line."""
    limit = metrics.limit()
    out = {}
    for index, text in translations.items():
        if not HEADING.match(text) or BREAK in text or not single_sentence(text):
            continue
        if metrics.em(text) <= limit:
            continue
        lines = keep_all_lines(text, metrics, limit)
        if len(lines) > 1:
            out[index] = dict(v6=text, ko=BREAK.join(lines))
    return out


LNG_ENTRY = re.compile(r'^(-?\d+)="(.*)"$')


def apply_breaks(lng, rows):
    """Rewrite the planned entries of a Korean english.lng (entry index = file order)."""
    lines = lng.decode('utf-8').split('\n')
    index, done = 0, []
    for n, line in enumerate(lines):
        m = LNG_ENTRY.match(line)
        if not m:
            continue
        row = rows.get(str(index))
        if row is not None:
            if m.group(2) != row['v6']:
                raise ValueError(f'lng entry {index}: expected the v6 heading text')
            lines[n] = f'{m.group(1)}="{row["ko"]}"'
            done.append(index)
        index += 1
    if sorted(done) != sorted(int(k) for k in rows):
        raise ValueError('Not every planned heading was found in english.lng')
    import hashlib
    data = '\n'.join(lines).encode('utf-8')
    return data, dict(entries=len(done), sha256=hashlib.sha256(data).hexdigest())


def check(rows, translations, metrics):
    """Rows keep the v6 words (single spaces become breaks) and every line fits the limit."""
    limit = metrics.limit()
    report = []
    for index, row in sorted(rows.items(), key=lambda kv: int(kv[0])):
        if translations[index] != row['v6']:
            raise ValueError(f'lng entry {index}: v6 text differs from the v1 translation')
        if not HEADING.match(row['v6']) or not single_sentence(row['v6']):
            raise ValueError(f'lng entry {index}: not a single-sentence error heading')
        lines = row['ko'].split(BREAK)
        if ' '.join(lines) != row['v6'] or len(lines) < 2 or any(not ln or ln != ln.strip() for ln in lines):
            raise ValueError(f'lng entry {index}: breaks must replace single spaces only')
        widest = max(metrics.em(ln) for ln in lines)
        if widest > limit:
            raise ValueError(f'lng entry {index}: line {widest:.3f} em exceeds {limit:.3f} em')
        report.append(dict(index=int(index), lines=len(lines), widest_em=round(widest, 4)))
    return dict(limit_em=round(limit, 4), bounds_em=[round(b, 4) for b in metrics.bounds()], safety=SAFETY,
                target_scale=TARGET_SCALE, placeholder=PLACEHOLDER, headings=len(report),
                max_lines=max((r['lines'] for r in report), default=0), rows=report)
