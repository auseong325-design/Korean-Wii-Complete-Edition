"""Swap the stopped local News feed to fictional Korean sample articles for manual captures.

Headlines and bodies become Korean renderings of the fictional examples shown in
the original USA manual pictures, and every article drops its picture, so manual
screenshots carry neither real news text nor news photos. Source names become an
example label without a logo; topics and locations stay as they are. `--restore` puts the preserved replay feed back.
Local Dolphin replay only; nothing is sent anywhere.
"""
import argparse,json,shutil,struct,sys,zlib
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.news_data import strings,localize,_header
from kwce.channels import load_library,compress_lz10

FEED=ROOT/'workspace/sandbox/news-v1/local-feed'
BACKUP=PRIVATE/'news-local-feed-before-manual-sample'
SAMPLES=[
 ('태평양 폭풍, 산간 지역에 반가운 눈 예보','강릉--태평양에서 발달한 강한 폭풍이 북쪽에서 내려오는 찬 공기와 만나 이번 겨울 첫 폭설을 뿌릴 것으로 보인다. 기상 당국은 주말까지 산간 지역에 최대 30센티미터의 눈이 내릴 수 있다고 밝혔다. 스키장들은 예년보다 일찍 문을 열 준비를 하고 있다.'),
 ('말하는 소를 보러 수천 명 몰려','한 시골 목장에 "말을 하는 소"가 있다는 소문이 퍼지면서 주말 동안 수천 명의 관람객이 몰렸다. 목장 주인은 소가 가끔 사람 이름을 부르는 것처럼 들린다고 말했다.'),
 ('유통업계, 연말 대목 매출 큰 폭 증가 기대','유통업계는 올해 연말 쇼핑 시즌 매출이 지난해보다 크게 늘어날 것으로 내다봤다. 특히 가전제품과 장난감 판매가 늘 것으로 보인다.'),
 ('기상 악화로 동해안 교통 대규모 지연','강한 눈보라로 동해안 일대의 도로와 철도 운행이 크게 늦어졌다. 당국은 불필요한 외출을 자제해 달라고 당부했다.'),
 ('영화계 부진 계속, 매출 제자리','올해 영화 관람객 수가 지난해와 비슷한 수준에 머물면서 영화계의 부진이 이어지고 있다.'),
 ('독감철 앞두고 백신 공급 안정','보건 당국은 독감 유행철을 앞두고 백신 공급이 안정적이라고 밝혔다. 예방 접종은 다음 달부터 시작된다.'),
 ('연료 소비 증가세 이어지나','겨울철 난방 수요가 늘면서 연료 소비가 계속 증가할 것이라는 전망이 나왔다.'),
]

def _example_logo(original):
    import io
    from PIL import Image,ImageDraw,ImageFont
    w,h=Image.open(io.BytesIO(original)).size;image=Image.new('RGB',(w,h),(255,255,255));draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(str(ROOT/'workspace/channels/forecast/references/NotoSansKR.ttf'),max(10,h*2//3))
    l,t,r,b=draw.textbbox((0,0),'예시',font=font);draw.text(((w-(r-l))/2-l,(h-(b-t))/2-t),'예시',font=font,fill=(110,110,110))
    out=io.BytesIO();image.save(out,'JPEG',quality=90);return out.getvalue()

def sample(data,offset=0):
    refs=strings(data);mapping={};n=offset
    for kind,_,_,text in refs:
        if not text.strip()or text in mapping:continue
        if kind=='headline':mapping[text]=SAMPLES[n%len(SAMPLES)][0];n+=1
        elif kind=='source':mapping[text]='예시'
        elif kind=='copyright':mapping[text]='예시 기사입니다.'
        else:mapping[text]=text
    # Bodies follow their own headline: pair them by article order.
    h=_header(data);out=bytearray(localize(data,mapping)[0])
    for i in range(h['articles']):
        base=h['article_table']+44*i;struct.pack_into('>I',out,base+16,0xffffffff)
    # The fictional samples are not attributed to a news agency: the required
    # source logo becomes a same-size plain baseline JPEG reading the example label.
    for i in range(h['sources']):
        base=h['source_table']+28*i;size,at=struct.unpack_from('>II',out,base+4)
        logo=_example_logo(bytes(out[at:at+size]))
        while len(out)%4:out+=b'\0'
        struct.pack_into('>II',out,base+4,len(logo),len(out));out+=logo
    body={}
    for i in range(h['articles']):
        base=h['article_table']+44*i;at,size=struct.unpack_from('>I',out,base+32)[0],struct.unpack_from('>I',out,base+28)[0]
        title=out[at:at+size].decode('utf-16-be');text=next(b for t,b in SAMPLES if t==title)
        if text not in body:
            while len(out)%4:out+=b'\0'
            body[text]=len(out);out+=text.encode('utf-16-be')+b'\0\0'
        struct.pack_into('>II',out,base+36,len(text.encode('utf-16-be')),body[text])
    while len(out)%4:out+=b'\0'
    struct.pack_into('>I',out,4,len(out));struct.pack_into('>I',out,8,zlib.crc32(out[12:])&0xffffffff)
    _header(bytes(out));return bytes(out),h['articles']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--restore',action='store_true');args=ap.parse_args()
    stopped();load_library()
    from libWiiPy.archive import decompress_lz77
    if args.restore:
        if not BACKUP.exists():raise SystemExit('No preserved replay feed')
        shutil.rmtree(FEED);shutil.copytree(BACKUP,FEED);print('restored preserved replay feed');return
    if BACKUP.exists():raise SystemExit('Sample feed already active; restore first')
    shutil.copytree(FEED,BACKUP)
    manifest=json.loads((FEED/'feed-manifest.json').read_text());total=0
    for hour,row in enumerate(manifest['files']):
        # Served files keep their 320-byte KD envelope; the payload is LZ10 news.bin.
        path=ROOT/'workspace/sandbox/news-v1/local-feed'/row['path'];raw=path.read_bytes()
        data,count=sample(decompress_lz77(raw[320:]),hour);total+=count;packed=compress_lz10(data)
        if decompress_lz77(packed)!=data:raise ValueError('News LZ10 roundtrip')
        path.write_bytes(raw[:320]+packed);row['sha256']=sha256(path);row['size']=len(raw)-len(raw[320:])+len(packed)
    manifest.update(manual_sample=True,fictional_articles=True,pictures_removed=True)
    (FEED/'feed-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(f'sample feed: {len(manifest["files"])} files, {total} articles, pictures removed')

if __name__=='__main__':main()
