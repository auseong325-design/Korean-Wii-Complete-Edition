"""sntp (ErikAndren, MIT) SD package: the official OSC archive, unmodified, plus a preset config.

Why: on the owner's console the WiiConnect24 universal time was never set (KD ioctl 0x14 -> -30),
which the WiiLink guide fixes with sntp (it sets KD universal time via ioctl 0x15 and the SYSCONF
clock bias). sntp.cfg only presets the UTC offset to Korea (+9 h); the user still confirms with A.
  sd-v1: sntp 1.3.1 (configs/sntp-v1.lock.json)
"""
import hashlib, json, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'configs/sntp-v1.lock.json'
ARCHIVE = ROOT / 'workspace/originals-download/sntp-1.3.1/sntp.zip'
CONFIG = b'# KWCE: Korea standard time (UTC+9, no daylight saving). Confirm the shown time with A.\noffset=32400\n'
README = '''KWCE - sntp 1.3.1 (WiiConnect24 시각 동기화)

왜: 이 본체는 WiiConnect24 표준시가 한 번도 맞춰지지 않아(조회 결과 -30) 뉴스 NEWS000006,
투표 239001 같은 오류가 날 수 있습니다. WiiLink 안내의 해결책이 이 sntp입니다.

사용법
1. 홈브류 채널에서 sntp를 실행합니다(인터넷 연결 필요, 유선 LAN 가능).
2. 화면의 시각이 지금 한국 시각인지, Timezone이 +09:00인지 확인합니다
   (sntp.cfg에 +9시간을 미리 넣어 두었습니다. 틀리면 좌우 버튼으로 30분씩 조정).
3. A를 눌러 저장하고 HOME으로 나옵니다.
4. 뉴스·투표·Mii 콘테스트를 다시 실행해 봅니다.
안 되면: WiiLink 안내대로 시계 전지(CR2032)를 빼고 2~3시간 둔 뒤 다시 끼우고 sntp를 한 번 더 실행합니다.

sntp는 본체 설정(SYSCONF의 시계 보정값)과 WiiConnect24 시각을 바꿉니다. Wii 메뉴에서 시계를 바꾸는 것과 같은 종류의 변경입니다.
원본: https://github.com/ErikAndren/sntp (MIT), 배포 https://oscwii.org/library/app/sntp. 바이너리는 수정하지 않았습니다.
'''
ALLOWED = {'apps/sntp/boot.dol', 'apps/sntp/meta.xml', 'apps/sntp/icon.png', 'apps/sntp/sntp.cfg', 'KWCE-SNTP-README-ko.txt'}


def sha(data): return hashlib.sha256(data).hexdigest()


def build(out):
    pin = json.loads(LOCK.read_text(encoding='utf-8'))
    raw = ARCHIVE.read_bytes()
    if sha(raw) != pin['archive_sha256']:
        raise ValueError('sntp archive differs from its pin')
    zf = zipfile.ZipFile(ARCHIVE); files = {}
    for info in zf.infolist():
        if info.is_dir(): continue
        if not info.filename.startswith('apps/sntp/') or '..' in info.filename:
            raise ValueError('Unexpected path in sntp archive')
        data = zf.read(info)
        if sha(data) != pin['payload_sha256'][info.filename.split('/')[-1]]:
            raise ValueError('sntp payload differs from its pin')
        files[info.filename] = data
    files['apps/sntp/sntp.cfg'] = CONFIG
    files['KWCE-SNTP-README-ko.txt'] = README.encode('utf-8')
    if set(files) != ALLOWED:
        raise ValueError('sntp package paths differ')
    out = Path(out)
    if out.exists():
        raise ValueError('Existing package preserved')
    for rel, data in files.items():
        p = out / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    record = dict(kind='sntp-sd', version=pin['version'], archive_sha256=pin['archive_sha256'], modified_upstream_binary=False,
                  hardware_verified=False, sd_files=[dict(path=r, bytes=len(d), sha256=sha(d)) for r, d in sorted(files.items())])
    manifest = json.dumps(record, indent=2, ensure_ascii=False).encode('utf-8') + b'\n'
    (out / 'package-manifest.json').write_bytes(manifest)
    (out / 'package-manifest.sha256').write_text(sha(manifest) + '\n', encoding='ascii')
    return record


def sd_files(package):
    package = Path(package).resolve()
    raw = (package / 'package-manifest.json').read_bytes()
    if sha(raw) != (package / 'package-manifest.sha256').read_text(encoding='ascii').strip():
        raise ValueError('sntp manifest hash differs')
    record = json.loads(raw); pin = json.loads(LOCK.read_text(encoding='utf-8'))
    if record.get('kind') != 'sntp-sd' or record.get('modified_upstream_binary') or record.get('archive_sha256') != pin['archive_sha256']:
        raise ValueError('sntp package scope differs')
    rows = record['sd_files']
    if {r['path'] for r in rows} != ALLOWED or len(rows) != len(ALLOWED):
        raise ValueError('sntp payload paths differ')
    result = []
    for row in rows:
        p = package / row['path']
        if p.is_symlink() or not p.resolve().is_relative_to(package):
            raise ValueError('sntp payload escapes package')
        data = p.read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']:
            raise ValueError('sntp payload changed')
        name = row['path'].split('/')[-1]
        if row['path'].startswith('apps/sntp/') and name in pin['payload_sha256'] and sha(data) != pin['payload_sha256'][name]:
            raise ValueError('sntp upstream binary differs')
        if name == 'sntp.cfg' and data != CONFIG:
            raise ValueError('sntp config differs')
        result.append((p, row['path']))
    return record, result
