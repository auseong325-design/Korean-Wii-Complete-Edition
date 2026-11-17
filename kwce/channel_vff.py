"""Bounded local FAT12 VFF cache editor, never downloads or changes signatures."""
import math,struct

class VFF:
    def __init__(self,data):
        self.data=data
        if len(data)<32 or data[:4]!=b'VFF 'or struct.unpack_from('>H',data,4)[0]!=0xfeff:raise ValueError('Unsupported VFF header')
        volume=struct.unpack_from('>I',data,8)[0];cluster=struct.unpack_from('>H',data,12)[0]*16
        if cluster!=512 or volume%512 or volume>32*1024*1024:raise ValueError('VFF bounds')
        total=volume//512
        if not 16<total<65525:raise ValueError('Only bounded FAT12/FAT16 VFF supported')
        # Same layout as Dolphin VFFUtil: FAT16 above 4084 clusters.
        self.fat16=total>=4085
        table=math.ceil((total*2 if self.fat16 else((total+1)//2)*3)/512)*512
        self.table_size=table;self.fat=32;self.root=32+2*table;self.start=self.root+4096
        self.cluster_count=total-(1+table//512*2+8)+2
        if self.start>len(data)or data[32:32+table]!=data[32+table:32+2*table]:raise ValueError('VFF redundant FAT mismatch')
    def next_cluster(self,cluster):
        if self.fat16:
            value=int.from_bytes(self.data[self.fat+2*cluster:self.fat+2*cluster+2],'little')
            return 0xfff if value>=0xfff8 else value
        at=self.fat+cluster*3//2;value=int.from_bytes(self.data[at:at+2],'little')
        return (value>>4 if cluster%2 else value)&0xfff
    def entries(self):
        rows=[]
        for at in range(self.root,self.root+4096,32):
            e=self.data[at:at+32]
            if e[0]==0:break
            if e[0]==0xe5 or e[11]&0x18 or e[11]==15:continue
            rows.append((e[:11],struct.unpack_from('<H',e,26)[0],struct.unpack_from('<I',e,28)[0]))
        return rows
    def read(self,name):
        key=self.key(name)
        for candidate,cluster,size in self.entries():
            if candidate!=key:continue
            data=bytearray();visited=set()
            while len(data)<size:
                if not 2<=cluster<self.cluster_count or cluster in visited:raise ValueError('VFF invalid chain')
                visited.add(cluster);at=self.start+(cluster-2)*512
                if at+512>len(self.data):raise ValueError('VFF data outside image')
                data.extend(self.data[at:at+512]);cluster=self.next_cluster(cluster)
            if size and cluster<0xff8:raise ValueError('VFF chain length mismatch')
            return bytes(data[:size])
        raise KeyError(name)
    @staticmethod
    def key(name):
        if name.count('.')!=1:raise ValueError('VFF requires safe 8.3 name')
        a,b=name.upper().split('.')
        if not 1<=len(a)<=8 or not 1<=len(b)<=3 or not all(c.isascii()and(c.isalnum()or c in '_~')for c in a+b):raise ValueError('Unsafe VFF name')
        return(a.ljust(8)+b.ljust(3)).encode('ascii')
    def add(self,name,payload):
        key=self.key(name)
        if any(e[0]==key for e in self.entries()):raise ValueError('Existing VFF file preserved')
        slots=[at for at in range(self.root,self.root+4096,32)if self.data[at]in[0,0xe5]]
        free=[i for i in range(2,self.cluster_count)if self.next_cluster(i)==0 and self.start+(i-1)*512<=len(self.data)]
        needed=math.ceil(len(payload)/512)
        if not payload or not slots or needed>len(free):raise ValueError('VFF capacity')
        chain=free[:needed];result=bytearray(self.data)
        for i,c in enumerate(chain):
            at=self.start+(c-2)*512;block=payload[512*i:512*(i+1)];result[at:at+512]=block+bytes(512-len(block))
            value=chain[i+1]if i+1<len(chain)else(0xffff if self.fat16 else 0xfff)
            for base in [32,32+self.table_size]:
                if self.fat16:
                    result[base+2*c:base+2*c+2]=value.to_bytes(2,'little');continue
                off=base+c*3//2;old=int.from_bytes(result[off:off+2],'little');new=(old&15)|(value<<4)if c%2 else(old&0xf000)|value
                result[off:off+2]=new.to_bytes(2,'little')
        e=bytearray(32);e[:11]=key;e[11]=0x20
        struct.pack_into('<H',e,24,0x5d41);struct.pack_into('<HI',e,26,chain[0],len(payload));result[slots[0]:slots[0]+32]=e
        checked=VFF(bytes(result))
        if checked.read(name)!=payload:raise ValueError('VFF payload roundtrip failed')
        for old_name,_,_ in self.entries():
            text=old_name[:8].decode().rstrip()+'.'+old_name[8:].decode().rstrip()
            if checked.read(text)!=self.read(text):raise ValueError('Existing VFF payload changed')
        return bytes(result)

def _lfn_checksum(short):
    s=0
    for b in short:s=(((s&1)<<7)+(s>>1)+b)&0xff
    return s

def add_long(vff,name,payload,alias_index=1):
    """Add a file whose name needs FAT long-filename entries (for example 2.bin.00).

    The 8.3 alias is BASE~N.EXT; LFN slots precede it in the root directory.
    Returns new image bytes. Reading back uses the alias through VFF.read.
    """
    import re
    if not re.fullmatch(r'[A-Za-z0-9_.]{1,64}',name):raise ValueError('Unsafe long VFF name')
    base,_,ext=name.rpartition('.')
    stem=re.sub(r'[^A-Z0-9_]','',base.upper())[:6]or'F';alias=f'{stem}~{alias_index}.{ext.upper()[:3]}'
    short=vff.key(alias)
    data=bytearray(VFF(vff.add(alias,payload)).data)
    # Locate the new short entry and move it after the LFN slots it needs.
    view=VFF(bytes(data));slot=next(at for at in range(view.root,view.root+4096,32)if data[at:at+11]==short)
    entry=bytes(data[slot:slot+32]);units=list(name.encode('utf-16-le'));chars=[name[i]for i in range(len(name))]
    count=math.ceil(len(chars)/13);free=[at for at in range(view.root,view.root+4096,32)if data[at]in(0,0xe5)or at==slot]
    run=None
    for i in range(len(free)-count):
        if all(free[i+k]==free[i]+32*k for k in range(count+1)):run=free[i];break
    if run is None:raise ValueError('VFF root directory full')
    data[slot:slot+32]=bytes(32)if data[slot+32]==0 else b'\xe5'+bytes(31)
    checksum=_lfn_checksum(short);padded=name.encode('utf-16-le')+b'\0\0';padded+=b'\xff'*(26*count-len(padded))
    for k in range(count):
        seq=count-k;part=padded[26*(seq-1):26*seq];e=bytearray(32)
        e[0]=seq|(0x40 if k==0 else 0);e[1:11]=part[0:10];e[11]=0x0f;e[13]=checksum;e[14:26]=part[10:22];e[28:32]=part[22:26]
        data[run+32*k:run+32*k+32]=e
    data[run+32*count:run+32*count+32]=entry
    checked=VFF(bytes(data))
    if checked.read(alias)!=payload:raise ValueError('Long VFF roundtrip failed')
    return bytes(data)
