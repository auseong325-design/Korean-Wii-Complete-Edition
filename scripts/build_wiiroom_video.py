"""Own Korean MOC5 test clip; pinned encoder, capability0, no external media."""
import hashlib, json, os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    target=ROOT/'workspace/sandbox/wiiroom-video-v2'
    if target.exists(): raise ValueError('Existing numbered video fixture preserved')
    cfg=json.loads((ROOT/'configs/mobipeg-runtime.lock.json').read_text(encoding='utf-8'))
    for row in cfg['files']:
        if digest(ROOT/row['path'])!=row['sha256']:raise ValueError('Pinned encoder differs')
    load_library()
    from PIL import Image,ImageDraw,ImageFont
    from kwce.wiiroom_visual import _font
    target.mkdir(parents=True);frames=target/'frames';frames.mkdir();video=bytearray()
    # A progress bar and changing counter make stale-frame playback visible.
    for n in range(250):
        im=Image.new('RGB',(320,240),(18,47,70));d=ImageDraw.Draw(im)
        d.text((20,24),'Wii의 방',font=_font(30),fill='white')
        d.text((20,80),'한국어 영상 재생 시험',font=_font(20),fill=(180,225,245))
        d.text((20,120),f'{n//25:02d}초 / 10초',font=_font(19),fill='white')
        d.rectangle((20,176,300,197),fill=(40,80,100));d.rectangle((20,176,20+280*n//249,197),fill=(46,190,225))
        d.text((20,213),'자체 제작한 테스트 영상',font=_font(14),fill=(180,225,245))
        y,cb,cr=im.convert('YCbCr').split()
        video.extend(y.tobytes());video.extend(cb.resize((160,120),Image.Resampling.BOX).tobytes());video.extend(cr.resize((160,120),Image.Resampling.BOX).tobytes())
        if n in (0,249):im.save(frames/f'{n:04d}.png')
    (target/'frames.yuv').write_bytes(video)
    src=ROOT/'scripts/OfflineMediaRunner.cs';compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    r=subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(target/'OfflineMediaRunner.exe'),str(src)],capture_output=True)
    (target/'compile.log').write_bytes(r.stdout+r.stderr)
    if r.returncode:raise ValueError('Media sandbox compile failed')
    # asm=0 avoids a reproducible access violation in this release's x264 fork.
    encode='-hide_banner -nostdin -f rawvideo -pixel_format yuv420p -video_size 320x240 -framerate 25 -i frames.yuv -f lavfi -i sine=frequency=440:sample_rate=32000 -t 10 -c:v mobiclip -pix_fmt yuv420p -threads 1 -x264-params asm=0:threads=1:rc-lookahead=0 -c:a pcm_s16le -ac 2 -ar 32000 -mo_audio pcm -f mobiclip_mo -report sample.mov'
    decode='-hide_banner -nostdin -i sample.mov -f null - -report'
    for name,cmd in [('encode',encode),('decode',decode)]:
        (target/f'{name}.txt').write_text(cmd,encoding='ascii')
        env=os.environ.copy();env['FFREPORT']=f'file={name}.log:level=32';env['SENTRY_DSN']=''
        r=subprocess.run([str(target/'OfflineMediaRunner.exe'),f'{name}.txt'],env=env,capture_output=True,timeout=75)
        (target/f'{name}-sandbox.log').write_bytes(r.stdout+r.stderr)
        if r.returncode:raise ValueError(f'MOC5 {name} failed; private diagnostic retained')
    data=(target/'sample.mov').read_bytes()
    if data[:4]!=b'MOC5'or b'KI'not in data:raise ValueError('Missing MOC5 header/index')
    record=dict(schema=1,synthetic=True,external_media=False,capability_count=0,encoder_version='2.3',
        encoder_asm=False,frames=250,fps=25,width=320,height=240,seconds=10,audio='stereo PCM 32000Hz',
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p))for p in [src,target/'OfflineMediaRunner.exe',target/'sample.mov']],
        decode_completed=True,channel_playback_verified=False)
    (target/'video-manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('PASS: own Korean 10s MOC5/PCM, capability0 encode/decode, asm disabled; channel playback pending')

if __name__=='__main__': main()
