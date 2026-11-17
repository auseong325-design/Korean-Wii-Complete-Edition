"""Korean-console builds of WiiLink's real-order Food Channel editions (Domino's, Just Eat).

WiiLink ships two Food Channel editions that place real orders: Domino's (USA, Canada) and
Just Eat (UK, Ireland, Spain, Germany, Austria, Italy). Each is the stock Japanese Food Channel
v512 with WiiLink's public bsdiff patches on contents 0-2 (banner, executable with the WiiLink
payload, English resources), which is what the WiiLink patcher installs. The rebuilt contents
are checked against WiiLink's own edition TMD before anything else is changed. On top of that
this module adds only what a Korean Wii needs:

1. Korea-area bridge (kwce.food_compat.patch_korean_area): SCGetArea KOR(6) -> JPN(0), the same
   bridge as the standard Korean build, so the channel starts and uses the Japanese
   personal-data path the payload expects.
2. Server country. The payload's sc::GetCountry() returns the first byte of SYSCONF IPL.SADR
   (136 on a Korean Wii) and sends it as X-WiiCountryCode on every request. The Domino's server
   accepts only 18/49 and the Just Eat server only 66/78/82/83/105/110; any other value is
   refused (InvalidCountry / ErrInvalidCountry). One instruction of GetCountry
   (srwi r3,r29,24 -> li r3,<code>) makes it return the chosen supported country, so one WAD is
   built per country. The Domino's order-tracker link (country "ca" when the value is 18) follows
   the same value. No code cave and no new DOL section are used.
3. Korean shared fonts (content 3), Korean HOME Menu (content 4) and the Korean column of the HOME
   dialog table in content 2 (the HOME library reads column 0 on a Korean console).
4. A Korean channel name with the edition and country in the IMET name slots (banner graphics
   kept), TMD region 4 (KOR).

The edition's menus stay English (WiiLink's text). Not applied: our Korean executable strings,
address card, phone check and confirm card; the payload formats addresses and phone numbers
itself and writes some of the same addresses (for example 0x80024620).

local=True makes the Dolphin-only test build: the payload's four service literals point to
127.0.0.2 and the API scheme is http. Hardware builds refuse any loopback address.
"""
import struct

from .channels import ChannelArchive, ROOT, load_library, sha256

TITLE = '000100014843484a'
BOOT = 9
SOURCE = 'workspace/channels/food/originals/food-japan-v512.wad'
REF = 'workspace/channels/food/references/wiilink-patcher'
PAYLOAD_VA = 0x80474580     # DOL data section holding the WiiLink payload (copied to RUN_BASE)
PAYLOAD_SIZE = 0x1800
RUN_BASE = 0x80001800       # payload link address (demae-patches payload.ld)
SCHEME_VA = 0x802d63b6      # "https://" literal of the API base URL
LOCAL = b'127.0.0.2'

EDITIONS = {
    'dominos': dict(folder='dominos', patches=('Dominos_0', 'Dominos_1', 'Dominos_2'),
                    tmd='dominos__Dominos.tmd', host=b'dom.wiilink24.com', label="Domino's",
                    country_site=0x800022f8, lz11=True, https=True,
                    server='https://dom.wiilink24.com (WiiLink Demae-Dominos)'),
    'justeat': dict(folder='eater', patches=('JustEat_0_English', 'JustEat_1_English', 'JustEat_2_English'),
                    tmd='eater__eater.tmd', host=b'eater.wiilink.ca', label='Just Eat',
                    country_site=0x800023b4, lz11=False, https=False,
                    server='http://eater.wiilink.ca (WiiLink Demae-JustEat)'),
}

# variant -> (edition, Wii SYSCONF country code the WiiLink server accepts, English name, Korean name)
VARIANTS = {
    'dominos-us': ('dominos', 49, 'United States', '미국'),
    'dominos-ca': ('dominos', 18, 'Canada', '캐나다'),
    'justeat-uk': ('justeat', 110, 'United Kingdom', '영국'),
    'justeat-ie': ('justeat', 82, 'Ireland', '아일랜드'),
    'justeat-es': ('justeat', 105, 'Spain', '스페인'),
    'justeat-de': ('justeat', 78, 'Germany', '독일'),
    'justeat-at': ('justeat', 66, 'Austria', '오스트리아'),
    'justeat-it': ('justeat', 83, 'Italy', '이탈리아'),
}

SRWI_R3_R29_24 = 0x57a3463e
LI_R3 = 0x38600000


def label(variant):
    edition, _code, country, _ko = VARIANTS[variant]
    return f"{EDITIONS[edition]['label']} - {country}"


def korean_name(variant):
    edition, _code, _country, ko = VARIANTS[variant]
    return f"음식 배달 채널 {EDITIONS[edition]['label']} ({ko})"


