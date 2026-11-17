"""Prepare, but never deploy/run, a personal HBC Korean mail-tool candidate."""
import argparse,hashlib,json,shutil,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def check(out):
    meta=json.loads((out/'package-manifest.json').read_text(encoding='utf-8'))
    if meta['source_candidate_revision']!=3 or meta['sd_deployed']or meta['hardware_success_verified']:raise ValueError('Mail package scope differs')
    for row in meta['files']:
        p=out/row['path']
        if not p.resolve().is_relative_to(out.resolve())or p.is_symlink()or not p.is_file()or digest(p)!=row['sha256']:raise ValueError('Mail package hash/path differs')
    app=out/'apps/kwce-mail';xml=ET.parse(app/'meta.xml').getroot()
    if xml.tag!='app'or xml.findtext('name')!='KWCE WiiLink Mail'or(app/'boot.dol').read_bytes()!=(ROOT/'workspace/hardware/mail-candidate-v3/boot.dol').read_bytes():raise ValueError('Mail HBC entry differs')
    load_library();from PIL import Image
    with Image.open(app/'icon.png')as im:
        if im.size!=(128,48):raise ValueError('Mail HBC icon size')
    print('PASS: Korean mail HBC candidate, pinned boot/source, valid metadata/icon; not deployed or run')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();out=ROOT/'workspace/hardware/mail-hbc-v1'
    if args.check:check(out);return
    if out.exists():raise SystemExit('Numbered mail HBC package preserved')
    source=ROOT/'workspace/hardware/mail-candidate-v3';manifest=json.loads((source/'candidate-manifest.json').read_text())
    for row in manifest['files']:
        if digest(source/row['path'])!=row['sha256']:raise ValueError('Mail candidate changed')
    app=out/'apps/kwce-mail';app.mkdir(parents=True);shutil.copyfile(source/'boot.dol',app/'boot.dol')
    shutil.copytree(source/'source',out/'source');shutil.copyfile(source/'builder.py',out/'builder.py');shutil.copyfile(source/'candidate-manifest.json',out/'source-candidate-manifest.json')
    xml=ET.Element('app',version='1')
    for tag,text in [('name','KWCE WiiLink Mail'),('coder','WiiLink / KWCE Korean adaptation'),('version','0.1 candidate'),('release_date','20261025000000'),('short_description','WiiLink 메일 한글 복원 후보'),('long_description','기본은 읽기 전용 검사입니다. 1+2 다음 +를 누르면 SD에 설정을 보관하고 실제 등록과 메일 설정 변경을 시도합니다. 실기 성공은 미검증입니다. HOME: 종료 / A: 검사 / B: 처음으로.')]:ET.SubElement(xml,tag).text=text
    ET.SubElement(xml,'no_ios_reload');ET.SubElement(xml,'ahb_access');ET.ElementTree(xml).write(app/'meta.xml',encoding='utf-8',xml_declaration=True)
    load_library();from PIL import Image,ImageDraw
    im=Image.new('RGB',(128,48),(24,86,130));draw=ImageDraw.Draw(im);draw.rounded_rectangle((7,9,43,36),radius=3,fill='white');draw.line((9,11,25,25,41,11),fill=(24,86,130),width=2);draw.text((51,9),'KWCE',fill='white');draw.text((51,25),'Wii Mail',fill='white');im.save(app/'icon.png')
    (out/'README-ko.txt').write_text('WiiLink 알림판 메일 한글 복원 후보\n\n이 패키지는 SD에 배포하거나 실기에서 실행하지 않았습니다.\napps/kwce-mail/은 Homebrew Channel용 앱 구조입니다. 기본 화면은 읽기 전용이며 A로 설정을 검사합니다.\n1+2 뒤 +는 실제 등록 및 메일 설정 변경을 실행하므로, Dolphin 미리보기와 동작이 다릅니다. 먼저 SD 보관본을 새 번호로 쓰고 다시 읽어 일치하는지 확인합니다.\n실패 도중의 등록 상태는 바뀔 수 있으며, 보관본이 있다는 이유로 복원이 보장되지는 않습니다.\n기존 콘솔 데이터, 키, 인증 정보 또는 실제 메일은 포함하지 않았습니다.\n실기 수신·송신·알림판 표시·대기 모드 검증은 남아 있습니다.\n원본과 변경 소스 및 GPL 라이선스는 source/에 있습니다.\n',encoding='utf-8')
    meta=dict(revision=1,source_candidate_revision=3,sd_deployed=False,external_registration_executed=False,hardware_success_verified=False,files=[dict(path=p.relative_to(out).as_posix(),sha256=digest(p))for p in sorted(out.rglob('*'))if p.is_file()])
    (out/'package-manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');check(out)
if __name__=='__main__':main()
