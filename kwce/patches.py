"""Version-locked resource patch and opt-in GC detection experiment.

Resource offsets: NinjaCheetah/wii-menu-visual-patcher @6600fdf.
GC condition motif: DacoTaco/priiloader hacks_hash.ini, Region Free EVERYTHING.
Only the GC fallback li is changed; broad region-free/master hacks are excluded.
The executable prototype does not establish successful GC/BC/MIOS boot.
"""
import hashlib,struct,re
from .formats import U8,ash_decompress,ash_compress

LAYOUT_SHA256='7e7ba5309e8f58617caa344f7629adfa928d9f80e3ef2891d3f56fba13f72b2b'
MENU_SHA1='98496cc8467f0749d7605fc175b1911827aa1fd0'
LAYOUT='arc/blyt/my_DiskCh_a_R.brlyt'
ASH_PATH='layout/common/diskBann2.ash'
CHANGES={0xff6:0xc1,0x1104:5,0x12bc:5,0x147c:7,0x157c:7,0x1658:5,
         0x1890:5,0x1c88:5,0x1d90:5,0x1e9a:0xc1,0x226a:0xc1}

def patch_layout(data,expected_hash=LAYOUT_SHA256):
    if hashlib.sha256(data).hexdigest()!=expected_hash:raise ValueError('Unsupported/unrecognized 43K layout; no patch applied')
    if data[:4]!=b'RLYT' or len(data)<=max(CHANGES):raise ValueError('Invalid BRLYT')
    result=bytearray(data)
    for offset,value in CHANGES.items():result[offset]=value
    if {i for i,(a,b) in enumerate(zip(data,result)) if a!=b}!=set(CHANGES):raise ValueError('Unexpected layout byte changes')
    return bytes(result)

def patch_resources(data):
    outer=U8(data);ash=outer.get(ASH_PATH);inner_data=ash_decompress(ash);inner=U8(inner_data)
    patched=patch_layout(inner.get(LAYOUT));new_inner=inner.replace(LAYOUT,patched);new_ash=ash_compress(new_inner)
    if ash_decompress(new_ash)!=new_inner:raise ValueError('ASH round-trip failed')
    result=outer.replace(ASH_PATH,new_ash)
    new_outer=U8(result);verified_inner=U8(ash_decompress(new_outer.get(ASH_PATH)))
    if verified_inner.get(LAYOUT)!=patched:raise ValueError('Nested resource verification failed')
    return result,dict(feature='hidden GC/DVD disc visuals',layout_bytes_changed=len(CHANGES),
                       unrelated_outer_files_unchanged=len(outer.files)-1,unrelated_inner_files_unchanged=len(inner.files)-1,
                       ash_round_trip=True,original_ash_bytes=len(ash),patched_ash_bytes=len(new_ash))

def _gc_candidates(data):
    # DOLs may load executable bytes inside a data section. Map all 18 sections.
    if len(data)<256:raise ValueError('Truncated DOL')
    hits=[];motif=bytes.fromhex('380000002c0000004082001038000036')
    for i in range(18):
        off,addr,size=[struct.unpack_from('>I',data,p+4*i)[0] for p in (0,0x48,0x90)]
        if not size:continue
        if off<256 or off+size>len(data):raise ValueError('Invalid DOL section bounds')
        for match in re.finditer(re.escape(motif),data[off:off+size]):
            p=off+match.start();address=addr+p-off
            if not 0x8137c74c<=address<0x8137e59c or p%4:continue
            # GC branch sets BS2_STT_GC_GAME (0x32), unlike nearby Wii branch.
            if data[p+24:p+28]!=bytes.fromhex('38000032'):continue
            if data[p+16:p+18]!=bytes.fromhex('900d'):continue
            hits.append((p,address))
    return hits

def gc_detection_prototype(data):
    if hashlib.sha1(data).hexdigest()!=MENU_SHA1:raise ValueError('Prototype accepts only exact original 43K DOL')
    hits=_gc_candidates(data)
    if len(hits)!=1:raise ValueError('GC fallback motif is not unique')
    off,addr=hits[0];patched=bytearray(data)
    # li r0,0 -> li r0,1 changes only the fallback result, preserving all stores.
    struct.pack_into('>I',patched,off,0x38000001)
    if sum(a!=b for a,b in zip(data,patched))!=1:raise ValueError('Unexpected executable differences')
    return bytes(patched),dict(feature='experimental GC fallback acceptance',address=hex(addr),file_offset=off,
                               instruction='li r0,1',changed_bytes=1,actual_disc_detection_verified=False,
                               BC_MIOS_launch_verified=False,applied_to_profile=False)
