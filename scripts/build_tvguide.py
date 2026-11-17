"""Immutable Korean TV Guide experiment. Console originals remain untouched."""
import argparse,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive
from kwce.votes_resources import translate_bmg

def executable(raw,mapping):
    result=bytearray(raw);records=[];changed_ranges=[]
    for source,target in sorted(mapping.items(),key=lambda item:-len(item[0])):
        before=source.encode('utf-16-be');after=target.encode('utf-16-be')
        if len(after)>len(before):raise ValueError('TV fixed literal exceeds allocation: '+source+' -> '+target)
        if sorted(re.findall(r'%[-+0-9.*]*[a-zA-Z]+',source))!=sorted(re.findall(r'%[-+0-9.*]*[a-zA-Z]+',target)):raise ValueError('TV format placeholder changed')
        count=0
        for match in re.finditer(re.escape(before+b'\0\0'),raw):
            at=match.start()
            if at%2 or not(at>=4485000 or 4151900<=at<4152100):continue
            if any(at<end and at+len(before)>start for start,end in changed_ranges):continue
            result[at:at+len(before)]=after+bytes(len(before)-len(after));changed_ranges.append((at,at+len(before)));count+=1
        if count:records.append(dict(source=source,text=target,occurrences=count))
    # Original service endpoints are redirected only in the emulator build.
    endpoint_count=0
    for match in re.finditer(rb'https?://[^\0\s<>"\x80-\xff]{3,250}',raw):
        old=match.group()
        if b'.wapp.wii.com'not in old:continue
        from urllib.parse import urlsplit
        parsed=urlsplit(old.decode());new=('http://127.0.0.2'+(parsed.path or'/')).encode()
        if len(new)>len(old):raise ValueError('TV local endpoint exceeds allocation')
        at=match.start();result[at:at+len(old)]=new+bytes(len(old)-len(new));endpoint_count+=1
    if not records or not endpoint_count:raise ValueError('TV executable translation/endpoint identity')
    return bytes(result),dict(translated_literals=sum(r['occurrences']for r in records),messages=records,local_endpoints=endpoint_count)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,choices=[1,2,3,4,5,6,7],default=7);parser.add_argument('--reproduce',action='store_true');args=parser.parse_args()
    out=ROOT/f'workspace/channels/tvguide/build-v{args.revision}'
    expected=None
    if args.reproduce:
        expected=(out/'tvguide-ko-local-test.wad').read_bytes();number=1
        while(ROOT/f'workspace/private/tvguide-reproduce-v{args.revision}-{number}').exists():number+=1
        out=ROOT/f'workspace/private/tvguide-reproduce-v{args.revision}-{number}'
    if out.exists():raise SystemExit('Existing TV build preserved')
    config=json.loads((ROOT/'configs/tvguide-messages-v1-ko.json').read_text(encoding='utf-8'));strings=json.loads((ROOT/'configs/tvguide-executable-v1-ko.json').read_text(encoding='utf-8'))
    if args.revision>=4:strings=json.loads((ROOT/'configs/tvguide-executable-v4-ko.json').read_text(encoding='utf-8'))
    source=(ROOT/'workspace/channels/tvguide/originals/tvguide-japan-original.wad').read_bytes()
    if hashlib.sha256(source).hexdigest()!=config['source_sha256']or config['source_sha256']!=strings['source_sha256']:raise ValueError('TV source hash differs')
    lib=load_library();title=lib.title.Title();title.load_wad(source)
    if title.tmd.title_id!='0001000148424e4a'or title.tmd.boot_index!=13:raise ValueError('TV source identity differs')
    original=[title.get_content_by_index(i)for i in range(14)]
    edited,record=executable(original[1],strings['messages'])
    if args.revision>=2:
        from kwce.tvguide_compat import local_registration_check
        edited,record['local_access']=local_registration_check(edited)
    if args.revision==4:
        from kwce.tvguide_compat import local_plain_downloads
        edited,record['local_downloads']=local_plain_downloads(edited)
    title.set_content(edited,1)
    archive=ChannelArchive(original[7]);counts={}
    for name,mapping in config['messages'].items():
        raw=archive.get(name);changed,count=translate_bmg(raw,mapping)
        # HAL's text substitutions are textual tags in addition to BMG controls.
        from draft_channel_localizations import messages,tokenize
        rows=messages(raw)
        if set(mapping)!={str(i)for i in range(len(rows))}:raise ValueError('TV message coverage differs')
        for i,message in enumerate(rows):
            old=''.join(tokenize(message));new=mapping[str(i)]
            for pattern in [r'#[0-9]{2}',r'<[家ＡＢ１２＋－十字！]+>']:
                if sorted(re.findall(pattern,old))!=sorted(re.findall(pattern,new)):raise ValueError('TV substitution tag differs: '+name+'/'+str(i))
        archive=ChannelArchive(archive.replace(name,changed));counts[name]=count
    content=archive.compact();manual_record=None
    if args.revision>=3:
        from kwce.tvguide_manual import korean_manual
        content,manual_record=korean_manual(content)
    title.set_content(content,7)
    from kwce.channel_korean_font import korean_shared_fonts
    fonts,font_record=korean_shared_fonts();title.set_content(fonts,8)
    from kwce.opera_font import korean_opera_font
    fonts,opera_record=korean_opera_font(original[3]);title.set_content(fonts,3)
    from kwce.home_menu import korean_home_menu,KOREAN_SHARED,SOURCES
    home,home_record=korean_home_menu(original[4],fix_dialogs=True,all_dialog_languages=True)
    home=ChannelArchive(home);korean=ChannelArchive(KOREAN_SHARED.read_bytes())
    for folder,path in SOURCES.items():home=ChannelArchive(home.replace(folder+'/LZ77_homeBtn.arc',korean.get(path)))
    title.set_content(home.compact(),4)
    banner_record=None;banner=original[0]
    if args.revision>=6:
        from kwce.tvguide_banner import korean_banner
        banner,banner_record=korean_banner(banner,mask_channels=args.revision>=7)
    banner=bytearray(banner)
    if banner[0x80:0x84]!=b'IMET':raise ValueError('TV banner IMET')
    for i in range(10):
        text='TV 가이드 채널'.encode('utf-16-be');at=0x40+0x5c+84*i;banner[at:at+84]=text+bytes(84-len(text))
    banner[0x630:0x640]=bytes(16);banner[0x630:0x640]=hashlib.md5(banner[0x40:0x640]).digest();title.set_content(bytes(banner),0);title.tmd.region=4
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(14)if check.get_content_by_index(i)!=original[i]]
    if changed!=[0,1,3,4,7,8]:raise ValueError('Unexpected TV content change')
    out.mkdir(parents=True);(out/'tvguide-ko-local-test.wad').write_bytes(wad)
    result=dict(revision=args.revision,title_id=title.tmd.title_id,boot_index=13,wad_sha256=hashlib.sha256(wad).hexdigest(),source_sha256=config['source_sha256'],changed_contents=changed,translated_bmg_slots=sum(counts.values()),bmg_files=counts,executable=record,korean_home=home_record,shared_fonts=font_record,opera_font=opera_record,full_localization_complete=False,hardware_success_verified=False,local_only=True)
    if manual_record is not None:result['manual']=manual_record
    if banner_record is not None:result['banner_textures']=banner_record
    (out/'build-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if expected is not None and expected!=wad:raise ValueError('TV reproduction differs')
    print('Reproduced byte-identically'if expected is not None else'Built','TV Guide revision',args.revision,': BMG',sum(counts.values()),'wide literals',record['translated_literals'],'local endpoints',record['local_endpoints'])
if __name__=='__main__':main()
