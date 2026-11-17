"""Linux-specific gates. Windows AppContainer/feed checks are not substituted."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.linux_runtime import BASE, PRIVATE, default_profile, digest, isolation_probe, stopped, validate
from kwce.toolchain import tool, DKP


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quick', action='store_true')
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    checks = []

    def step(name, fn):
        start = time.monotonic()
        try:
            fn()
            ok = True
        except Exception as exc:
            (PRIVATE / (name.replace(' ', '-') + '-error.txt')).write_text(str(exc))
            ok = False
        checks.append({'name': name, 'passed': ok})
        print(f"{'PASS' if ok else 'FAIL'} {name} ({time.monotonic()-start:.1f}s)", flush=True)

    def require(ok):
        if not ok:
            raise ValueError('Gate did not match expected state')

    def command(name, cmd, timeout=180):
        def run():
            result = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True,
                                    timeout=timeout)
            (PRIVATE / (name.replace(' ', '-') + '.log')).write_bytes(result.stdout + result.stderr)
            require(result.returncode == 0)
        step(name, run)

    # No runtime profile is read while Dolphin is running.
    try:
        stopped()
    except ValueError:
        print('FAIL Close Dolphin before Linux checks')
        return 1

    def dependencies():
        for file in ('requirements-phase0.txt', 'requirements-linux.txt'):
            for line in (ROOT / 'configs' / file).read_text().splitlines():
                if '==' in line and not line.startswith('#'):
                    name, version = line.split('==')
                    require(importlib.metadata.version(name) == version)
        from kwce.channels import load_library
        load_library()
        import PIL, Crypto.Cipher.AES, unicorn, capstone
    step('locked Python dependencies', dependencies)

    def toolchain():
        lock = json.loads((ROOT / 'configs/gc-comment-linux.lock.json').read_text())
        require(digest(tool('powerpc-eabi-gcc.exe')) == lock['compiler_sha256'])
        require(digest(tool('powerpc-eabi-objcopy.exe')) == lock['objcopy_sha256'])
        for row in json.loads((ROOT / 'configs/devkit-linux.lock.json').read_text()):
            name = row['url'].rsplit('/', 1)[1]
            package = ROOT / ('tools/linux/' if 'linux_x86_64' in name else 'tools/packages/') / name
            require(digest(package) == row['sha256'])
        require(tool('elf2dol.exe', DKP/'tools/bin').is_file())
    step('locked Linux toolchain', toolchain)
    profiles = sorted(BASE.glob('*/profile.json'))
    step('prepared profile inventory', lambda: require(bool(profiles) and (BASE / default_profile() / 'profile.json').is_file()))
    for record in profiles:
        step(record.parent.name, lambda name=record.parent.name: validate(name))
    if profiles:
        step('network filesystem capability isolation', lambda: isolation_probe(profiles[0].parent))
    command('Linux guard regression', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_linux*.py'])
    if not args.quick:
        command('Dolphin regression', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_dolphin*.py'])
        command('GC regression', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_gc*.py'])
        command('DVD native PPC regression', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_dvd_native*.py'])
        command('DVD read contract regression', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_dvd_player_*.py'])
        command('DVD probe regression', ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_dvd_probe*.py'])
        command('Wii compile link DOL smoke', ['scripts/smoke_toolchain.py'])
        command('original SD audit', ['scripts/audit_sd.py', '--verify'])
    print('NOT PORTED: Windows AppContainer, C# synthetic-feed servers, Windows package launchers')
    report = {'checks': checks, 'quick': args.quick, 'passed': all(c['passed'] for c in checks),
              'scope': 'Linux environment gates only; not the original entire Windows suite'}
    (PRIVATE / 'verification.json').write_text(json.dumps(report, indent=2))
    print('LINUX GATES PASS' if report['passed'] else 'LINUX GATES FAILED')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
