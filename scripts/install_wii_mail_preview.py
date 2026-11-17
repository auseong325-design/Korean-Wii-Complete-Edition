"""Switch only the stopped incapable mail preview; preserve the prior lock."""
import json,shutil,subprocess
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped
from prepare_wii_mail_preview import BASE

def main():
    stopped();candidate=ROOT/'workspace/hardware/mail-candidate-v3';meta=json.loads((candidate/'candidate-manifest.json').read_text())
    if not meta.get('preview_write_symbols_absent')or meta['external_registration_executed']:raise ValueError('Unapproved mail preview')
    for row in meta['files']:
        if sha256(candidate/row['path'])!=row['sha256']:raise ValueError('Mail candidate artifact differs')
    symbols=subprocess.check_output([str(ROOT/'tools/devkitpro-root/opt/devkitpro/devkitPPC/bin/powerpc-eabi-nm.exe'),'-C','--defined-only',str(candidate/'preview.elf')],text=True)
    if'Patcher()'in symbols or'NWC24Config::WriteConfig()'in symbols:raise ValueError('Registration/config write symbol in preview')
    lock=ROOT/'configs/wii-mail-preview.lock.json';old=lock.read_bytes();snapshot=ROOT/'configs/wii-mail-preview-v2-ko.json'
    if snapshot.exists():raise ValueError('Previous mail preview lock preserved')
    snapshot.write_bytes(old);shutil.copy2(candidate/'preview.dol',BASE/'preview.dol');data=json.loads(old)
    next(r for r in data['files']if r['path'].endswith('/preview.dol'))['sha256']=sha256(BASE/'preview.dol')
    data['candidate_revision']=3;lock.write_text(json.dumps(data,indent=2));print('Installed incapable mail preview candidate 3; prior lock/binaries preserved')
if __name__=='__main__':main()
