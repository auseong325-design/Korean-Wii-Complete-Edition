"""Deterministic synthetic Everybody Votes Channel feed for the isolated test NAND.

This mirrors the WiiLink24 EVC file generator's byte layout (references/access-source/*.go)
and the fields the client parser reads (references/protocol-research.md).  It builds the two
feed files the channel downloads:

  * ``first_data.bin`` - the country/language lookup (``decodeFirstPlayInfoData`` @0x80062d40).
    The public WiiLink service never lists country 136 (Korea) in ``countryCodes`` (const.go),
    which is why a real Korean console shows "국가 이용 불가"; this synthetic file adds a 136 entry
    with several supported languages so the channel proceeds and the question-language switch has
    something to cycle.
  * ``voting.bin`` - the pack (``decodePackData`` @0x80062f54) carrying open questions in several
    languages (복수 언어 질문 전환), closed national results with per-region detail + a position table
    (지역 지도), and a closed worldwide result with per-country detail + a country table (국가별 그래프).

All counts/offsets are produced the way the Go generator produces them (offset = size of
everything serialised so far), and every value stays inside the parser's documented bounds, so
the output is accepted without contacting any server.  No console backup/save/key is used; only
the public protocol constants are read.  Output is deterministic (fixed timestamps), so the feed
regenerates byte-for-byte.
"""
import re
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / 'workspace/channels/votes/references/access-source'

# EVC LanguageCode enum (const.go): Japanese..FrenchCanadian = 0..8.
LANG = dict(Japanese=0, English=1, German=2, French=3, Spanish=4, Italian=5, Dutch=6,
            Portuguese=7, FrenchCanadian=8)

# Minutes-since-2000 window the client accepts (protocol-research.md 7.3): ~2007..2036.
WINDOW_LO, WINDOW_HI = 0x382F20, 0x120EB20
# Fixed, deterministic timestamps well inside the window.
OPEN_START = 0x00C80000   # ~2023, open now (2026 is inside [start, end])
OPEN_END = 0x010A0000     # ~2036-ish but < WINDOW_HI; keeps questions open across the test clock
PAST_START = 0x00B00000   # a closed poll in the past
PAST_END = 0x00B0A000     # closed (end well before the test clock)


def _go_text(name):
    return (ACCESS / name).read_text(encoding='utf-8')


def parse_countries():
    """{code: [name per language]} from const.go ``countries`` (7 columns: JP,EN,DE,FR,ES,IT,NL)."""
    body = re.search(r'var countries = map\[int\]\[\]string\{(.*?)\n\}', _go_text('const.go'), re.S)[1]
    out = {}
    for code, names in re.findall(r'(\d+):\s*\{([^}]*)\}', body):
        out[int(code)] = [s for s in re.findall(r'"((?:[^"\\]|\\.)*)"', names)]
    return out


def parse_supported_languages():
    """The language *display names* table (first_data.go ``supportedLanguages``), in order."""
    body = re.search(r'var supportedLanguages = \[\]string\{(.*?)\n\}', _go_text('first_data.go'), re.S)[1]
    return [s for s in re.findall(r'"((?:[^"\\]|\\.)*)"', body)]


def parse_country_codes():
    body = re.search(r'var countryCodes = \[\]uint8\{(.*?)\n\}', _go_text('const.go'), re.S)[1]
    return [int(v) for v in re.findall(r'\d+', body)]


def parse_country_supported_languages():
    body = re.search(r'var countriesSupportedLanguages = map\[uint8\]\[\]LanguageCode\{(.*?)\n\}',
                     _go_text('const.go'), re.S)[1]
    out = {}
    for code, langs in re.findall(r'(\d+):\s*\{([^}]*)\}', body):
        out[int(code)] = [LANG[name.strip()] for name in langs.split(',') if name.strip()]
    return out


def _crc_finish(pack):
    """Set Filesize@4 and CRC32@8 (CRC over [12:], zlib/IEEE) exactly like the generator."""
    pack = bytearray(pack)
    struct.pack_into('>I', pack, 4, len(pack))
    struct.pack_into('>I', pack, 8, zlib.crc32(pack[12:]) & 0xffffffff)
    return bytes(pack)


def _lz11_literal(data):
    """A valid LZ11 stream made only of literal runs (same shape make_channel_access_fixtures uses)."""
    out = bytearray(b'\x11' + len(data).to_bytes(3, 'little'))
    for i in range(0, len(data), 8):
        out.append(0)
        out.extend(data[i:i + 8])
    return bytes(out)


def _signed(pack):
    """File on the wire: 320-byte zero signature block + LZ11(pack)."""
    return bytes(320) + _lz11_literal(_crc_finish(pack))


