"""Kirby TV Channel SWF (Flash 9, AS2) editing: CWS/FWS, tags and AVM1 actions.

Only bounded, verified edits are made: the action list is parsed into
objects whose branch targets and block ends are references, so inserting
actions recomputes every If/Jump offset and DefineFunction/Try/With size.
Untouched DoInitAction blocks are copied byte for byte.
"""
import struct
import zlib

TAG_DO_ACTION = 12
TAG_EXPORT = 56
TAG_DO_INIT = 59
TAG_EDIT_TEXT = 37


# ---------------------------------------------------------------- container

def unpack(swf):
    """Return (signature, version, uncompressed FWS bytes)."""
    if swf[:3] == b'FWS':
        return 'FWS', swf[3], bytes(swf)
    if swf[:3] != b'CWS':
        raise ValueError('Not a SWF')
    length = struct.unpack_from('<I', swf, 4)[0]
    body = zlib.decompress(swf[8:])
    data = b'FWS' + swf[3:4] + struct.pack('<I', length) + body
    if len(data) != length:
        raise ValueError('SWF length differs')
    return 'CWS', swf[3], data


def pack(fws, signature='CWS'):
    data = bytearray(fws)
    struct.pack_into('<I', data, 4, len(data))
    if signature == 'FWS':
        return bytes(data)
    # Level 9 + fixed window: deterministic output for byte-identical builds.
    co = zlib.compressobj(9, zlib.DEFLATED, 15, 9)
    return b'CWS' + bytes(data[3:8]) + co.compress(bytes(data[8:])) + co.flush()


def header_end(data):
    nbits = data[8] >> 3
    return 8 + (5 + 4 * nbits + 7) // 8 + 4


def tags(data):
    """List of (code, start, header_length, payload_length) up to End."""
    pos = header_end(data)
    out = []
    while pos < len(data):
        word = struct.unpack_from('<H', data, pos)[0]
        code, length, head = word >> 6, word & 63, 2
        if length == 63:
            length = struct.unpack_from('<I', data, pos + 2)[0]
            head = 6
        if pos + head + length > len(data):
            raise ValueError('SWF tag bounds')
        out.append((code, pos, head, length))
        pos += head + length
        if code == 0:
            break
    return out


def tag_bytes(code, payload):
    if len(payload) < 63:
        return struct.pack('<H', code << 6 | len(payload)) + payload
    return struct.pack('<HI', code << 6 | 63, len(payload)) + payload


def cstr(raw, at):
    end = raw.index(b'\0', at)
    return raw[at:end].decode('utf-8'), end + 1


def exports(data):
    """character id -> exported name (first wins)."""
    names = {}
    for code, pos, head, length in tags(data):
        if code != TAG_EXPORT:
            continue
        raw = data[pos + head:pos + head + length]
        count = struct.unpack_from('<H', raw, 0)[0]
        at = 2
        for _ in range(count):
            cid = struct.unpack_from('<H', raw, at)[0]
            name, at = cstr(raw, at + 2)
            names.setdefault(cid, name)
    return names


def init_actions(data):
    """exported class name -> (tag index, sprite id, action bytes)."""
    names = exports(data)
    result = {}
    for index, (code, pos, head, length) in enumerate(tags(data)):
        if code != TAG_DO_INIT:
            continue
        raw = data[pos + head:pos + head + length]
        sid = struct.unpack_from('<H', raw, 0)[0]
        name = names.get(sid, str(sid))
        if name in result:
            raise ValueError('Duplicate DoInitAction class ' + name)
        result[name] = (index, sid, raw[2:])
    return result


def replace_tags(data, replacements):
    """replacements: tag index -> new payload. Returns new FWS bytes."""
    listing = tags(data)
    out = bytearray(data[:header_end(data)])
    for index, (code, pos, head, length) in enumerate(listing):
        if index in replacements:
            out += tag_bytes(code, replacements[index])
        else:
            out += data[pos:pos + head + length]
    end = listing[-1][1] + listing[-1][2] + listing[-1][3]
    out += data[end:]
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)


# ---------------------------------------------------------------- actions

class Action:
    __slots__ = ('op', 'payload', 'target', 'ends', 'offset')

    def __init__(self, op, payload=b''):
        self.op = op
        self.payload = bytes(payload)
        self.target = None   # If/Jump: Action or END
        self.ends = None     # DefineFunction(2)/With/Try: list of Action or END
        self.offset = None

    def size(self):
        return 1 if self.op < 0x80 else 3 + len(self.payload)

    def __repr__(self):
        return f'Action({self.op:#04x},{self.payload[:16]!r})'


END = 'END'
BRANCH = (0x99, 0x9D)
BLOCKS = (0x8E, 0x9B, 0x8F, 0x94)
UNSUPPORTED = (0x8A, 0x8D)   # WaitForFrame skip counts are action counts


def _block_sizes(act):
    """(byte offset of size fields inside payload, number of sizes)."""
    p = act.payload
    if act.op == 0x94:
        return [0]
    if act.op == 0x8F:
        return [1, 3, 5]
    # DefineFunction / DefineFunction2: code size is the last u16
    return [len(p) - 2]


def parse(code):
    acts = []
    pos = 0
    while pos < len(code):
        op = code[pos]
        if op >= 0x80:
            length = struct.unpack_from('<H', code, pos + 1)[0]
            act = Action(op, code[pos + 3:pos + 3 + length])
        else:
            act = Action(op)
        act.offset = pos
        acts.append(act)
        pos += act.size()
    if pos != len(code):
        raise ValueError('AVM1 stream bounds')
    by_offset = {a.offset: a for a in acts}
    by_offset[len(code)] = END

    def at(offset):
        if offset not in by_offset:
            raise ValueError(f'AVM1 reference into an action at {offset:#x}')
        return by_offset[offset]
    for act in acts:
        if act.op in UNSUPPORTED:
            raise ValueError('WaitForFrame action is not supported')
        if act.op in BRANCH:
            act.target = at(act.offset + 5 + struct.unpack_from('<h', act.payload, 0)[0])
        elif act.op in BLOCKS:
            start = act.offset + act.size()
            ends = []
            for field in _block_sizes(act):
                start += struct.unpack_from('<H', act.payload, field)[0]
                ends.append(at(start))
            act.ends = ends
    return acts