def _sections(dol):
    off = struct.unpack_from('>18I', dol, 0)
    addr = struct.unpack_from('>18I', dol, 0x48)
    size = struct.unpack_from('>18I', dol, 0x90)
    return [(off[i], addr[i], size[i]) for i in range(18) if size[i]]


def _va_to_file(dol, va, length=1):
    for off, addr, size in _sections(dol):
        if addr <= va and va + length <= addr + size:
            return off + va - addr
    raise ValueError(f'0x{va:08x} is outside the DOL sections')


def _payload(dol):
    sec = [(off, size) for off, addr, size in _sections(dol) if addr == PAYLOAD_VA]
    if len(sec) != 1 or sec[0][1] != PAYLOAD_SIZE:
        raise ValueError('WiiLink payload section not found')
    return sec[0][0]


# SHA-256 of the WiiLink files fetched from patcher.wiilink24.com (variants-acquisition.json).
PATCH_SHA256 = {
    'Dominos_0': '72928ccb556f4248f7adae4ab78394e523a0a7b640d97092f9ee0917e29faeb2',
    'Dominos_1': '6651f7dc2c049b1ae76ad44d664d8f7df9465a1696c2e2dd9217a2932c63c002',
    'Dominos_2': 'e71450e3b23d555f1164e95151505163a633e1f992b1f3af50758370c5e7646b',
    'JustEat_0_English': 'fd892968528bd8b9557f761244f05c0abbd5f8d6e1e9b0068ddfb69c8e228f63',
    'JustEat_1_English': '889ed14168e127b837b39ad36d8aaa28483b94d4b0f0fd391e649d6192900939',
    'JustEat_2_English': 'e71450e3b23d555f1164e95151505163a633e1f992b1f3af50758370c5e7646b',
    'dominos__Dominos.tmd': 'de430ae669e0c7aa8c5268340f4d268dc601ae4462b516e920b9c46404cd1b90',
    'eater__eater.tmd': '7431b62fc627b6ea795312de771a72120d5268c4111358ee83e928e59eb23524',
}


def edition_contents(stock, stock_tmd, edition):
    """Contents 0-2 of a WiiLink edition, rebuilt from the stock contents like the WiiLink patcher.

    stock = {index: bytes} of the Japanese v512 WAD, stock_tmd = its TMD bytes. The WiiLink
    patcher packs the patched contents into the edition TMD, so its content hashes are not a
    reference (the Domino's TMD still lists the stock hashes). The check is: every input file
    has its pinned SHA-256, and the edition TMD equals the stock TMD apart from the content
    records and the region byte (3 = any), so the stock TMD with region 4 is equivalent."""
    from . import bspatch
    e = EDITIONS[edition]
    tmd = (ROOT / REF / e['tmd']).read_bytes()
    if sha256(tmd) != PATCH_SHA256[e['tmd']]:
        raise ValueError(f'{edition}: WiiLink TMD differs from the pinned file')
    if len(tmd) != len(stock_tmd) or [i for i in range(0x140, 0x1E4) if tmd[i] != stock_tmd[i]] != [0x19d] or tmd[0x19d] != 3:
        raise ValueError(f'{edition}: WiiLink TMD header differs from stock beyond the region byte')
    out, patches = {}, {}
    for i, name in enumerate(e['patches']):
        raw = (ROOT / REF / f"bsdiff__{e['folder']}__{name}.bsdiff").read_bytes()
        if sha256(raw) != PATCH_SHA256[name]:
            raise ValueError(f'{edition}: {name} differs from the pinned WiiLink patch')
        out[i] = bspatch.apply(stock[i], raw)
        patches[name] = dict(patch_sha256=sha256(raw), content_sha256=sha256(out[i]), bytes=len(out[i]))
    return out, dict(patches=patches, wiilink_tmd=e['tmd'], wiilink_tmd_sha256=sha256(tmd),
                     wiilink_tmd_header='stock except region byte 3 (any)')


