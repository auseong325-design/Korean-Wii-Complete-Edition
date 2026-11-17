"""Public patch bundle (design v3): PC-side patcher, community-style binary deltas.

A public bundle holds no finished WADs and no whole Nintendo files. It holds, per SD file of a
personal bundle (kwce-rc-sd-vN):
  - KWCE's own files verbatim (installer, text, Priiloader definitions, GPL players, our TMDs), and
  - for every channel WAD a recipe: which official base title to fetch (Nintendo update server, plus the
    WiiLink patches the WiiLink Patcher itself applies), and per content keep / copy / zstd delta.
The patcher rebuilds every SD file and refuses a file whose SHA-256 differs from the personal bundle.

Keys: title keys are derived with libWiiPy's built-in common keys, exactly like WiiLink Patcher and
NUSGet; this module holds no key material.
"""
import hashlib
import json
import shutil
import struct
import urllib.request
from pathlib import Path

import zstandard

from kwce import bspatch
from kwce.channels import load_library

ROOT = Path(__file__).resolve().parents[1]
WIILINK = 'https://patcher.wiilink24.com'
UA = {'User-Agent': 'KWCE-Patcher/1'}
SYSMENU = dict(name='System Menu 4.3K', title_id='0000000100000002', version=518)
MAX_WINDOW = 1 << 30


def sha1(b): return hashlib.sha1(b).hexdigest()
def sha256(b): return hashlib.sha256(b).hexdigest()
def al(x, a): return (x + a - 1) & ~(a - 1)


def crypto():
    load_library()
    from libWiiPy.title import crypto as c
    return c


# ---------------------------------------------------------------- deltas
def make_delta(base, target):
    wl = max(20, min(30, (len(base) + len(target)).bit_length()))
    params = zstandard.ZstdCompressionParameters.from_level(19, source_size=len(target), dict_size=len(base),
                                                            window_log=wl, enable_ldm=True,
                                                            write_content_size=True, write_checksum=True)
    d = zstandard.ZstdCompressionDict(base, dict_type=zstandard.DICT_TYPE_RAWCONTENT) if base else None
    return zstandard.ZstdCompressor(compression_params=params, dict_data=d).compress(target)


def apply_delta(base, patch, size):
    d = zstandard.ZstdCompressionDict(base, dict_type=zstandard.DICT_TYPE_RAWCONTENT) if base else None
    out = zstandard.ZstdDecompressor(dict_data=d, max_window_size=MAX_WINDOW).decompress(patch, max_output_size=size)
    if len(out) != size:
        raise ValueError('delta output size mismatch')
    return out


# ---------------------------------------------------------------- WAD
class Wad:
    """Exact-layout WAD view: sections as stored, contents as encrypted blobs in TMD order."""

    def __init__(self, raw):
        if raw[4:8] not in (b'Is\0\0', b'ib\0\0') or struct.unpack('>I', raw[:4])[0] != 0x20:
            raise ValueError('not an installable WAD')
        self.header = raw[:0x20]
        cert, crl, tik, tmd, data, foot = struct.unpack('>6I', raw[8:0x20])
        o = 0x40
        self.cert = raw[o:o + cert]; o += al(cert, 0x40)
        self.crl = raw[o:o + crl]; o += al(crl, 0x40)
        self.ticket = raw[o:o + tik]; o += al(tik, 0x40)
        self.tmd = raw[o:o + tmd]; o += al(tmd, 0x40)
        self.records = records(self.tmd)
        self.enc = []
        p = o
        for r in self.records:
            n = al(r['size'], 16)
            self.enc.append(raw[p:p + n]); p += al(n, 0x40)
        o += al(data, 0x40)
        self.footer = raw[o:o + foot]
        self.length = len(raw)
        self.title_id = self.tmd[0x18C:0x194].hex()
        self._key = None

    def key(self):
        if self._key is None:
            t = self.ticket
            self._key = crypto().decrypt_title_key(t[0x1BF:0x1CF], t[0x1F1], t[0x1DC:0x1E4])
        return self._key

    def dec_full(self, i):
        """Decrypted content including the up-to-15 padding bytes of the last AES block."""
        r = self.records[i]
        return crypto().decrypt_content(self.enc[i], self.key(), r['index'], al(r['size'], 16))

    def dec(self, i):
        return self.dec_full(i)[:self.records[i]['size']]


