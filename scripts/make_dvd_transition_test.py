"""Own test bars: still menu -> interlaced 4:3 MPEG-2/LPCM; marked-PES fault disc."""
import hashlib,json,shutil,sys
from pathlib import Path
from make_dvd_test_disc import ROOT,tool,run

def main():
    base=ROOT/'workspace/test-media/dvd';work=ROOT/'workspace/build/dvd-transition-test-v1'
    if work.exists()or any((base/f'kwce-dvd-test-v{n}.iso').exists()for n in (2,3)):raise ValueError('DVD transition revisions preserved')
    work.mkdir();menu=ROOT/'workspace/build/dvd-test-disc-v1/menu.mpg';shutil.copy2(menu,work/'menu.mpg')
    ffmpeg,dvdauthor,mkisofs=tool('ffmpeg'),tool('dvdauthor'),tool('mkisofs')
    run(ffmpeg,'-y','-f','lavfi','-i','testsrc2=size=720x480:rate=60000/1001:duration=20',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=20','-vf','tinterlace=mode=interleave_top,format=yuv420p',
        '-target','ntsc-dvd','-aspect','4:3','-flags','+ilme+ildct','-top','1','-b:v','4000k','-c:a','pcm_dvd','-ac','2','-ar','48000','-t','20',work/'title.mpg')
    (work/'dvd.xml').write_text('''<dvdauthor dest="DVD">
<vmgm><fpc>jump titleset 1 menu;</fpc><menus><video format="ntsc" aspect="4:3"/></menus></vmgm>
<titleset><menus><video format="ntsc" aspect="4:3"/><pgc entry="root"><vob file="menu.mpg" pause="inf"/>
<button name="1">jump title 1;</button><button name="2">jump title 1 chapter 2;</button></pgc></menus>
<titles><video format="ntsc" aspect="4:3"/><audio format="pcm" channels="2" samplerate="48khz"/>
<pgc><vob file="title.mpg" chapters="0,0:10"/><post>call menu;</post></pgc></titles></titleset></dvdauthor>''',encoding='utf-8')
    run(dvdauthor,'-x','dvd.xml',cwd=work)
    for revision in (2,3):
        marked=0
        if revision==3:
            p=work/'DVD/VIDEO_TS/VTS_01_1.VOB';data=bytearray(p.read_bytes())
            for at in range(0,len(data)-2047,2048):
                off=at+14+(data[at+13]&7)
                if data[at:at+4]==b'\0\0\1\xba'and data[off:off+3]==b'\0\0\1'and 0xe0<=data[off+3]<=0xef:
                    data[off+6]|=0x30;marked+=1;break
            if marked!=1:raise ValueError('Synthetic video PES marker injection failed')
            p.write_bytes(data)
        iso=base/f'kwce-dvd-test-v{revision}.iso';run(mkisofs,'-dvd-video','-V','KWCE_TRANSITION','-o',iso,work/'DVD')
        record=dict(file=iso.name,synthetic=True,sha256=hashlib.sha256(iso.read_bytes()).hexdigest(),size=iso.stat().st_size,content='own test bars/tones, still menu -> interlaced 4:3 MPEG2/LPCM',menu_buttons=2,chapters=2,marked_pes_sectors=marked,actual_encryption=False,tools='configs/dvd-test-media.lock.json',menu_sha256=hashlib.sha256(menu.read_bytes()).hexdigest())
        iso.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        print(f'PASS: synthetic DVD v{revision}; interlaced/LPCM, marker fault sectors {marked}')

if __name__=='__main__':main()
