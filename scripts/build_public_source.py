"""KWCE 공개판의 GPL-3.0 대응 소스 묶음을 만든다.

  .venv\\Scripts\\python.exe scripts\\build_public_source.py --config configs/public-source-v1.json --version 1 [--reproduce]

결과: workspace/public/kwce-source-vN.zip (+ .manifest.json). 새 번호로만 만들고 덮어쓰지 않는다.
- KWCE 자체 소스: own_dirs 중 Git이 무시하지 않는 파일(작업 공간·원본·도구·키는 .gitignore로 빠짐) + LICENSE.
- WiiMC 포크(DVD 재생기): 원본 커밋 그대로(git archive) + 판마다 KWCE가 바꾼 파일. 검증 대상 판은 원본+바뀐 파일로
  다시 만든 전체 트리가 빌드 기록(sources 해시)과 파일마다 같아야 한다.
- Set Personal Data 포크(주소 설정): 고정 원본 + 실제로 빌드한 트리에서 바뀐 파일. 그 트리의 링크 결과가
  빌드 기록의 linked_dol_sha256과 같아야 한다. libpatcher(MIT) 원본 동봉.
- 이 PC의 사용자 이름·프로젝트 폴더 이름이 든 파일이 있으면 실패. 같은 입력이면 zip 바이트가 같다.
"""
import argparse
import fnmatch
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import dvd_player_fork  # noqa: E402

LEAK_MARKERS = [Path.home().name.encode(), ROOT.parent.name.encode(), ROOT.name.encode()]
LEAK_ALLOW = {'scripts/build_public_source.py', 'scripts/build_public_patcher_win.py'}  # compute markers, contain none
BUILD_JUNK = ['*.o', '*.d', '*.a', '*.elf', '*.dol', '*.map']


def sha256(b): return hashlib.sha256(b).hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd)


def own_files(dirs):
    names = git('ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', *dirs).split(b'\0')
    out = {}
    for n in sorted(x.decode() for x in names if x):
        p = ROOT / n
        if p.is_file() and '__pycache__' not in p.parts:
            out[n] = p.read_bytes()
    return out


def read_tree(root, skip_dirs=('.git', 'executables', 'build'), junk=()):
    root = Path(root); out = {}
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root)
        if p.is_file() and not any(part in skip_dirs for part in rel.parts[:-1]) and not any(
                fnmatch.fnmatch(p.name, j) for j in junk):
            out[rel.as_posix()] = p.read_bytes()
    return out


def changes(base, tree):
    changed = {k: v for k, v in tree.items() if base.get(k) != v}
    removed = sorted(set(base) - set(tree))
    return changed, removed


def wiimc_tree(upstream, revision, tweaks):
    """Upstream working tree (same ignore rule as the build) + dvd_player_fork.apply(revision)."""
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / 'source'
        shutil.copytree(upstream, stage, ignore=shutil.ignore_patterns('.git', 'executables', 'build'))
        dvd_player_fork.apply(stage, ROOT, revision)
        if tweaks:  # build_linux_dvd_player.py edits made right before compiling
            (stage / 'source/mplayer/version.h').write_text(
                '#define VERSION "UNKNOWN-' + tweaks['gcc_version'] + '"\n'
                '#define MP_TITLE "%s "VERSION" (C) 2000-2012 MPlayer Team\\n"\n', newline='\n')
            hdr = (stage / 'source/mplayer/ffmpeg/version.h').read_text()
            ver = hdr.split('"')[1]
            (stage / 'source/mplayer/ffmpeg/VERSION').write_text(ver + '\n', newline='\n')
            mk = stage / 'Makefile'; text = mk.read_text()   # text mode, as on Linux: CRLF -> LF
            old = '\tcd source/mplayer; $(MAKE) -f Makefile; cd ../..'
            if text.count(old) != 1:
                raise SystemExit('WiiMC Makefile rule differs')
            mk.write_bytes(text.replace(old, '\t$(MAKE) -C source/mplayer -f Makefile').encode())
        tree = read_tree(stage, skip_dirs=())
    return {k: (v.replace(b'\r\n', b'\n') if k.endswith('.sh') else v) for k, v in tree.items()}


