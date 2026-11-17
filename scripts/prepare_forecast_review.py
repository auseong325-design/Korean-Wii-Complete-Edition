"""Create a separate stopped v26 review profile and capability-zero helper."""
import json, os, shutil, subprocess
from pathlib import Path
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot


def main():
    stopped()
    source = ROOT/'workspace/sandbox/forecast-manual-v1'
    target = ROOT/'workspace/sandbox/forecast-review-v1'
    helper = ROOT/'tools/channel-sandbox/review-v1/bin'
    if target.exists() or helper.exists(): raise SystemExit('Existing review experiment preserved')
    protected = {alias: snapshot(ROOT/'workspace/sandbox'/alias)
                 for alias in ['forecast-v1', 'forecast-manual-v1', 'gc-v6']}
    before = PRIVATE/'forecast-before-review-v1.json'
    if before.exists(): raise SystemExit('Existing before manifest preserved')
    before.write_text(json.dumps(protected), encoding='utf-8')
    for p in source.rglob('*'):
        if p.is_symlink() or p.is_junction(): raise ValueError('Indirect source')
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('Cache','Logs','ScreenShots','StateSaves'))
    for p in (target/'user/Config').glob('*.ini'):
        text = p.read_text(encoding='utf-8-sig')
        p.write_text(text.replace(str(source),str(target)), encoding='utf-8')
    (target/'review-profile.json').write_text(json.dumps(dict(schema=1,purpose='isolated-local-weather-review',
        real_time_weather=False,source_build=26)), encoding='utf-8')
    base = ROOT/'tools/channel-sandbox/v1/bin'
    lock = json.loads((base/'helper-build.json').read_text())
    for row in lock['files']:
        if sha256(ROOT/row['path']) != row['sha256']: raise ValueError('Original helper changed')
    text = (base/'ChannelRunner.cs').read_text()
    old = 'new string[]{"forecast-v1"}'
    if text.count(old) != 1: raise ValueError('Helper scope identity')
    helper.mkdir(parents=True)
    cs = helper/'ChannelRunner.cs'; cs.write_text(text.replace(old,'new string[]{"forecast-review-v1"}'),encoding='utf-8')
    exe = helper/'AppContainerRunner.exe'
    compiler = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(exe),str(cs)],check=True)
    files = lock['files'] + [dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in [cs,exe,Path(__file__)]]
    (helper/'helper-build.json').write_text(json.dumps(dict(capability_count=0,review_only=True,files=files),indent=2))
    for alias, original in protected.items():
        if snapshot(ROOT/'workspace/sandbox'/alias) != original: raise ValueError('Protected source changed')
    print('Prepared independent v26 review profile and capability-zero helper; three original profiles unchanged')


if __name__ == '__main__': main()
