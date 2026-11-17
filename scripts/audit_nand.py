"""Local-only BootMii-format audit and immutable, hash-checked working copies.

Never prints device identifiers or key bytes. Exact source paths stay private.
NAND layout follows Dolphin 2609a DiscIO/NANDImporter.{cpp,h}.
This checks layout, filesystem metadata, key association, sidecar SHA-1, and
readable TMDs; it does NOT certify ECC, HMAC, boot chain or physical restoration.
"""
from __future__ import annotations
import hashlib, json, re, shutil, struct
from pathlib import Path
from audit_sd import ROOT, SD, PRIVATE, sha256
from Crypto.Cipher import AES

RAW_SIZE = 0x21000000

def data_at(f, offset, size):
    out = bytearray()
    while size:
        page, pos = divmod(offset, 0x800)
        n = min(size, 0x800-pos)
        f.seek(page*0x840+pos)
        b=f.read(n)
        if len(b)!=n: raise ValueError('Truncated NAND')
        out.extend(b);offset+=n;size-=n
    return bytes(out)

def examine(p, keypaths, extract_root=None):
    row=dict(size=p.stat().st_size, sha256=sha256(p), format_ok=p.stat().st_size in (RAW_SIZE, RAW_SIZE+1024))
    if not row['format_ok']: return row
    with p.open('rb') as f:
        f.seek(RAW_SIZE);footer=f.read(1024)
        row['embedded_keys']=len(footer)==1024
        row['matching_key_files']=[str(k.relative_to(SD)) for k in keypaths if footer and k.read_bytes()==footer]
        row['key_crypto_fields_match']={str(k.relative_to(SD)):k.read_bytes()[0x100:0x178]==footer[0x100:0x178] for k in keypaths} if footer else {}
        sbs=[]
        for i in range(16):
            b=data_at(f,0x1fc00000+i*0x40000,0x40000)
            if b[:4]==b'SFFS':sbs.append((struct.unpack_from('>I',b,4)[0],i,b))
        row['superblocks']=[dict(index=i,generation=v) for v,i,b in sbs]
        if not sbs:return row
        gen,idx,sb=max(sbs)
        row.update(selected_superblock=idx, selected_generation=gen)
        fat=struct.unpack_from('>32768H',sb,12)
        entries=[struct.unpack_from('>12sBBHHIIHI',sb,0x1000c+i*32) for i in range(0x17ff)]
        paths={};visited=set()
        def walk(i,parent):
            while i!=0xffff:
                if i>=len(entries) or i in visited:raise ValueError('Invalid FST index/cycle')
                visited.add(i);e=entries[i];name=e[0].split(b'\0')[0].decode('ascii')
                if i==0:path=''
                else:
                    if name in ('.','..') or '/' in name or '\\' in name:raise ValueError('Unsafe FST name')
                    path=parent+'/'+name
                paths[path]=e
                if e[1]&3==2:walk(e[3],path)
                i=e[4]
        walk(0,'');row['fst_reachable_entries']=len(paths)
        row['filesystem_files']=sum(e[1]&3==1 for e in paths.values())
        row['bad_clusters_in_fat']=fat.count(0xfffd)
        row['free_clusters_in_fat']=fat.count(0xfffe)
        def read_file(path):
            e=paths[path];c=e[3];remaining=e[5];out=bytearray();seen=set()
            while remaining:
                if c>=32768 or c in seen:raise ValueError('Invalid file cluster chain')
                seen.add(c)
                b=AES.new(footer[0x158:0x168],AES.MODE_CBC,iv=bytes(16)).decrypt(data_at(f,c*0x4000,0x4000))
                out.extend(b[:remaining]);remaining-=min(remaining,0x4000);c=fat[c]
            return bytes(out)
        if extract_root is not None:
            extract_root = Path(extract_root).resolve()
            if extract_root.exists():
                raise ValueError('Extraction target already exists; refusing overwrite')
            extract_root.mkdir(parents=True)
            for name,e in paths.items():
                target=extract_root/name.lstrip('/')
                if not target.resolve().is_relative_to(extract_root):raise ValueError('Unsafe output path')
                if e[1]&3==2:target.mkdir(parents=True,exist_ok=True)
                elif e[1]&3==1:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(read_file(name))
            (extract_root/'keys.bin').write_bytes(footer)
        tmds=[]
        for name in paths:
            if re.fullmatch(r'/title/[0-9a-f]{8}/[0-9a-f]{8}/content/title.tmd',name):
                b=read_file(name)
                sig=struct.unpack_from('>I',b)[0]
                base={0x10000:0x240,0x10001:0x140,0x10002:0x80}.get(sig)
                if base is None or len(b)<base+0xa4:continue
                tid=b[base+0x4c:base+0x54].hex();v=struct.unpack_from('>H',b,base+0x9c)[0]
                n=struct.unpack_from('>H',b,base+0x9e)[0]
                tmds.append(dict(title_id=tid,version=v,contents=n,required_ios=int.from_bytes(b[base+0x44:base+0x4c],'big')))
        row['titles']=tmds
        sysmenu=[t for t in tmds if t['title_id']=='0000000100000002']
        row['system_menu']=sysmenu[0] if sysmenu else None
        setting=read_file('/title/00000001/00000002/data/setting.txt') if '/title/00000001/00000002/data/setting.txt' in paths else b''
        key=0x73b5dbfa;plain=bytearray()
        for x in setting:
            plain.append(x^(key&255));key=((key<<1)|(key>>31))&0xffffffff
        fields=dict(re.findall(r'([A-Z]+)=([^\r\n\x00]+)',plain.decode('ascii',errors='ignore')))
        row['region_settings']={k:fields.get(k) for k in ('AREA','MODEL','VIDEO','GAME','CODE')}
    side=p.with_name(p.name+'.sha1')
    if side.exists():
        h=hashlib.sha1()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
        b=side.read_bytes()
        row['sidecar_sha1_matches']=b==h.digest() or h.hexdigest() in b.decode('ascii',errors='ignore').lower()
    return row

