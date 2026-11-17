"""Author a synthetic DVD-Video test disc (menu, 2 chapters, 2 audio, 1 subtitle).

Every picture and sound is generated here (test bars, tones, Noto Sans KR text);
no film, broadcast or retail disc content is used. Tools are the hash-locked
ffmpeg/dvdauthor/spumux/mkisofs of configs/dvd-test-media.lock.json.
Output: workspace/test-media/dvd/kwce-dvd-test-v<N>.iso (new number only).
"""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TOOLS=ROOT/'tools/dvd-test-tools'
FONT=ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf'

def tool(name):
    hits=sorted(TOOLS.glob(f'**/{name}.exe'))
    if not hits:raise SystemExit(f'{name}.exe missing; extract the locked tools first')
    return str(hits[0])

def run(*cmd,cwd=None):
    r=subprocess.run([str(c) for c in cmd],cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:raise SystemExit(f'{Path(cmd[0]).name} failed:\n'+(r.stderr or r.stdout)[-3000:])
    return r

def image(path,size,draw,flat=False):
    """flat=True: no anti-aliasing, so spumux sees at most 3 colours + transparent."""
    from kwce.channels import load_library;load_library()
    from PIL import Image,ImageDraw,ImageFont
    im=Image.new('RGBA',size,(0,0,0,0));d=ImageDraw.Draw(im)
    if flat:d.fontmode='1'
    draw(d,lambda px:ImageFont.truetype(str(FONT),px));im.save(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
    out=ROOT/'workspace/test-media/dvd';iso=out/f'kwce-dvd-test-v{args.revision}.iso'
    if iso.exists():raise SystemExit('Existing test disc preserved')
    work=ROOT/f'workspace/build/dvd-test-disc-v{args.revision}'
    if work.exists():shutil.rmtree(work)
    work.mkdir(parents=True);out.mkdir(parents=True,exist_ok=True)
    ffmpeg,dvdauthor,spumux,mkisofs=tool('ffmpeg'),tool('dvdauthor'),tool('spumux'),tool('mkisofs')
    # Title: two 20 s chapters of test bars with a burnt-in label; two tone tracks.
    for n,label in enumerate(['1장  테스트 영상','2장  테스트 영상'],1):
        image(work/f'label{n}.png',(720,120),lambda d,f,label=label:d.text((360,60),label,font=f(56),fill=(255,255,255,255),stroke_width=4,stroke_fill=(0,0,0,255),anchor='mm'))
    run(ffmpeg,'-y','-f','lavfi','-i','smptebars=size=720x480:rate=30000/1001:duration=20','-f','lavfi','-i','testsrc2=size=720x480:rate=30000/1001:duration=20',
        '-i',work/'label1.png','-i',work/'label2.png',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=40','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=40',
        '-filter_complex',"[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[b];[b][2:v]overlay=0:330:enable='lt(t,20)'[c];[c][3:v]overlay=0:330:enable='gte(t,20)'[v]",
        '-map','[v]','-map','4:a','-map','5:a','-target','ntsc-dvd','-aspect','16:9','-b:v','4000k','-c:a','ac3','-b:a','192k',work/'title_raw.mpg')
    image(work/'sub.png',(720,480),lambda d,f:d.text((360,420),'자막 테스트 (한국어)',font=f(40),fill=(255,255,0,255),stroke_width=3,stroke_fill=(0,0,0,255),anchor='mm'),flat=True)
    (work/'sub.xml').write_text('<subpictures><stream><spu start="00:00:01.00" end="00:00:38.00" image="sub.png" force="no"/></stream></subpictures>',encoding='utf-8')
    with open(work/'title_raw.mpg','rb') as src,open(work/'title.mpg','wb') as dst:
        r=subprocess.run([spumux,'-s0','sub.xml'],cwd=work,stdin=src,stdout=dst,stderr=subprocess.PIPE)
    if r.returncode:raise SystemExit('spumux title failed:\n'+r.stderr.decode(errors='replace')[-2000:])
    # Menu: still background with two buttons and spumux highlight/select overlays (4 colours).
    def background(d,f):
        d.rectangle((0,0,720,480),fill=(24,74,140,255));d.text((360,110),'KWCE 테스트 DVD',font=f(60),fill=(255,255,255,255),anchor='mm')
        for y,t in [(250,'본편 재생'),(340,'2장부터 재생')]:
            d.rounded_rectangle((210,y-35,510,y+35),18,fill=(255,255,255,255));d.text((360,y),t,font=f(36),fill=(20,40,80,255),anchor='mm')
    image(work/'menu_bg.png',(720,480),background)
    for name,color in [('hl',(0,200,255,255)),('sel',(255,140,0,255))]:
        image(work/f'menu_{name}.png',(720,480),lambda d,f,c=color:[d.rounded_rectangle((200,y-45,520,y+45),24,outline=c,width=8) for y in (250,340)],flat=True)
    run(ffmpeg,'-y','-loop','1','-i',work/'menu_bg.png','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','2','-vf','format=yuv420p',
        '-target','ntsc-dvd','-aspect','4:3','-c:a','ac3','-shortest',work/'menu_raw.mpg')
    (work/'menu.xml').write_text('<subpictures><stream><spu force="yes" start="00:00:00.00" highlight="menu_hl.png" select="menu_sel.png" autooutline="infer" autoorder="rows"/></stream></subpictures>',encoding='utf-8')
    with open(work/'menu_raw.mpg','rb') as src,open(work/'menu.mpg','wb') as dst:
        r=subprocess.run([spumux,'menu.xml'],cwd=work,stdin=src,stdout=dst,stderr=subprocess.PIPE)
    if r.returncode:raise SystemExit('spumux menu failed:\n'+r.stderr.decode(errors='replace')[-2000:])
    (work/'dvd.xml').write_text('''<dvdauthor dest="DVD">
 <vmgm><fpc>jump titleset 1 menu;</fpc><menus><video format="ntsc" aspect="4:3"/></menus></vmgm>
 <titleset>
  <menus><video format="ntsc" aspect="4:3"/>
   <pgc entry="root"><vob file="menu.mpg" pause="inf"/>
    <button name="1">jump title 1;</button><button name="2">jump title 1 chapter 2;</button></pgc></menus>
  <titles><video format="ntsc" aspect="16:9"/><audio lang="ko"/><audio lang="en"/><subpicture lang="ko"/>
   <pgc><vob file="title.mpg" chapters="0,0:20"/><post>call menu;</post></pgc></titles>
 </titleset>
</dvdauthor>''',encoding='utf-8')
    run(dvdauthor,'-x','dvd.xml',cwd=work)
    run(mkisofs,'-dvd-video','-V','KWCE_DVD_TEST','-o',iso,work/'DVD')
    digest=hashlib.sha256(iso.read_bytes()).hexdigest()
    (out/f'kwce-dvd-test-v{args.revision}.json').write_text(json.dumps(dict(file=iso.name,sha256=digest,size=iso.stat().st_size,synthetic=True,
        content='generated test bars/tones/Korean labels only',menu_buttons=2,chapters=2,audio_tracks=['ko 440 Hz','en 880 Hz'],subtitles=['ko'],
        tools='configs/dvd-test-media.lock.json'),ensure_ascii=False,indent=1),encoding='utf-8')
    print(json.dumps(dict(iso=str(iso.relative_to(ROOT)),sha256=digest,bytes=iso.stat().st_size)))

if __name__=='__main__':main()