def serialize(acts):
    pos = 0
    for act in acts:
        act.offset = pos
        pos += act.size()
    total = pos

    def where(ref):
        return total if ref is END else ref.offset
    out = bytearray()
    for act in acts:
        payload = bytearray(act.payload)
        if act.op in BRANCH:
            delta = where(act.target) - (act.offset + 5)
            if not -32768 <= delta < 32768:
                raise ValueError('AVM1 branch range')
            struct.pack_into('<h', payload, 0, delta)
        elif act.op in BLOCKS:
            start = act.offset + act.size()
            for field, ref in zip(_block_sizes(act), act.ends):
                size = where(ref) - start
                if not 0 <= size < 65536:
                    raise ValueError('AVM1 block size')
                struct.pack_into('<H', payload, field, size)
                start = where(ref)
        act.payload = bytes(payload)
        out.append(act.op)
        if act.op >= 0x80:
            out += struct.pack('<H', len(payload)) + payload
    return bytes(out)


def pool(acts):
    first = acts[0]
    if first.op != 0x88:
        return []
    count = struct.unpack_from('<H', first.payload, 0)[0]
    at, out = 2, []
    for _ in range(count):
        text, at = cstr(first.payload, at)
        out.append(text)
    return out


def set_pool(acts, strings):
    if acts[0].op != 0x88:
        raise ValueError('Expected a constant pool')
    acts[0].payload = struct.pack('<H', len(strings)) + b''.join(s.encode('utf-8') + b'\0' for s in strings)


def push_values(payload, strings):
    at, out = 0, []
    while at < len(payload):
        kind = payload[at]
        at += 1
        if kind == 0:
            text, at = cstr(payload, at)
            out.append(('str', text))
        elif kind == 1:
            out.append(('float', struct.unpack_from('<f', payload, at)[0]))
            at += 4
        elif kind in (2, 3):
            out.append(('null' if kind == 2 else 'undef', None))
        elif kind in (4, 5):
            out.append(('reg' if kind == 4 else 'bool', payload[at]))
            at += 1
        elif kind == 6:
            out.append(('double', struct.unpack('<d', payload[at + 4:at + 8] + payload[at:at + 4])[0]))
            at += 8
        elif kind == 7:
            out.append(('int', struct.unpack_from('<i', payload, at)[0]))
            at += 4
        elif kind in (8, 9):
            index = payload[at] if kind == 8 else struct.unpack_from('<H', payload, at)[0]
            at += 1 if kind == 8 else 2
            out.append(('str', strings[index]))
        else:
            raise ValueError('Unknown push type')
    return out


# ------------------------------------------------------------ small assembler

OPS = {'End': 0x00, 'Pop': 0x17, 'GetVariable': 0x1C, 'SetVariable': 0x1D, 'Equals2': 0x49,
       'StrictEquals': 0x66, 'Not': 0x12, 'TypeOf': 0x44, 'GetMember': 0x4E, 'SetMember': 0x4F,
       'CallMethod': 0x52, 'NewObject': 0x40, 'Enumerate2': 0x55, 'Return': 0x3E,
       'PushDuplicate': 0x4C, 'Add2': 0x47, 'Delete': 0x3A, 'InitObject': 0x43, 'Less2': 0x48}


def push(*values):
    raw = bytearray()
    for value in values:
        if isinstance(value, tuple) and value[0] == 'reg':
            raw += bytes([4, value[1]])
        elif isinstance(value, bool):
            raw += bytes([5, int(value)])
        elif isinstance(value, int):
            raw += b'\x07' + struct.pack('<i', value)
        elif value is None:
            raw += b'\x02'
        elif isinstance(value, str):
            if '\0' in value:
                raise ValueError('NUL in AVM1 string')
            raw += b'\x00' + value.encode('utf-8') + b'\0'
        else:
            raise ValueError('Unsupported push value')
    if len(raw) >= 65536:
        raise ValueError('Push too long')
    return Action(0x96, raw)


def op(name):
    return Action(OPS[name])


def reg(number):
    return ('reg', number)


def store(number):
    return Action(0x87, bytes([number]))


def member_chain(*names):
    """Push the value of a dotted global path, e.g. nintendo.vodf.wii."""
    acts = [push(names[0]), op('GetVariable')]
    for name in names[1:]:
        acts += [push(name), op('GetMember')]
    return acts


class Label:
    """Placeholder resolved to the action that follows it."""


def branch(kind, label):
    act = Action(0x99 if kind == 'jump' else 0x9D, b'\0\0')
    act.target = label
    return act


def function2(params, registers, body, flags=0x2a):
    """Anonymous DefineFunction2; params: [(register, name)]."""
    raw = bytearray(b'\0')
    raw += struct.pack('<HBH', len(params), registers, flags)
    for number, name in params:
        raw += bytes([number]) + name.encode('ascii') + b'\0'
    raw += b'\0\0'
    act = Action(0x8E, raw)
    return act, body


def link(items):
    """Flatten [Action | Label | (function, body)] into actions with resolved refs.

    Indexes are global within the flattened block; a function's end and a
    label that closes a block both resolve to the action following them,
    which serializes to the same byte offset as the block end.
    """
    flat = []

    def emit(seq):
        for item in seq:
            if isinstance(item, tuple):
                func, body = item
                flat.append(func)
                emit(body)
                func.ends = [('INDEX', len(flat))]
            elif isinstance(item, Label):
                item.index = len(flat)
            else:
                flat.append(item)
    emit(items)
    for act in flat:
        if isinstance(act.target, Label):
            if not hasattr(act.target, 'index'):
                raise ValueError('Unplaced AVM1 label')
            act.target = ('INDEX', act.target.index)
    return flat


