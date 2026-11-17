"""Make a public patch bundle (design v3) from a personal SD bundle.

  .venv-linux/bin/python scripts/build_public_bundle.py --package kwce-rc-sd-v51 [--seed DIR] [--only forecast]
Output: workspace/public/kwce-public-vN (new number each run; nothing is uploaded).
--seed DIR: prebuilt official base WADs named '<base name>.wad' (hash-checked) to skip downloads.
Bases come from configs/public-bases-v1.json and are fetched from the Nintendo update server and
the WiiLink patch server exactly as WiiLink Patcher does; cache: workspace/public/cache.
"""
import argparse
import concurrent.futures
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import public_patch as pp  # noqa: E402

CONFIG = ROOT / 'configs/public-bases-v1.json'
PUBLIC = ROOT / 'workspace/public'
_state = {}


def _init(cache, specs, sysname, src):
    _state['bases'] = pp.Bases(cache, specs, log=lambda *_: None)
    _state['dicts'] = pp.Dicts(pp.Wad(_state['bases'].path(sysname).read_bytes()), src)


def _one(args):
    rel, src, candidates, out = args
    data = Path(src).read_bytes()
    if rel.endswith('.wad'):
        return rel, dict(mode='wad', **pp.make_wad_recipe(data, candidates, _state['bases'], _state['dicts'], Path(out), rel))
    return rel, pp.make_file_recipe(data, _state['dicts'], Path(out), rel)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--package', required=True); ap.add_argument('--seed'); ap.add_argument('--only')
    ap.add_argument('--workers', type=int, default=6)
    a = ap.parse_args()
    cfg = json.loads(CONFIG.read_text())
    src = ROOT / 'workspace/hardware' / a.package
    cache = PUBLIC / 'cache'; cache.mkdir(parents=True, exist_ok=True)
    bases = pp.Bases(cache, cfg['bases'])
    if a.seed:
        for name, spec in cfg['bases'].items():
            f = Path(a.seed) / f'{name}.wad'
            if f.is_file() and not bases.path(name).is_file() and pp.sha256(f.read_bytes()) == spec.get('wad_sha256'):
                shutil.copyfile(f, bases.path(name))
    changed = False
    for name, spec in cfg['bases'].items():            # fetch what is missing, pin hashes
        w = bases.wad(name)
        if not spec.get('wad_sha256'):
            spec['wad_sha256'] = pp.sha256(bases.path(name).read_bytes()); changed = True
        spec.setdefault('contents', [r['sha1'] for r in w.records])
    if changed:
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + '\n')
    n = 1
    while (PUBLIC / f'kwce-public-v{n}').exists():
        n += 1
    out = PUBLIC / f'kwce-public-v{n}'; out.mkdir(parents=True)
    jobs = []
    for p in sorted(src.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(src).as_posix()
        parts = rel.split('/')
        ch = parts[1] if parts[0] == 'kwce-rc' and len(parts) == 3 else None
        if a.only and ch != a.only:
            continue
        jobs.append((rel, str(p), cfg['candidates'].get(ch, []), str(out)))
    files = {}
    with concurrent.futures.ProcessPoolExecutor(a.workers, initializer=_init,
                                                initargs=(cache, cfg['bases'], cfg['sysmenu'], str(src))) as ex:
        for rel, rec in ex.map(_one, jobs):
            files[rel] = rec
            size = rec.get('patch_total', rec.get('patch_bytes', rec['size'] if rec['mode'] == 'verbatim' else 0))
            print(f"{rec['mode']:8} {size / 1024:9.0f} KiB  {rel}  {rec.get('base') or ''} {rec.get('dict') or ''}", flush=True)
    used = {r['base'] for r in files.values() if r['mode'] == 'wad' and r['base']} | {cfg['sysmenu']}
    manifest = dict(kind='kwce-public-patch-v1', source_package=a.package, sysmenu=cfg['sysmenu'],
                    bases={k: v for k, v in cfg['bases'].items() if k in used}, files=files,
                    terms='Patches and KWCE-made files only: no finished WADs, no whole Nintendo files, no keys. '
                          'Bases are fetched by the user from the Nintendo update server and the WiiLink patch server.')
    raw = (json.dumps(manifest, ensure_ascii=False, indent=1) + '\n').encode()
    (out / 'manifest.json').write_bytes(raw); (out / 'manifest.sha256').write_text(pp.sha256(raw) + '\n')
    bad = pp.audit_bundle(out)
    if bad:
        raise SystemExit(f'FAIL {out.name}: public terms violated: {bad}')
    total = sum(f.stat().st_size for f in out.rglob('*') if f.is_file())
    src_total = sum(Path(j[1]).stat().st_size for j in jobs)
    print(f'PASS {out.name}: {len(files)} files, bundle {total / 1e6:.1f} MB for {src_total / 1e6:.1f} MB of SD files')


if __name__ == '__main__':
    main()
