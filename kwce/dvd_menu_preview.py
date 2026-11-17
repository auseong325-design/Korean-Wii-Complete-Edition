"""Emulator-only DVD insertion preview, using the 43K disc channel artwork.

Dolphin rejects DVD-Video as a drive image. A verified synthetic Wii header
drives BAD_DISK; only this dedicated test NAND renders that state as a DVD.
This resource is not an optical-drive detector and is not a hardware patch.
"""
import struct
from .formats import U8,ash_decompress,ash_compress
from .channels import layout_sections,rebuild_layout,replace_textbox
from .disk_dvd_anim import ASH_PATH,LAYOUT,_contents

def patch_preview(resource):
    outer=U8(resource);arc=U8(ash_decompress(outer.get(ASH_PATH)))
    sections=layout_sections(arc.get(LAYOUT))
    label=None
    for i,s in enumerate(sections):
        if s[:4] in (b"wnd1",b"pic1",b"pan1") and s[12:28].split(b"\0")[0] in (b"W_DVD",b"W_Wii",b"W_GC"):
            hidden_pane=bytearray(s);hidden_pane[8]&=~1;sections[i]=bytes(hidden_pane)
        if s[:4]==b'txt1' and s[12:28].split(b'\0')[0]==b'T_Comment1':
            label=bytearray(replace_textbox(s,'DVD 비디오'))
            label[12:28]=b'KWCE_DVD'.ljust(16,b'\0');label[8]|=1;label[10]=255
            struct.pack_into('>ff',label,0x24,0,-60)
    # Native code sets T_Comment1 from BMG at runtime. Keep that pane for its
    # caller, hide its error animation, and add an independent preview label.
    if label is None:raise ValueError('Native disc comment pane missing')
    last=max(i for i,s in enumerate(sections)if s[:4]==b'pae1')
    sections.insert(last,bytes(label))
    inner=arc.replace(LAYOUT,rebuild_layout(arc.get(LAYOUT),sections));changed=0
    hidden={'WiiDisk','GCDisk','RefWii','RefGC','ShadeWii','ShadeGC','ShadeWii_00','UnknownDisk','RefUnknown','T_Comment1','W_DVD','W_Wii','W_GC'}
    visible={'DVDDisk','RefDVD','SahdeDVD'}
    for suffix in ['Unknown','UnknownLoop']:
        name='arc/anim/my_DiskCh_a_R_'+suffix+'.brlan';data=bytearray(U8(inner).get(name))
        for pane,material,tags in _contents(bytes(data)):
            for off,tag,tracks in tags:
                for track,target,curve,keys in tracks:
                    value=None
                    if tag==b'RLVC' and target==16 and pane in hidden|visible:value=0 if pane in hidden else 255
                    if tag==b'RLPA' and pane in {'N_DVD0','N_RefDVD'} and target==1:
                        data[track+1]=0;value=0 # centre X; retain original Y from the layout
                    if tag==b'RLPA' and pane=='SahdeDVD' and target==0:value=0
                    if tag==b'RLPA' and pane=='W_DVD' and target in (6,7):value=1
                    if value is not None and curve==2:
                        for key in keys:struct.pack_into('>ff',data,key+4,float(value),0.0)
                        changed+=1
        inner=U8(inner).replace(name,bytes(data))
    packed=ash_compress(inner)
    if ash_decompress(packed)!=inner:raise ValueError('DVD preview ASH roundtrip failed')
    return outer.replace(ASH_PATH,packed),dict(emulator_only=True,synthetic_insertion=True,changed_tracks=changed,hardware_detection=False)