def splice(acts, index, items):
    """Insert assembled items before acts[index]; refs inside items resolve locally.

    A reference to the end of the inserted block becomes the action that was
    at acts[index]. Existing references to acts[index] keep pointing to it, so
    branches that jumped there skip the inserted code (asserted absent by
    callers that need fall-through only).
    """
    flat = link(items)
    follower = acts[index] if index < len(acts) else END

    def resolve(ref):
        if isinstance(ref, tuple) and ref[0] == 'INDEX':
            return flat[ref[1]] if ref[1] < len(flat) else follower
        return ref
    for act in flat:
        if act.target is not None:
            act.target = resolve(act.target)
        if act.ends is not None:
            act.ends = [resolve(r) for r in act.ends]
    acts[index:index] = flat
    return len(flat)


def references_to(acts, target):
    return [a for a in acts if a.target is target or (a.ends and any(e is target for e in a.ends))]


# ------------------------------------------------------- Kirby TV patches

SWF_PATH = 'trusted/Gumball2.12.RC-1.swf'
SERVICE_HOST = 'kirby.wiilink24.com'
LOCAL_HOST = '127.0.0.2'
WII_SYSTEM = ('nintendo', 'vodf', 'wii', 'system', 'WiiSystem')
LOCALE = ('gb', 'locale', 'LocaleManager')


def _values(act, strings):
    return push_values(act.payload, strings) if act.op == 0x96 else None


def _find_push(acts, strings, values, start=0, end=None):
    end = len(acts) if end is None else end
    for i in range(start, end):
        if _values(acts[i], strings) == values:
            return i
    raise ValueError(f'AVM1 pattern not found: {values!r}')


def _body(acts, index):
    func = acts[index]
    if func.op not in (0x8E, 0x9B):
        raise ValueError('Expected a function definition')
    end = len(acts) if func.ends[0] is END else acts.index(func.ends[0])
    return index + 1, end


def _member_name(act, strings):
    values = _values(act, strings)
    return values[-1][1] if values and values[-1][0] == 'str' else None


def _wii_constant(name):
    return member_chain(*WII_SYSTEM) + [push(name), op('GetMember')]


def korean_as_english(acts, strings):
    """LocaleManager(): language 9 is treated as English for every UI decision."""
    i = _find_push(acts, strings, [('reg', 1), ('str', '_wiiLangCode'), ('double', 0.0), ('str', 'nintendo')])
    j = next(k for k in range(i, i + 16) if acts[k].op == 0x4F)
    if _member_name(acts[j - 2], strings) != 'getLanguage' or acts[j - 1].op != 0x52:
        raise ValueError('LocaleManager language read differs')
    follower = acts[j + 1]
    if references_to(acts, follower):
        raise ValueError('Insertion point is a branch target')
    skip = Label()
    items = [push(reg(1), '_wiiLangCode'), op('GetMember')] + _wii_constant('LANG_KOREAN') + [
        op('Equals2'), op('Not'), branch('if', skip),
        push(reg(1), '_wiiLangCode')] + _wii_constant('LANG_ENGLISH') + [op('SetMember'), skip]
    return splice(acts, j + 1, items)


def _korean_console():
    return [push(0)] + member_chain(*WII_SYSTEM) + [push('getLanguage'), op('CallMethod')] + _wii_constant('LANG_KOREAN') + [op('Equals2')]


DATE_MANAGER = ('gb', 'time', 'DateManager')


def korean_dates(acts, strings):
    """DateManager: "<day><suffix> <month>" becomes " <month> <day>일" on Korean consoles.

    Every date in the screens is getDateAbbrev(day) + ' ' + getShortMonth(m).
    On a Korean console getDateAbbrev stores the day and returns '', and
    getShortMonth appends it after the (overlay-translated) month name.
    """
    def function_at(name):
        i = next(k for k in range(len(acts) - 1) if _values(acts[k], strings) == [('reg', 1), ('str', name)] and acts[k + 1].op == 0x8E)
        return i + 1
    f = function_at('getDateAbbrev')
    lo, hi = _body(acts, f)
    if _values(acts[lo], strings) != [('reg', 4)] or acts[lo + 1].op != 0x4B or references_to(acts, acts[lo]):
        raise ValueError('getDateAbbrev body differs')
    skip = Label()
    added = splice(acts, lo, _korean_console() + [op('Not'), branch('if', skip)] + member_chain(*DATE_MANAGER) + [
        push('kwceDay', reg(4)), op('SetMember'), push(''), op('Return'), skip])
    f = function_at('getShortMonth')
    lo, hi = _body(acts, f)
    if [a.op for a in acts[hi - 2:hi]] != [0x96, 0x3E] or _values(acts[hi - 2], strings) != [('reg', 1)] or references_to(acts, acts[hi - 2]):
        raise ValueError('getShortMonth ending differs')
    skip = Label()
    added += splice(acts, hi - 2, _korean_console() + [op('Not'), branch('if', skip)] + member_chain(*DATE_MANAGER) + [
        push('kwceDay'), op('GetMember'), op('TypeOf'), push('undefined'), op('StrictEquals'), branch('if', skip),
        push(reg(1), ' '), op('Add2')] + member_chain(*DATE_MANAGER) + [push('kwceDay'), op('GetMember'), op('Add2'),
        push('일'), op('Add2'), store(1), op('Pop')] + member_chain(*DATE_MANAGER) + [push('kwceDay'), op('Delete'), op('Pop'), skip])
    return dict(korean_date_order='month day일', actions=added)


KOREAN_UTC_OFFSET = 9      # KST, no daylight saving time
DAY_SUFFIX = '일'
LESS_THAN_A_DAY = '1일 미만'


def _function_index(acts, strings, owner_register, name):
    """Index of the DefineFunction2 assigned to <register>.<name>."""
    for i in range(len(acts) - 1):
        if _values(acts[i], strings) == [('reg', owner_register), ('str', name)] and acts[i + 1].op == 0x8E:
            return i + 1
    raise ValueError('AVM1 function not found: ' + name)


def _function2_params(act):
    """[(register, name)] of a DefineFunction2 action."""
    p = act.payload
    _, at = cstr(p, 0)
    count = struct.unpack_from('<H', p, at)[0]
    at += 5
    params = []
    for _ in range(count):
        register = p[at]
        name, at = cstr(p, at + 1)
        params.append((register, name))
    return params