def records(tmd):
    n = struct.unpack('>H', tmd[0x1DE:0x1E0])[0]
    out = []
    for i in range(n):
        r = tmd[0x1E4 + 36 * i:0x1E4 + 36 * i + 36]
        cid, index, typ, size = struct.unpack('>IHHQ', r[:16])
        out.append(dict(cid=cid, index=index, type=typ, size=size, sha1=r[16:36].hex()))
    return out


def encrypt(dec_full, key, index):
    return crypto().encrypt_content(dec_full, key, index)


def build_wad(header, cert, crl, ticket, tmd, enc, footer, length):
    """Sections and contents on 0x40 boundaries, then cut or zero-fill to the recorded file length
    (tools differ on trailing padding; the make step proves byte equality before a recipe is kept)."""
    out = bytearray(header)
    for part in (cert, crl, ticket, tmd, *enc, footer):
        out += bytes(al(len(out), 0x40) - len(out)); out += part
    if len(out) > length:
        if any(out[length:]):
            raise ValueError('WAD layout longer than recorded length')
        del out[length:]
    return bytes(out) + bytes(length - len(out))


# ---------------------------------------------------------------- official bases
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def build_base(spec, log=print):
    """Same steps as WiiLink-Patcher-GUI v1.5.3 patch_channel(): NUS title, WiiLink bsdiff/ticket/TMD."""
    lib = load_library()
    folder = spec.get('patch_folder') or ''
    add = spec.get('additional_files') or []
    title = lib.title.Title()
    title.load_tmd(lib.title.download_tmd(spec['title_id'], spec.get('version')))
    tik = get(f"{WIILINK}/{folder.lower()}/{spec['title_id']}.tik") if 'ticket' in add else \
        lib.title.download_ticket(spec['title_id'], spec.get('version'))
    title.load_ticket(tik)
    title.load_cert_chain(lib.title.download_cert_chain())
    title.load_content_records()
    title.content.content_list = [lib.title.download_content(title.tmd.title_id, r.content_id)
                                  for r in title.tmd.content_records]
    for p in spec.get('patches') or []:
        raw = get(f"{WIILINK}/bsdiff/{folder.lower()}/{p['patch_name']}.bsdiff")
        title.set_content(bspatch.apply(title.get_content_by_index(p['content_id']), raw), p['content_id'])
    if 'tmd' in add:
        title.load_tmd(get(f"{WIILINK}/{folder.lower()}/{folder}.tmd"))
    return title.dump_wad()


class Bases:
    """Hash-checked cache of rebuilt official titles (cache/<sha-of-name>.wad)."""

    def __init__(self, cache, specs, log=print):
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True)
        self.specs = specs; self.log = log; self._mem = {}

    def path(self, name):
        return self.cache / (hashlib.sha1(name.encode()).hexdigest()[:16] + '.wad')

    def wad(self, name):
        if name not in self._mem:
            spec = self.specs[name]; p = self.path(name)
            raw = p.read_bytes() if p.is_file() else None
            if raw is None or (spec.get('wad_sha256') and sha256(raw) != spec['wad_sha256']):
                self.log(f'  받는 중: {name}')
                raw = build_base(spec, self.log)
                if spec.get('wad_sha256') and sha256(raw) != spec['wad_sha256']:
                    raise ValueError(f'{name}: 받은 원본이 지원하는 판과 다릅니다(닌텐도 서버 또는 WiiLink 패치가 바뀜)')
                p.write_bytes(raw)
            self._mem = {name: Wad(raw)}          # keep one in memory
        return self._mem[name]


