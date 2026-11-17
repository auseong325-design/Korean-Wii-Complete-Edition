"""Shared local channel tooling. Never emits title keys, tickets or resources."""
import hashlib,struct,sys
from collections import defaultdict,deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load_library():
    sys.path[:0]=([str(ROOT/'tools/channel-python')] if sys.platform == 'win32' else []) + [str(ROOT/'external/channel-tools/libWiiPy-71ad5b90/src')]
    import libWiiPy
    return libWiiPy

class ChannelArchive:
    """Preserve U8 topology; support Nintendo's virtual '.' directory only."""
    def __init__(self,data):
        self.data=data;self.files={};self.nodes={}
        if data[:4]!=bytes.fromhex('55aa382d')or len(data)<44:raise ValueError('Invalid channel U8')
        root,header,start=struct.unpack_from('>III',data,4)
        if root<32 or root+12>len(data):raise ValueError('Invalid U8 root')
        kind,parent,count=struct.unpack_from('>III',data,root)
        strings=root+count*12
        if kind!=0x1000000 or parent or not 0<count<100000 or not strings<=root+header<=start<=len(data):raise ValueError('Invalid U8 bounds')
        stack=[('',count,0)]
        for index in range(1,count):
            while stack and index>=stack[-1][1]:stack.pop()
            if not stack:raise ValueError('U8 tree ended early')
            at=root+12*index;word,value,size=struct.unpack_from('>III',data,at);kind=word>>24;no=strings+(word&0xffffff);end=data.find(b'\0',no,root+header)
            if no<strings or end<no:raise ValueError('U8 name bounds')
            name=data[no:end].decode('ascii')
            if not name or name=='..' or '/'in name or '\\'in name or (name=='.'and kind!=1):raise ValueError('Unsafe U8 component')
            path='/'.join(x for x in [stack[-1][0],name if name!='.'else '']if x)
            if kind==1:
                if value!=stack[-1][2]or not index<size<=stack[-1][1]:raise ValueError('U8 directory bounds')
                stack.append((path,size,index))
            elif kind==0:
                if path in self.files or value<start or value+size>len(data):raise ValueError('U8 file bounds/duplicate')
                self.files[path]=(value,size);self.nodes[path]=at
            else:raise ValueError('Invalid U8 node')
    def get(self,name):
        at,size=self.files[name];return self.data[at:at+size]
    def replace(self,name,payload):
        result=bytearray(self.data);at,size=self.files[name]
        if size==len(payload):result[at:at+size]=payload
        else:
            result.extend(bytes(-len(result)%32));at=len(result);result.extend(payload)
            struct.pack_into('>II',result,self.nodes[name]+4,at,len(payload))
        checked=ChannelArchive(bytes(result))
        if checked.get(name)!=payload or any(self.get(n)!=checked.get(n)for n in self.files if n!=name):raise ValueError('Archive preservation failed')
        return bytes(result)
    def compact(self):
        start=struct.unpack_from('>I',self.data,12)[0];out=bytearray(self.data[:start])
        for name in self.files:
            out.extend(bytes(-len(out)%32));offset=len(out);payload=self.get(name);out.extend(payload)
            struct.pack_into('>II',out,self.nodes[name]+4,offset,len(payload))
        checked=ChannelArchive(bytes(out))
        if any(checked.get(name)!=self.get(name)for name in self.files):raise ValueError('U8 compaction content mismatch')
        return bytes(out)

def compress_lz10(data):
    """Bounded greedy LZ10; 4KiB window, 18-byte references, 64 candidates."""
    data=bytes(data)
    if len(data)>0xffffff:raise ValueError('LZ10 size limit')
    out=bytearray(b'\x10'+len(data).to_bytes(3,'little'));positions=defaultdict(lambda:deque(maxlen=64));pos=0
    while pos<len(data):
        flag_at=len(out);out.append(0);flags=0
        for bit in range(7,-1,-1):
            if pos>=len(data):break
            key=data[pos:pos+3];best=0;distance=0
            if len(key)==3:
                limit=min(18,len(data)-pos)
                for old in reversed(positions[key]):
                    if pos-old>4096:break
                    length=0
                    while length<limit and data[old+length]==data[pos+length]:length+=1
                    if length>best:best=length;distance=pos-old
                    if best==limit:break
            take=best if best>=3 else 1
            if take>=3:
                flags|=1<<bit;out.extend(struct.pack('>H',((take-3)<<12)|(distance-1)))
            else:out.append(data[pos])
            for i in range(pos,pos+take):
                if i+3<=len(data):positions[data[i:i+3]].append(i)
            pos+=take
        out[flag_at]=flags
    return bytes(out)

