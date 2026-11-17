"""Channel banner/icon/sound for the KWCE DVD player, made from the System Menu's own
disc channel layout (diskBann2.ash: background, title bar, official DVD disc art).

Banner: the disc channel scene with only the DVD (centred), its reflection and
shadow, and "DVD 플레이어" in the title bar; banner_Start = the disc channel's
intro (my_DiskCh_a_R_Start), banner_Loop = its DiskLoop slowed to one turn per
6 s with every non-rotation track disabled. Icon: the same scene at tile size
with the channel name. Sound: the template's BNS header with silent ADPCM.
Nothing is drawn by hand; all pictures are the System Menu's textures.
"""
import hashlib,struct
from .formats import U8,ash_decompress
from .channels import layout_sections,rebuild_layout,replace_textbox,load_library,compress_lz10
from .u8_build import build_u8
from .disk_dvd_anim import ASH_PATH,LAYOUT,ANIM,_contents,DISABLED

TITLE='DVD 플레이어'
HIDE_BANNER=['N_Wii0','N_GC0','ShadeWii','ShadeGC','N_RefWii','N_RefGC','ShadeWii_00','N_Unknown','N_Ref0_00','W_Wii','W_GC','T_Comment0','T_Comment1']
CENTRE=['N_DVD0','N_RefDVD','SahdeDVD','W_DVD']
SPIN={('DVDDisk',0,b'RLPA'),('RefDVD',1,b'RLTS')}

def _edit_layout(layout,hide,texts,size=None,root_scale=None,show=(),font=None):
    sections=layout_sections(layout);seen=set()
    for i,s in enumerate(sections):
        kind=s[:4]
        if kind==b'lyt1' and size:
            s=bytearray(s);struct.pack_into('>ff',s,12,*size);sections[i]=bytes(s);continue
        if kind not in(b'pan1',b'pic1',b'txt1',b'wnd1',b'bnd1'):continue
        name=s[12:28].split(b'\0')[0].decode('ascii');s=bytearray(s)
        if name in hide:s[8]&=0xfe;seen.add(name)
        if name in show:s[8]|=1;s[10]=255;seen.add(name)
        if name in CENTRE:struct.pack_into('>f',s,0x24,0.0);seen.add(name)
        if name=='RootPane' and root_scale:struct.pack_into('>ff',s,0x3c,root_scale,root_scale)
        if kind==b'txt1' and name in texts:
            s=bytearray(replace_textbox(bytes(s),texts[name]));seen.add(name)
            if font and name in font:struct.pack_into('>ff',s,0x64,*font[name])
        sections[i]=bytes(s)
    missing=(set(hide)|set(show)|set(CENTRE)|set(texts))-seen
    if missing:raise ValueError(f'Disc channel panes not found: {sorted(missing)}')
    return rebuild_layout(layout,sections)

def _slow_loop(loop,frames=360):
    """DiskLoop with only the DVD spin, slowed to `frames` per turn; same byte size."""
    out=bytearray(loop);pos=0x10
    while out[pos:pos+4]!=b'pai1':pos+=struct.unpack_from('>I',out,pos+4)[0]
    struct.pack_into('>H',out,pos+8,frames)
    for name,material,tags in _contents(loop):
        for to,magic,tracks in tags:
            if (name,material,magic) not in SPIN:out[to:to+4]=DISABLED;continue
            for te,target,curve,keys in tracks:
                if target!=(5 if magic==b'RLPA' else 2):continue  # rotation Z / texture rotation
                if len(keys)!=2 or curve!=2:raise ValueError('Unexpected DiskLoop spin track')
                (f0,v0,_),(f1,v1,_)=(struct.unpack_from('>fff',loop,k) for k in keys)
                step=(v1-v0)/frames
                struct.pack_into('>fff',out,keys[0],0.0,v0,step);struct.pack_into('>fff',out,keys[1],float(frames),v1,step)
    return bytes(out)

def _arc(layout_name,layout,anims,textures):
    files={f'arc/blyt/{layout_name}.brlyt':layout}
    files.update({f'arc/anim/{n}.brlan':d for n,d in anims.items()})
    files.update({f'arc/timg/{n}':d for n,d in textures.items()})
    return build_u8(files)

