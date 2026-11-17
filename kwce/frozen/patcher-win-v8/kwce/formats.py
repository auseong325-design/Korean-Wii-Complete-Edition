"""Bounded ASH0 codec and U8 edits preserving original directory metadata.

Format references: NinjaCheetah/ASH0-tools (9-bit symbols, 11-bit distances),
NinjaCheetah/libWiiPy archive/ash.py and archive/u8.py. No external executable.
"""
import struct,heapq
from collections import Counter,defaultdict,deque

class Bits:
    def __init__(self,data):self.data=data;self.pos=0
    def read(self,n):
        if self.pos+n>len(self.data)*8:raise ValueError('Truncated ASH stream')
        value=0
        for _ in range(n):
            value=value*2+((self.data[self.pos//8]>>(7-self.pos%8))&1);self.pos+=1
        return value

class Writer:
    def __init__(self):self.data=bytearray();self.value=0;self.count=0
    def write(self,value,n):
        if value<0 or value>=1<<n:raise ValueError('Invalid bit value')
        self.value=(self.value<<n)|value;self.count+=n
        while self.count>=8:
            self.count-=8;self.data.append((self.value>>self.count)&255)
        self.value&=(1<<self.count)-1
    def finish(self):
        if self.count:self.write(0,8-self.count)
        # Native readers prefetch an entire next word at a word boundary.
        return bytes(self.data)+bytes((-len(self.data))%4+4)

def _read_tree(bits,width):
    count=0
    def node(depth):
        nonlocal count
        count+=1
        if count>(1<<(width+1))-1 or depth>64:raise ValueError('Invalid ASH tree')
        if bits.read(1):return (node(depth+1),node(depth+1))
        return bits.read(width)
    return node(0)

def _decode(bits,tree):
    while isinstance(tree,tuple):tree=tree[bits.read(1)]
    return tree

def ash_decompress(data,max_size=16*1024*1024):
    if len(data)<16 or data[:4]!=b'ASH0':raise ValueError('Not ASH0')
    size,split=struct.unpack_from('>II',data,4);size&=0xffffff
    if size>max_size or split<12 or split%4 or split>=len(data):raise ValueError('Invalid ASH bounds')
    sym=Bits(data[12:split]);dist=Bits(data[split:])
    st=_read_tree(sym,9);dt=_read_tree(dist,11);out=bytearray()
    while len(out)<size:
        value=_decode(sym,st)
        if value<256:out.append(value)
        else:
            length=value-256+3;distance=_decode(dist,dt)+1
            if distance>len(out) or len(out)+length>size:raise ValueError('Invalid ASH back-reference')
            for _ in range(length):out.append(out[-distance])
    return bytes(out)

def _huffman(freq):
    freq=Counter(freq)
    if not freq:freq[0]=1
    if len(freq)==1:freq[0 if 0 not in freq else 1]=1
    heap=[(count,serial,sym) for serial,(sym,count) in enumerate(sorted(freq.items()))];heapq.heapify(heap);serial=len(heap)
    while len(heap)>1:
        a=heapq.heappop(heap);b=heapq.heappop(heap)
        heapq.heappush(heap,(a[0]+b[0],serial,(a[2],b[2])));serial+=1
    return heap[0][2]

def _write_tree(writer,tree,width,codes,value=0,length=0):
    if isinstance(tree,int):writer.write(0,1);writer.write(tree,width);codes[tree]=(value,length)
    else:
        writer.write(1,1)
        _write_tree(writer,tree[0],width,codes,value*2,length+1)
        _write_tree(writer,tree[1],width,codes,value*2+1,length+1)

def ash_compress(data):
    if len(data)>0xffffff:raise ValueError('ASH size limit')
    tokens=[];positions=defaultdict(lambda:deque(maxlen=64));i=0
    while i<len(data):
        best=0;distance=0;key=data[i:i+3]
        if len(key)==3:
            for old in reversed(positions[key]):
                if i-old>2048:break
                length=0;limit=min(258,len(data)-i)
                while length<limit and data[old+length]==data[i+length]:length+=1
                if length>best:best=length;distance=i-old
                if best==limit:break
        take=best if best>=3 else 1
        tokens.append((best-3+256,distance-1) if best>=3 else (data[i],None))
        for p in range(i,i+take):
            if p+3<=len(data):positions[data[p:p+3]].append(p)
        i+=take
    sw=Writer();dw=Writer();sc={};dc={}
    _write_tree(sw,_huffman(Counter(t[0] for t in tokens)),9,sc)
    _write_tree(dw,_huffman(Counter(t[1] for t in tokens if t[1] is not None)),11,dc)
    for symbol,distance in tokens:
        sw.write(*sc[symbol])
        if distance is not None:dw.write(*dc[distance])
    symbols=sw.finish();distances=dw.finish()
    return b'ASH0'+struct.pack('>II',len(data),12+len(symbols))+symbols+distances

class U8:
    """Pure U8 only. Refuses unsafe names, invalid trees and out-of-range data."""
    def __init__(self,data):
        self.data=data;self.files={};self.entries={}
        if len(data)<44 or data[:4]!=bytes.fromhex('55aa382d'):raise ValueError('Not a pure U8 archive')
        root,header,start=struct.unpack_from('>III',data,4)
        if root<32 or root+12>len(data):raise ValueError('Invalid U8 root')
        typ,parent,count=struct.unpack_from('>III',data,root)
        if typ!=0x01000000 or parent!=0 or not count or count>100000:raise ValueError('Invalid U8 root metadata')
        strings=root+12*count
        if strings>root+header or root+header>start or start>len(data):raise ValueError('Invalid U8 header bounds')
        stack=[('',count,0)]
        for i in range(1,count):
            while stack and i>=stack[-1][1]:stack.pop()
            if not stack:raise ValueError('U8 directory ended early')
            off=root+12*i;t,value,size=struct.unpack_from('>III',data,off);kind=t>>24;no=strings+(t&0xffffff)
            end=data.find(b'\0',no,root+header)
            if no<strings or end<no:raise ValueError('Invalid U8 string offset')
            name=data[no:end].decode('ascii')
            if not name or name in ('.','..') or '/' in name or '\\' in name:raise ValueError('Unsafe U8 name')
            path=(stack[-1][0]+'/'+name).lstrip('/')
            if path in self.entries:raise ValueError('Duplicate U8 path')
            self.entries[path]=off
            if kind==1:
                if value!=stack[-1][2] or not i<size<=stack[-1][1]:raise ValueError('Invalid U8 directory parent/end')
                stack.append((path,size,i))
            elif kind==0:
                if value<start or value+size>len(data):raise ValueError('U8 file outside archive')
                self.files[path]=(value,size)
            else:raise ValueError('Invalid U8 node kind')

    def get(self,path):
        off,size=self.files[path];return self.data[off:off+size]

    def replace(self,path,replacement):
        out=bytearray(self.data);off,size=self.files[path]
        if len(replacement)==size:out[off:off+size]=replacement
        else:
            # Append preserves every original directory parent/index and all
            # other file data, avoiding topology changes in generic repackers.
            out.extend(bytes((-len(out))%32));off=len(out);out.extend(replacement)
            struct.pack_into('>II',out,self.entries[path]+4,off,len(replacement))
        checked=U8(bytes(out))
        if checked.get(path)!=replacement:raise ValueError('U8 replacement failed')
        for name in self.files:
            if name!=path and self.get(name)!=checked.get(name):raise ValueError('Unrelated U8 file changed')
        return bytes(out)