def layout_sections(data):
    if data[:6]!=b'RLYT\xfe\xff' or len(data)<16:raise ValueError('Unsupported BRLYT')
    if struct.unpack_from('>I',data,8)[0]!=len(data):raise ValueError('BRLYT size mismatch')
    pos=16;sections=[]
    while pos<len(data):
        if pos+8>len(data):raise ValueError('BRLYT bounds')
        size=struct.unpack_from('>I',data,pos+4)[0]
        if size<8 or pos+size>len(data):raise ValueError('BRLYT section bounds')
        sections.append(data[pos:pos+size]);pos+=size
    if len(sections)!=struct.unpack_from('>H',data,14)[0]:raise ValueError('BRLYT section count')
    return sections

def textbox(section):
    if section[:4]!=b'txt1':return None
    if len(section)<116:raise ValueError('Short textbox')
    size=struct.unpack_from('>H',section,78)[0];offset=struct.unpack_from('>I',section,88)[0]
    if size%2 or (size and(offset<116 or offset+size>len(section))):raise ValueError('Textbox string bounds')
    return section[12:28].split(b'\0')[0].decode('ascii'),section[offset:offset+size].decode('utf-16-be').rstrip('\0')

def replace_textbox(section,text):
    payload=(text+'\0').encode('utf-16-be')
    if len(payload)>65535:raise ValueError('Textbox exceeds uint16')
    result=bytearray(section);offset=len(result);result.extend(payload);result.extend(bytes(-len(result)%4))
    struct.pack_into('>I',result,4,len(result));struct.pack_into('>HH',result,76,len(payload),len(payload));struct.pack_into('>I',result,88,offset)
    return bytes(result)

def fit_korean_textbox(section,text):
    """Fit explicit short Korean labels without changing pane or animations.

    Added Hangul glyph advances equal the RFNT cell width. Keep font height
    and line spacing; reduce only horizontal font scale when necessary.
    Long explanatory messages retain their existing line wrapping.
    """
    import math
    if '\n' in text or len(text)>12 or not any('\uac00'<=c<='\ud7a3' for c in text):return section
    width=struct.unpack_from('>f',section,68)[0]
    font_width=struct.unpack_from('>f',section,100)[0]
    if not math.isfinite(width) or not math.isfinite(font_width) or width<=0 or font_width<=0:raise ValueError('Textbox metric bounds')
    units=sum(1 if '\uac00'<=c<='\ud7a3' else .55 for c in text)
    needed=units*font_width
    if needed<=width-1:return section
    result=bytearray(section);struct.pack_into('>f',result,100,font_width*(width-1)/needed)
    return bytes(result)

def patch_utf16_literals(data,replacements):
    """Change bounded, terminated UTF-16 constants without moving pointers."""
    import re
    original=bytes(data);result=bytearray(data);slots={};counts={}
    for source,target in replacements.items():
        needle=source.encode('utf-16-be');positions=[];at=original.find(needle)
        while at>=0:
            if at%2:raise ValueError('Unaligned UTF16 literal')
            lo=at
            while lo>=2 and original[lo-2:lo]!=b'\0\0':
                lo-=2
                if at-lo>4096:raise ValueError('UTF16 constant start bounds')
            hi=at
            while hi+2<=len(original)and original[hi:hi+2]!=b'\0\0':
                hi+=2
                if hi-at>4096:raise ValueError('UTF16 constant end bounds')
            if hi+2>len(original):raise ValueError('Unterminated UTF16 constant')
            slots[lo,hi]=original[lo:hi].decode('utf-16-be');positions.append(at);at=original.find(needle,at+2)
        if len(positions)!=1:raise ValueError('Expected unique localized UTF16 literal')
        counts[source]=len(positions)
    for (lo,hi),before in slots.items():
        after=before
        for source,target in replacements.items():after=after.replace(source,target)
        if re.findall(r'%[-+ #0-9.*hlLzjt]*[a-zA-Z%]',before)!=re.findall(r'%[-+ #0-9.*hlLzjt]*[a-zA-Z%]',after):raise ValueError('Format tokens changed')
        encoded=after.encode('utf-16-be')
        if len(encoded)>hi-lo:raise ValueError('UTF16 localized constant exceeds original slot')
        result[lo:hi]=encoded+bytes(hi-lo-len(encoded))
    return bytes(result),sum(counts.values())

def rebuild_layout(data,sections):
    if len(sections)>65535:raise ValueError('BRLYT section count exceeds uint16')
    result=bytearray(data[:16]+b''.join(sections));struct.pack_into('>I',result,8,len(result));struct.pack_into('>H',result,14,len(sections))
    layout_sections(result);return bytes(result)

def sha256(data):return hashlib.sha256(data).hexdigest()
