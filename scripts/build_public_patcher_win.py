"""Windows 단독 KWCE 패처 꾸러미를 만든다 (공개판 설계 v3, 남은 일 1).

  .venv\\Scripts\\python.exe scripts\\build_public_patcher_win.py --config configs/public-patcher-win-v1.json --version 1
  .venv\\Scripts\\python.exe scripts\\build_public_patcher_win.py --config ... --version 1 --reproduce

결과: workspace/public/kwce-patcher-win-vN.zip (+ .manifest.json). 새 번호로만 만들고 덮어쓰지 않는다.
구성: runtime/(CPython 3.12.10 내장 배치, 표준 라이브러리는 해시 기반 .pyc zip), app/(패처 .py 소스와 의존
패키지), bundle/(공개 패치 묶음), licenses/, KWCE-Patcher.bat, README-ko.txt. 같은 입력이면 zip 바이트가 같다.
빌드는 Windows + Python 3.12.10에서만 한다(.pyc 매직·.pyd ABI가 런타임과 같아야 함).
"""
import argparse
import fnmatch
import hashlib
import io
import json
import py_compile
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import public_patch as pp  # noqa: E402

README = ROOT / 'docs/release/patcher-win-README-ko.txt'
BAT = ('@echo off\r\n'
       'chcp 65001 >nul\r\n'
       'title KWCE Patcher\r\n'
       '"%~dp0runtime\\python.exe" -I -X utf8 "%~dp0app\\run.py" %*\r\n'
       'echo.\r\n'
       'pause\r\n')
# v5+: the wizard holds the window itself; pause only when it stops early (non-zero exit)
BAT2 = ('@echo off\r\n'
        'chcp 65001 >nul\r\n'
        'title KWCE Patcher\r\n'
        '"%~dp0runtime\\python.exe" -I -X utf8 "%~dp0app\\run.py" %* || pause\r\n')
# v7+: UTF-8 (read after chcp 65001); a clear message when only the .bat was extracted from the zip
BAT3 = ('@echo off\r\n'
        'chcp 65001 >nul\r\n'
        'title KWCE Patcher\r\n'
        'if not exist "%~dp0runtime\\python.exe" (\r\n'
        '  echo.\r\n'
        '  echo   압축을 모두 푼 뒤 실행하세요. zip 안에서 바로 실행하면 동작하지 않습니다.\r\n'
        '  echo   Extract the whole ZIP first, then run KWCE-Patcher.bat.\r\n'
        '  echo.\r\n'
        '  pause\r\n'
        '  exit /b 1\r\n'
        ')\r\n'
        '"%~dp0runtime\\python.exe" -I -X utf8 "%~dp0app\\run.py" %* || pause\r\n')
LAUNCHERS = {None: BAT, 1: BAT, 2: BAT2, 3: BAT3}
PTH = 'python312.zip\r\n.\r\n..\\app\r\n'
LEAK_MARKERS = [Path.home().name.encode(), ROOT.parent.name.encode(), ROOT.name.encode()]  # this machine's user and project folder


def sha256(b): return hashlib.sha256(b).hexdigest()


def excluded(name, patterns): return any(fnmatch.fnmatch(name, p) for p in patterns)


def tree(src, exclude_dirs=()):
    """(relative posix path, bytes) of a source package, without caches."""
    src = Path(src)
    for p in sorted(src.rglob('*')):
        rel = p.relative_to(src)
        if not p.is_file() or any(part in ('__pycache__', *exclude_dirs) for part in rel.parts) or p.suffix == '.pyc':
            continue
        yield rel.as_posix(), p.read_bytes()


