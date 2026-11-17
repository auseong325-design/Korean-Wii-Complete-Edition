"""Package a pinned, unmodified official HBC app; no console access.

python scripts/export_account_linker.py [--package N]   (default: current, see kwce/account_linker_package.py)
sd-v1 keeps its original recipe (checked-out HEAD, working-tree licence).
sd-v2+ read source and licence from the pinned tag commit without checking it out.
"""
import argparse
import io
import json
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from kwce.account_linker_package import ALLOWED, CURRENT, VERSIONS, lock as load_lock, sd_files, sha

README = {
    1: ('WiiLink Account Linker 2.1.0 (공식 원본)\n\n'
        '본체에 등록된 Wii 메일과 별개로, 사용자가 WiiLink 계정에 본체를 연결하는 도구입니다. '
        '현재 WiiLink 계정 연결 장애가 표시되어 있으므로 서비스 복구 뒤 시험하세요. '
        'Homebrew Channel에서 실행한 다음 화면의 안내에 따라 본인이 계정에 로그인하고 연결 코드를 입력합니다. '
        '연결 과정은 Wii 번호와 본체 인증 정보 및 일련번호를 WiiLink로 보냅니다. '
        '본체 국가나 언어 설정은 이 패키지가 바꾸지 않습니다. '
        '한국판 실기 호환과 서버 승인, 계정 연결 성공은 미검증입니다. '
        '로그인 코드, 본체 번호, 키와 인증서는 공유하지 마세요.\n'),
    2: ('WiiLink Account Linker 2.2.0 (공식 원본)\n\n'
        '본체에 등록된 Wii 메일과 별개로, 사용자가 WiiLink 계정에 본체를 연결하는 도구입니다. '
        '2.2.0은 WiiLink 로그인 서버가 바뀐 뒤의 새 연결 ID를 사용합니다. 이전 2.1.0으로 연결이 되지 않았다면 이 판을 쓰세요. '
        'Homebrew Channel에서 실행한 다음 화면의 안내에 따라 본인이 계정에 로그인하고 연결 코드를 입력합니다. '
        '연결 과정은 Wii 번호와 본체 인증 정보 및 일련번호를 WiiLink로 보냅니다. '
        '본체 국가나 언어 설정은 이 패키지가 바꾸지 않습니다. '
        '한국판 실기 호환과 서버 승인, 계정 연결 성공은 미검증입니다. '
        '로그인 코드, 본체 번호, 키와 인증서는 공유하지 마세요.\n'),
}


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', type=int, default=CURRENT, choices=sorted(VERSIONS))
    number = ap.parse_args().package
    kind = VERSIONS[number][0]
    lock = load_lock(number)
    repo = ROOT / 'external/other-tools/AccountLinker'
    if number == 1:
        commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    else:
        commit = git(repo, 'rev-parse', lock['source_tag'] + '^{commit}').decode().strip()
    if commit != lock['source_commit']: raise ValueError('Pinned upstream source commit differs')
    out = ROOT / f'workspace/hardware/kwce-account-linker-sd-v{number}'
    if out.exists(): raise ValueError('Existing package preserved')
    request = urllib.request.Request(lock['archive_url'], headers={'User-Agent': 'KWCE-Offline-Audit'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(lock['archive_bytes'] + 1)
    if len(data) != lock['archive_bytes'] or sha(data) != lock['archive_sha256']:
        raise ValueError('Official release archive hash or size differs')
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.testzip() is not None: raise ValueError('Release archive CRC mismatch')
        for name in ('boot.dol', 'icon.png', 'meta.xml'):
            key = 'apps/wiilink-account-linker/' + name
            infos = [i for i in z.infolist() if i.filename == key and not i.is_dir()]
            if len(infos) != 1 or infos[0].file_size > 4_000_000:
                raise ValueError('Release archive app payload differs')
            files[key] = z.read(infos[0])
            if sha(files[key]) != lock['payload_sha256'][name]:
                raise ValueError('Release archive app payload hash differs')
    root = ET.fromstring(files['apps/wiilink-account-linker/meta.xml'])
    if root.findtext('version') != 'v' + lock['version'] or root.find('ahb_access') is None:
        raise ValueError('Account Linker metadata differs')
    if not files['apps/wiilink-account-linker/icon.png'].startswith(bytes.fromhex('89504e470d0a1a0a')):
        raise ValueError('Account Linker icon is not PNG')
    files['apps/wiilink-account-linker/source.zip'] = git(repo, 'archive', '--format=zip', commit)
    files['apps/wiilink-account-linker/LICENSE'] = ((repo / 'LICENCE').read_bytes() if number == 1
                                                    else git(repo, 'show', f'{commit}:LICENCE'))
    files['apps/wiilink-account-linker/SOURCE.txt'] = (
        f"WiiLink Account Linker v{lock['version']}, unchanged upstream release binary.\n"
        f"Source: {lock['source_repository']} commit {commit}; source.zip is git archive of that commit.\n"
        'License: GNU Affero General Public License v3; see LICENSE.\n'
        f"Official release SHA-256: {lock['archive_sha256']}.\n").encode('utf-8')
    files['KWCE-ACCOUNT-LINKER-README-ko.txt'] = README[number].encode('utf-8')
    if set(files) != ALLOWED: raise ValueError('Unexpected package output')
    out.mkdir(parents=True)
    for name, content in files.items():
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    record = {'kind':kind,'version':lock['version'],
              'release_archive_sha256':lock['archive_sha256'],'source_commit':commit,
              'modified_upstream_binary':False,'hardware_verified':False,
              'sd_files':[{'path':name,'bytes':len(content),'sha256':sha(content)} for name,content in sorted(files.items())]}
    manifest=(json.dumps(record,indent=2)+'\n').encode('utf-8')
    (out/'package-manifest.json').write_bytes(manifest)
    (out/'package-manifest.sha256').write_text(sha(manifest)+'\n',encoding='ascii')
    sd_files(out)
    print(f"PASS: pinned official Account Linker {lock['version']} release, source, license, exact payload "
          f"-> {out.name}; hardware untested")

if __name__ == '__main__': main()
