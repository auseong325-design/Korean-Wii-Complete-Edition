"""Bounded local Wii Room LZ11 decoding; never exposes resource contents."""


def decompress_lz11(data,limit=48*1024*1024):
    if len(data)<4 or data[0]!=0x11:raise ValueError('Expected LZ11')
    size=int.from_bytes(data[1:4],'little');pos=4
    if not size:
        if len(data)<8:raise ValueError('Short LZ11 extended header')
        size=int.from_bytes(data[4:8],'little');pos=8
    if not 0<size<=limit:raise ValueError('LZ11 output bounds')
    out=bytearray()
    def take(count):
        nonlocal pos
        if pos+count>len(data):raise ValueError('Truncated LZ11')
        b=data[pos:pos+count];pos+=count;return b
    while len(out)<size:
        flags=take(1)[0]
        for bit in range(7,-1,-1):
            if len(out)==size:break
            if not flags&(1<<bit):out+=take(1);continue
            a=take(1)[0];kind=a>>4
            if kind==0:
                b,c=take(2);length=((a&15)<<4|b>>4)+0x11;distance=((b&15)<<8|c)+1
            elif kind==1:
                b,c,d=take(3);length=((a&15)<<12|b<<4|c>>4)+0x111;distance=((c&15)<<8|d)+1
            else:
                b=take(1)[0];length=kind+1;distance=((a&15)<<8|b)+1
            if distance>len(out)or len(out)+length>size:raise ValueError('LZ11 reference bounds')
            for _ in range(length):out.append(out[-distance])
    return bytes(out)


def reencode_lz11_same_size(original,edited):
    """Keep original matches unless an equal-length edit invalidates them.

    This avoids recompressing the multi-megabyte executable. An invalidated
    match becomes literal bytes; all retained matches are checked against the
    edited output, including overlapping references.
    """
    decoded=decompress_lz11(original)
    if len(decoded)!=len(edited):raise ValueError('LZ11 edit must preserve raw size')
    if decoded==edited:return original
    size=len(edited);pos=4 if int.from_bytes(original[1:4],'little')else 8;at=0
    out=bytearray(original[:pos]);group=[]
    def emit(reference,payload):
        group.append((reference,payload))
        if len(group)==8:flush()
    def flush():
        if not group:return
        out.append(sum(1<<(7-i)for i,(reference,_)in enumerate(group)if reference))
        for _,payload in group:out.extend(payload)
        group.clear()
    while at<size:
        flags=original[pos];pos+=1
        for bit in range(7,-1,-1):
            if at==size:break
            start=pos
            if not flags&(1<<bit):emit(False,edited[at:at+1]);pos+=1;at+=1;continue
            a=original[pos];pos+=1;kind=a>>4
            if kind==0:
                b,c=original[pos:pos+2];pos+=2;length=((a&15)<<4|b>>4)+0x11;distance=((b&15)<<8|c)+1
            elif kind==1:
                b,c,d=original[pos:pos+3];pos+=3;length=((a&15)<<12|b<<4|c>>4)+0x111;distance=((c&15)<<8|d)+1
            else:
                b=original[pos];pos+=1;length=kind+1;distance=((a&15)<<8|b)+1
            if edited[at:at+length]==edited[at-distance:at-distance+length]:emit(True,original[start:pos])
            else:
                for value in edited[at:at+length]:emit(False,bytes([value]))
            at+=length
    flush()
    if len(out)<len(original):out.extend(bytes(len(original)-len(out)))
    result=bytes(out)
    if decompress_lz11(result)!=edited:raise ValueError('LZ11 edited roundtrip')
    return result


