"""Compile private Korean mail tool + an incapable preview, without running either."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
DKP=ROOT/'tools/devkitpro-root/opt/devkitpro'
PAGES=[
 ('Wii 알림판 · WiiLink 메일','A: 설정 검사 (읽기 전용)\n\n1과 2를 함께 누르면 복원 안내로 이동합니다.\nHOME: 종료\n\n본체 번호·암호는 화면에 표시하지 않습니다.'),
 ('설정 파일 검사 완료','파일 구조와 검사 합계가 올바릅니다.\n\n이 결과는 메일 등록·수신·송신 성공을\n의미하지 않습니다.\n\nB: 처음으로   HOME: 종료'),
 ('설정 파일 검사 실패','설정 파일을 읽거나 검사하지 못했습니다.\n\n복원을 실행하지 말고 원인을 확인해 주세요.\n\nB: 처음으로   HOME: 종료'),
 ('WiiLink 메일 복원 안내','실행하면 본체의 메일 설정을 바꾸고\nWiiLink 서버에 본체를 등록합니다.\n\n먼저 SD에 기존 설정을 새 번호로 보관합니다.\n등록 이후 서버 상태는 되돌리지 않습니다.\n\n+: 실행   B: 취소'),
 ('메일 복원 처리 중','기존 설정 보관과 서버 등록을 진행합니다.\n\n완료될 때까지 전원을 끄거나\nSD 카드를 빼지 마세요.'),
 ('메일 등록 처리 완료','WiiLink 메일 설정을 반영했습니다.\n\nWii 알림판에서 수신·송신을 직접\n확인해야 최종 동작을 판정할 수 있습니다.\n\nHOME: 종료'),
 ('메일 복원 처리 실패','설정 보관·등록·설정 반영 중 실패했습니다.\n현재 상태는 확인이 필요합니다.\n\n설정을 임의로 삭제하거나 반복 등록하지 말고\n보관 파일과 상태를 점검해 주세요.\n\nHOME: 종료'),
 ('에뮬레이터 미리보기','이 파일은 화면 검수 전용입니다.\n\n등록·설정 쓰기 코드는 포함하지 않았습니다.\n실기 복원 성공을 의미하지 않습니다.\n\nB: 처음으로   HOME: 종료'),
]

def screens(out):
    load_library();from PIL import Image,ImageDraw,ImageFont
    from kwce.wiiroom_visual import _font
    chunks=[]
    for title,body in PAGES:
        image=Image.new('RGB',(320,240),(15,37,56));draw=ImageDraw.Draw(image)
        draw.text((14,15),title,font=_font(16),fill=(83,214,245));draw.line((14,43,306,43),fill=(83,214,245))
        draw.multiline_text((14,57),body,font=_font(12),spacing=7,fill='white')
        raw=bytearray()
        for y in range(240):
            for x in range(0,320,2):
                a,b=image.getpixel((x,y)),image.getpixel((x+1,y))
                def convert(c):
                    r,g,b=c;return (round(16+.257*r+.504*g+.098*b),round(128-.148*r-.291*g+.439*b),round(128+.439*r-.368*g-.071*b))
                p,q=convert(a),convert(b);raw.extend((p[0],(p[1]+q[1])//2,q[0],(p[2]+q[2])//2))
        chunks.append(raw)
    header='static const unsigned char screens[8][153600] __attribute__((aligned(32))) = {\n'+',\n'.join('{'+','.join(map(str,x))+'}'for x in chunks)+'\n};\n'
    (out/'screens.h').write_text(header)

def main():
    source=ROOT/'external/other-tools/Mail-Patcher';lock=json.loads((ROOT/'configs/sources.lock.json').read_text())
    row=next(r for r in lock if r['repository']=='WiiLink24/Mail-Patcher')
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=row['commit']:raise ValueError('Mail patcher source revision differs')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('Pinned mail source modified')
    number=1
    while(ROOT/f'workspace/hardware/mail-candidate-v{number}').exists():number+=1
    out=ROOT/f'workspace/hardware/mail-candidate-v{number}';work=out/'source';work.mkdir(parents=True)
    for name in ['config.cpp','config.h','patcher.cpp','patcher.h','utils.cpp','utils.h','errors.h','LICENSE']:shutil.copy2(source/name,work/name)
    shutil.copy2(ROOT/'homebrew/wii-mail/source/main.cpp',work/'main.cpp')
    # Identifiers are not printed. Failure leaves the registration state as it
    # actually stands, rather than unconditionally marking it Registered.
    p=work/'patcher.cpp';text=p.read_text();start=text.index('  s64 wiino =');end=text.index('  return error_code;',start)
    text=text[:start]+text[end:]
    text=text.replace('  config.SetCreationStage(NWC24CreationStage::Registered);\n  config.WriteConfig();\n','',1)
    # Upstream's do/while(0) never retries after continue; retain its bound.
    if text.count('} while (0);')!=2:raise ValueError('Upstream retry layout differs')
    text=text.replace('} while (0);','} while (ret == -33 && tries >= 0);')
    # Successful calls must leave their retry loops immediately.
    text=text.replace('    ret = outbuf[0];\n','    ret = outbuf[0];\n    if (ret == 0) break;\n',1)
    text=text.replace('    if (outbuf[0] == -33)','    ret = outbuf[0];\n    if (outbuf[0] == -33)',1)
    p.write_text(text)
    p=work/'config.cpp';text=p.read_text()
    old='  m_data = *(static_cast<ConfigData*>(file->data));\n  return true;'
    if text.count(old)!=1:raise ValueError('Mail config read layout differs')
    text=text.replace(old,'  if (file->size != sizeof(m_data)) { free(file->data); delete file; return false; }\n  m_data = *(static_cast<ConfigData*>(file->data));\n  free(file->data); delete file;\n  return m_data.version == 8 && CheckNwc24Config() == 0 && u32(m_data.creation_stage) <= 2;')
    p.write_text(text);screens(work)
    compiler=DKP/'devkitPPC/bin/powerpc-eabi-g++.exe'
    commands=[]
    for preview,name in [(False,'boot'),(True,'preview')]:
        files=[work/n for n in (['main.cpp','config.cpp','utils.cpp']if preview else['main.cpp','config.cpp','patcher.cpp','utils.cpp'])]
        command=[str(compiler),'-std=gnu++20','-O2','-Wall','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-mrvl','-mcpu=750','-meabi','-mhard-float','-DGEKKO','-I'+str(work),'-I'+str(DKP/'libogc/include'),'-L'+str(DKP/'libogc/lib/wii')]
        if preview:command+=['-DKWCE_PREVIEW_ONLY']
        command=[*command,*map(str,files),'-lwiiuse','-lbte','-lfat','-logc','-lm','-o',str(out/(name+'.elf'))];commands.append(command)
        result=subprocess.run(command,capture_output=True,text=True)
        (out/(name+'-compiler.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise SystemExit('Mail tool compile failed; diagnostics preserved privately')
        subprocess.run([str(DKP/'tools/bin/elf2dol.exe'),str(out/(name+'.elf')),str(out/(name+'.dol'))],check=True,capture_output=True)
    symbols=subprocess.check_output([str(DKP/'devkitPPC/bin/powerpc-eabi-nm.exe'),'-C','--defined-only',str(out/'preview.elf')],text=True)
    if'Patcher()'in symbols or'NWC24Config::WriteConfig()'in symbols:raise ValueError('Preview contains registration/config-write implementation')
    shutil.copy2(Path(__file__).resolve(),out/'builder.py')
    (out/'README-ko.txt').write_text('WiiLink 메일 복원 후보입니다. 실기 성공은 미확인입니다.\nboot.dol: 읽기 전용으로 시작하며, 1+2 뒤 +를 눌러야 SD 보관·실제 등록·설정 변경을 실행합니다.\npreview.dol: 등록·설정 쓰기 기능이 없는 화면 검수 전용입니다.\n에이전트는 실기용 boot.dol을 실행하지 않았으며, SD에도 복사하지 않았습니다.\n원본 WiiLink GPL-3.0 소스와 변경 소스를 source/에 포함했습니다.\n',encoding='utf-8')
    manifest=dict(source_commit=row['commit'],korean_frontend=True,preview_has_registration=False,preview_write_symbols_absent=True,compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),compile_commands=commands,hardware_success_verified=False,external_registration_executed=False,sd_deployed=False,files=[dict(path=p.relative_to(out).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in sorted(out.rglob('*'))if p.is_file()])
    (out/'candidate-manifest.json').write_text(json.dumps(manifest,indent=2));print('Built Korean mail candidate',number,'and incapable preview; not run or deployed')
if __name__=='__main__':main()