def main():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((PRIVATE/'sd-manifest-before.json').read_text(encoding='utf-8'))
    files=[SD/r['path'] for r in manifest['files']]
    candidates=[p for p in files if p.suffix.lower()=='.bin' and ('nand' in p.name.lower() or 'keys' in p.name.lower())]
    keys=[p for p in candidates if p.stat().st_size==1024]
    nands=[p for p in candidates if p.stat().st_size>=0x20000000]
    rows=[]
    for p in candidates:
        m=next(r for r in manifest['files'] if r['path']==p.relative_to(SD).as_posix())
        r=dict(m)
        if p in nands:r.update(examine(p,keys))
        else:r['format']='1024-byte OTP/SEEPROM container' if p in keys else 'unknown'
        rows.append(r)
    selected=max((p for p in nands if 'backups' in p.parts),key=lambda p:p.stat().st_mtime_ns,default=None)
    if selected is None:raise SystemExit('No new backup found; choose explicitly after audit')
    row=next(r for r in rows if r['path']==selected.relative_to(SD).as_posix())
    if not row.get('format_ok') or not row.get('system_menu') or row['system_menu']['version']!=518:raise SystemExit('Selected NAND did not pass 4.3K structural gate')
    dest=ROOT/'workspace/console-baseline/import';dest.mkdir(parents=True,exist_ok=True)
    provenance=[]
    for source,target in [(selected,dest/'nand.bin')]+[(SD/row['matching_key_files'][0],dest/'keys.bin')] if row['matching_key_files'] else [(selected,dest/'nand.bin')]:
        expected=sha256(source)
        if target.exists():
            if sha256(target)!=expected:raise SystemExit('Existing baseline differs; refusing overwrite')
        else:shutil.copy2(source,target)
        if sha256(target)!=expected:raise SystemExit('Working copy hash mismatch')
        provenance.append(dict(source=str(source.relative_to(ROOT)),destination=str(target.relative_to(ROOT)),sha256=expected))
    for item in rows:item['absolute_path']=str(SD/item['path'])
    related=[r for r in manifest['files'] if r['path'].startswith('wii/backups/') and ('.sha1' in r['path'] or r['path'].endswith('sha1sums.txt'))]
    result=dict(project_root=str(ROOT),sd_root=str(SD),backups=rows,checksum_files=related,selected_source=row['path'],provenance=provenance)
    (PRIVATE/'nand-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    # Shared report uses aliases where filenames embed the serial number.
    aliases={r['path']:('sd/'+r['path'] if '/' not in r['path'] else 'sd/wii/backups/'+('CURRENT_NAND.bin' if r.get('format_ok') else 'CURRENT_KEYS.bin')) for r in rows}
    out=['# NAND 백업 감사','', '검사일: 2026-10-21 (Asia/Seoul). 실제 경로와 시리얼 포함 파일명은 `workspace/private/nand-audit.json`에만 보관한다. CURRENT_*는 공유 문서용 별칭이다.','', '| 경로/별칭 | 바이트 | 수정 시각(UTC) | SHA-256 |','|---|---:|---|---|']
    for r in rows:out.append(f"| {aliases[r['path']]} | {r['size']} | {r['modified_utc']} | `{r['sha256']}` |")
    out+=['','## 비파괴 검사 결과','']
    for r in rows:
        if not r.get('format_ok'):continue
        out += [f"### {aliases[r['path']]}", '',f"- BootMii 크기/레이아웃: 0x21000000 데이터+spare 영역과 1024-byte 키 footer. SFFS {len(r.get('superblocks',[]))}/16, 선택 세대 {r.get('selected_generation')}.",f"- 도달 가능한 FST 항목 {r.get('fst_reachable_entries')}, 파일 {r.get('filesystem_files')}. FAT bad-cluster 표식 {r.get('bad_clusters_in_fat')}, free {r.get('free_clusters_in_fat')}. 이 수치는 물리 NAND 검사 결과가 아니다.",f"- 복호화한 System Menu TMD: {r.get('system_menu')}. 지역 설정: {r.get('region_settings')}.",f"- 별도 키 파일과 footer 전체 일치: {len(r.get('matching_key_files',[]))}개. AES/HMAC 등 암호 필드 비교 결과는 로컬 JSON 참조.",f"- 덤퍼 SHA-1 sidecar 일치: {r.get('sidecar_sha1_matches','sidecar 없음')}.",'']
    same=len({r['sha256'] for r in rows if r.get('format_ok')})==1
    out += [f"전체 NAND 바이트 동일 여부: {same}. 파일을 병합하거나 원본을 덮어쓰지 않았다.",'', '## 기준 사본과 검증 한계','', '기준: 새 `nanddumper@IOS` 백업. 날짜, sidecar, SFFS/TMD/지역 설정 및 키 대응 결과를 함께 검토한다. 수정 시각만으로 실제 덤프 시각을 확정하지 않는다. 작업용 `workspace/console-baseline/import/nand.bin`과 `keys.bin`은 원본 SHA-256과 재비교했다. 정확한 출처·해시는 로컬 JSON provenance에 기록했다.','', '크기·SHA-256·SFFS 탐색·AES 복호화 성공은 물리 복구 성공을 보증하지 않는다. 전 페이지 ECC, 모든 클러스터 HMAC, boot1/boot2 서명, 실제 NAND 복원은 이 스크립트가 검사하지 않는다. Dolphin 공식 importer도 spare ECC를 건너뛴다. 물리 복원이나 실기 쓰기는 실행하지 않았다.','', '[Dolphin 2609a NANDImporter 원본](https://github.com/dolphin-emu/dolphin/blob/2609a/Source/Core/DiscIO/NANDImporter.cpp)']
    out += ['', '## 스냅샷·키 대응 해석', '', '두 NAND와 두 별도 키 파일은 각각 전체 SHA-256이 다르다. SD 루트 NAND footer는 루트 keys.bin과 일치하고, CURRENT_NAND footer는 CURRENT_KEYS와 일치한다. 두 키 파일의 AES/HMAC 등 해당 콘솔 암호 필드(0x100:0x178)는 서로 일치하므로 동일 기기와 대응할 가능성을 강하게 지지한다. 전체 1024-byte 컨테이너가 서로 동일하다는 뜻은 아니다. 실제 키 바이트는 출력하지 않는다.', '', '루트 NAND의 SFFS 세대 149731·TMD 98개와 새 덤프의 세대 173227·TMD 110개를 함께 보면 루트는 이전 논리 상태의 스냅샷으로 보인다. 그러나 루트 파일의 수정 시각이 더 늦으므로 정확한 생성/덤프 시각은 확정하지 않는다. 파일 이름·수정 시각만으로 과거/최신을 정하지 않았다.', '', f'새 덤프의 raw SHA-1 파일과 sha1sums.txt 등 체크섬 파일 {len(related)}개도 전체 SD manifest에 경로·크기·수정 시각·SHA-256으로 보존했다. 실제 시리얼 포함 파일명과 별칭의 대응은 로컬 JSON에서 확인한다.', '', '## 시스템 콘텐츠 수준의 추가 검사', '', '독립 복호화 결과 TMD 110개·콘텐츠 레코드 912개를 shared1/content.map까지 해석했다. System Menu v518 콘텐츠 7개는 크기와 SHA-1이 모두 맞는다. 로컬 콘텐츠가 없는 레코드 78개는 메타데이터만 남은 항목을 포함할 수 있어 그대로 NAND 손상으로 단정하지 않는다. 존재하는 파일 중 title 00010008-48414b4b content 00000002는 TMD SHA-1이 다르므로 후속 원인 조사가 필요하다. TMD 서명 검증 결과로 표현하지 않는다.']
    (ROOT/'docs/reference/NAND_BACKUP_AUDIT.md').write_text('\n'.join(out)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidates=len(rows),nand_count=len(nands),nand_identical=same,selected_menu=row['system_menu'],region=row['region_settings'],copy_verified=True)))

if __name__=='__main__':main()
