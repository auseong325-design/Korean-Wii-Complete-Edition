"""New stopped project NAND + synthetic local Room replies; no online service."""
import ast,configparser,json,shutil,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,tostring
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_votes_local_settings import records
from prepare_gc_v6 import snapshot
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.wiiroom_feed import xml_response

PROFILE='wiiroom-test-v1-user'
TITLE='000100014843494a'

def register():
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/wiiroom-test-v1'
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)
    return PROFILE

def fixtures(feed,video=None,guest=False):
    if feed.exists():raise SystemExit('Existing Room fixture preserved')
    feed.mkdir();ref=ROOT/'external/channel-tools/WiiRoom-reference/first.py'
    lock=json.loads((ROOT/'configs/wiiroom-server-references.lock.json').read_text())
    rows=lock.get('files',[])
    row=next(r for r in rows if r.get('path',r.get('file'))=='first.py')
    if sha256(ref)!=row['sha256']:raise ValueError('Pinned first protocol reference changed')
    tree=ast.parse(ref.read_text(encoding='utf-8'));constants={};fields={}
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign):
            for target in n.targets:
                if isinstance(target,ast.Name)and target.id in ('FIRST_BIN_KEY','FIRST_BIN_IV'):constants[target.id]=ast.literal_eval(n.value)
        if isinstance(n,ast.Dict):
            for k,v in zip(n.keys,n.values):
                if isinstance(k,ast.Constant)and k.value in ('shopkey','smpkey'):
                    try:fields[k.value]=ast.literal_eval(v)
                    except(ValueError,TypeError):pass
    if set(constants)!={'FIRST_BIN_KEY','FIRST_BIN_IV'}or set(fields)!={'shopkey','smpkey'}:raise ValueError('Protocol constants unavailable')
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad,unpad
    now=datetime.now(timezone.utc).replace(tzinfo=None);stamp=now.strftime('%Y-%m-%dT%H:%M:%S');routes=[]
    xml=xml_response
    def save(route,name,payload):
        (feed/name).write_bytes(payload);routes.append(('* '+route,name))
    config=dict(maint=0,url1='http://127.0.0.2/url1/',url2='http://127.0.0.2/url2/',url3='http://127.0.0.2/url3/',eulaver=3,shopurl='http://127.0.0.2/shop/index.esf',shopkey=fields['shopkey'],shopvalid=1,akahost=5,akaca=1,smpkey=fields['smpkey'],fmax=30,bmax=10,upddt=stamp)
    # Keep the reference availability flag for parser compatibility; the shop
    # points only to our container and has no ordering/payment route.
    plain=xml('Config',config);encrypted=AES.new(constants['FIRST_BIN_KEY'],AES.MODE_CBC,iv=constants['FIRST_BIN_IV']).encrypt(pad(plain,16))
    if unpad(AES.new(constants['FIRST_BIN_KEY'],AES.MODE_CBC,iv=constants['FIRST_BIN_IV']).decrypt(encrypted),16)!=plain:raise ValueError('First config roundtrip')
    save('/conf/first.bin','first.bin',encrypted)
    save('/url1/conf/eula.xml','eula.xml',xml('LicenseAgree',dict(agree='Wii의 방 로컬 테스트 안내\n이 테스트는 PC 안의 예시 응답만 사용합니다.\n외부 등록·전송·주문은 제공하지 않습니다.\n한국어 번역과 내부 화면 검수는 진행 중입니다.')))
    save('/url2/reginfo.cgi','region.xml',xml('RegionInfo',dict(sdt=stamp,cdt=(now+timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%S'),limited=0)))
    save('/url1/conf/datetime.xml','datetime.xml',xml('DateTime',dict(upddt=stamp)))
    save('/url2/miiinfo.cgi','miiinfo.xml',xml('MiiInfo',dict(code=0,msg='LOCAL TEST')))
    intro=dict(seq=1,cntid=1,cnttype=1,dispsec=5,dimg=1,random=0,linktype=0)
    event=dict(date=now.strftime('%Y-%m-%d'),frameid=1000001,color='000000',postertime=5,adinfo=(dict(pref=2,adid=1),dict(pref=1,adid=1)),posterinfo=[dict(seq=1,posterid=1)],introinfo=[intro],newsinfo=[dict(page=1,news='한국어 로컬 테스트입니다. 동영상·주문·외부 등록은 아직 제공하지 않습니다.')])
    if video:event['newsinfo']=[dict(page=1,news='한국어 예시 영상과 방을\n살펴보세요.\n\n외부 등록이나 전송은\n이루어지지 않습니다.')]
    save('/url1/event/today.xml','event.xml',xml('Event',event))
    # Colours are parsed as 6-digit RRGGBB; a short value is parser error 20 (354120).
    save('/url1/special/all.xml','special.xml',xml('SpPageList',dict(pageinfo=[dict(sppageid=1,name='로컬 예시',level=1,miiid=1,color1='F08080',color2='80C0F0',logo1id='g1234',news='로컬 테스트입니다.',valid=int(guest),pref='1'*47)],upddt=stamp)))
    if guest:
        from kwce.wiiroom_guest import add_guest_fixtures
        add_guest_fixtures(save,stamp,(now+timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%S'))
    # The theatre schema needs at least two posters; categid is 5-7 characters.
    save('/url3/pay/event/today.xml','theatre-event.xml',xml('Event',dict(date=now.strftime('%Y-%m-%d'),postertime=5,posterinfo=[dict(seq=1,posterid=1,geofilter=0),dict(seq=2,posterid=2,geofilter=0)],introinfo=intro)))
    save('/url1/conf2/paylink.xml','theatre-link.xml',xml('MovieLink',dict(linkinfo=dict(movieid=1,categid='11111'))))
    movies=[dict(rank=i,movieid=i,title=label,genre=i,strdt=stamp,pop=0)for i,label in enumerate(['한국어 서비스 화면 예시','영상 재생 준비 안내'],1)]
    save('/url1/list/new/all.xml','new.xml',xml('New',dict(movieinfo=movies)))
    save('/url1/list/category/search/10001','category-search.xml',xml('SearchMovies',dict(num=1,categid=10001,movieinfo=movies)))
    movie_hashes={1:'c4',2:'c8'}  # observed client hash directories for these synthetic ids
    for i,label in enumerate(['한국어 서비스 화면 예시','영상 재생 준비 안내'],1):
        save(f'/url1/movie/{movie_hashes[i]}/{i}.met',f'movie-{i}.xml',xml('MovieMeta',dict(movieid=i,title=label,len='00:00:10'if video else'00:00:05',aspect=1,genre=i,sppageid=int(guest),dsdist=0,staff=0)))
    if video:
        payload=video.read_bytes()
        if payload[:4]!=b'MOC5'or b'KI'not in payload:raise ValueError('Invalid own MOC5 fixture')
        save('/url1/movie/c4/1.mov','sample.mov',payload)
        routes.append(('* /url1/movie/c8/2.mov','sample.mov'))
        for mid,hsh in movie_hashes.items():
            for quality in ('L','H'):routes.append((f'* /url1/movie/{hsh}/{mid}-{quality}.mov','sample.mov'))
    for genre in range(10):
        save(f'/url3/pay/list/category/{genre}.xml',f'theatre-category-{genre}.xml',xml('PayCategoryList',dict(type=genre,img=0,categinfo=[dict(place=1,categid='11111',name='작품 안내 예시')])) )
    # Requested right after entering the room. The beacon is analytics on the public
    # server, which only answers a fixed code; nothing is recorded here either.
    save('/url1/beacon/1','beacon.xml',xml('SampleRequest',dict(code=1,msg='local')))
    save('/url3/pay/list/category/header.xml','theatre-header.xml',xml('PayCategoryHeader',dict(img=0,listinfo=[dict(place=1,type=10,text='예시 분류')])))
    # Own synthetic still image; the public server uses baseline 4:2:0 JPEG
    # under an .img extension. No programme, poster or personal photo is used.
    from PIL import Image,ImageDraw,ImageFont
    import io
    pic=Image.new('RGB',(832,456),(20,48,73));draw=ImageDraw.Draw(pic);font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',48);small=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',26)
    draw.text((70,100),'Wii의 방 · 로컬 테스트',font=font,fill=(255,255,255));draw.text((72,220),'PC 안에서 재생하는 예시 화면입니다.',font=small,fill=(188,226,241));draw.text((72,275),'외부 등록 · 주문 · 동영상 전송 없음',font=small,fill=(188,226,241));encoded=io.BytesIO();pic.save(encoded,'JPEG',subsampling=2,progressive=False)
    save('/url1/intro/1-1.img','intro.jpg',encoded.getvalue());routes.append(('* /url3/pay/intro/1-1.img','intro.jpg'))
    poster=pic.resize((256,360));encoded=io.BytesIO();poster.save(encoded,'JPEG',subsampling=2,progressive=False)
    save('/url1/wall/1.img','poster.jpg',encoded.getvalue());routes.append(('* /url3/pay/wall/1.img','poster.jpg'))
    # Programme list thumbnails use the 160x120 category image, not wall posters.
    for i in(1,2):routes.append((f'* /url1/movie/{movie_hashes[i]}/{i}.img','category-10001.jpg'))
    # Wall images are size-checked per kind (channel table at 0x806d5a10): posters
    # are 256x360 and the frame (event frameid; the access log masks 6+ digit
    # numbers as "ID") is 256x96.
    banner=Image.new('RGB',(256,96),(20,48,73));draw=ImageDraw.Draw(banner);draw.text((14,12),'Wii의 방',font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',30),fill=(255,255,255));draw.text((16,56),'로컬 테스트 안내',font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',20),fill=(188,226,241))
    encoded=io.BytesIO();banner.save(encoded,'JPEG',subsampling=2,progressive=False);save('/url1/wall/1000001.img','banner.jpg',encoded.getvalue())
    # Room category lists: 01 all, 02 concierge Miis, 03 rooms (5-digit category ids).
    for n,(cid,label) in enumerate([(10001,'예시 분류'),(20001,'예시 안내원'),(30001,'예시 방')],1):
        save(f'/url1/list/category/{n:02d}.xml',f'category-{n}.xml',xml('CategoryList',dict(type=3,categinfo=[dict(place=1,categid=cid,name=label,sppageid=0,splinktext=label)])))
        thumb=Image.new('RGB',(160,120),(20,48,73));ImageDraw.Draw(thumb).text((12,44),label,font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',22),fill=(255,255,255))
        encoded=io.BytesIO();thumb.save(encoded,'JPEG',subsampling=2,progressive=False);save(f'/url1/list/category/img/{cid}.img',f'category-{cid}.jpg',encoded.getvalue())
    save('/url1/wall/1.met','poster.xml',xml('PosterMeta',dict(posterid=1,msg='한국어 로컬 테스트',movieid=1,title='예시 안내')))
    routes.append(('* /url3/pay/wall/2.img','poster.jpg'))
    for n in(1,2):save(f'/url3/pay/wall/{n}.met',f'theatre-poster-{n}.xml',xml('PosterMeta',dict(posterid=n,msg='한국어 로컬 테스트',movieid=n,title='예시 안내',type=0)))
    for delta in range(-7,15):
        day=now+timedelta(days=delta);infos=[]
        for i in range(7):
            d=day+timedelta(days=i);infos.append(dict(date=d.strftime('%Y-%m-%d'),wday=(d.weekday()+1)%7,holiday=0,thead=0))
        save('/url1/cal/'+day.strftime('%Y%m%d')+'.xml','calendar-'+str(delta+7)+'.xml',xml('Calendar',dict(dayinfo=infos)))
    # Check the XML replies against the channel's own schema files (content 2, xml/*.bin).
    from kwce.channels import ChannelArchive
    from kwce.wiiroom_schema import tree,problems
    title=load_library().title.Title();title.load_wad((ROOT/'workspace/channels/wiiroom/originals/wiiroom-japan-v1025.wad').read_bytes())
    content=title.get_content_by_index(2);schemas=ChannelArchive(content[content.find(b'U\xaa8-'):])
    checked={'event.xml':'Event','special.xml':'SpPageList','theatre-event.xml':'PayEvent','theatre-link.xml':'MovieLink','eula.xml':'LicenseAgree','region.xml':'RegionInfo','miiinfo.xml':'MiiInfo','poster.xml':'PosterMeta','theatre-poster-1.xml':'PayPosterMeta','theatre-poster-2.xml':'PayPosterMeta','new.xml':'AllNewMovies','beacon.xml':'SampleRequest','theatre-header.xml':'PayCategoryHeader','category-1.xml':'CategoryList','category-2.xml':'CategoryList','category-3.xml':'CategoryList'}
    checked.update({'category-search.xml':'SearchMovies','movie-1.xml':'MovieMeta','movie-2.xml':'MovieMeta'})
    if guest:checked.update({'room-page.xml':'SpPage','room-binary.xml':'SpPageBin','synthetic-guide.xml':'ConciergeMii'})
    checked.update({f'theatre-category-{i}.xml':'PayCategoryList'for i in range(10)})
    for name,schema in checked.items():
        found=problems((feed/name).read_bytes(),tree(schemas.get(f'xml/{schema}.bin')))
        if found:raise ValueError(f'{name} does not match the Room schema: {found}')
    if len({a for a,b in routes})!=len(routes):raise ValueError('Duplicate Room routes')
    for route,name in routes:
        target=feed/name
        if not target.resolve().is_relative_to(feed.resolve())or not target.is_file():raise ValueError('Missing/unsafe Room route payload')
    (feed/'routes.tsv').write_text('\n'.join(a+'\t'+b for a,b in routes)+'\n',encoding='ascii')
    metadata=dict(local_only=True,synthetic=True,external_registration=False,commerce=False,media_playback=video is not None,synthetic_room=guest,reference_commit=lock.get('commit'),created_utc=stamp,files=[dict(path=p.name,size=p.stat().st_size,sha256=sha256(p))for p in sorted(feed.iterdir())if p.is_file()])
    (feed/'fixture-manifest.json').write_text(json.dumps(metadata,indent=2))
    return len(routes)

def main():
    stopped();lib=load_library();target=ROOT/'workspace/sandbox/wiiroom-test-v1';source=ROOT/'workspace/sandbox/gc-v6';runtime=ROOT/'workspace/sandbox/votes-test-v1'
    if target.exists():raise SystemExit('Existing Wii Room profile preserved')
    wad=ROOT/'workspace/channels/wiiroom/build-v1/wiiroom-ko-local-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Room WAD differs')
    before=snapshot(source);manifest=PRIVATE/'gc-v6-before-wiiroom-v1.json'
    if manifest.exists():raise SystemExit('Existing original preservation manifest kept')
    manifest.write_text(json.dumps(before,indent=2))
    shutil.copytree(source/'user',target/'user',ignore=shutil.ignore_patterns('Logs','ScreenShots','Cache','StateSaves'))
    shutil.copytree(runtime/'Dolphin-x64',target/'Dolphin-x64');shutil.copy2(runtime/'NetProbe.exe',target/'NetProbe.exe')
    user=target/'user';ini=user/'Config/Dolphin.ini';cfg=configparser.ConfigParser(strict=False);cfg.optionxform=str;cfg.read(ini,encoding='utf-8-sig')
    for section in cfg.sections():
        for key,value in list(cfg[section].items()):cfg[section][key]=value.replace(str(source),str(target))
    cfg['Core']['DefaultISO']='';cfg['Core']['EnableWiiLink']='False';cfg['Core']['OverrideRegionSettings']='True'
    with ini.open('w',encoding='utf-8')as stream:cfg.write(stream)
    import re
    path=user/'Config/WiimoteNew.ini';controls=path.read_text(encoding='utf-8-sig');controls=re.sub(r'^Buttons/A\s*=.*$','Buttons/A = `Click 0` | pulse(`Click 0`, 0.25)',controls,flags=re.M);controls=re.sub(r'^Buttons/Home\s*=.*$','Buttons/Home = RETURN | `Click 2`',controls,flags=re.M)
    controls=re.sub(r'^(Shake/[XYZ])\s*=.*$',r'\1 =',controls,flags=re.M);path.write_text(controls,encoding='utf-8')
    reference=ROOT/'workspace/sandbox/news-v1/user/Wii';path=user/'Wii/shared2/sys/SYSCONF';data=bytearray(path.read_bytes());ref=(reference/'shared2/sys/SYSCONF').read_bytes();a,b=records(data),records(ref)
    for key in ['IPL.INC','NET.WCFG','IPL.IDL']:
        start,end,kind=a[key];left,right,other=b[key]
        if(end-start,kind)!=(right-left,other):raise ValueError('Settings type differs')
        data[start:end]=ref[left:right]
    path.write_bytes(data);shutil.copy2(reference/'shared2/sys/net/02/config.dat',user/'Wii/shared2/sys/net/02/config.dat')
    title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(user/'Wii').install_title(title)
    register();launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    count=fixtures(target/'local-feed')
    if snapshot(source)!=before:raise ValueError('Preserved GC v6 changed')
    result=dict(profile=PROFILE,title_id=TITLE,installed_wad_sha256=sha256(wad),runtime_sha256=sha256(target/'Dolphin-x64/Dolphin.exe'),probe_sha256=sha256(target/'NetProbe.exe'),preserved_gc_files=len(before),fixture_routes=count,capability_count=0,local_only=True)
    (target/'preparation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