def patch_country(dol, edition, code):
    """sc::GetCountry -> constant `code`. dol = uncompressed edition executable."""
    if not 0 < code < 0x8000:
        raise ValueError('country code')
    base = _payload(dol)
    words = list(struct.unpack_from(f'>{PAYLOAD_SIZE // 4}I', dol, base))
    li_r4 = [k for k, w in enumerate(words) if w == 0x38801008]          # li r4,0x1008 (SCFindByteArrayItem size)
    srwi = [k for k, w in enumerate(words) if w == SRWI_R3_R29_24]
    if len(li_r4) != 1 or len(srwi) != 1 or words[li_r4[0] - 1] != 0x38a00010:   # li r5,0x10 (IPL.SADR)
        raise ValueError(f'{edition}: GetCountry signature not unique')
    k = srwi[0]
    if not 0 < k - li_r4[0] < 16 or 0x83bf0000 not in words[li_r4[0]:k]:     # lwz r29,0(r31): first word of SADR
        raise ValueError(f'{edition}: GetCountry body differs')
    nxt = words[k + 1]
    if nxt >> 26 != 18 or nxt & 3:                                          # b <epilogue>
        raise ValueError(f'{edition}: GetCountry epilogue differs')
    site = RUN_BASE + 4 * k
    if site != EDITIONS[edition]['country_site']:
        raise ValueError(f'{edition}: GetCountry site moved (0x{site:08x})')
    start = k
    while start > 0 and words[start] >> 16 != 0x9421:                       # stwu r1,-x(r1)
        start -= 1
    callers = sum(1 for j, w in enumerate(words) if w >> 26 == 18 and w & 3 == 1 and
                  4 * j + ((w & 0x3fffffc) - (0x4000000 if w & 0x2000000 else 0)) == 4 * start)
    data = bytearray(dol)
    at = base + 4 * k
    data[at:at + 4] = struct.pack('>I', LI_R3 | code)
    return bytes(data), dict(function='payload sc::GetCountry (X-WiiCountryCode and the Domino\'s tracker link)',
                             function_entry=f'0x{RUN_BASE + 4 * start:08x}', site=f'0x{site:08x}',
                             dol_file_offset=f'0x{at:x}', original=f'{SRWI_R3_R29_24:08x}',
                             patched=f'{LI_R3 | code:08x}', country_code=code, callers=callers,
                             console_country_ignored=True, code_cave=False)


# Domino's payload only (the shipped binary, not the current WiiLink source): before copying the Wii
# number it compares ES device ID with Dolphin's default 0x0403AC68 and stops with "Please use a NAND
# dump from a real console". A real Wii never has that ID. Local revision >= 2 builds branch past it,
# because the test bed uses Dolphin's default ID and talks only to 127.0.0.2.
DEFAULT_ID_CHECK = bytes.fromhex('3d2004036129ac687c0a480040a20024')   # lis/ori 0x0403ac68; cmpw r10,r9; bne +0x24
DEFAULT_ID_SKIP = bytes.fromhex('48000024')                              # b +0x24


def skip_default_id_check(dol):
    """Dolphin-only (local builds): never show the payload's default-device-ID stop screen."""
    base = _payload(dol)
    at = dol.find(DEFAULT_ID_CHECK, base, base + PAYLOAD_SIZE)
    if at < 0 or dol.find(DEFAULT_ID_CHECK, at + 1, base + PAYLOAD_SIZE) >= 0:
        raise ValueError('Default device-ID check not found exactly once')
    site = at + 12
    data = bytearray(dol)
    data[site:site + 4] = DEFAULT_ID_SKIP
    return bytes(data), dict(site=f'0x{RUN_BASE + site - base:08x}', original='40a20024', patched='48000024',
                             reason='Dolphin default device ID 0x0403ac68 in the test bed; local build only')


def redirect_local(dol, edition):
    """Dolphin-only: the payload's four service literals -> 127.0.0.2, API scheme http."""
    e = EDITIONS[edition]
    host = e['host']
    base = _payload(dol)
    data = bytearray(dol)
    hosts, at = 0, data.find(host, base, base + PAYLOAD_SIZE)
    while at >= 0:
        if data[at - 1] != 0 or data[at + len(host):at + len(host) + 1] != b'/':
            raise ValueError(f'{edition}: unexpected service literal context')
        end = data.index(b'\0', at)
        old = bytes(data[at:end])
        new = LOCAL + old[len(host):]
        data[at:end] = new + bytes(len(old) - len(new))
        hosts += 1
        at = data.find(host, at + 1, base + PAYLOAD_SIZE)
    if hosts != 4 or host in data:
        raise ValueError(f'{edition}: service literal count')
    downgraded = 0
    if e['https']:
        s = _va_to_file(dol, SCHEME_VA, 9)
        if bytes(data[s:s + 9]) != b'https://\0':
            raise ValueError(f'{edition}: API scheme literal differs')
        data[s:s + 9] = b'http://\0\0'
        downgraded = 1
    return bytes(data), dict(hosts=hosts, loopback=LOCAL.decode(), scheme='http', https_downgraded=downgraded)