def compress_lz10_optimal(data):
    """Minimum byte-cost LZ10 parse including flag groups, for small UI BMGs."""
    from collections import defaultdict,deque
    from array import array
    data=bytes(data);n=len(data)
    if not 0<n<=1024*1024:raise ValueError('Optimal LZ10 input bound')
    history=defaultdict(lambda:deque(maxlen=256));matches=[]
    for pos in range(n):
        key=data[pos:pos+3];best=0;distance=0;limit=min(18,n-pos)
        if len(key)==3:
            for prev in reversed(history[key]):
                if pos-prev>4096:break
                length=3
                while length<limit and data[prev+length]==data[pos+length]:length+=1
                if length>best:best=length;distance=pos-prev
                if best==limit:break
        matches.append((best,distance));history[key].append(pos)
    costs=array('I',bytes(4*8*(n+1)));choices=bytearray(8*n)
    for pos in range(n-1,-1,-1):
        for mod in range(8):
            nxt=(mod+1)%8;flag=int(mod==0);best=1+flag+costs[8*(pos+1)+nxt];choice=1
            for size in range(3,matches[pos][0]+1):
                cost=2+flag+costs[8*(pos+size)+nxt]
                if cost<best:best=cost;choice=size
            costs[8*pos+mod]=best;choices[8*pos+mod]=choice
    out=bytearray(b'\x10'+n.to_bytes(3,'little'));pos=0;mod=0
    while pos<n:
        if mod==0:flag_at=len(out);out.append(0)
        size=choices[8*pos+mod]
        if size==1:out.append(data[pos])
        else:
            out[flag_at]|=1<<(7-mod);ref=((size-3)<<12)|(matches[pos][1]-1);out.extend(ref.to_bytes(2,'big'))
        pos+=size;mod=(mod+1)%8
    return bytes(out)


def compress_lz11_optimal(data,candidates=64):
    """Minimum bit-cost LZ11 parse for Room layout resources.

    Tokens cost 9 bits (literal) or 17/25/33 bits (references of 3-16,
    17-272 and 273+ bytes) including their flag bit, which equals the stream
    size up to the final flag byte. Inside long repeats the previous match
    is continued instead of searched again.
    """
    from collections import defaultdict,deque
    from array import array
    data=bytes(data);n=len(data)
    if not 0<n<0x1000000:raise ValueError('Optimal LZ11 input bound')
    history=defaultdict(lambda:deque(maxlen=candidates));best_len=array('I',bytes(4*n));best_dist=array('H',bytes(2*n))
    carry=(0,0)
    for pos in range(n):
        key=data[pos:pos+3];limit=min(65808,n-pos)
        if carry[0]>64:best,distance=carry[0]-1,carry[1]
        else:
            best=0;distance=0
            if len(key)==3:
                for prev in reversed(history[key]):
                    if pos-prev>4096:break
                    length=3
                    while length<limit and data[prev+length]==data[pos+length]:length+=1
                    if length>best:best=length;distance=pos-prev
                    if best==limit:break
        best=min(best,limit);best_len[pos]=best;best_dist[pos]=distance;carry=(best,distance)
        if len(key)==3:history[key].append(pos)
    cost=array('Q',bytes(8*(n+1)));choice=array('I',bytes(4*n))
    for pos in range(n-1,-1,-1):
        c=9+cost[pos+1];pick=1;L=best_len[pos]
        if L>=3:
            for size in set(list(range(3,min(L,16)+1))+[min(L,272),L,min(L,17),min(L,273)]):
                if size<3:continue
                bits=17 if size<=16 else 25 if size<=272 else 33
                v=bits+cost[pos+size]
                if v<c:c=v;pick=size
        cost[pos]=c;choice[pos]=pick
    out=bytearray(b'\x11'+n.to_bytes(3,'little'));pos=0;mod=0
    while pos<n:
        if mod==0:flag_at=len(out);out.append(0)
        size=choice[pos]
        if size==1:out.append(data[pos])
        else:
            out[flag_at]|=1<<(7-mod);d=best_dist[pos]-1
            if size<=16:out.extend(bytes([((size-1)<<4)|(d>>8),d&255]))
            elif size<=272:s=size-0x11;out.extend(bytes([s>>4,((s&15)<<4)|(d>>8),d&255]))
            else:s=size-0x111;out.extend(bytes([0x10|(s>>12),(s>>4)&255,((s&15)<<4)|(d>>8),d&255]))
        pos+=size;mod=(mod+1)%8
    result=bytes(out)
    if decompress_lz11(result)!=data:raise ValueError('LZ11 roundtrip')
    return result
