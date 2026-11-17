"""HOME Menu archive for the KWCE DVD player, built from the System Menu's own HOME Menu.

Source: layout/common/homeBtn1.ash + layout/kor/homeBtn1.ash of the System Menu
resource (th_HomeBtn_d.brlyt, its 41 BRLANs, textures and the P1..P4 cursor
layouts). The player renders this layout with the ported NW4R-style engine
(homebrew/kwce-dvd/source/kwce/lyt) and plays the original animations.

Only one change is made to the layout: the System Menu variant has a single
large button (N_btnL_00, "Wii 메뉴로"); the DVD HOME Menu needs four, after the
item list of the System Menu's own message/jpn/dvdhome.bmg (TOP MENU, MENU,
停止, チャンネル一覧へ). N_btnL_00 is copied to N_btnL_01..03 with their own
materials (so the press flash, a material colour animation, stays per button)
and new I4 label textures drawn with the system font wbf1 at the size that
reproduces the original "Wii 메뉴로" texture. The 2x2 grid sits between the
top and bottom bars at their opened positions (bar_00 y=230, bar_10 y=-236).
Output: an uncompressed U8 (arc/blyt, arc/anim, arc/timg).
"""
import hashlib,struct
from .formats import U8,ash_decompress
from .channels import layout_sections,rebuild_layout,load_library,ChannelArchive
from .u8_build import build_u8
from . import tpl
from .wbf_text import WiiFontRenderer
from .channel_korean_font import korean_shared_fonts

COMMON='layout/common/homeBtn1.ash';KOREAN='layout/kor/homeBtn1.ash'
LAYOUT='arc/blyt/th_HomeBtn_d.brlyt'
# button index -> (label, position inside N_cntBtn_all); 0 keeps the original texture
BUTTONS={1:('타이틀 메뉴',(-148.0,90.0)),2:('DVD 메뉴',(148.0,90.0)),3:('정지',(-148.0,-42.0)),0:(None,(148.0,-42.0))}
LABEL_SIZE=35;LABEL_CENTRE=(120.5,31.5)  # fitted to tx_btn_L_00_KOR.tpl ("Wii 메뉴로")
# Stop dialog ("재생을 정지했습니다."): the dialog's A/B label panes get a hidden second label each;
# the player shows either the original 예/아니요 or these.
DIALOG_LABELS={'tx_msgBtn_00':('tx_msgBtn_02','처음부터 재생'),'tx_msgBtn_01':('tx_msgBtn_03','Wii 메뉴로')}
DIALOG_CENTRE_DY=-0.5  # tx_msgBtn_00_KOR.tpl ("예") fit
PER_BUTTON_MATERIALS=['btnL_00_L','btnL_00_M','btnL_00_R','tx_btnL_00']

def _name(section):return section[12:28].split(b'\0')[0].decode('ascii')

def _set_name(section,name):
    s=bytearray(section);raw=name.encode('ascii')
    if len(raw)>15:raise ValueError(f'Pane name too long: {name}')
    s[12:28]=raw.ljust(16,b'\0');return bytes(s)

def _texture_names(section):
    n=struct.unpack_from('>H',section,8)[0];base=12;out=[]
    for i in range(n):
        off=struct.unpack_from('>I',section,base+8*i)[0];out.append(section[base+off:].split(b'\0')[0].decode('ascii'))
    return out

def _texture_section(names):
    table=bytearray();blob=bytearray();base=8*len(names)
    for n in names:table+=struct.pack('>II',base+len(blob),0);blob+=n.encode('ascii')+b'\0'
    body=struct.pack('>HH',len(names),0)+table+blob;body+=bytes(-(len(body)+8)%4)
    return b'txl1'+struct.pack('>I',8+len(body))+body

def _materials(section):
    n=struct.unpack_from('>H',section,8)[0];offs=[struct.unpack_from('>I',section,12+4*i)[0] for i in range(n)]
    return [section[o:(offs[i+1] if i+1<n else len(section))] for i,o in enumerate(offs)]

def _material_section(mats):
    head=12+4*len(mats);offs=[];pos=head
    for m in mats:offs.append(pos);pos+=len(m)
    body=struct.pack('>HH',len(mats),0)+b''.join(struct.pack('>I',o) for o in offs)+b''.join(mats)
    return b'mat1'+struct.pack('>I',8+len(body))+body

def _mat_name(m):return m[:20].split(b'\0')[0].decode('ascii')

def _label(renderer,template,text,centre=LABEL_CENTRE):
    load_library();from PIL import Image
    w,h=tpl.texture_records(template)[0]['width'],tpl.texture_records(template)[0]['height']
    size=LABEL_SIZE
    while size>24 and renderer.line_width(text,size/renderer.height)>w-8:size-=1  # long labels shrink to fit
    canvas=Image.new('L',(w,h));renderer.render(text,size,canvas,centre=centre)
    return tpl.encode(template,0,canvas.convert('RGBA'))

