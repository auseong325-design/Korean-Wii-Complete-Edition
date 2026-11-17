"""Current News source/installation/delta/feed audit; no raw content output."""
import json
import subprocess
import sys
from audit_sd import ROOT, PRIVATE, sha256
from prepare_gc_v6 import snapshot
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.channel_patch import apply_patch
from kwce.channel_validation import verify_installed_title


def main():
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True)
    if 'dolphin.exe' in running.stdout.lower():
        raise SystemExit('Close Dolphin before final verification')
    base = ROOT / 'workspace/channels/news'
    active = json.loads((base / 'active-build.json').read_text())
    revision = active['revision']
    folder = base / f'build-v{revision}'
    meta = json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))
    row = meta['wads'][active['variant']]
    if active['variant'] != 'personal' or sha256(folder / row['file']) != row['sha256']:
        raise ValueError('Unexpected News build')
    acq = json.loads((base / 'originals/acquisition.json').read_text())
    for r in acq['files']:
        p = base / 'originals' / r['alias']
        if (p.stat().st_size, p.stat().st_mtime_ns, sha256(p)) != (r['size'], r['mtime_ns'], r['sha256']):
            raise ValueError('Preserved original changed')
    refs = json.loads((base / 'references/source-lock.json').read_text())
    for r in refs['files']:
        if sha256(base / 'references' / r['file']) != r['sha256']:
            raise ValueError('Pinned reference changed')
    library = load_library()
    target = library.title.Title()
    target.load_wad((folder / row['file']).read_bytes())
    count = verify_installed_title(ROOT / 'workspace/sandbox/news-v1/user/Wii', target.tmd.title_id, target.tmd.dump())
    patch_dir = base / f'patches/v{revision}'
    patch = json.loads((patch_dir / 'manifest.json').read_text())
    source = library.title.Title()
    original = base / 'originals/news-usa-wiilink-archive.wad'
    if sha256(original) != patch['base_sha256']:
        raise ValueError('Delta base changed')
    source.load_wad(original.read_bytes())
    source.tmd.region = 4
    for r in patch['contents']:
        p = patch_dir / r['file']
        if sha256(p) != r['sha256']:
            raise ValueError('Private delta changed')
        source.set_content(apply_patch(source.get_content_by_index(r['index']), p.read_bytes()), r['index'])
    if source.dump_wad() != (folder / row['file']).read_bytes():
        raise ValueError('Private delta reconstruction differs')
    before = json.loads((PRIVATE / 'news-resume-before-feed-v2.json').read_text())['forecast']
    historical_snapshot_match = snapshot(ROOT / 'workspace/sandbox/forecast-v1') == before
    # The old News replay snapshot predates subsequent reviewed Forecast work.
    # Keep it intact and report drift; current preservation is checked against
    # the maintained v22 build/runtime locks, not a newly overwritten snapshot.
    subprocess.run([sys.executable, str(ROOT / 'scripts/launch_forecast.py'), '--preserved-check'], check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/launch_channel_feed.py'), 'news', '--check'], check=True)
    result = dict(passed=True, revision=revision, variant=active['variant'],
                  originals_preserved=len(acq['files']), pinned_references=len(refs['files']),
                  installed_contents=count, private_delta_byte_identical=True,
                  forecast_v22_current_preserved_check=True,
                  forecast_historical_snapshot_match=historical_snapshot_match,
                  live_service_verified=False,
                  machine_translation_review_complete=False,
                  child_exit_hex=json.loads((ROOT / 'workspace/sandbox/news-v1/child-exit.json').read_text())['exit_code_hex'])
    (PRIVATE / f'news-v{revision}-runtime-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