# ---------------------------------------------------------------- delta dictionaries
HOME_ASH = ['sysash:layout/common/homeBtn1.ash', 'sysash:layout/kor/homeBtn1.ash']
OWN_CANDIDATES = [[], ['sys'], HOME_ASH, ['file:kwce/dvd/player.dol'], ['file:kwce/dvd/home.arc']]


class Dicts:
    """Delta dictionaries by token: 'own' (same-index base content), 'sys' (all System Menu contents),
    'sysash:<path>' (an ASH member of the System Menu resource archive, decompressed),
    'file:<rel>' (another SD file of the same bundle, already present under root)."""

    def __init__(self, sysmenu, root):
        self.sysmenu = sysmenu; self.root = Path(root); self._sys = None; self._ash = {}

    def sys(self):
        if self._sys is None:
            self._sys = b''.join(self.sysmenu.dec(i) for i in range(len(self.sysmenu.records)))
        return self._sys

    def ash(self, path):
        if path not in self._ash:
            from kwce.formats import U8, ash_decompress
            for i in range(len(self.sysmenu.records)):
                d = self.sysmenu.dec(i)
                if d[:4] != b'U\xaa8-':
                    continue
                try:
                    self._ash[path] = ash_decompress(U8(d).get(path)); break
                except Exception:
                    continue
            else:
                raise ValueError('System Menu resource not found: ' + path)
        return self._ash[path]

    def resolve(self, tokens, own=b''):
        out = b''
        for t in tokens:
            if t == 'own': out += own
            elif t == 'sys': out += self.sys()
            elif t.startswith('sysash:'): out += self.ash(t[7:])
            elif t.startswith('file:'): out += (self.root / t[5:]).read_bytes()
            else: raise ValueError('unknown dictionary ' + t)
        return out

    def best(self, target, candidates, own=b''):
        """(tokens, patch): the first candidate unless a later one is at least 10% smaller."""
        best = None
        for tokens in candidates:
            try:
                patch = make_delta(self.resolve(tokens, own), target)
            except (OSError, ValueError):
                continue
            if best is None or len(patch) < len(best[1]) * 0.9:
                best = (tokens, patch)
        return best


def _save(out_dir, name, blob):
    p = Path(out_dir) / 'patch' / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(blob)


# ---------------------------------------------------------------- make
def _content_rows(tw, bw, dicts, rel, own_candidates):
    sys_by_sha = {r['sha1']: i for i, r in enumerate(dicts.sysmenu.records)}
    same_key = bw is not None and bw.ticket[0x1BF:0x1CF] == tw.ticket[0x1BF:0x1CF] and bw.ticket[0x1F1] == tw.ticket[0x1F1]
    rows, blobs, total = [], {}, 0
    for i, r in enumerate(tw.records):
        row = dict(index=r['index'], size=r['size'], sha1=r['sha1'])
        full = tw.dec_full(i); dec = full[:r['size']]
        if sha1(dec) != r['sha1']:
            raise ValueError(f'{rel}: content {i} does not match its TMD')
        if any(full[r['size']:]):
            row['pad'] = full[r['size']:].hex()
        if same_key and tw.enc[i] == bw.enc[i]:
            row['mode'] = 'keep'
        elif r['sha1'] in sys_by_sha:
            row.update(mode='copy', sys=sys_by_sha[r['sha1']])
        else:
            if bw is not None:
                tokens, patch = dicts.best(dec, [['own'], ['own', 'sys']], bw.dec(i))
            else:
                tokens, patch = dicts.best(dec, own_candidates)
            row.update(mode='delta', dict=tokens, patch=f'{rel}.c{i}.zst', patch_bytes=len(patch))
            blobs[row['patch']] = patch; total += len(patch)
        rows.append(row)
    return rows, blobs, total


