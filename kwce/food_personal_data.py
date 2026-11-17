"""Personal-data (Set Personal Data, SPD) facts and fictional test data for Demae.

Demae's PD library picks the SPD title and the pd.dat path with SCGetArea:
  area 0 JPN -> 00010008-4843434a (HCCJ), 1 USA -> HCCE, 2 EUR -> HCCP,
  any other area (Korea=6) -> no title id / NULL path.
Call sites (stock and WiiLink DOLs, identical addresses):
  0x802346b0 path table (SCGetArea at 0x80234710/0x80234758/0x802347ac),
             table at 0x803102b8: +0/+44/+88 pd.dat, +132/+172/+212 nocopy dir
  0x80234534 SPD title id + installed-TMD version query (SCGetArea at 0x8023456c)
  0x801a7750 'Go to Set Personal Data' launch target (SCGetArea at 0x801a77b8)
  string table 'HCCJ/HCCE/HCCP' at 0x8047111c
WiiLink's Demae_1_Japan patch already rewrites the USA/EUR entries to HCCJ; the
title-local bridge kwce.food_compat.patch_korean_area (SCGetArea 6->0) sends a
Korean console down the JPN/HCCJ path in both the local and hardware builds.

pd.dat itself is handled by kwce.personal_data_format (read-only reuse).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPD_TITLE = '000100084843434a'
PD_PATH = '/title/00010008/4843434a/data/nocopy/pd.dat'
PATH_TABLE = 0x803102b8
CALL_SITES = {'path_table': [0x80234710, 0x80234758, 0x802347ac], 'title_check': [0x8023456c],
              'spd_launch': [0x801a77b8]}
SCGETAREA = 0x80238050
PD_CHANNEL = ROOT / 'workspace/channels/personal-data'
KOREAN_SAMPLE = PD_CHANNEL / 'local-feed-v1/fictional-pd-plain.bin'

# Shift-JIS-encodable fictional values: isolates a Hangul/Shift-JIS problem in
# Demae's request path from a data-format problem. Obviously fictional.
JP_COMPATIBLE = dict(last_name='テスト', first_name='タロウ', kana_last_name='テスト', kana_first_name='タロウ',
                     zip_code='1000000', state='テスト県', city='テスト市', home_address='テスト町1-1',
                     apartment_number='', phone_number='0300000000', email_address='test@example.com')


def korean_sample():
    """The personal-data worker's fictional Korean plaintext, hash-checked."""
    import hashlib, json
    from kwce import personal_data_format as fmt
    manifest = json.loads((PD_CHANNEL / 'local-feed-v1/fixture-manifest.json').read_text(encoding='utf-8'))
    if not (manifest.get('fictional') and manifest.get('synthetic') and manifest.get('local_only')):
        raise ValueError('Personal-data sample is not marked fictional/synthetic/local')
    expected = next(f['sha256'] for f in manifest['files'] if f['path'] == 'fictional-pd-plain.bin')
    plain = KOREAN_SAMPLE.read_bytes()
    if hashlib.sha256(plain).hexdigest() != expected:
        raise ValueError('Personal-data fictional sample differs from its manifest')
    fmt.check(plain)
    return plain


def jp_compatible(plain):
    """Same PDFF template with Shift-JIS-encodable fictional values."""
    from kwce import personal_data_format as fmt
    out = plain
    for name, value in JP_COMPATIBLE.items():
        value.encode('shift-jis')  # must be representable on Demae's SJIS request path
        out = fmt.put(out, name, value)
    fmt.check(out)
    return out


def variant(name):
    plain = korean_sample()
    if name == 'korean':
        return fix_korean_name_order(plain)
    if name == 'korean-spd':
        return spd_identical(plain)
    if name == 'jp-compatible':
        return jp_compatible(plain)
    raise ValueError('Unknown personal-data variant: ' + name)


def spd_identical(plain):
    """Fictional data exactly as the Korean SPD writes it (lead review 2026-10-28, wave 2).

    The Korean SPD has no reading field: it stores kana == name for BOTH the family
    and the given field (scripts/verify_personal_data_test.py). Demae refuses a pd.dat
    whose family reading is empty ("「이름」의 「읽는 법」이 없습니다"), which is what the
    'korean' variant (fix_korean_name_order) triggered. This variant keeps the
    worker's sample unchanged and asserts the SPD invariant. Display order on
    Demae's layout stays given + family ("길동 홍 님") - not patched, see food.md."""
    from kwce import personal_data_format as fmt
    f = fmt.fields(plain)
    for name, kana in (('last_name', 'kana_last_name'), ('first_name', 'kana_first_name')):
        if not f[name] or f[kana] != f[name]:
            raise ValueError('Fictional data is not Korean-SPD-identical: ' + name)
    fmt.check(plain)
    return plain


def fix_korean_name_order(plain):
    """Demae's layout prints given-name then family-name (Japanese order), so a
    Korean name stored family/given shows reversed ("길동 홍"). The safe test-data
    fix is to carry the whole Korean name in the given-name field and clear the
    family field, so the same layout reads "홍길동". No DOL/layout change.
    Real Korean SPD data keeps family+given separate and would read reversed on
    this layout unless the SPD stores the full name in the given field or the
    channel's name concatenation is patched (DOL; deferred)."""
    from kwce import personal_data_format as fmt
    f = fmt.fields(plain)
    full = (f['last_name'] + f['first_name']).strip()
    kana = (f['kana_last_name'] + f['kana_first_name']).strip()
    out = plain
    out = fmt.put(out, 'first_name', full); out = fmt.put(out, 'last_name', '')
    out = fmt.put(out, 'kana_first_name', kana); out = fmt.put(out, 'kana_last_name', '')
    fmt.check(out)
    return out


def summary(plain):
    """Non-secret summary of fictional data (field emptiness + PIN flags)."""
    from kwce import personal_data_format as fmt
    f = fmt.fields(plain)
    return dict(home_address_set=bool(f['home_address']), kana_set=bool((f['kana_last_name'] + f['kana_first_name']).strip()),
                phone_digits=sum(c.isdigit() for c in f['phone_number']), zip_digits=sum(c.isdigit() for c in f['zip_code']),
                pin_protected=f['pin_protected'], sjis_encodable=_sjis_ok(f))


def _sjis_ok(f):
    try:
        for k, v in f.items():
            if isinstance(v, str):
                v.encode('shift-jis')
        return True
    except UnicodeEncodeError:
        return False