def _edit_layout(layout,textures_added):
    sections=layout_sections(layout)
    txl=next(i for i,s in enumerate(sections) if s[:4]==b'txl1');mat=next(i for i,s in enumerate(sections) if s[:4]==b'mat1')
    tex_names=_texture_names(sections[txl]);mats=_materials(sections[mat])
    mat_index={_mat_name(m):i for i,m in enumerate(mats)}
    missing=[n for n in PER_BUTTON_MATERIALS if n not in mat_index]
    if missing:raise ValueError(f'HOME Menu materials not found: {missing}')
    # locate the N_btnL_00 subtree: pan1, pas1 ... matching pae1
    start=next(i for i,s in enumerate(sections) if s[:4]==b'pan1' and _name(s)=='N_btnL_00')
    if sections[start+1][:4]!=b'pas1':raise ValueError('N_btnL_00 has no children')
    depth=0;end=start+1
    while True:
        k=sections[end][:4];depth+=k==b'pas1';depth-=k==b'pae1'
        if depth==0:break
        end+=1
    subtree=sections[start:end+1];copies=[]
    for b in sorted(BUTTONS):
        label,(x,y)=BUTTONS[b];part=[]
        remap={}
        if b:
            for base in PER_BUTTON_MATERIALS:
                m=bytearray(mats[mat_index[base]]);new=base.replace('_00','_%02d'%b);m[0:20]=new.encode('ascii').ljust(20,b'\0')
                if base=='tx_btnL_00':
                    tex='tx_btn_L_%02d_KOR.tpl'%b;tex_names.append(tex);textures_added.append(('tx_btn_L_00_KOR.tpl',tex,label))
                    struct.pack_into('>H',m,0x40,len(tex_names)-1)
                remap[mat_index[base]]=len(mats);mats.append(bytes(m))
        for s in subtree:
            s=bytearray(s)
            if s[:4] in(b'pan1',b'pic1',b'txt1',b'wnd1',b'bnd1'):
                name=_name(s)
                if b:s=bytearray(_set_name(s,name.replace('_00','_%02d'%b,1)))
                if name=='N_btnL_00':struct.pack_into('>ff',s,0x24,x,y)
                if s[:4]==b'pic1':
                    mi=struct.unpack_from('>H',s,0x5c)[0]
                    if mi in remap:struct.pack_into('>H',s,0x5c,remap[mi])
                if name=='let_icn_00':s[8]&=0xfe  # HBM::init hides it until unread mail is explicitly known
            part.append(bytes(s))
        copies.extend(part)
    sections=sections[:start]+copies+sections[end+1:]
    for src,(new,label) in DIALOG_LABELS.items():
        at=next(i for i,s in enumerate(sections) if s[:4]==b'pic1' and _name(s)==src)
        m=bytearray(mats[mat_index[src]]);m[0:20]=new.encode('ascii').ljust(20,b'\0')
        tex=new+'_KOR.tpl';tex_names.append(tex);textures_added.append((src+'_KOR.tpl',tex,label))
        struct.pack_into('>H',m,0x40,len(tex_names)-1);mats.append(bytes(m))
        pane=bytearray(_set_name(sections[at],new));pane[8]&=0xfe;struct.pack_into('>H',pane,0x5c,len(mats)-1)
        sections.insert(at+1,bytes(pane))
    # txl1/mat1 come before the pane tree, so their indices are unchanged
    sections[txl]=_texture_section(tex_names);sections[mat]=_material_section(mats)
    return rebuild_layout(layout,sections)

def dvd_home_archive(resource,revision=2):
    """resource: System Menu 0000009d.app-style resource (U8 with layout/*/homeBtn1.ash)."""
    if revision==1:
        from .dvd_home_ui_v1 import dvd_home_archive as preserved
        return preserved(resource)
    res=U8(resource);common=U8(ash_decompress(res.get(COMMON)));korean=U8(ash_decompress(res.get(KOREAN)))
    files={}
    for arc in (common,korean):
        for n in arc.files:files[n]=arc.get(n)
    added=[];files[LAYOUT]=_edit_layout(korean.get(LAYOUT),added)
    fonts,font_record=korean_shared_fonts();renderer=WiiFontRenderer(ChannelArchive(fonts).get('wbf1.brfna'))
    for src,tex,label in added:
        template=korean.get('arc/timg/'+src);w,h=(tpl.texture_records(template)[0][k] for k in ('width','height'))
        centre=LABEL_CENTRE if src.startswith('tx_btn_L') else (w/2,h/2+DIALOG_CENTRE_DY)
        files['arc/timg/'+tex]=_label(renderer,template,label,centre)
    if revision>=3:
        # Player volume has a public runtime API; label it explicitly rather
        # than imply that these controls change the remote's speaker EEPROM.
        from PIL import Image
        for tex,text,size in [('tx_cntrl_00_KOR.tpl','재생·리모컨 설정',26),('tx_cntrl_01_KOR.tpl','재생·리모컨 설정 닫기',26),('tx_optn_00_KOR.tpl','재생 음량',24)]:
            path='arc/timg/'+tex;template=files[path];info=tpl.texture_records(template)[0]
            canvas=Image.new('L',(info['width'],info['height']));renderer.render(text,size,canvas,centre=(info['width']/2,info['height']/2))
            files[path]=tpl.encode(template,0,canvas.convert('RGBA'))
    archive=build_u8(files,dot=False)
    record=dict(source=[COMMON,KOREAN],layout=LAYOUT,buttons={str(b):(BUTTONS[b][0] or 'Wii 메뉴로 (original texture)') for b in sorted(BUTTONS)},
                dialog_labels={new:label for new,label in DIALOG_LABELS.values()},
                label_font='wbf1 (verified local 43K shared font)',label_size=LABEL_SIZE,files=len(files),bytes=len(archive),sha256=hashlib.sha256(archive).hexdigest())
    return archive,record
