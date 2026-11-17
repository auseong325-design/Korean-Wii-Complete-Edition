"""Package the KWCE DVD player as a channel WAD (00010001-KDVD, fakesigned).

Contents: 0 banner (kwce.dvd_banner, System Menu disc channel art), 1 boot DOL
(workspace/channels/dvd-player/build-vN), 2 the local 43K Korean shared font
copy (read by the player via ES_OpenContent), 3 (with --home) the HOME Menu archive
(workspace/channels/dvd-player/home-ui-vN). TMD: IOS58, boot index 1,
region KOR, access rights 3 (bit0 = hardware access/AHBPROT, bit1 = DVD video:
ES enables DVD video reads when the title starts).
The ticket/TMD/certificate structure comes from a local channel WAD template;
no key material is printed. Output: a new workspace/channels/dvd-player/wad-vM.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_korean_font import korean_shared_fonts
from kwce.dvd_banner import dvd_player_content0
from kwce.dvd_disc_hook import DVD_TITLE

TEMPLATE=ROOT/'workspace/channels/mii-contest/originals/mii-contest-usa-wiilink-archive.wad'
RESOURCE=ROOT/'workspace/experiments/gc-native-v6/menu-resource.app'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',type=int,required=True);ap.add_argument('--revision',type=int,required=True)
    ap.add_argument('--home',type=int,help='HOME Menu archive revision (content 3); player builds from R2 need it');args=ap.parse_args()
    out=ROOT/f'workspace/channels/dvd-player/wad-v{args.revision}'
    if out.exists():raise SystemExit('Existing DVD player WAD preserved')
    build=ROOT/f'workspace/channels/dvd-player/build-v{args.build}'
    dol=(build/'boot.dol').read_bytes();manifest=json.loads((build/'build-manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(dol).hexdigest()!=manifest['boot_dol_sha256']:raise SystemExit('DOL differs from its build manifest')
    adapter=None
    if args.revision>=10:
        from kwce.dvd_channel_boot import channel_boot
        dol,adapter=channel_boot(dol)
    lib=load_library();title=lib.title.Title();title.load_wad(TEMPLATE.read_bytes())
    template0=title.get_content_by_index(0)
    banner,banner_record=dvd_player_content0(RESOURCE.read_bytes(),template0,args.revision)
    fonts,font_record=korean_shared_fonts()
    contents=[banner,dol,fonts];home_record=None
    if manifest['revision']>=2 and not args.home:raise SystemExit('Player R2+ needs --home')
    if args.home:
        home_dir=ROOT/f'workspace/channels/dvd-player/home-ui-v{args.home}';home=(home_dir/'home.arc').read_bytes()
        home_record=json.loads((home_dir/'home-ui-manifest.json').read_text(encoding='utf-8'))
        if hashlib.sha256(home).hexdigest()!=home_record['sha256']:raise SystemExit('HOME Menu archive differs from its manifest')
        contents.append(home)
    title.set_title_id(f'{DVD_TITLE:016X}')
    title.set_title_version(args.revision)
    keep=len(contents)  # reuse the template's first records, drop the rest
    if keep>len(title.content.content_records):raise SystemExit('Template WAD has too few content records')
    for i,data in enumerate(contents):title.set_content(data,i,cid=i,content_type=1)
    title.content.content_records=title.content.content_records[:keep];title.content.content_list=title.content.content_list[:keep]
    title.content.num_contents=keep;title.tmd.content_records=title.content.content_records;title.tmd.num_contents=keep
    title.tmd.ios_tid='000000010000003A';title.tmd.ios_version=58
    title.tmd.boot_index=1;title.tmd.region=4;title.tmd.access_rights=3;title.tmd.group_id=0x3031
    title.fakesign()
    wad=title.dump_wad()
    check=lib.title.Title();check.load_wad(wad)
    got=[check.get_content_by_index(i) for i in range(len(check.tmd.content_records))]
    if got!=contents or check.tmd.title_id.upper()!=f'{DVD_TITLE:016X}' or check.tmd.access_rights!=3 or check.tmd.boot_index!=1:
        raise SystemExit('WAD verification failed')
    if not check.get_is_fakesigned():raise SystemExit('Fakesign failed')
    out.mkdir(parents=True);(out/'dvd-player.wad').write_bytes(wad)
    record=dict(revision=args.revision,player_build=args.build,title_id=f'{DVD_TITLE:016x}',ios=58,access_rights=3,region='KOR',
                contents=['banner','boot.dol','korean shared font copy']+(['HOME Menu archive'] if args.home else []),home_ui=args.home,wad_sha256=hashlib.sha256(wad).hexdigest(),banner=banner_record,
                font=font_record,boot_adapter=adapter,css_decryption=manifest['css_decryption'],signed='fakesigned (cIOS/Trucha or Dolphin)',publish=False)
    (out/'wad-manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=1),encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('revision','player_build','title_id','wad_sha256')}))

if __name__=='__main__':main()