def _u16z(text):
    return text.encode('utf-16-be') + b'\0\0'


# --------------------------------------------------------------------------- first_data.bin

def build_first_data(extra_country=136, extra_langs=(1, 0, 2), lang_overrides=None):
    """Country/language lookup including a synthetic entry for `extra_country`.

    Layout (first_data.go): Version,Filesize,CRC32, NumberOfCountries(u8), CountryTableOffset(u32),
    NumberOfLanguages(u8), LanguageTable[u32]*, CountryTable[{u8 code,u8 n,[4]u8 langs}]*, LanguageText.

    `lang_overrides` (code -> language ids) rewrites the advertised languages of countries
    already in the list; it is used by the country-disguise feed to advertise the USA entry
    with exactly the languages its synthetic voting pack carries. Default None leaves every
    real entry untouched, so the original feed regenerates byte-for-byte.
    """
    names = parse_supported_languages()
    codes = parse_country_codes()
    supported = parse_country_supported_languages()
    if extra_country is not None and extra_country not in codes:
        codes = codes + [extra_country]
        supported = dict(supported)
        supported[extra_country] = list(extra_langs)
    if lang_overrides:
        supported = dict(supported)
        for code, langs in lang_overrides.items():
            supported[code] = list(langs)

    num_lang = len(names)
    header_size = 18 + num_lang * 4           # == CountryTableOffset
    country_table = bytearray()
    for code in codes:
        langs = supported.get(code, [])[:4]
        row = bytes([code, len(langs)]) + bytes(langs) + bytes(4 - len(langs))
        country_table.extend(row)             # 6 bytes each

    text_base = header_size + len(country_table)
    lang_table = bytearray()
    lang_text = bytearray()
    for name in names:
        lang_table.extend(struct.pack('>I', text_base + len(lang_text)))
        lang_text.extend(_u16z(name))

    pack = bytearray()
    pack += struct.pack('>III', 1, 0, 0)                  # Version, Filesize, CRC32 (filled later)
    pack += struct.pack('>B', len(codes))                 # NumberOfCountries
    pack += struct.pack('>I', header_size)                # CountryTableOffset
    pack += struct.pack('>B', num_lang)                   # NumberOfLanguages
    pack += lang_table
    pack += country_table
    pack += lang_text
    assert len(pack) - len(lang_text) == text_base
    return bytes(pack)


# --------------------------------------------------------------------------- voting.bin

class _Pack:
    """Serialises the voting.bin body section by section, recording table offsets."""

    def __init__(self):
        self.header = bytearray(0x45)
        self.body = bytearray()

    def _set(self, off, fmt, *vals):
        struct.pack_into(fmt, self.header, off, *vals)

    def offset(self):
        return 0x45 + len(self.body)


def _question_info(poll_id, cat1, cat2, start, end, num_langs, entry_number):
    # QuestionInfo 0x13: PollID,Cat1,Cat2,Start,End,NumSupportedLanguages(<5),QuestionTableEntryNumber
    return struct.pack('>IBBIIBI', poll_id, cat1, cat2, start, end, num_langs, entry_number)