def korean_days_text(acts, strings):
    """LocaleManager.getDaysAsText(pDays): '<n>일' (or '1일 미만') on Korean consoles.

    The original reads locale.time_units (day.single/plural, mod.less_than)
    from the service XML. The synthetic feed has no time_units and the live
    WiiLink file was not seen to carry them, so the intro's [number_days]
    would become 'undefined'. Other languages keep the XML-driven text.
    """
    f = _function_index(acts, strings, 2, 'getDaysAsText')
    if _function2_params(acts[f]) != [(3, 'pDays')]:
        raise ValueError('getDaysAsText parameters differ')
    lo, _ = _body(acts, f)
    first = acts[lo]
    if _values(first, strings) != [('double', 0.0), ('str', 'gb')] or references_to(acts, first):
        raise ValueError('getDaysAsText body differs')
    whole, skip = Label(), Label()
    items = _korean_console() + [op('Not'), branch('if', skip),
                                 push(reg(3), 1), op('Less2'), op('Not'), branch('if', whole),
                                 push(LESS_THAN_A_DAY), op('Return'),
                                 whole, push(reg(3), DAY_SUFFIX), op('Add2'), op('Return'),
                                 skip]
    return dict(korean_days_text='<n>' + DAY_SUFFIX, less_than_a_day=LESS_THAN_A_DAY, actions=splice(acts, lo, items))


def korean_time_zone(acts, strings):
    """DateManager.countryTimeZoneOffset: +9 instead of UNKNOWN (0) on Korean consoles.

    Countries outside the channel's 18 PAL entries (Korea 136 included) get
    GBCountryTimeZone.UNKNOWN = 0, so every date was shown in UTC. Only that
    unsupported-country branch changes; supported countries keep their entry.
    Server time, episode dates and the expiry date all pass through the same
    offset, so episode states are unchanged and only shown dates move to KST.
    """
    f = _function_index(acts, strings, 2, '__get__countryTimeZoneOffset')
    lo, hi = _body(acts, f)
    i = _find_push(acts, strings, [('str', 'isCountryCodeSupported')], lo, hi)
    if [a.op for a in acts[i + 1:i + 5]] != [0x52, 0x12, 0x12, 0x9D]:
        raise ValueError('countryTimeZoneOffset support check differs')
    j = i + 5
    tail = [(a.op, _values(a, strings)) for a in acts[j:j + 9]]
    expected = [(0x96, [('str', 'gb')]), (0x1C, None), (0x96, [('str', 'time')]), (0x4E, None),
                (0x96, [('str', 'GBCountryTimeZone')]), (0x4E, None), (0x96, [('str', 'UNKNOWN')]), (0x4E, None), (0x3E, None)]
    if tail != expected or references_to(acts, acts[j]):
        raise ValueError('countryTimeZoneOffset UNKNOWN branch differs')
    skip = Label()
    items = _korean_console() + [op('Not'), branch('if', skip), push(KOREAN_UTC_OFFSET), op('Return'), skip]
    return dict(korean_utc_offset_hours=KOREAN_UTC_OFFSET, scope='unsupported-country branch only',
                actions=splice(acts, j, items))


def _text_object(text):
    """{target: {data: text}} built with InitObject."""
    return [push('target', 'data', text, 1), op('InitObject'), push(1), op('InitObject')]


def _unit_object(unit):
    """A trans_unit-like object as XML2Object would produce it."""
    items, count = [], 0
    for field in ('message', 'title', 'label'):
        if field in unit:
            items += [push(field)] + _text_object(unit[field])
            count += 1
    if 'badge' in unit:
        items += [push('badge', 'data', str(unit['badge']), 1), op('InitObject')]
        count += 1
    if not count:
        raise ValueError('Missing-ID unit without text')
    return items + [push(count), op('InitObject')]


def missing_table(acts, strings, missing):
    """LocaleManager.kwceKoMissing = {id: unit} at class initialisation."""
    k = next(i for i, a in enumerate(acts) if _values(a, strings) and ('str', 'ASSetPropFlags') in _values(a, strings))
    start = next(i for i in range(k, k - 12, -1) if (_values(acts[i], strings) or [None])[:3] == [('int', 1), ('null', None), ('str', 'gb')])
    if references_to(acts, acts[start]):
        raise ValueError('Missing-ID table insertion point is a branch target')
    items = member_chain(*LOCALE) + [push('kwceKoMissing')]
    for key, unit in missing:
        items += [push(key)] + _unit_object(unit)
    items += [push(len(missing)), op('InitObject'), op('SetMember')]
    return splice(acts, start, items)


def missing_fallback(acts, strings):
    """getLocaleInfoByID: a Korean console gets kwceKoMissing[pID] when the XML lacks pID.

    Original: r2 = this._transUnits[pID]; if (r2) {} return r2. The truthy If
    jumps over the inserted code; only a missing unit falls through into it.
    """
    f = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 2), ('str', 'getLocaleInfoByID')]
             and acts[i + 1].op == 0x8E)
    lo, hi = _body(acts, f + 1)
    body = acts[lo:hi]
    expected = [0x96, 0x4E, 0x96, 0x4E, 0x87, 0x17, 0x96, 0x12, 0x12, 0x9D, 0x96, 0x3E]
    if [a.op for a in body] != expected or _values(body[0], strings) != [('reg', 1), ('str', '_transUnits')] \
            or body[9].target is not body[10] or _values(body[10], strings) != [('reg', 2)]:
        raise ValueError('getLocaleInfoByID body differs')
    follower = body[10]
    if [a for a in references_to(acts, follower) if a is not body[9]]:
        raise ValueError('Unexpected reference to the getLocaleInfoByID return')
    skip = Label()
    items = _korean_console() + [op('Not'), branch('if', skip)] + member_chain(*LOCALE) + [
        push('kwceKoMissing'), op('GetMember'), push(reg(3)), op('GetMember'), store(2), op('Pop'), skip]
    added = splice(acts, lo + 10, items)
    if body[9].target is not follower:
        raise ValueError('Present-unit branch no longer skips the fallback')
    return added