def _imd5(archive):
    load_library();from libWiiPy.archive import decompress_lz77
    payload=b'LZ77'+compress_lz10(archive)
    if decompress_lz77(payload)!=archive:raise ValueError('Banner compression mismatch')
    return b'IMD5'+len(payload).to_bytes(4,'big')+bytes(8)+hashlib.md5(payload).digest()+payload

def _silent_sound(template_sound,seconds=2):
    """Template BNS (IMD5-wrapped) with the same INFO chunk and silent DSP-ADPCM frames."""
    if template_sound[:4]!=b'IMD5':raise ValueError('Template sound wrapper')
    bns=template_sound[32:]
    if bns[:4]!=b'BNS ':raise ValueError('Template sound is not BNS')
    info_off,info_len,data_off,data_len=struct.unpack_from('>IIII',bns,0x10)
    info=bytearray(bns[info_off:info_off+info_len])
    channels=info[0x0a];rate=struct.unpack_from('>H',info,0x0c)[0]
    samples=rate*seconds;frames=(samples+13)//14;per=frames*8
    info[0x09]=0;struct.pack_into('>II',info,0x10,0,samples)
    table=8+struct.unpack_from('>I',info,0x18)[0]
    for ch in range(channels):
        cinfo=8+struct.unpack_from('>I',info,table+4*ch)[0]
        struct.pack_into('>I',info,cinfo,ch*per)
        adpcm=8+struct.unpack_from('>I',info,cinfo+4)[0]
        struct.pack_into('>HHhhHhh',info,adpcm+0x22,0,0,0,0,0,0,0)  # gain, pred/scale, hist, loop pred/scale, loop hist
    data=b'DATA'+(8+per*channels).to_bytes(4,'big')+bytes(per*channels)
    out=bytearray(bns[:0x20]);out+=info;out+=bytes(-len(out)%32)
    data_at=len(out);out+=data
    struct.pack_into('>I',out,0x08,len(out));struct.pack_into('>IIII',out,0x10,0x20,len(info),data_at,len(data))
    return b'IMD5'+len(out).to_bytes(4,'big')+bytes(8)+hashlib.md5(bytes(out)).digest()+bytes(out)

def _small_icon(inner):
    """The 43K menu's icon buffer is 0x19000, never a full disc-channel archive."""
    from .dvd_home_ui import _materials,_material_section,_texture_names,_texture_section,_mat_name
    from . import tpl
    sections=layout_sections(inner.get(LAYOUT));panes={s[12:28].split(b'\0')[0].decode():s for s in sections if s[:4]in(b'pan1',b'pic1',b'txt1')}
    mats=_materials(next(s for s in sections if s[:4]==b'mat1'));names=_texture_names(next(s for s in sections if s[:4]==b'txl1'))
    out=[];used=[];textures={};smallmats=[]
    for name,pos,size,scale in [('Back0',(0,0),(128,96),1),('DVDDisk',(0,9),(256,256),0.265625),('T_Comment0',(0,-35),(128,20),1)]:
        pane=bytearray(panes[name]);pane[8]|=1;pane[10]=255
        struct.pack_into('>fff',pane,0x24,*pos,0);struct.pack_into('>ff',pane,0x3c,scale,scale);struct.pack_into('>ff',pane,0x44,*size)
        field=0x5c if pane[:4]==b'pic1'else 0x50;mi=struct.unpack_from('>H',pane,field)[0];mat=bytearray(mats[mi])
        flags=struct.unpack_from('>I',mat,0x3c)[0];count=flags&15
        for j in range(count):
            ti=struct.unpack_from('>H',mat,0x40+j*4)[0];tex=names[ti];data=inner.get('arc/timg/'+tex)
            if tex not in used:
                used.append(tex)
                if name=='DVDDisk':
                    image=tpl.decode(data,0).resize((64,64))
                    header=bytearray(data[:tpl.texture_records(data)[0]['offset']]);texoff=struct.unpack_from('>I',header,12)[0]
                    struct.pack_into('>HH',header,texoff,64,64);data=bytes(header)+bytes(tpl.data_size(5,64,64));data=tpl.encode(data,0,image)
                textures[tex]=data
            struct.pack_into('>H',mat,0x40+j*4,used.index(tex))
        struct.pack_into('>H',pane,field,len(smallmats));smallmats.append(bytes(mat))
        if name=='T_Comment0':
            pane=bytearray(replace_textbox(bytes(pane),TITLE));struct.pack_into('>ff',pane,0x64,15,18)
        out.append(bytes(pane))
    root=bytearray(panes['RootPane']);struct.pack_into('>ff',root,0x44,128,96)
    layout=next(s for s in sections if s[:4]==b'lyt1');layout=bytearray(layout);struct.pack_into('>ff',layout,12,128,96)
    keep=[bytes(layout),_texture_section(used),_material_section(smallmats)]
    keep += [s for s in sections if s[:4]==b'fnl1']
    keep += [bytes(root),b'pas1\0\0\0\x08',*out,b'pae1\0\0\0\x08']
    # Even a static icon needs the root group container: native new-message
    # binding iterates it unconditionally when the thumbnail is initialized.
    keep += [b'grp1'+struct.pack('>I',28)+b'RootGroup'.ljust(16,b'\0')+bytes(4)]
    result=_arc('icon',rebuild_layout(inner.get(LAYOUT),keep),{},textures)
    if len(result)>0x19000:raise ValueError('DVD icon exceeds the 43K icon buffer')
    return result

