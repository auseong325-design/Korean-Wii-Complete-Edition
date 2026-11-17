"""Bounded, read-only validation of the pinned Dolphin host FST format.

Never returns names, owners, groups or attributes. Layout: pinned HostFS.cpp
SerializedFstEntry (32 bytes), preorder tree, child count at byte 28.
"""
import hashlib,struct

def inspect_fst(data):
    if not data or len(data)%32 or len(data)>32*100000:raise ValueError('FST record bounds invalid')
    total=len(data)//32;cursor=0;files=0;dirs=0;deepest=0
    def visit(depth):
        nonlocal cursor,files,dirs,deepest
        if depth>8 or cursor>=total:raise ValueError('FST depth/child count invalid')
        row=data[32*cursor:32*(cursor+1)];cursor+=1;deepest=max(deepest,depth)
        raw=row[:12];end=raw.find(b'\0');name=raw if end<0 else raw[:end]
        if not name or (depth==0 and name!=b'/') or (depth>0 and (name in [b'.',b'..'] or b'/' in name or b'\\' in name)):
            raise ValueError('FST component invalid')
        isfile=row[18];children=struct.unpack_from('>I',row,28)[0]
        if isfile not in [0,1] or any(x>3 for x in row[19:22]):raise ValueError('FST metadata invalid')
        if depth==0 and isfile:raise ValueError('FST root must be a directory')
        if isfile:
            if children:raise ValueError('FST file has children')
            files+=1
        else:dirs+=1
        if children>total-cursor:raise ValueError('FST child count exceeds records')
        for _ in range(children):visit(depth+1)
    visit(0)
    if cursor!=total:raise ValueError('FST has unreferenced records')
    return dict(valid=True,records=total,files=files,directories=dirs,max_depth=deepest,sha256=hashlib.sha256(data).hexdigest())