def _walk_function():
    """kwceWalk(o=r2, D=r3): replace o.*.data strings found in D (exact match)."""
    loop, end, not_object = Label(), Label(), Label()
    body = [
        push(reg(2)), op('Enumerate2'),
        loop, store(0), push(None), op('Equals2'), branch('if', end),
        push(reg(0)), store(4), op('Pop'),
        push(reg(2), reg(4)), op('GetMember'), store(5), op('Pop'),
        push(reg(5)), op('TypeOf'), push('object'), op('StrictEquals'), op('Not'), branch('if', not_object),
        push(reg(3), reg(5), 2)] + member_chain(*LOCALE) + [push('kwceWalk'), op('CallMethod'), op('Pop'),
        branch('jump', loop),
        not_object,
        push(reg(4), 'data'), op('StrictEquals'), op('Not'), branch('if', loop),
        push(reg(5)), op('TypeOf'), push('string'), op('StrictEquals'), op('Not'), branch('if', loop),
        push(reg(3), reg(5)), op('GetMember'), store(6), op('Pop'),
        push(reg(6)), op('TypeOf'), push('string'), op('StrictEquals'), op('Not'), branch('if', loop),
        push(reg(2), reg(4), reg(6)), op('SetMember'),
        branch('jump', loop),
        end]
    return function2([(2, 'o'), (3, 'D')], 7, body)


def _entry_function(dictionary):
    """kwceKo(o=r2): on Korean consoles translate the loaded XML object once."""
    ret, have = Label(), Label()
    build = [push(0, 'Object'), op('NewObject'), store(3), op('Pop')]
    for source, target in dictionary:
        build += [push(reg(3), source, target), op('SetMember')]
    build += member_chain(*LOCALE) + [push('kwceKoD', reg(3)), op('SetMember')]
    body = [push(0)] + member_chain(*WII_SYSTEM) + [push('getLanguage'), op('CallMethod')] + _wii_constant('LANG_KOREAN') + [
        op('Equals2'), op('Not'), branch('if', ret)] + member_chain(*LOCALE) + [
        push('kwceKoD'), op('GetMember'), store(3), op('Pop'),
        push(reg(3)), op('TypeOf'), push('object'), op('StrictEquals'), branch('if', have)] + build + [
        have,
        push(reg(3), reg(2), 2)] + member_chain(*LOCALE) + [push('kwceWalk'), op('CallMethod'), op('Pop'),
        ret]
    return function2([(2, 'o')], 4, body)


def define_overlay(acts, strings, dictionary):
    """Add LocaleManager.kwceKo / kwceWalk before the class's ASSetPropFlags."""
    k = next(i for i, a in enumerate(acts) if _values(a, strings) and ('str', 'ASSetPropFlags') in _values(a, strings))
    start = next(i for i in range(k, k - 12, -1) if (_values(acts[i], strings) or [None])[:3] == [('int', 1), ('null', None), ('str', 'gb')])
    if references_to(acts, acts[start]):
        raise ValueError('Overlay insertion point is a branch target')
    items = member_chain(*LOCALE) + [push('kwceWalk'), _walk_function(), op('SetMember')]
    items += member_chain(*LOCALE) + [push('kwceKo'), _entry_function(dictionary), op('SetMember')]
    return splice(acts, start, items)


def call_overlay(acts, strings):
    """DataController.remoteXML_onLoadComplete: kwceKo(this.dataXMLObj) after the load."""
    f = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 2), ('str', 'remoteXML_onLoadComplete')]
             and acts[i + 1].op == 0x8E)
    lo, hi = _body(acts, f + 1)
    i = _find_push(acts, strings, [('reg', 1), ('str', 'dataXMLObj'), ('reg', 1), ('str', '_urlLoader')], lo, hi)
    if [a.op for a in acts[i + 1:i + 5]] != [0x4E, 0x96, 0x4E, 0x4F] or _member_name(acts[i + 2], strings) != 'data':
        raise ValueError('dataXMLObj assignment differs')
    if references_to(acts, acts[i + 5]):
        raise ValueError('Overlay call point is a branch target')
    items = [push(reg(1), 'dataXMLObj'), op('GetMember'), push(1)] + member_chain(*LOCALE) + [push('kwceKo'), op('CallMethod'), op('Pop')]
    return splice(acts, i + 5, items)


def replace_strings(acts, strings, old, new):
    count = 0
    if old in strings:
        strings = [new if s == old else s for s in strings]
        set_pool(acts, strings)
        count += 1
    for act in acts[1:]:
        if act.op == 0x96 and b'\x00' + old.encode() + b'\x00' in act.payload:
            values = push_values(act.payload, strings)
            if any(k == 'str' and v == old for k, v in values):
                raise ValueError('Inline service host push is not expected')
    return strings, count


TOOLTIP_CLASS = ('gb', 'buttons', 'GumballButtonToolTip')
TOOLTIP_LABEL = 682              # DefineEditText 'label' of the ToolTip symbol (sprite 683)
TOOLTIP_LABEL_PX = 23.0          # its "Alor 0513" size
TOOLTIP_HANGUL_WIDTH = 20        # px per Hangul syllable (glyph advance at 23px is about 19.0)


def _tooltip_width_function():
    """kwceTipWidth(s=r2): FONT_WIDTH per character as before, TOOLTIP_HANGUL_WIDTH per Hangul syllable, + 10."""
    loop, end, other, step = Label(), Label(), Label(), Label()
    body = [
        push(0), store(3), op('Pop'),
        push(0), store(4), op('Pop'),
        loop,
        push(reg(4), reg(2), 'length'), op('GetMember'), op('Less2'), op('Not'), branch('if', end),
        push(reg(4), 1, reg(2), 'charCodeAt'), op('CallMethod'), store(5), op('Pop'),
        push(reg(5), 0xAC00), op('Less2'), branch('if', other),
        push(0xD7A3, reg(5)), op('Less2'), branch('if', other),
        push(reg(3), TOOLTIP_HANGUL_WIDTH), op('Add2'), store(3), op('Pop'),
        branch('jump', step),
        other,
        push(reg(3))] + member_chain(*TOOLTIP_CLASS) + [push('FONT_WIDTH'), op('GetMember'), op('Add2'), store(3), op('Pop'),
        step,
        push(reg(4), 1), op('Add2'), store(4), op('Pop'),
        branch('jump', loop),
        end,
        push(reg(3), 10), op('Add2'), op('Return')]
    return function2([(2, 's')], 6, body)