def dvd_player_content0(resource,template_content0,revision=1):
    """resource: a System Menu 0000009d.app with the DVD visuals (KWCE gc v6/v7).
    template_content0: an existing channel content 0 (IMET prefix and BNS header only)."""
    if revision<=6:
        from .dvd_banner_v1 import dvd_player_content0 as preserved
        return preserved(resource,template_content0)
    if revision<=8:
        from .dvd_banner_v2 import dvd_player_content0 as preserved
        return preserved(resource,template_content0,revision)
    inner=U8(ash_decompress(U8(resource).get(ASH_PATH)))
    layout=inner.get(LAYOUT)
    textures={n.split('/')[-1]:inner.get(n) for n in inner.files if n.endswith('.tpl')}
    start=inner.get(ANIM.format('Start'));loop=_slow_loop(inner.get(ANIM.format('DiskLoop')))
    banner=_edit_layout(layout,HIDE_BANNER,{'T_Bar':TITLE})
    icon=_edit_layout(layout,[n for n in HIDE_BANNER if n!='T_Comment0']+['N_Bar'],{'T_Comment0':TITLE},
                      size=(128.0,96.0),root_scale=128/608,show=['T_Comment0'],font={'T_Comment0':(72.0,84.0)})
    banner_arc=_arc('banner',banner,{'banner_Start':start,'banner_Loop':loop},textures)
    icon_arc=_small_icon(inner)
    load_library()
    template=U8(template_content0[0x640:])
    sound=_silent_sound(template.get('meta/sound.bin'))
    meta={'meta/banner.bin':_imd5(banner_arc),'meta/icon.bin':_imd5(icon_arc),'meta/sound.bin':sound}
    outer=build_u8(meta,dot=False)
    prefix=bytearray(template_content0[:0x640])
    prefix[0:0x40]=b'kwceDvdPlayer'.ljust(0x40,b'\0')
    if prefix[0x80:0x84]!=b'IMET':raise ValueError('Template IMET')
    struct.pack_into('>III',prefix,0x8c,len(icon_arc),len(banner_arc),len(sound)-32)
    # The template channel uses banner/channel scripts and alternate sound.
    # This native layout has no RSO/CS payload: inheriting those flags makes
    # ChannelManager choose a missing script renderer and dereference NULL.
    struct.pack_into('>I',prefix,0x98,0)
    name=TITLE.encode('utf-16-be')
    for language in range(10):
        at=0x40+0x5c+84*language;prefix[at:at+84]=name+bytes(84-len(name))
    prefix[0x630:0x640]=bytes(16);prefix[0x630:0x640]=hashlib.md5(prefix[0x40:0x640]).digest()
    return bytes(prefix)+outer,dict(banner_bytes=len(banner_arc),icon_bytes=len(icon_arc),sound_bytes=len(sound),
                                    textures=sorted(textures),title=TITLE,source='System Menu disc channel layout')