def build(cfg):
    files, report = {}, {}
    # KWCE's own source
    own = own_files(cfg['own_dirs'])
    for n, d in own.items():
        files[n] = d
    files['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    readme = (ROOT / cfg['readme']).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\n', '\r\n')
    files['SOURCE-README-ko.txt'] = b'\xef\xbb\xbf' + readme.encode()
    report['own_files'] = len(own)
    for name, src in (cfg.get('extra_files') or {}).items():  # v2+: e.g. the OFL text for the bundled font
        files[name] = (ROOT / src).read_bytes()
    # WiiMC fork
    w = cfg['wiimc']; up = ROOT / w['upstream']
    if git('rev-parse', 'HEAD', cwd=up).decode().strip() != w['commit'] or git('status', '--porcelain', cwd=up).strip():
        raise SystemExit('WiiMC upstream checkout is not the pinned clean commit')
    files[f"third_party/wiimc-{w['commit'][:7]}.zip"] = git('archive', '--format=zip', f"--prefix=wiimc-{w['commit'][:7]}/", 'HEAD', cwd=up)
    base = read_tree(up)
    for rev, spec in w['revisions'].items():
        tree = wiimc_tree(up, int(rev), spec.get('linux_build_tweaks'))
        verified = None
        if spec.get('verify'):
            want = {k.replace('\\', '/'): v for k, v in json.loads((ROOT / spec['verify']).read_text())['sources'].items()}
            got = {k: sha256(v) for k, v in tree.items()}
            if got != want:
                diff = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
                raise SystemExit(f'WiiMC r{rev} source differs from its build record: {diff[:5]}')
            verified = f'all {len(want)} files match {spec["verify"]}'
        changed, removed = changes(base, tree)
        for k, v in changed.items():
            files[f'generated/wiimc-kwce-r{rev}/{k}'] = v
        files[f'generated/wiimc-kwce-r{rev}/KWCE-REMOVED.txt'] = ''.join(f'{r}\n' for r in removed).encode()
        report[f'wiimc_r{rev}'] = dict(changed=len(changed), removed=len(removed), verified=verified, ships_as=spec['ships_as'])
    # Set Personal Data fork
    s = cfg['spd']; ref = read_tree(ROOT / s['upstream']); built = ROOT / s['built_tree']
    rec = json.loads((ROOT / s['verify']).read_text(encoding='utf-8'))
    if sha256((built / 'set-personal-data.dol').read_bytes()) != rec['linked_dol_sha256']:
        raise SystemExit('Set Personal Data built tree is not the one recorded in ' + s['verify'])
    tree = read_tree(built, skip_dirs=('build',), junk=BUILD_JUNK)
    for k, prefix in rec['fork']['written'].items():
        if not sha256(tree[k]).startswith(prefix):
            raise SystemExit(f'Set Personal Data written file differs: {k}')
    for k, v in ref.items():
        files[f"third_party/set-personal-data-{s['commit'][:8]}/{k}"] = v
    for k, v in read_tree(ROOT / s['libpatcher']).items():
        files[f'third_party/{Path(s["libpatcher"]).name}/{k}'] = v
    changed, removed = changes(ref, tree)
    for k, v in changed.items():
        files[f'generated/set-personal-data-kwce-r2/{k}'] = v
    files['generated/set-personal-data-kwce-r2/KWCE-REMOVED.txt'] = ''.join(f'{r}\n' for r in removed).encode()
    report['set_personal_data_r2'] = dict(changed=len(changed), removed=len(removed), ships_as=s['ships_as'],
                                          verified=f"linked DOL {rec['linked_dol_sha256'][:16]} = {s['verify']}")
    # checks
    leaks = [n for n, d in files.items() if n not in LEAK_ALLOW and not n.endswith('.zip')
             and any(m in d for m in LEAK_MARKERS)]
    if leaks:
        raise SystemExit(f'local user/project names found in: {leaks[:5]}')
    bad = [n for n in files if Path(n).suffix.lower() in ('.wad', '.dol', '.elf', '.tik', '.tmd', '.app')]
    if bad:
        raise SystemExit(f'binaries in the source bundle: {bad[:5]}')
    return files, report


def make_zip(files, root, date):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(f'{root}/{name}', tuple(date))
            info.compress_type = zipfile.ZIP_STORED if name.endswith('.zip') else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', required=True); ap.add_argument('--version', type=int, required=True)
    ap.add_argument('--reproduce', action='store_true')
    a = ap.parse_args()
    cfg = json.loads((ROOT / a.config).read_text(encoding='utf-8'))
    out = ROOT / f'workspace/public/kwce-source-v{a.version}.zip'; man = out.with_suffix('.manifest.json')
    files, report = build(cfg)
    z = make_zip(files, cfg['zip_root'], cfg['zip_date'])
    if a.reproduce:
        same = sha256(z) == sha256(out.read_bytes())
        print(f"재현 {'일치' if same else '불일치'}: {sha256(z)[:16]}")
        raise SystemExit(0 if same else 1)
    if out.exists() or man.exists():
        raise SystemExit(f'{out.name}이(가) 이미 있습니다. 새 번호를 쓰세요')
    out.write_bytes(z)
    man.write_text(json.dumps(dict(name=out.name, zip_sha256=sha256(z), zip_bytes=len(z), config=a.config,
                                   config_sha256=sha256((ROOT / a.config).read_bytes()), report=report,
                                   files={n: [len(d), sha256(d)] for n, d in sorted(files.items())}),
                              ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{out.name}: {len(z) / 1e6:.1f}MB, 파일 {len(files)}개')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