def korean_tooltip_width(acts, strings):
    """GumballButtonToolTip: bubble width from Hangul-aware character widths on Korean consoles.

    The original __set__labelText sets centerWidth = value.length * FONT_WIDTH (14) + 10, and
    UIButtonToolTip.updateDisplay gives the label text field the same width. A Hangul syllable
    of the 23px label is about 19px wide, so Korean tooltips were cut on the right (settings:
    '채널 소개', '에피소드 편성표 안내', '열쇠 알아보기', '새 에피소드 소식 설정'). On a Korean console
    the width is recomputed right after the original call with TOOLTIP_HANGUL_WIDTH per Hangul
    syllable; other characters keep FONT_WIDTH, so text without Hangul keeps its width.
    """
    # 1) static helper next to FONT_WIDTH = 14 in the class initialiser
    k = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 1), ('str', 'FONT_WIDTH'), ('int', 14)]
             and acts[i + 1].op == 0x4F)
    follower = acts[k + 2]
    if references_to(acts, follower):
        raise ValueError('Tooltip helper insertion point is a branch target')
    added = splice(acts, k + 2, [push(reg(1), 'kwceTipWidth'), _tooltip_width_function(), op('SetMember')])
    # 2) recompute after the original width call in __set__labelText
    f = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 2), ('str', '__set__labelText')]
             and acts[i + 1].op == 0x8E)
    if _function2_params(acts[f + 1]) != [(5, 'value')]:
        raise ValueError('GumballButtonToolTip.__set__labelText parameters differ')
    lo, hi = _body(acts, f + 1)
    i = _find_push(acts, strings, [('reg', 5), ('str', 'length')], lo, hi)
    pattern = [(a.op, _values(a, strings)) for a in acts[i:i + 16]]
    expected = [(0x96, [('reg', 5), ('str', 'length')]), (0x4E, None), (0x96, [('str', 'gb')]), (0x1C, None),
                (0x96, [('str', 'buttons')]), (0x4E, None), (0x96, [('str', 'GumballButtonToolTip')]), (0x4E, None),
                (0x96, [('str', 'FONT_WIDTH')]), (0x4E, None), (0x0C, None), (0x96, [('int', 10)]), (0x47, None),
                (0x96, [('int', 1), ('reg', 1), ('str', '__set__centerWidth')]), (0x52, None), (0x17, None)]
    if pattern != expected:
        raise ValueError('Tooltip width expression differs')
    follower = acts[i + 16]
    if references_to(acts, follower):
        raise ValueError('Tooltip width insertion point is a branch target')
    skip = Label()
    items = _korean_console() + [op('Not'), branch('if', skip), push(reg(5), 1)] + member_chain(*TOOLTIP_CLASS) + [
        push('kwceTipWidth'), op('CallMethod'), push(1, reg(1), '__set__centerWidth'), op('CallMethod'), op('Pop'), skip]
    added += splice(acts, i + 16, items)
    return dict(hangul_width_px=TOOLTIP_HANGUL_WIDTH, other_width='FONT_WIDTH (14, unchanged)', padding_px=10,
                scope='Korean console only, dynamic-width tooltips', actions=added)


TOOLTIP_WIDTH_EXPRESSION = [(0x96, [('reg', 5), ('str', 'length')]), (0x4E, None), (0x96, [('str', 'gb')]), (0x1C, None),
                            (0x96, [('str', 'buttons')]), (0x4E, None), (0x96, [('str', 'GumballButtonToolTip')]), (0x4E, None),
                            (0x96, [('str', 'FONT_WIDTH')]), (0x4E, None), (0x0C, None), (0x96, [('int', 10)]), (0x47, None)]


def korean_tooltip_width_once(acts, strings):
    """GumballButtonToolTip (revision 9): one Hangul-aware bubble width, computed by the original call.

    Revision 8 kept the original centerWidth = value.length * FONT_WIDTH + 10 call and set the
    width a second time right after it. Here the original expression itself becomes
    kwceTipWidth(value), on every console (Korean-console build), so labelText assigns only the
    Hangul-aware width. Text without Hangul gets exactly the original width.
    This alone did not fix the RC6 photos (IMG_5702-5705); Dolphin showed the same cut bubble.
    The settings cards (HSGridButton) set centerWidth again after labelText, see
    korean_hs_tooltip_width (revision 11). The earlier explanation for this revision, that the
    Wii player keeps only the first _width assignment of a frame, was wrong.
    """
    k = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 1), ('str', 'FONT_WIDTH'), ('int', 14)]
             and acts[i + 1].op == 0x4F)
    follower = acts[k + 2]
    if references_to(acts, follower):
        raise ValueError('Tooltip helper insertion point is a branch target')
    added = splice(acts, k + 2, [push(reg(1), 'kwceTipWidth'), _tooltip_width_function(), op('SetMember')])
    f = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 2), ('str', '__set__labelText')]
             and acts[i + 1].op == 0x8E)
    if _function2_params(acts[f + 1]) != [(5, 'value')]:
        raise ValueError('GumballButtonToolTip.__set__labelText parameters differ')
    lo, hi = _body(acts, f + 1)
    i = _find_push(acts, strings, [('reg', 5), ('str', 'length')], lo, hi)
    n = len(TOOLTIP_WIDTH_EXPRESSION)
    if [(a.op, _values(a, strings)) for a in acts[i:i + n]] != TOOLTIP_WIDTH_EXPRESSION:
        raise ValueError('Tooltip width expression differs')
    call = [(a.op, _values(a, strings)) for a in acts[i + n:i + n + 3]]
    if call != [(0x96, [('int', 1), ('reg', 1), ('str', '__set__centerWidth')]), (0x52, None), (0x17, None)]:
        raise ValueError('Tooltip width call differs')
    if any(references_to(acts, a) for a in acts[i:i + n]):
        raise ValueError('Tooltip width expression is a branch target')
    del acts[i:i + n]
    items = [push(reg(5), 1)] + member_chain(*TOOLTIP_CLASS) + [push('kwceTipWidth'), op('CallMethod')]
    added += splice(acts, i, items) - n
    return dict(hangul_width_px=TOOLTIP_HANGUL_WIDTH, other_width='FONT_WIDTH (14, unchanged)', padding_px=10,
                scope='every console, the one dynamic-width computation (no second centerWidth call)', actions=added)


