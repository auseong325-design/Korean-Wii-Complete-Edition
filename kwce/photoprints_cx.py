"""CX Huffman (8-bit, type 0x28) encoder that always fits the 6-bit child offsets.

kwce.cx_huffman.compress lays child pairs out breadth-first and raises when a
wide tree level pushes a child pair more than 63 pairs past its parent. That
happens for some v10 font sheets. This module keeps the proven breadth-first
stream whenever it fits (the layout the console already decoded in v6-v9) and
otherwise lays the same Huffman tree out depth-first, switching to the oldest
pending node whenever deferring it any longer could miss its 63-pair window.
Both layouts are decoded by kwce.cx_huffman.decompress, which mirrors the
console decoder; every stream is round-trip checked.
"""
import heapq,struct
from collections import Counter
from . import cx_huffman


def _tree(data):
    freq=Counter(data)
    if len(freq)==1:freq[(data[0]+1)&0xff]=0
    heap=[(n,i,('leaf',s)) for i,(s,n) in enumerate(sorted(freq.items()))];heapq.heapify(heap);k=len(heap)
    while len(heap)>1:
        a=heapq.heappop(heap);b=heapq.heappop(heap);heapq.heappush(heap,(a[0]+b[0],k,('node',a[2],b[2])));k+=1
    return heap[0][2]


def _deadline_layout(root):
    """Return [(node, table index of its child pair)] with every offset in 0..63."""
    slot={id(root):1};order=[];pending=[(0,root)];p=1   # pending: (pair index of the node byte, node)
    while pending:
        rest=sorted(pv+64 for pv,_ in pending[:-1])
        if all(d>=p+i for i,d in enumerate(rest,start=1)):j=len(pending)-1          # depth-first
        else:j=min(range(len(pending)),key=lambda i:pending[i][0])                  # oldest is due
        pv,node=pending.pop(j)
        if not 0<=p-pv-1<=0x3f:raise ValueError('Huffman tree cannot be laid out within 6-bit offsets')
        at=2*p;order.append((node,at));slot[id(node[1])]=at;slot[id(node[2])]=at+1
        for c in(node[2],node[1]):
            if c[0]=='node':pending.append((p,c))
        p+=1
    return order,slot,2*p


def compress_deadline(data):
    root=_tree(data);order,slot,size=_deadline_layout(root)
    table=bytearray(size+(-size)%4)
    for node,at in order:
        here=slot[id(node)];offset=(at-(here&~1)-2)//2
        if not 0<=offset<=0x3f:raise ValueError('Huffman tree offset overflow')
        table[here]=offset|(0x80 if node[1][0]=='leaf' else 0)|(0x40 if node[2][0]=='leaf' else 0)
        for j,c in enumerate(node[1:]):
            if c[0]=='leaf':table[at+j]=c[1]
    table[0]=len(table)//2-1
    codes={}
    def walk(node,code,length):
        if node[0]=='leaf':codes[node[1]]=(code,length);return
        walk(node[1],code<<1,length+1);walk(node[2],(code<<1)|1,length+1)
    walk(root,0,0)
    out=bytearray([0x28])+len(data).to_bytes(3,'little')+table;acc=0;n=0
    for s in data:
        code,length=codes[s]
        for bit in range(length-1,-1,-1):
            acc=(acc<<1)|((code>>bit)&1);n+=1
            if n==32:out+=struct.pack('<I',acc);acc=0;n=0
    if n:out+=struct.pack('<I',acc<<(32-n))
    return bytes(out)


def compress(data):
    """(stream, layout) with layout 'bfs' (shared encoder) or 'deadline' (fallback)."""
    try:out,layout=cx_huffman.compress(data),'bfs'
    except ValueError:out,layout=compress_deadline(data),'deadline'
    if cx_huffman.decompress(out)!=bytes(data):raise ValueError('CX Huffman roundtrip failed')
    return out,layout