def build(variant, *, local=False, revision=1):
    """Return (WAD bytes, manifest dict). Hardware builds are fakesigned; local builds are not.

    revision 1: area bridge + server country + Korean fonts / HOME / HOME CSV / IMET names.
    revision 2: local builds only -- revision 1 plus skip_default_id_check for Domino's."""
    if revision not in (1, 2) or (revision == 2 and not local):
        raise ValueError('Food edition revision 2 exists for local test builds only')
    from .food_compat import patch_korean_area
    from .wiiroom_formats import decompress_lz11, compress_lz11_optimal
    from .channel_korean_font import korean_shared_fonts
    from .home_menu import korean_home_menu, KOREAN_SHARED, SOURCES
    from .food_banner import korean_banner
    from .food_resources import korean_home_csv, HOME_CSV
    from .hardware import hardware_wad
    edition, code, country, _ko = VARIANTS[variant]
    e = EDITIONS[edition]
    lib = load_library()
    source = (ROOT / SOURCE).read_bytes()
    title = lib.title.Title()
    title.load_wad(source)
    if title.tmd.title_id != TITLE or title.tmd.boot_index != BOOT or title.tmd.title_version != 512:
        raise ValueError('Food source identity differs')
    stock = {i: title.get_content_by_index(i) for i in range(title.tmd.num_contents)}
    wl, wl_rec = edition_contents(stock, title.tmd.dump(), edition)

    raw1 = wl[1]
    packed = raw1[:1] == b'\x11'
    if packed != e['lz11']:
        raise ValueError(f'{edition}: content 1 encoding differs from the WiiLink edition')
    dol = decompress_lz11(raw1) if packed else raw1
    if dol[:4] != b'\x00\x00\x01\x00':
        raise ValueError(f'{edition}: content 1 is not a DOL')
    dol, area = patch_korean_area(dol)
    dol, country_rec = patch_country(dol, edition, code)
    local_rec = None
    if local:
        dol, local_rec = redirect_local(dol, edition)
        if revision >= 2 and edition == 'dominos':
            dol, local_rec['default_id_check_skipped'] = skip_default_id_check(dol)
    elif b'127.0.0' in dol or b'localhost' in dol:
        raise ValueError('Hardware build must not contain loopback endpoints')
    if packed:
        content1 = compress_lz11_optimal(dol)
        if decompress_lz11(content1) != dol:
            raise ValueError('Food edition LZ11 roundtrip failed')
    else:
        content1 = dol
    title.set_content(content1, 1)

    banner, banner_rec = korean_banner(wl[0], name=korean_name(variant))
    title.set_content(banner, 0)

    outer = ChannelArchive(wl[2])
    csv, csv_rec = korean_home_csv(outer.get(HOME_CSV))
    content2 = outer.replace(HOME_CSV, csv)
    if set(ChannelArchive(content2).files) != set(outer.files):
        raise ValueError('Food edition content 2 file list changed')
    title.set_content(content2, 2)

    fonts, font_rec = korean_shared_fonts()
    title.set_content(fonts, 3)
    home, home_rec = korean_home_menu(stock[4], fix_dialogs=True, all_dialog_languages=True)
    home = ChannelArchive(home)
    korean = ChannelArchive(KOREAN_SHARED.read_bytes())
    for folder, path in SOURCES.items():
        name = folder + '/LZ77_homeBtn.arc'
        if name in home.files:
            home = ChannelArchive(home.replace(name, korean.get(path)))
    title.set_content(home.compact(), 4)
    title.tmd.region = 4
    built = title.dump_wad()

    if local:
        wad, checks = built, None
    else:
        wad, checks = hardware_wad(built, source)
    check = lib.title.Title()
    check.load_wad(wad)
    changed = [i for i in range(check.tmd.num_contents) if check.get_content_by_index(i) != stock[i]]
    if changed != [0, 1, 2, 3, 4] or check.tmd.region != 4 or check.tmd.title_id != TITLE:
        raise ValueError('Unexpected Food edition content change: ' + str(changed))
    for i in range(5, check.tmd.num_contents):
        if check.get_content_by_index(i) != stock[i]:
            raise ValueError('Food edition changed a content it must keep')
    manifest = dict(channel='food', variant=variant, edition=edition, edition_label=label(variant),
                    country=country, country_code=code, title_id=TITLE, boot_index=BOOT,
                    wad_sha256=sha256(wad), original_sha256=sha256(source), wiilink=wl_rec,
                    service=e['server'], korean_area_bridge=area, server_country=country_rec,
                    banner=banner_rec, home_csv=csv_rec, shared_fonts=font_rec, korean_home=home_rec,
                    content1_encoding='LZ11 (as WiiLink ships it)' if packed else 'uncompressed DOL (as WiiLink ships it)',
                    changed_contents=changed, tmd_region=check.tmd.region, menus='English (WiiLink edition text)',
                    not_applied=['Korean executable strings', 'address card', 'phone check', 'confirm card'],
                    real_orders_tested=False, local_only=local, hardware_candidate=not local,
                    full_localization_complete=False, hardware_success_verified=False)
    if local_rec is not None:
        manifest['local_redirect'] = local_rec
    if checks is not None:
        manifest['hardware_checks'] = checks
    return wad, manifest