def korean_tooltip_width_guarded(acts, strings):
    """GumballButtonToolTip (revision 10): revision 9 plus centerWidth ignores undefined/null.

    UIButton sets every tooltip property after labelText, ending with
    centerWidth = _toolTipCenterWidth. For a button that gives no width this is undefined;
    the original setter skipped only the _dynamicProps flag for that value and still passed
    it to UIButtonToolTip, so _centerWidth became undefined and updateDisplay assigned
    NaN/undefined to _x and _width. Here an undefined/null value returns before the parent
    setter, so _centerWidth keeps the labelText width.
    The guard is harmless but was not the cause of the RC6 photos: the revision 10 probe in
    Dolphin (2026-10-31) showed the settings cards pass a defined width (text.length * 15,
    see korean_hs_tooltip_width) together with a NaN x offset.
    """
    record = korean_tooltip_width_once(acts, strings)
    f = next(i for i in range(len(acts) - 1) if _values(acts[i], strings) == [('reg', 2), ('str', '__set__centerWidth')]
             and acts[i + 1].op == 0x8E)
    lo, hi = _body(acts, f + 1)
    body = acts[lo:hi]
    shape = [(a.op, _values(a, strings)) for a in body]
    expected = [(0x96, [('reg', 3), ('reg', 1), ('str', '_centerWidth')]), (0x4E, None), (0x49, None), (0x12, None),
                (0x12, None), (0x9D, None),
                (0x96, [('reg', 3), ('undef', None)]), (0x49, None), (0x12, None), (0x4C, None), (0x9D, None),
                (0x17, None), (0x96, [('reg', 3), ('null', None)]), (0x49, None), (0x12, None), (0x12, None),
                (0x9D, None),
                (0x96, [('reg', 1), ('str', '_dynamicProps'), ('bool', 0)]), (0x4F, None),
                (0x96, [('reg', 3), ('int', 1), ('reg', 2), ('str', '__set__centerWidth')]), (0x52, None), (0x17, None),
                (0x96, [('double', 0.0), ('reg', 1), ('str', '__get__centerWidth')]), (0x52, None), (0x3E, None)]
    if shape[:len(expected)] != expected:
        raise ValueError('GumballButtonToolTip.__set__centerWidth differs')
    same_value, defined = body[5], body[16]
    getter = body[22]
    if same_value.target is not getter or defined.target is not body[19]:
        raise ValueError('GumballButtonToolTip.__set__centerWidth branches differ')
    defined.target = getter   # undefined/null: return the current width, do not call UIButtonToolTip
    record.update(scope='every console; one dynamic-width computation; centerWidth ignores undefined/null',
                  undefined_width='skipped (keeps the labelText width)')
    return record


HS_GRID_BUTTON = '__Packages.gb.buttons.HSGridButton'


def korean_hs_tooltip_width(acts, strings):
    """HSGridButton.invalidate (revision 11): toolTipCenterWidth = kwceTipWidth(text), not text.length * 15.

    The four settings cards are HSGridButton. invalidate() sets toolTipXOffset from the help
    XML (no x_offset attribute -> Number(undefined) = NaN) and toolTipCenterWidth =
    getToolTipText().length * 15. On rollover UIButton gives the tooltip labelText first
    (GumballButtonToolTip computes its own width and places the end caps and the label), then
    xOffset = NaN (every later _x becomes NaN, which the Wii player ignores) and finally
    centerWidth = length * 15, which only the _width assignments follow. Revision 10 probe in
    Dolphin (2026-10-31): history 'L c232 c180', _xOffset NaN. With both widths from the same
    kwceTipWidth, caps, body and label agree. Text without Hangul keeps a similar width.
    """
    hits = [k for k in range(len(acts) - 6)
            if _values(acts[k], strings) == [('str', 'getToolTipText')] and acts[k + 1].op == 0x52
            and _values(acts[k + 2], strings) == [('str', 'length')] and acts[k + 3].op == 0x4E
            and _values(acts[k + 4], strings) == [('int', 15)] and acts[k + 5].op == 0x0C
            and _values(acts[k + 6], strings) == [('int', 1), ('reg', 1), ('str', '__set__toolTipCenterWidth')]]
    if len(hits) != 1:
        raise ValueError(f'HSGridButton tooltip width expression found {len(hits)} times')
    k = hits[0]
    if any(references_to(acts, a) for a in acts[k + 2:k + 6]):
        raise ValueError('HSGridButton tooltip width expression is a branch target')
    del acts[k + 2:k + 6]
    added = splice(acts, k + 2, [push(1)] + member_chain(*TOOLTIP_CLASS) + [push('kwceTipWidth'), op('CallMethod')])
    return dict(width='GumballButtonToolTip.kwceTipWidth(getToolTipText()) instead of length * 15',
                x_offset='unchanged (NaN from the help XML, as in the original)', actions=added - 4)


def edit_text_font(fws, cid):
    """(font id, font height px) of a DefineEditText."""
    for code, pos, head, length in tags(fws):
        if code != TAG_EDIT_TEXT or struct.unpack_from('<H', fws, pos + head)[0] != cid:
            continue
        at = pos + head + 2
        nbits = fws[at] >> 3
        at += (5 + 4 * nbits + 7) // 8
        flags = fws[at]
        if not flags & 1:
            raise ValueError('Edit text without a font')
        font, height = struct.unpack_from('<HH', fws, at + 2)
        return font, height / 20
    raise ValueError(f'DefineEditText {cid} not found')


