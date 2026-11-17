"""Nintendo CX Huffman (8-bit symbols, type 0x28) used by RFNA font sheets."""
import heapq,struct
from collections import Counter


def decompress(data):
    if data[0]!=0x28:raise ValueError('Not CX Huffman 8-bit')
    size=int.from_bytes(data[1:4],'little');tree=4;table=(data[tree]+1)*2;stream=tree+table
    out=bytearray();node=tree+1;pos=stream
    while len(out)<size:
        if pos+4>len(data):raise ValueError('Huffman stream truncated')
        word=struct.unpack_from('<I',data,pos)[0];pos+=4
        for bit in range(31,-1,-1):
            value=data[node];right=(word>>bit)&1
            child=(node&~1)+(value&0x3f)*2+2+right
            if value&(0x40 if right else 0x80):
                out.append(data[child])
                if len(out)==size:break
                node=tree+1
            else:node=child
    return bytes(out)


def compress(data):
    """Return a stream that `decompress` (and the console) decodes to `data`.

    Child pairs are laid out breadth-first. This fits the 6-bit node offsets for
    font sheets (all 43K wbf1/wbf2 sheets re-encode to their original sizes) but
    not for every 256-symbol distribution; those raise ValueError, never a bad stream.
    """
    freq=Counter(data)
    if len(freq)==1:freq[(data[0]+1)&0xff]=0  # a tree needs two leaves
    heap=[(n,i,('leaf',s))for i,(s,n) in enumerate(sorted(freq.items()))];heapq.heapify(heap);k=len(heap)
    while len(heap)>1:
        a=heapq.heappop(heap);b=heapq.heappop(heap);heapq.heappush(heap,(a[0]+b[0],k,('node',a[2],b[2])));k+=1
    root=heap[0][2]
    # Breadth-first placement: every internal node owns a child pair; child pairs are
    # allocated in visit order so the 6-bit forward offsets stay small.
    queue=[root];slot={id(root):1};nxt=2  # slot: table index of each node byte
    order=[]
    while queue:
        node=queue.pop(0)
        if node[0]=='leaf':continue
        at=nxt;nxt+=2;order.append((node,at))
        for c in node[1:]:
            if c[0]=='node':queue.append(c)
        slot[id(node[1])]=at;slot[id(node[2])]=at+1
    table=bytearray(nxt+(-nxt)%4)
    for node,at in order:
        here=slot[id(node)];offset=(at-(here&~1)-2)//2
        if not 0<=offset<=0x3f:raise ValueError('Huffman tree offset overflow')
        flags=(0x80 if node[1][0]=='leaf' else 0)|(0x40 if node[2][0]=='leaf' else 0)
        table[here]=offset|flags
        for j,c in enumerate(node[1:]):
            if c[0]=='leaf':table[at+j]=c[1]
    table[0]=len(table)//2-1
    codes={}
    def walk(node,code,length):
        if node[0]=='leaf':codes[node[1]]=(code,length);return
        walk(node[1],code<<1,length+1);walk(node[2],(code<<1)|1,length+1)
    walk(root,0,0)
    out=bytearray([0x28])+len(data).to_bytes(3,'little')+table
    acc=0;n=0
    for s in data:
        code,length=codes[s]
        for bit in range(length-1,-1,-1):
            acc=(acc<<1)|((code>>bit)&1);n+=1
            if n==32:out+=struct.pack('<I',acc);acc=0;n=0
    if n:out+=struct.pack('<I',acc<<(32-n))
    return bytes(out)
