"""Build a new numbered Internet Channel sandbox helper and pin it in the runtime lock.

  .venv\\Scripts\\python.exe scripts\\prepare_internet_helper.py --revision 2

Creates tools/internet-sandbox/vN/bin once: InternetRunner (derived from
scripts/FeedRunner.cs exactly as revision 1) and InternetServer revision 2
(kwce/internet_server.py: persistent HTTP/1.1, no half-close right after a
response, header-name-only logging). Replaces the helper rows in
configs/internet-runtime.lock.json and records lock['helper']. Never starts
Dolphin; the profile and the earlier helper folders stay unchanged.
"""
import argparse
import json
import sys

from audit_sd import ROOT, sha256
from prepare_channel_access import stopped
from prepare_internet_test import LOCK, runner_source

sys.path.insert(0, str(ROOT))
from kwce.internet_server import server_source, compile_csharp  # noqa: E402

REVISIONS = (2,)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revision', type=int, choices=REVISIONS, default=REVISIONS[-1])
    args = ap.parse_args()
    stopped()
    out = ROOT / f'tools/internet-sandbox/v{args.revision}/bin'
    if out.exists():
        raise SystemExit('Existing Internet helper preserved: ' + str(out))
    lock = json.loads(LOCK.read_text())
    out.mkdir(parents=True)
    sources = {'InternetRunner.cs': runner_source(), 'InternetServer.cs': server_source()}
    for name, text in sources.items():
        (out / name).write_text(text, encoding='ascii', newline='\n')
        compile_csharp(out / name, (out / name).with_suffix('.exe'))
    helper_rows = [dict(path=p.relative_to(ROOT).as_posix(), sha256=sha256(p)) for p in sorted(out.iterdir()) if p.suffix in ('.cs', '.exe')]
    kept = [r for r in lock['files'] if not r['path'].startswith('tools/internet-sandbox/')]
    lock['files'] = kept + helper_rows
    lock['helper'] = out.relative_to(ROOT).as_posix()
    lock['helper_revision'] = args.revision
    LOCK.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'Built Internet helper v{args.revision} ({len(helper_rows)} files) and pinned it in the runtime lock')


if __name__ == '__main__':
    main()