def _tooltip_label_check(fws):
    """The tooltip label really is 'Alor 0513' at 23px and its Hangul advances fit TOOLTIP_HANGUL_WIDTH."""
    from .kirbytv_swf_font import parse_font3, EM
    font_id, height = edit_text_font(fws, TOOLTIP_LABEL)
    if (font_id, height) != (1, TOOLTIP_LABEL_PX):
        raise ValueError(f'Tooltip label font differs: {font_id} {height}')
    for code, pos, head, length in tags(fws):
        if code == 75 and struct.unpack_from('<H', fws, pos + head)[0] == font_id:
            font = parse_font3(fws[pos + head:pos + head + length])
            break
    else:
        raise ValueError('Tooltip font not found')
    hangul = [a for c, a in zip(font['codes'], font['advances']) if 0xAC00 <= c <= 0xD7A3]
    if not hangul:
        raise ValueError('Tooltip font has no Hangul glyphs')
    widest = max(hangul) / EM * height
    if widest > TOOLTIP_HANGUL_WIDTH - 0.5:
        raise ValueError(f'Hangul advance {widest:.2f}px exceeds the tooltip width per syllable')
    return dict(font='Alor 0513', size_px=height, hangul_glyphs=len(hangul), widest_hangul_px=round(widest, 2))


def _edit_class(data, classes, name, editor):
    index, sid, code = classes[name]
    acts = parse(code)
    strings = pool(acts)
    record = editor(acts, strings)
    new = serialize(acts)
    check = parse(new)
    if serialize(check) != new:
        raise ValueError('AVM1 reserialization unstable')
    return index, struct.pack('<H', sid) + new, record


def patch(swf, dictionary, local, glyphs=None, dates=False, missing=None, days=False, time_zone=False,
          tooltip=False, bitmaps=None, hs_tooltip=False):
    """Return (patched SWF, record). dictionary: [(english, korean)] exact texts.

    glyphs: optional (characters, HangulSource, extend_fonts keyword args)
    adding Hangul outlines to the embedded fonts (revision 2+); dates: the
    Korean month/day order in DateManager (revision 2+); missing: [(id, unit)]
    Korean units for locale IDs the service XML lacks (revision 3+); days:
    Korean getDaysAsText and time_zone: KST for the unsupported-country branch
    (revision 4+); tooltip: Hangul-aware GumballButtonToolTip width (True:
    revision 8, a second width call on Korean consoles; 'once': revision 9,
    the original width call itself; 'guarded': revision 10+, 'once' plus a
    centerWidth setter that ignores undefined/null); bitmaps: {character id:
    DefineBitsLossless2 payload} for the Korean logo pieces (revision 8+);
    hs_tooltip: HSGridButton passes kwceTipWidth(text) instead of
    text.length * 15 as the tooltip width (revision 11+, needs tooltip).
    Revision 1 passes none of them and is unchanged.
    """
    import hashlib
    signature, version, data = unpack(swf)
    classes = init_actions(data)
    replacements = {}
    record = dict(source_sha256=hashlib.sha256(swf).hexdigest(), swf_version=version)

    def locale(acts, strings):
        a = korean_as_english(acts, strings)
        b = define_overlay(acts, strings, dictionary)
        result = dict(korean_as_english_actions=a, overlay_actions=b, dictionary_entries=len(dictionary))
        if missing:
            result.update(missing_ids=len(missing), missing_table_actions=missing_table(acts, strings, missing),
                          missing_fallback_actions=missing_fallback(acts, strings))
        if days:
            result['days_text'] = korean_days_text(acts, strings)
        return result
    i, payload, record['LocaleManager'] = _edit_class(data, classes, '__Packages.gb.locale.LocaleManager', locale)
    replacements[i] = payload
    i, payload, n = _edit_class(data, classes, '__Packages.gb.data.DataController', call_overlay)
    replacements[i] = payload
    record['DataController'] = dict(overlay_call_actions=n)
    if local:
        def host(acts, strings):
            _, count = replace_strings(acts, strings, SERVICE_HOST, LOCAL_HOST)
            if count != 1:
                raise ValueError('Service host not found in ApplicationController pool')
            return dict(service_host=SERVICE_HOST, local_host=LOCAL_HOST)
        i, payload, record['ApplicationController'] = _edit_class(data, classes, '__Packages.ApplicationController', host)
        replacements[i] = payload
    if dates or time_zone:
        def date_manager(acts, strings):
            result = korean_dates(acts, strings) if dates else {}
            if time_zone:
                result['time_zone'] = korean_time_zone(acts, strings)
            return result
        i, payload, record['DateManager'] = _edit_class(data, classes, '__Packages.gb.time.DateManager', date_manager)
        replacements[i] = payload
    if tooltip:
        editor = {'once': korean_tooltip_width_once, 'guarded': korean_tooltip_width_guarded}.get(tooltip,
                                                                                                    korean_tooltip_width)
        i, payload, record['GumballButtonToolTip'] = _edit_class(data, classes, '__Packages.gb.buttons.GumballButtonToolTip',
                                                                 editor)
        replacements[i] = payload
    if hs_tooltip:
        i, payload, record['HSGridButton'] = _edit_class(data, classes, HS_GRID_BUTTON, korean_hs_tooltip_width)
        replacements[i] = payload
    fws = replace_tags(data, replacements)
    if glyphs is not None:
        from .kirbytv_swf_font import extend_fonts
        characters, source, params = glyphs
        fws, record['embedded_fonts'] = extend_fonts(fws, characters, source, **params)
    if tooltip:
        record['GumballButtonToolTip']['label_check'] = _tooltip_label_check(fws)
    if bitmaps:
        from .kirbytv_logo import replace_bitmaps
        fws = replace_bitmaps(fws, bitmaps)
        record['logo_bitmaps'] = {str(cid): dict(sha256=hashlib.sha256(p).hexdigest(), bytes=len(p)) for cid, p in sorted(bitmaps.items())}
    out = pack(fws, signature)
    _, _, check = unpack(out)
    after = init_actions(check)
    for name, (index, sid, code) in classes.items():
        if index not in replacements and after[name][2] != code:
            raise ValueError('Unrelated class changed: ' + name)
    record.update(output_sha256=hashlib.sha256(out).hexdigest(), changed_classes=len(replacements), local_endpoint=bool(local))
    return out, record


def service_hosts(swf):
    """Remote host strings of ApplicationController (for hardware checks)."""
    _, _, data = unpack(swf)
    _, _, code = init_actions(data)['__Packages.ApplicationController']
    strings = pool(parse(code))
    return sorted(s for s in strings if s in (SERVICE_HOST, LOCAL_HOST) or s.startswith('127.'))
