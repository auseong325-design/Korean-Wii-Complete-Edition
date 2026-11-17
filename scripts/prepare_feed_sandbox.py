"""Build a new immutable pair of local-feed helpers; preserve v1."""
import json
import argparse
import os
from pathlib import Path
import subprocess
from audit_sd import ROOT, sha256


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=3);args=ap.parse_args()
    if not 2<=args.revision<=100:raise SystemExit('Invalid helper revision')
    out = ROOT / f'tools/feed-sandbox/v{args.revision}/bin'
    if out.exists():
        raise SystemExit('Existing feed helper preserved')
    out.mkdir(parents=True)
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    paths = []
    for name in ['FeedServer', 'FeedRunner']:
        source = ROOT / 'scripts' / (name + '.cs')
        exe = out / (name + '.exe')
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64',
                        '/out:' + str(exe), str(source)], check=True)
        paths.extend([source, exe])
    paths.append(ROOT / 'workspace/sandbox/news-v1/NetProbe.exe')
    (out / 'helper-build.json').write_text(json.dumps(dict(files=[dict(
        path=p.relative_to(ROOT).as_posix(), sha256=sha256(p)) for p in paths]), indent=2))
    print(f'Built feed helper v{args.revision}; older helpers preserved')


if __name__ == '__main__':
    main()