def build_voting(country_code=136, langs=(1, 0, 2)):
    """A pack with closed national/worldwide polls that carry results, plus one open national poll.

    Closed polls (6001/6002 national, 6501 worldwide) appear in the question table *and* the result
    tables, so the result screens find both the regional/country detail and the poll's question text
    in every language (국가별 그래프 / 지역 지도 and the 질문 언어 변경 switch on the result view).  The open
    poll 7001 exercises the switch on the live voting screen.
    """
    countries = parse_countries()
    num_langs = len(langs)
    assert num_langs < 5, 'NumberOfSupportedLanguages must stay < 5'

    # Visibly different text per language so the 질문 언어 변경 switch is observable on screen.
    text = {
        6001: {0: ('ローカルテスト: 好きな季節は？', '春', '秋'),
               1: ('Local test: favourite season?', 'Spring', 'Autumn'),
               2: ('Lokaltest: Lieblingsjahreszeit?', 'Fruehling', 'Herbst'),
               3: ('Test local : saison préférée ?', 'Printemps', 'Automne')},
        6002: {0: ('ローカルテスト: 朝は何派？', 'ごはん', 'パン'),
               1: ('Local test: breakfast?', 'Rice', 'Bread'),
               2: ('Lokaltest: Fruehstueck?', 'Reis', 'Brot'),
               3: ('Test local : petit-déjeuner ?', 'Riz', 'Pain')},
        7001: {0: ('ローカルテスト: 休日の過ごし方は？', '外出', '家'),
               1: ('Local test: how to spend a day off?', 'Go out', 'Stay in'),
               2: ('Lokaltest: freier Tag?', 'Ausgehen', 'Zuhause'),
               3: ('Test local : jour de congé ?', 'Sortir', 'Rester')},
        6501: {0: ('ローカルテスト: 犬と猫は？', '犬', '猫'),
               1: ('Local test: dogs or cats?', 'Dogs', 'Cats'),
               2: ('Lokaltest: Hund oder Katze?', 'Hund', 'Katze'),
               3: ('Test local : chien ou chat ?', 'Chien', 'Chat')},
    }
    national = [(6001, PAST_START, PAST_END), (6002, PAST_START, PAST_END), (7001, OPEN_START, OPEN_END)]
    worldwide = (6501, PAST_START, PAST_END)

    p = _Pack()
    p._set(0x00, '>I', 0)                 # Version
    p._set(0x0C, '>I', OPEN_START)        # Timestamp (unread by parser, kept sane)
    p._set(0x10, '>B', country_code)      # CountryCode
    p._set(0x11, '>B', 0)                 # PublicityFlag
    p._set(0x12, '>B', 1)                 # QuestionVersion
    p._set(0x13, '>B', 1)                 # ResultVersion

    # --- National question table (0x14 count, 0x15 offset) : capped 6
    p._set(0x14, '>B', len(national))
    p._set(0x15, '>I', p.offset())
    for i, (pid, start, end) in enumerate(national):
        p.body += _question_info(pid, 0, 3, start, end, num_langs, i * num_langs)

    # --- Worldwide question table (0x19 count, 0x1A offset) : capped 2
    p._set(0x19, '>B', 1)
    p._set(0x1A, '>I', p.offset())
    p.body += _question_info(worldwide[0], 0, 3, worldwide[1], worldwide[2], num_langs,
                             len(national) * num_langs)

    # --- Question text info table (0x1E count, 0x1F offset) + the text blobs.
    all_qs = [pid for pid, _s, _e in national] + [worldwide[0]]
    total_entries = len(all_qs) * num_langs
    p._set(0x1E, '>B', total_entries)
    info_off = p.offset()
    p._set(0x1F, '>I', info_off)
    info = bytearray()                       # QuestionTextInfo 0x0D each: lang,qOff,r1Off,r2Off
    for _ in range(total_entries):
        info += struct.pack('>BIII', 0, 0, 0, 0)
    p.body += info
    # Now the text, patching the just-written info entries with real offsets.
    idx = 0
    for pid in all_qs:
        for code in langs:
            q, r1, r2 = text[pid][code]
            at = info_off - 0x45 + idx * 0x0D
            struct.pack_into('>B', p.body, at, code)
            struct.pack_into('>I', p.body, at + 1, p.offset()); p.body += _u16z(q)
            struct.pack_into('>I', p.body, at + 5, p.offset()); p.body += _u16z(r1)
            struct.pack_into('>I', p.body, at + 9, p.offset()); p.body += _u16z(r2)
            idx += 1

    # --- National results (0x23 count, 0x24 offset) : capped 13; the two closed polls, with detail.
    num_regions = 4                                   # 4 synthetic regions
    national_results = [(6001, 1200, 800, 900, 1100), (6002, 640, 360, 540, 460)]
    p._set(0x23, '>B', len(national_results))
    p._set(0x24, '>I', p.offset())
    for order, (pid, m1, m2, f1, f2) in enumerate(national_results):
        # NationalResult 0x23: id,m1,m2,f1,f2,pred1,pred2,showVoters,showDetail,detailNum,detailStart
        p.body += struct.pack('>7IBBBI', pid, m1, m2, f1, f2, m1 - 50, m2 + 50,
                              1, 1, num_regions, num_regions * order)

    # --- Detailed national results (0x28 count u16, 0x2A offset) : stride 0x0D, placed per region.
    p._set(0x28, '>H', num_regions * len(national_results))
    p._set(0x2A, '>I', p.offset())
    for order in range(len(national_results)):
        for r in range(num_regions):
            r1 = 300 + 40 * r + 10 * order
            r2 = 180 + 25 * r + 7 * order
            # 0x0D: VotersR1, VotersR2, PositionEntryTableCount, PositionTableEntryNumber
            p.body += struct.pack('>IIBI', r1, r2, 1, r)

    # --- Position table (0x2E count u16, 0x30 offset) : 2 bytes (x,y) per region.
    p._set(0x2E, '>H', num_regions)
    p._set(0x30, '>I', p.offset())
    for r in range(num_regions):
        p.body += bytes([40 + 30 * r, 60 + 20 * r])

    # --- Worldwide result (0x34 count u8 == 1, 0x35 offset) : stride 0x21.
    graph_codes = [1, 16, 18, 36, 49, 77, 78, 110]      # 8 countries for the T_country_00..07 graph
    p._set(0x34, '>B', 1)
    p._set(0x35, '>I', p.offset())
    # WorldWideResult 0x21: id,m1,m2,f1,f2,pred1,pred2,NumDetailed(u8),DetailedNumber(u32)
    p.body += struct.pack('>7IBI', 6501, 5200, 4800, 4100, 3900, 5150, 4850, len(graph_codes), 0)

    # --- Detailed worldwide (0x39 count u16 <=0x80, 0x3B offset) : stride 0x1A, one per country.
    p._set(0x39, '>H', len(graph_codes))
    p._set(0x3B, '>I', p.offset())
    languages_cols = 7                      # const.go `languages` has 7 entries
    for i, code in enumerate(graph_codes):
        m1, m2, f1, f2 = 400 + 30 * i, 360 + 25 * i, 380 + 28 * i, 340 + 22 * i
        # 0x1A: Field0, m1, m2, f1, f2, Flag(u8), CountryTableCount(u8), CountryTableNumber(u32)
        p.body += struct.pack('>IIIIIBBI', code, m1, m2, f1, f2, 0, languages_cols, i * languages_cols)

    # --- Country table (0x3F count u16, 0x41 offset) : CountryInfoTable {lang u8, textOff u32}
    #     one row per (country x language), then the UTF-16 names (countries.go order).
    p._set(0x3F, '>H', len(graph_codes) * languages_cols)
    info_country_off = p.offset()
    p._set(0x41, '>I', info_country_off)
    rows = bytearray()
    for _ in range(len(graph_codes) * languages_cols):
        rows += struct.pack('>BI', 0, 0)
    p.body += rows
    k = 0
    for code in graph_codes:
        names = countries[code]
        for col in range(languages_cols):
            at = info_country_off - 0x45 + k * 5
            struct.pack_into('>B', p.body, at, col)
            struct.pack_into('>I', p.body, at + 1, p.offset())
            p.body += _u16z(names[col] if col < len(names) else names[0])
            k += 1

    return bytes(p.header) + bytes(p.body)


