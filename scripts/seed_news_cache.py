"""Replay public country-136 News files, locally translated, inside the isolated News NAND.

Host-only public HTTP download of news.wiilink.ca files; the emulator keeps zero
network capability. The KD envelope (320 bytes) is removed exactly as Dolphin's
KD does for signed, unencrypted downloads. Korean text is appended by
kwce.news_data; English article text is machine translated offline.
"""
import argparse,datetime,hashlib,json,re,shutil,struct,subprocess,sys,time,urllib.request
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from prepare_news import register
import launch_dolphin as launcher

URL='http://news.wiilink.ca/v2/1/136/news.bin.{:02d}'
CACHE=PRIVATE/'news-mt-cache.json'
FEED_URL=lambda user:((user.parent/'local-feed').resolve().as_uri()+'/v2/1/136/news.bin').encode()

def korean(texts):
    from kwce.forecast_data import forecast_mapping
    from kwce import local_mt
    config=json.loads((ROOT/'configs/news-data-ko.json').read_text(encoding='utf-8'));places=forecast_mapping()
    cache=json.loads(CACHE.read_text(encoding='utf-8'))if CACHE.exists()else{}
    result={};pending=[]
    for text in texts:
        if text in config['fixed']:result[text]=config['fixed'][text];continue
        if text in places:result[text]=places[text];continue
        for pattern,target in config['patterns']:
            if re.match(pattern,text):result[text]=re.sub(pattern,target,text);break
        else:
            if text.startswith('REUTERS/'):result[text]=text
            elif text in cache:result[text]=cache[text]
            else:pending.append(text)
    # Keep photo credits ("... REUTERS/Name/File Photo") in English after the translated caption.
    split=[];credits=[]
    for text in pending:
        at=text.find('REUTERS/')
        split.append(text[:at].rstrip()if at>0 else text);credits.append(' '+text[at:]if at>0 else'')
    if split:
        for text,body,credit in zip(pending,local_mt.translate(split),credits):cache[text]=body+credit;result[text]=cache[text]
    CACHE.write_text(json.dumps(cache,ensure_ascii=False,indent=0),encoding='utf-8')
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,required=True);ap.add_argument('--hours',type=int,default=24)
    ap.add_argument('--feed-only',action='store_true',help='prepare HTTP replay files; let Dolphin populate its VFF')
    ap.add_argument('--reuse-local',action='store_true',help='reuse the preserved, already translated legacy feed without downloading or translating')
    args=ap.parse_args()
    if args.reuse_local and not args.feed_only:raise SystemExit('--reuse-local requires --feed-only')
    if not 1<=args.attempt<=100 or not 1<=args.hours<=24:raise SystemExit('Invalid arguments')
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before seeding News')
    register();user=launcher.user_path('news-v1-user');data=user/'Wii/title/00010002/48414745/data'
    vff_path=data/'wc24dl.vff';dl_path=user/'Wii/shared2/wc24/nwc24dl.bin'
    backup=PRIVATE/f'news-before-replay-{args.attempt}'
    if backup.exists():raise SystemExit('Existing News replay snapshot preserved')
    from kwce.channels import load_library,compress_lz10
    from kwce.channel_vff import VFF,add_long
    from kwce.news_data import strings,localize
    from kwce.local_mt import model_record
    load_library();from libWiiPy.archive import decompress_lz77
    dl=bytearray(dl_path.read_bytes());index=None
    for i in range(120):
        e=dl[2048+512*i:2560+512*i]
        url=e[180:416].split(b'\0')[0]
        if set(struct.unpack_from('>II',e,8))=={0x00010002,0x48414745}and url in(b'http://news.wiilink.ca/v2/1/136/news.bin',FEED_URL(user)):index=i
    if index is None:raise SystemExit('Run News once so it registers its download task')
    entry=dl[2048+512*index:2560+512*index];name=entry[416:480].split(b'\0')[0].decode('ascii')
    if int.from_bytes(entry[4:8],'big')&8:raise SystemExit('Encrypted News task unsupported')
    backup.mkdir();shutil.copy2(vff_path,backup/'wc24dl.vff');shutil.copy2(dl_path,backup/'nwc24dl.bin')
    empty=PRIVATE/'news-empty-vff.bin'
    if not args.feed_only and not empty.exists():
        if VFF(vff_path.read_bytes()).entries():raise SystemExit('Expected the channel-created empty VFF on first seed')
        shutil.copy2(vff_path,empty)
    vff=None if args.feed_only else VFF(empty.read_bytes())
    hour=datetime.datetime.now(datetime.timezone.utc).hour;rows=[];raw_files={}
    for back in range(args.hours):
        h=(hour-back)%24
        if args.reuse_local:
            legacy=user.parent/'local-feed/v2/1/136'/f'news.bin.{h:02d}'
            raw=legacy.read_bytes()
        else:
            with urllib.request.urlopen(URL.format(h),timeout=30)as r:raw=r.read(8*1024*1024+1)
        if len(raw)<=320:raise ValueError('Missing News envelope')
        if len(raw)>8*1024*1024:raise ValueError('News download exceeds size bound')
        raw_files[h]=raw
    texts=set()
    for raw in raw_files.values():texts.update(t for _,_,_,t in strings(decompress_lz77(raw[320:]))if t.strip())
    mapping=None if args.reuse_local else korean(sorted(texts))
    feed=user.parent/'local-feed/news.wiilink.ca/v2/1/136'
    if args.feed_only and feed.exists():raise SystemExit('Existing HTTP feed preserved; select a fresh feed snapshot')
    feed.mkdir(parents=True,exist_ok=True)
    for n,(h,raw) in enumerate(raw_files.items()):
        if args.reuse_local:
            payload=decompress_lz77(raw[320:]);packed=raw[320:]
            record=dict(reused_local_translation=True,strings=len(strings(payload)),not_server_signed=True)
        else:
            payload,record=localize(decompress_lz77(raw[320:]),mapping);packed=compress_lz10(payload)
        if decompress_lz77(packed)!=payload:raise ValueError('News LZ10 roundtrip')
        if not args.feed_only:
            try:vff=VFF(add_long(vff,f'{name}.{h:02d}',packed,alias_index=n+1))
            except ValueError as error:
                if 'capacity'in str(error):break
                raise
        rows.append(dict(hour=h,source_sha256=hashlib.sha256(raw).hexdigest(),size=len(packed),**record))
        # The original public host is redirected to a server inside the same
        # capability-zero AppContainer. Keep the old file:// feed intact.
        (feed/f'news.bin.{h:02d}').write_bytes(raw[:320]+packed)
    now=int(time.time()//60);off=2048+512*index
    if args.feed_only:
        # Restore only the known News task from the obsolete file:// experiment.
        canonical=b'http://news.wiilink.ca/v2/1/136/news.bin'
        dl[off+180:off+416]=canonical+bytes(236-len(canonical))
        struct.pack_into('>I',dl,off+4,int.from_bytes(dl[off+4:off+8],'big')&~32)
    else:
        struct.pack_into('>I',dl,off+48,now);struct.pack_into('>i',dl,off+32,0);struct.pack_into('>H',dl,off+26,0)
        struct.pack_into('>II',dl,128+16*index+4,now+60,now)
        vff_path.write_bytes(vff.data)
    dl_path.write_bytes(dl)
    result=dict(profile='news-v1-user',task=index,vff_name=name,files=rows,translation=model_record(),strings=len(texts),feed_only=args.feed_only,reused_local=args.reuse_local,method='in-container HTTP replay, local offline MT; not live emulator service success')
    (user.parent/'local-feed/feed-manifest.json').write_text(json.dumps(dict(channel='news',host='news.wiilink.ca',files=[dict(path=p.relative_to(user.parent/'local-feed').as_posix(),sha256=sha256(p),size=p.stat().st_size)for p in sorted(feed.glob('news.bin.*'))],not_server_signed=True,machine_translation=True),indent=2))
    (PRIVATE/f'news-replay-{args.attempt}.json').write_text(json.dumps(result,indent=1));print(json.dumps(dict(task=index,files=len(rows),strings=len(texts))))
if __name__=='__main__':main()
