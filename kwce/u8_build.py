"""Build a U8 archive from {path: bytes}, Nintendo channel layout (root -> '.' -> dirs)."""
import struct

def build_u8(files,dot=True):
    tree={}
    for path,data in files.items():
        node=tree;parts=path.split('/')
        for part in parts[:-1]:node=node.setdefault(part,{})
        node[parts[-1]]=bytes(data)
    if dot:tree={'.':tree}
    nodes=[];names=bytearray(b'\0');payloads=[]
    def walk(name,item,parent):
        index=len(nodes);name_off=len(names);names.extend(name.encode('ascii')+b'\0')
        if isinstance(item,dict):
            nodes.append([1,name_off,parent,0])
            for child in sorted(item,key=lambda n:(isinstance(item[n],dict),n.lower())):walk(child,item[child],index)
            nodes[index][3]=len(nodes)
        else:
            nodes.append([0,name_off,0,len(item)]);payloads.append((index,item))
    nodes.append([1,0,0,0])  # root
    for child in sorted(tree,key=lambda n:(isinstance(tree[n],dict),n.lower())):walk(child,tree[child],0)
    nodes[0][3]=len(nodes)
    header_size=len(nodes)*12+len(names)
    data_offset=(0x20+header_size+0x1f)&~0x1f
    out=bytearray(data_offset)
    for index,item in payloads:
        out.extend(bytes(-len(out)%32));nodes[index][2]=len(out);out.extend(item)
    struct.pack_into('>IIII',out,0,0x55AA382D,0x20,header_size,data_offset)
    at=0x20
    for kind,name_off,value,size in nodes:
        struct.pack_into('>III',out,at,(kind<<24)|name_off,value,size);at+=12
    out[at:at+len(names)]=names
    return bytes(out)