def make_wad_recipe(target_raw, candidates, bases, dicts, out_dir, rel):
    """Recipe for one WAD. With no fitting official base the WAD is KWCE's own title (GPL player,
    settings fork): its sections are stored as they are and each content is a copy/delta."""
    tw = Wad(target_raw)
    best = None
    for name in candidates:
        bw = bases.wad(name)
        if bw.title_id != tw.title_id or len(bw.records) != len(tw.records):
            continue
        rows, blobs, total = _content_rows(tw, bw, dicts, rel, None)
        if best is None or total < best['total'] * 0.9:
            best = dict(base=name, rows=rows, blobs=blobs, total=total, bw=bw)
    if best is None:
        rows, blobs, total = _content_rows(tw, None, dicts, rel, [c for c in OWN_CANDIDATES])
        best = dict(base=None, rows=rows, blobs=blobs, total=total, bw=None)
    bw, blobs = best['bw'], best['blobs']
    recipe = dict(base=best['base'], contents=best['rows'], patch_total=best['total'], length=tw.length,
                  header=tw.header.hex(), sha256=sha256(target_raw), size=len(target_raw))
    for field in ('cert', 'crl', 'ticket', 'tmd', 'footer'):
        mine = getattr(tw, field)
        if bw is not None and mine == getattr(bw, field):
            recipe[field] = 'base'
        elif not mine:
            recipe[field] = ''
        elif field == 'footer':
            # a footer is usually a copy of the banner content: refer to it instead of storing it
            same = [i for i, r in enumerate(tw.records) if r['size'] == len(mine) and r['sha1'] == sha1(mine)]
            if same:
                recipe[field] = f'content:{same[0]}'
            else:
                patch = make_delta(tw.dec(0), mine)
                blobs[f'{rel}.footer.zst'] = patch; recipe[field] = f'delta:{len(mine)}:{rel}.footer.zst'
                recipe['patch_total'] += len(patch)
        else:
            blobs[f'{rel}.{field}'] = mine; recipe[field] = f'{rel}.{field}'
            recipe['patch_total'] += len(mine)
    for name, blob in blobs.items():
        _save(out_dir, name, blob)
    if apply_wad_recipe(recipe, bases, dicts, out_dir) != target_raw:      # prove it before accepting
        raise ValueError(f'{rel}: recipe does not reproduce the file')
    return recipe


def apply_wad_recipe(recipe, bases, dicts, bundle):
    bw = bases.wad(recipe['base']) if recipe['base'] else None
    part = {}
    for field in ('cert', 'crl', 'ticket', 'tmd'):
        v = recipe[field]
        part[field] = getattr(bw, field) if v == 'base' else (Path(bundle) / 'patch' / v).read_bytes() if v else b''
    t = part['ticket']
    key = crypto().decrypt_title_key(t[0x1BF:0x1CF], t[0x1F1], t[0x1DC:0x1E4])
    enc, decs = [], {}
    for i, row in enumerate(recipe['contents']):
        if row['mode'] == 'keep':
            enc.append(bw.enc[i]); continue
        if row['mode'] == 'copy':
            dec = dicts.sysmenu.dec(row['sys'])
        else:
            base = dicts.resolve(row['dict'], bw.dec(i) if 'own' in row['dict'] else b'')
            dec = apply_delta(base, (Path(bundle) / 'patch' / row['patch']).read_bytes(), row['size'])
        if sha1(dec) != row['sha1']:
            raise ValueError('patched content hash mismatch')
        pad = bytes.fromhex(row['pad']) if 'pad' in row else bytes(al(row['size'], 16) - row['size'])
        enc.append(encrypt(dec + pad, key, row['index'])); decs[i] = dec
    def content(i):
        return decs[i] if i in decs else bw.dec(i)
    f = recipe['footer']
    if f == 'base': footer = bw.footer
    elif not f: footer = b''
    elif f.startswith('content:'): footer = content(int(f[8:]))
    else:
        _, size, name = f.split(':', 2)
        footer = apply_delta(content(0), (Path(bundle) / 'patch' / name).read_bytes(), int(size))
    return build_wad(bytes.fromhex(recipe['header']), part['cert'], part['crl'], part['ticket'], part['tmd'], enc,
                     footer, recipe['length'])


