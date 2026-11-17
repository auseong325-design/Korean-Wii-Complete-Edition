"""Numbered own TV Guide schedule feed (local-feed-v7): header + epg + str.

Unlike local-feed-v2..v6 (header-only diagnostics), v7 also serves the
synthetic epg.bin / str.bin that the DOL schedule state fetches after region
selection (DOL 0x8039cc4c / 0x8039cca4). All resources are HDPK blobs under the
same 'main' root and satisfy HeaderValidate (0x803a2580), EpgValidate
(0x803a2950, cross-references the header station table) and StrValidate
(0x803a2cac). No real broadcast schedule, station or console data is used.

Creating is safe and does NOT activate (the active feed stays whatever it is).
Pass --activate (lead, with Dolphin stopped) to copy it into the test profile
and re-pin the runtime lock, mirroring refresh_tvguide_fixtures.py. Pass
--reproduce to verify byte-identical regeneration into workspace/private.
"""
import argparse, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit_sd import PRIVATE, sha256
from kwce.tvguide_fixtures import feed_v7_resources

BASE = ROOT / 'workspace/sandbox/tvguide-test-v1'
MODULE = BASE / 'user/Wii/title/00010001/48424e4a/data/wc24pubk.mod'
OUT = ROOT / 'workspace/channels/tvguide/local-feed-v7'
# The DOL appends the file name to either the base path (/) or a numbered
# shard (/binN/); serve both so region selection reaches the schedule either way.
PREFIXES = [''] + ['bin%d/' % i for i in range(1, 11)]
FILES = {'header.bin': 'header', 'epg.bin': 'epg', 'str.bin': 'string'}


def resources():
    r = feed_v7_resources(MODULE.read_bytes())
    return {name: r[key] for name, key in FILES.items()}


def routes_text():
    lines = []
    for prefix in PREFIXES:
        for name in FILES:
            lines.append('* /%s%s\t%s' % (prefix, name, name))
    return '\n'.join(lines) + '\n'


def write_feed(out):
    out.mkdir(parents=True)
    for name, payload in resources().items():
        (out / name).write_bytes(payload)
    (out / 'routes.tsv').write_text(routes_text(), encoding='ascii')
    manifest = dict(revision=7, local_only=True, synthetic=True, serves_schedule=True,
                    header_diagnostic_only=False,
                    files=[dict(path=p.name, sha256=sha256(p)) for p in sorted(out.iterdir())])
    (out / 'fixture-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def activate():
    from prepare_channel_access import stopped
    from prepare_tvguide_test import BASE as PROFILE_BASE, PROFILE, register
    import launch_dolphin as launcher
    stopped(); register()
    feed = PROFILE_BASE / 'local-feed'
    backup = PRIVATE / 'tvguide-before-feed-v7'
    if backup.exists():
        raise SystemExit('TV feed-v7 backup preserved')
    shutil.copytree(feed, backup)
    lock = ROOT / 'configs/tvguide-runtime.lock.json'
    snapshot = ROOT / 'configs/tvguide-runtime-before-feed-v7.lock.json'
    if snapshot.exists():
        raise SystemExit('TV runtime snapshot preserved')
    shutil.copyfile(lock, snapshot)
    for p in feed.iterdir():
        if p.is_file():
            p.unlink()
    for p in OUT.iterdir():
        shutil.copyfile(p, feed / p.name)
    data = json.loads(lock.read_text())
    row = next(r for r in data['files'] if r['path'].endswith('local-feed/fixture-manifest.json'))
    row['sha256'] = sha256(feed / 'fixture-manifest.json')
    lock.write_text(json.dumps(data, indent=2))
    launcher.scrub_download_tasks(PROFILE)
    print('Activated TV schedule feed v7 into the test profile; runtime lock re-pinned')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--activate', action='store_true', help='lead only, Dolphin stopped')
    ap.add_argument('--reproduce', action='store_true')
    args = ap.parse_args()
    if args.reproduce:
        n = 1
        while (PRIVATE / ('tvguide-feed-v7-reproduce-%d' % n)).exists():
            n += 1
        tmp = PRIVATE / ('tvguide-feed-v7-reproduce-%d' % n)
        m = write_feed(tmp)
        expected = {p.name: (OUT / p.name).read_bytes() for p in sorted(tmp.iterdir())}
        for p in sorted(tmp.iterdir()):
            if p.name == 'fixture-manifest.json':
                continue
            if p.read_bytes() != expected[p.name]:
                raise SystemExit('TV feed-v7 reproduction differs: ' + p.name)
        print('Reproduced TV feed-v7 byte-identically:', ', '.join(sorted(FILES)))
        return
    if args.activate:
        activate(); return
    if OUT.exists():
        raise SystemExit('Existing TV feed-v7 preserved')
    m = write_feed(OUT)
    sizes = ', '.join('%s=%d' % (f['path'], next(len(v) for n, v in resources().items() if n == f['path']))
                      for f in m['files'] if f['path'] in FILES)
    print('Built TV schedule feed v7 (not activated):', sizes)
    print('Activate (lead, Dolphin stopped):  .venv\\Scripts\\python.exe scripts\\build_tvguide_feed_v7.py --activate')


if __name__ == '__main__':
    main()
