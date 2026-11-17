"""Own two-title DVD: TFF then BFF, to catch progressive-output field starvation."""
import argparse,hashlib,json,shutil
from make_dvd_test_disc import ROOT,tool,run

def main():
    p=argparse.ArgumentParser();p.add_argument('--revision',type=int,choices=[4,5],default=4);a=p.parse_args()
    work=ROOT/f'workspace/build/dvd-field-test-v{a.revision-3}';base=ROOT/'workspace/test-media/dvd';iso=base/f'kwce-dvd-test-v{a.revision}.iso'
    if work.exists()or iso.exists():raise ValueError('Numbered field-test media preserved')
    work.mkdir();shutil.copy2(ROOT/'workspace/build/dvd-transition-test-v1/menu.mpg',work/'menu.mpg')
    shutil.copy2(ROOT/'workspace/build/dvd-transition-test-v1/title.mpg',work/'tff.mpg')
    run(tool('ffmpeg'),'-y','-f','lavfi','-i','testsrc2=size=720x480:rate=60000/1001:duration=45',
        '-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=45',
        '-vf','tinterlace=mode=interleave_bottom,format=yuv420p','-target','ntsc-dvd','-aspect','4:3',
        '-flags','+ilme+ildct','-top','0','-b:v','4000k','-c:a','pcm_dvd','-ac','2','-ar','48000','-t','45',work/'bff.mpg')
    xml='''<dvdauthor dest="DVD"><vmgm><fpc>jump titleset 1 menu;</fpc>
<menus><video format="ntsc" aspect="4:3"/></menus></vmgm><titleset>
<menus><video format="ntsc" aspect="4:3"/><pgc entry="root"><vob file="menu.mpg" pause="inf"/>
<button name="1">jump title 1;</button><button name="2">jump title 2;</button></pgc></menus>
<titles><video format="ntsc" aspect="4:3"/><audio format="pcm" channels="2" samplerate="48khz"/>
<pgc><vob file="tff.mpg" chapters="0,0:10"/><post>call menu;</post></pgc>
<pgc><vob file="bff.mpg" chapters="0,0:10"/><post>call menu;</post></pgc>
</titles></titleset></dvdauthor>'''
    if a.revision==5:
        xml=xml.replace('<button name="1">jump title 1;</button><button name="2">jump title 2;</button>',
                        '<button name="1">jump title 2;</button><button name="2">jump title 1;</button>')
    (work/'dvd.xml').write_text(xml,encoding='utf-8')
    run(tool('dvdauthor'),'-x','dvd.xml',cwd=work)
    run(tool('mkisofs'),'-dvd-video','-V','KWCE_FIELD_TEST','-o',iso,work/'DVD')
    record=dict(file=iso.name,synthetic=True,sha256=hashlib.sha256(iso.read_bytes()).hexdigest(),size=iso.stat().st_size,
                content='own bars/tones; TFF20s/BFF45s titles; LPCM48k stereo; BFF first button='+str(a.revision==5),
                menu_buttons=2,titles=2,actual_encryption=False,tools='configs/dvd-test-media.lock.json')
    iso.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: synthetic DVD v{a.revision}, separate TFF/BFF titles, BFF first button={a.revision==5}')

if __name__=='__main__':main()