def make_file_recipe(data, dicts, out_dir, rel):
    """Non-WAD SD file: copy of a System Menu content, a delta when a dictionary really helps
    (under 70% of plain compression), else the file itself (KWCE's own work)."""
    for i, r in enumerate(dicts.sysmenu.records):
        if r['size'] == len(data) and r['sha1'] == sha1(data):
            return dict(mode='copy', sys=i, sha256=sha256(data), size=len(data))
    if len(data) > 200000:
        cands = [c for c in OWN_CANDIDATES if 'file:' + rel not in c]
        plain = len(make_delta(b'', data))
        tokens, patch = dicts.best(data, cands)
        if tokens and len(patch) < plain * 0.7:
            _save(out_dir, rel + '.zst', patch)
            return dict(mode='delta', dict=tokens, patch=rel + '.zst', patch_bytes=len(patch), sha256=sha256(data), size=len(data))
    p = Path(out_dir) / 'files' / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    return dict(mode='verbatim', sha256=sha256(data), size=len(data))


# ---------------------------------------------------------------- apply (the patcher)
def _needs_files(rec):
    toks = list(rec.get('dict', [])) + [t for c in rec.get('contents', []) for t in c.get('dict', [])]
    return any(t.startswith('file:') for t in toks)


def apply_bundle(bundle, out, cache, log=print):
    bundle, out = Path(bundle), Path(out)
    raw = (bundle / 'manifest.json').read_bytes()
    if sha256(raw) != (bundle / 'manifest.sha256').read_text().strip():
        raise ValueError('패치 묶음 manifest가 손상됐습니다')
    m = json.loads(raw)
    if out.exists() and any(out.iterdir()):
        raise ValueError('출력 폴더가 비어 있지 않습니다')
    bases = Bases(cache, m['bases'], log)
    dicts = Dicts(Wad(_base_bytes(bases, m['sysmenu'])), out)
    order = sorted(m['files'].items(), key=lambda kv: (_needs_files(kv[1]), kv[1]['mode'] == 'wad', kv[1].get('base') or '', kv[0]))
    for done, (rel, rec) in enumerate(order, 1):
        if rec['mode'] == 'wad':
            data = apply_wad_recipe(rec, bases, dicts, bundle)
        elif rec['mode'] == 'copy':
            data = dicts.sysmenu.dec(rec['sys'])
        elif rec['mode'] == 'delta':
            data = apply_delta(dicts.resolve(rec['dict']), (bundle / 'patch' / rec['patch']).read_bytes(), rec['size'])
        else:
            data = (bundle / 'files' / rel).read_bytes()
        if sha256(data) != rec['sha256']:
            raise ValueError(f'{rel}: 결과가 기대한 해시와 다릅니다. 이 파일은 만들지 않습니다')
        p = out / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        log(f'  [{done}/{len(order)}] {rel}')
    return m


def _base_bytes(bases, name):
    bases.wad(name)
    return bases.path(name).read_bytes()


def audit_bundle(bundle):
    """Violations of the public terms: finished WADs or files identical to an official content."""
    bundle = Path(bundle); m = json.loads((bundle / 'manifest.json').read_text())
    official = {h for spec in m['bases'].values() for h in spec.get('contents', [])}
    bad = []
    for p in bundle.rglob('*'):
        if p.is_file():
            d = p.read_bytes()
            if len(d) > 0x40 and d[:4] == b'\x00\x00\x00\x20' and d[4:8] in (b'Is\0\0', b'ib\0\0'):
                bad.append(('finished WAD', p.relative_to(bundle).as_posix()))
            if sha1(d) in official:
                bad.append(('whole official content', p.relative_to(bundle).as_posix()))
    return bad


def tree_equal(a, b):
    """True when directory trees a and b hold the same files with the same bytes."""
    fa = {p.relative_to(a).as_posix(): p for p in Path(a).rglob('*') if p.is_file()}
    fb = {p.relative_to(b).as_posix(): p for p in Path(b).rglob('*') if p.is_file()}
    return set(fa) == set(fb) and all(sha256(fa[k].read_bytes()) == sha256(fb[k].read_bytes()) for k in fa)
