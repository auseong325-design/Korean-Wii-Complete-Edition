"""Read-only SD inventory. Private exact paths/hashes stay under ignored workspace.

No source file is opened for writing. Full verification includes size, mtime_ns,
SHA-256, missing and extra files. Run before and after local work.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SD = ROOT / 'sd'
PRIVATE = ROOT / 'workspace' / 'private'

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def sanitize(s: str) -> str:
    s = re.sub(r'(?im)^.*(?:BSSID|SSID|Access Point).*$','[wireless access-point field redacted]',s)
    s = re.sub(r'(?im)^.*(?:console.?id|device.?id|serial|일련|시리얼|MAC(?:\s+address)?|friend.?code|친구.?코드|certificat|private.?key|OTP|SEEPROM).*$', '[console identifier/security field redacted]', s)
    s = re.sub(r'(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b', '[MAC redacted]', s)
    s = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IPv4 redacted]', s)
    s = re.sub(r'\b\d{8,}\b', '[long identifier redacted]', s)
    s = re.sub(r'(?i)\b[A-Z]{2,4}\d{6,}\b', '[serial redacted]', s)
    return s

def inventory():
    if not SD.is_dir():
        raise SystemExit('SD directory is missing')
    rows = []
    for p in sorted(SD.rglob('*')):
        if p.is_symlink() or p.is_junction() or getattr(p.lstat(), 'st_file_attributes', 0) & 0x400:
            raise SystemExit('Refusing SD symlink/reparse traversal')
        if p.is_file():
            st = p.stat()
            rows.append(dict(path=p.relative_to(SD).as_posix(), size=st.st_size,
                             mtime_ns=st.st_mtime_ns,
                             modified_utc=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                             sha256=sha256(p)))
    return dict(created_utc=datetime.now(timezone.utc).isoformat(), files=rows,
                file_count=len(rows), total_bytes=sum(x['size'] for x in rows))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--reports', action='store_true')
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if args.reports:
        for name in ('SysCheck.csv', 'WiiMedic_Report.txt', 'IOSsyscheck.log'):
            matches = [p for p in SD.rglob(name) if p.is_file()]
            for p in matches:
                raw = p.read_bytes()
                for enc in ('utf-8-sig', 'cp949', 'cp1252'):
                    try:
                        s = raw.decode(enc)
                        break
                    except UnicodeDecodeError:
                        pass
                print('REPORT:', name)
                print(sanitize(s))
        return
    baseline = PRIVATE / 'sd-manifest-before.json'
    if not args.verify and baseline.exists():
        raise SystemExit('Baseline already exists; use --verify (no overwrite allowed)')
    current = inventory()
    if args.verify:
        before = json.loads(baseline.read_text(encoding='utf-8'))
        old = {r['path']: r for r in before['files']}
        new = {r['path']: r for r in current['files']}
        diff = dict(missing=sorted(old.keys()-new.keys()), added=sorted(new.keys()-old.keys()),
                    changed=[p for p in old.keys() & new.keys() if any(old[p][k] != new[p][k] for k in ('size','mtime_ns','sha256'))])
        current['verification'] = diff
        out = PRIVATE / 'sd-manifest-after.json'
        out.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
        ok = not any(diff.values())
        print(json.dumps(dict(unchanged=ok, files=current['file_count'], bytes=current['total_bytes'],
                              differences={k: len(v) for k,v in diff.items()})))
        raise SystemExit(0 if ok else 1)
    baseline.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(files=current['file_count'], bytes=current['total_bytes'], baseline=str(baseline))))

if __name__ == '__main__':
    main()