def stdlib_zip(lib, exclude_dirs):
    """Hash-based (unchecked) .pyc of the standard library, like the official embeddable python312.zip."""
    buf = io.BytesIO(); n = 0
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(Path(lib).rglob('*.py')):
            rel = p.relative_to(lib)
            if any(part in exclude_dirs for part in rel.parts[:-1]):
                continue
            out = Path(tmp) / 'x.pyc'
            try:
                py_compile.compile(str(p), cfile=str(out), dfile=rel.as_posix(), doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            except py_compile.PyCompileError:
                continue                                   # a few stdlib templates are not valid modules
            info = zipfile.ZipInfo(rel.with_suffix('.pyc').as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, out.read_bytes()); n += 1
    return buf.getvalue(), n


def app_sources(cfg, version, create):
    """{'kwce/<module>': path, 'run.py': path}. v7+ (cfg freeze) read a frozen copy under kwce/frozen/patcher-win-vN,
    made on the first build, so later edits to the live files never change an existing package."""
    live = {f'kwce/{n}': ROOT / 'kwce' / n for n in cfg['kwce_modules']}
    live['run.py'] = ROOT / cfg.get('entry', 'kwce/patcher_entry_v1.py')   # v1-v4: frozen v1 entry
    if not cfg.get('freeze'):
        return live
    frozen = ROOT / 'kwce/frozen' / f'patcher-win-v{version}'
    if not frozen.exists():
        if not create:
            raise SystemExit(f'{frozen.relative_to(ROOT)} is missing; it is made by the first build')
        for rel, src in live.items():
            (frozen / rel).parent.mkdir(parents=True, exist_ok=True)
            (frozen / rel).write_bytes(src.read_bytes())
    return {rel: frozen / rel for rel in live}


def collect(cfg, version=0, create=False):
    if sys.platform != 'win32' or '.'.join(map(str, sys.version_info[:3])) != cfg['python_version']:
        raise SystemExit(f"Windows + Python {cfg['python_version']}에서만 빌드합니다 (지금 {sys.platform} {sys.version.split()[0]})")
    home = Path(sys.base_prefix)
    files = {}
    # runtime
    for name in cfg['runtime_files']:
        files[f'runtime/{name}'] = (home / name).read_bytes()
    for p in sorted((home / 'DLLs').iterdir()):
        if p.is_file() and not excluded(p.name, cfg['runtime_dll_exclude']):
            files[f'runtime/{p.name}'] = p.read_bytes()
    files['runtime/python312.zip'], nstd = stdlib_zip(home / 'Lib', set(cfg['stdlib_exclude_dirs']))
    files['runtime/python312._pth'] = PTH.encode()
    # app
    for name, src in (cfg.get('app_files') or {}).items():   # v8+: data the wizard shows (versioned configs only)
        files[f'app/{name}'] = (ROOT / src).read_bytes()
    for rel, src in app_sources(cfg, version, create).items():
        files[f'app/{rel}'] = src.read_bytes()
    licenses = {'licenses/Python-LICENSE.txt': (home / 'LICENSE.txt').read_bytes()}
    if cfg.get('kwce_license'):  # v3+: KWCE itself is GPL-3.0
        licenses['licenses/KWCE-LICENSE.txt'] = (ROOT / cfg['kwce_license']).read_bytes()
    for name, src in (cfg.get('extra_licenses') or {}).items():  # v4+: e.g. Noto Sans KR OFL
        licenses[name] = (ROOT / src).read_bytes()
    for pkg, spec in cfg['packages'].items():
        for rel, data in tree(ROOT / spec['from'], spec.get('exclude_dirs', ())):
            files[f'app/{pkg}/{rel}'] = data
        if 'license' in spec:
            licenses[f'licenses/{pkg}/{Path(spec["license"]).name}'] = (ROOT / spec['license']).read_bytes()
        if 'dist' in spec:
            for rel, data in tree(ROOT / spec['dist']):
                if 'licen' in rel.lower() or 'copying' in rel.lower():
                    licenses[f'licenses/{pkg}/{rel.removeprefix("licenses/")}'] = data
    files.update(licenses)
    # bundle
    bundle = ROOT / 'workspace/public' / cfg['bundle']
    problems = pp.audit_bundle(bundle)
    if problems:
        raise SystemExit(f'패치 묶음 감사 위반: {problems[:3]}')
    for rel, data in tree(bundle):
        files[f'bundle/{rel}'] = data
    m = json.loads((bundle / 'manifest.json').read_bytes())
    # top level
    files['KWCE-Patcher.bat'] = LAUNCHERS[cfg.get('launcher')].encode('utf-8' if cfg.get('launcher') == 3 else 'ascii')
    files['README-ko.txt'] = b'\xef\xbb\xbf' + (ROOT / cfg['readme'] if cfg.get('readme') else README).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\n', '\r\n').encode()
    return files, {'stdlib_modules': nstd, 'source_package': m.get('source_package')}


def check(files):
    bad = [n for n in files if not n.isascii()]
    if bad:
        raise SystemExit(f'zip 안 이름은 ASCII만 씁니다: {bad[:3]}')
    leaks = [n for n, d in files.items() if not n.startswith('bundle/') and any(k in d for k in LEAK_MARKERS)]
    if leaks:
        raise SystemExit(f'로컬 경로가 든 파일: {leaks[:5]}')
    if any(n.lower().endswith('.wad') for n in files):
        raise SystemExit('꾸러미에 WAD가 있습니다')


def make_zip(files, root, date):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(f'{root}/{name}', tuple(date))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])
    return buf.getvalue()


def build(cfg, version, create=False):
    files, extra = collect(cfg, version, create)
    files['app/build-info.json'] = json.dumps({
        'patcher': f'kwce-patcher-win-v{version}', 'bundle': cfg['bundle'], 'source_package': extra['source_package'],
        'python': cfg['python_version']}, ensure_ascii=False, indent=1).encode()
    check(files)
    return files, extra, make_zip(files, cfg['zip_root'], cfg['zip_date'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', required=True); ap.add_argument('--version', type=int, required=True)
    ap.add_argument('--reproduce', action='store_true', help='다시 만들어 기존 zip과 바이트가 같은지만 확인')
    a = ap.parse_args()
    cfg = json.loads((ROOT / a.config).read_text(encoding='utf-8'))
    out = ROOT / f'workspace/public/kwce-patcher-win-v{a.version}.zip'
    man = out.with_suffix('.manifest.json')
    if a.reproduce:
        _, _, z = build(cfg, a.version)
        old = out.read_bytes()
        same = sha256(z) == sha256(old)
        print(f"재현 {'일치' if same else '불일치'}: {sha256(z)[:16]} vs {sha256(old)[:16]}")
        raise SystemExit(0 if same else 1)
    if out.exists() or man.exists():
        raise SystemExit(f'{out.name}이(가) 이미 있습니다. 새 번호를 쓰세요')
    files, extra, z = build(cfg, a.version, create=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(z)
    man.write_text(json.dumps({
        'name': out.name, 'zip_sha256': sha256(z), 'zip_bytes': len(z), 'config': a.config,
        'config_sha256': sha256((ROOT / a.config).read_bytes()), 'bundle': cfg['bundle'],
        'source_package': extra['source_package'], 'stdlib_modules': extra['stdlib_modules'],
        'built_on': f'{sys.platform} Python {sys.version.split()[0]}',
        'files': {n: [len(d), sha256(d)] for n, d in sorted(files.items())},
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{out.name}: {len(z) / 1e6:.1f}MB, 파일 {len(files)}개, 표준 라이브러리 {extra["stdlib_modules"]}개, sha256 {sha256(z)[:16]}')


if __name__ == '__main__':
    main()
