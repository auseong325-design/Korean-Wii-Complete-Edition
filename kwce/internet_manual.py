"""Korean Internet Channel manual (Opera HTML in the content-2 U8 archive).

A translation unit is a *run*: the text between two block-level tags or line
breaks together with the inline tags inside it (img, a, strong, span, ...). Each
inline tag becomes a placeholder {n} in an English template, so Korean word
order can move button icons. The block structure outside runs (including every
<br>) is byte-for-byte kept; inside a run every original tag is emitted exactly
once and the run must stay well nested. Scripts, styles and comments are never
touched.
"""
import re
from html.parser import HTMLParser

INLINE = {'img', 'a', 'b', 'strong', 'em', 'i', 'u', 'span', 'font', 'sup', 'sub', 'small', 'big', 'nobr', 'wbr'}
VOID = {'img', 'br', 'wbr'}
PLACEHOLDER = re.compile(r'\{(\d+)\}')


class _Tokens(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tokens = []
        self.skip = 0

    def _add(self, kind, raw, tag=None):
        self.tokens.append((kind, raw, tag, self.skip > 0))

    def handle_starttag(self, tag, attrs):
        self._add('start', self.get_starttag_text(), tag)
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_startendtag(self, tag, attrs):
        self._add('empty', self.get_starttag_text(), tag)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip -= 1
        self._add('end', '</' + tag + '>', tag)

    def handle_data(self, text):
        self._add('data', text)

    def handle_entityref(self, name):
        self._add('data', '&' + name + ';')

    def handle_charref(self, name):
        self._add('data', '&#' + name + ';')

    def handle_comment(self, text):
        self._add('other', '<!--' + text + '-->')

    def handle_decl(self, text):
        self._add('other', '<!' + text + '>')

    def handle_pi(self, text):
        self._add('other', '<?' + text + '>')

    def parse_bogus_comment(self, i, report=1):
        # '<! DOCTYPE html >' style declarations: keep the raw bytes.
        pos = self.rawdata.find('>', i + 2)
        if pos == -1:
            return -1
        if report:
            self._add('other', self.rawdata[i:pos + 1])
        return pos + 1


def tokens(html):
    parser = _Tokens()
    parser.feed(html)
    parser.close()
    if ''.join(t[1] for t in parser.tokens) != html:
        raise ValueError('Manual HTML does not round-trip through the tokenizer')
    return parser.tokens


def _inline(token):
    kind, raw, tag, skipped = token
    return not skipped and (kind == 'data' or (kind in ('start', 'end', 'empty') and tag in INLINE))


def runs(html):
    """Yield (first, last, template, tags) for each run holding Latin text."""
    toks = tokens(html)
    i = 0
    while i < len(toks):
        if not _inline(toks[i]):
            i += 1
            continue
        j = i
        while j < len(toks) and _inline(toks[j]):
            j += 1
        chunk = toks[i:j]
        text = ''.join(t[1] for t in chunk if t[0] == 'data')
        if re.search('[A-Za-z]', re.sub(r'&[A-Za-z]+;|&#\w+;', '', text)):
            parts, tags = [], []
            for t in chunk:
                if t[0] == 'data':
                    parts.append(t[1])
                else:
                    parts.append('{%d}' % len(tags))
                    tags.append(t[1])
            yield i, j, ' '.join(''.join(parts).split()), tags
        i = j


def _well_nested(raw_tags):
    stack = []
    for raw in raw_tags:
        m = re.match(r'</?([A-Za-z0-9]+)', raw)
        name = m.group(1).lower()
        if raw.startswith('</'):
            if not stack or stack.pop() != name:
                return False
        elif name not in VOID and not raw.endswith('/>'):
            stack.append(name)
    return not stack


def fill(template, tags, korean):
    """Korean template -> HTML; every placeholder exactly once, nesting kept."""
    found = [int(n) for n in PLACEHOLDER.findall(korean)]
    if sorted(found) != list(range(len(tags))):
        raise ValueError(f'Placeholder set differs: {template!r}')
    order = [tags[n] for n in found]
    if _well_nested(tags):
        if not _well_nested(order):
            raise ValueError(f'Inline tags no longer nest: {korean!r}')
    elif order != tags:
        # A run that opens or closes a tag across a block boundary keeps its tag order.
        raise ValueError(f'Open inline tags must keep their order: {korean!r}')
    if re.search(r'[<>]', PLACEHOLDER.sub('', korean)):
        raise ValueError(f'Raw markup in translation: {korean!r}')
    return PLACEHOLDER.sub(lambda m: tags[int(m.group(1))], korean)


def localize_html(html, mapping, used):
    toks = tokens(html)
    out = []
    pos = 0
    for first, last, template, tags in runs(html):
        out.extend(t[1] for t in toks[pos:first])
        raw = ''.join(t[1] for t in toks[first:last])
        if template in mapping:
            lead = raw[:len(raw) - len(raw.lstrip())]
            trail = raw[len(raw.rstrip()):]
            out.append(lead + fill(template, tags, mapping[template]) + trail)
            used.add(template)
        else:
            out.append(raw)
        pos = last
    out.extend(t[1] for t in toks[pos:])
    result = ''.join(out)
    before = [t[1] for t in toks if not _inline(t)]
    after = [t[1] for t in tokens(result) if not _inline(t)]
    if before != after:
        raise ValueError('Manual block structure changed')
    return result


def untranslated(html, mapping):
    return [template for _, _, template, _ in runs(html) if template not in mapping]
