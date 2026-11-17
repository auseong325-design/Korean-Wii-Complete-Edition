"""Read the Room channel's HDPK001B XML schema files (content 2, xml/*.bin).

A node at file offset p+0x20 holds type, name, first child, next sibling,
back link, flags (top byte 1 = required), min, max; p and name offsets are
relative to 0x20 and the root is p=4. Type 0 is a container whose min/max
bound its repeat count; leaves bound the value (numbers) or length (strings).
"""
import struct

BASE=0x20
TYPES={0:'list',1:'wide-string',2:'string',3:'integer',4:'boolean',5:'hex',6:'scalar',8:'date/time'}

def tree(data):
    if data[:8]!=b'HDPK001B':raise ValueError('Room schema magic')
    def text(o):
        s=BASE+o;return data[s:data.index(b'\0',s)].decode('ascii')
    def build(p,depth=0):
        if depth>16:raise ValueError('Room schema depth')
        t,name,child,nxt,back,flags,lo,hi=struct.unpack_from('>8I',data,BASE+p)
        node=dict(type=t,name=text(name),required=bool(flags>>24),min=lo,max=hi)
        if t==0 and child:
            kids=[];c=child
            while c:
                kids.append(build(c,depth+1));c=struct.unpack_from('>I',data,BASE+c+12)[0]
            node['children']=kids
        return node
    return build(4)

def problems(xml,schema):
    """Check repeat counts, required leaves and text/string lengths and
    integer ranges and boolean values. Scalar and date/time formats remain
    subject to the channel's runtime parser."""
    from xml.etree.ElementTree import fromstring
    root=fromstring(xml);out=[]
    def check(element,node,path):
        for child in node.get('children',[]):
            found=element.findall(child['name']);where=path+'/'+child['name']
            if child['type']==0:
                if not child['min']<=len(found)<=child['max']:out.append(f'{where}: count {len(found)} not in {child["min"]}..{child["max"]}')
                for item in found:check(item,child,where)
                continue
            if not found:
                if child['required']:out.append(f'{where}: missing')
                continue
            for item in found:
                value=item.text or ''
                if child['type']in(1,2)and not child['min']<=len(value)<=child['max']:out.append(f'{where}: length {len(value)} not in {child["min"]}..{child["max"]}')
                if child['type']==3:
                    lower=child['min'];upper=child['max']
                    if lower==0x80000000 and upper==0x7fffffff:lower=-0x80000000
                    numeric=(value[1:]if value.startswith('-')else value).isdigit()
                    if not numeric or not lower<=int(value)<=upper:out.append(f'{where}: value not in {lower}..{upper}')
                if child['type']==4 and value not in('0','1'):out.append(f'{where}: expected boolean 0 or 1')
    # Root tags differ from schema names (Event/PayEvent, New/AllNewMovies); not checked.
    check(root,schema,root.tag);return out