# --------------------------------------------------------------------------- feed assembly

def build_feed(country_code=136, langs=(1, 0, 2)):
    """Return ({filename: bytes}, {route: filename}) for the rich synthetic Votes feed."""
    first = _signed(build_first_data(country_code, langs))
    voting = _signed(build_voting(country_code, langs))
    files = {'first_data.bin': first, 'voting.bin': voting, 'ok.bin': b'100'}
    routes = {
        '* /first_data.bin': 'first_data.bin',
        f'* /{country_code}/voting.bin': 'voting.bin',
        '* /cgi-bin/vote.cgi': 'ok.bin',
        '* /cgi-bin/suggest.cgi': 'ok.bin',
        '* /index.html': 'ok.bin',
    }
    return files, routes


def build_disguise_feed(real=49, keep=136, langs=(1, 0, 2)):
    """Feed for the country-disguised build (build-v19), which presents country 49 (USA).

    It serves the ``/049/`` paths the disguised channel requests AND keeps the ``/136/`` paths,
    so the same test NAND feed also boots the undisguised v17/v18 (country 136). ``first_data``
    advertises BOTH countries with ``langs`` -- the exact languages the synthetic packs carry,
    English(1) first, which is what a Korean console (system language 9) resolves to -- so the
    질문 언어 변경 switch cycles languages that actually have text. The country path is zero-padded
    to three digits (``%03d``), i.e. ``/049/``, exactly as the channel builds it.

    Everything stays inside the client parser's documented bounds (see build_voting /
    build_first_data); deterministic, so local-feed-v2 regenerates byte-for-byte.
    """
    first = _signed(build_first_data(extra_country=keep, extra_langs=langs,
                                     lang_overrides={real: langs}))
    files = {
        'first_data.bin': first,
        'voting.bin': _signed(build_voting(keep, langs)),
        'voting_%03d.bin' % real: _signed(build_voting(real, langs)),
        'ok.bin': b'100',
    }
    routes = {
        '* /first_data.bin': 'first_data.bin',
        '* /%03d/voting.bin' % keep: 'voting.bin',
        '* /%03d/voting.bin' % real: 'voting_%03d.bin' % real,
        '* /cgi-bin/vote.cgi': 'ok.bin',
        '* /cgi-bin/suggest.cgi': 'ok.bin',
        '* /index.html': 'ok.bin',
    }
    return files, routes
