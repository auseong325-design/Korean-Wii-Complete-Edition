"""Bounded Yaz0 decoding for local Votes resource analysis."""

def decode_yaz0(data):
    if data[:4]!=b'Yaz0' or len(data)<16:raise ValueError('Invalid Yaz0')
    size=int.from_bytes(data[4:8],'big')
    if size>32*1024*1024:raise ValueError('Yaz0 bound')
    out=bytearray();pos=16
    while len(out)<size:
        flags=data[pos];pos+=1
        for bit in range(7,-1,-1):
            if len(out)==size:break
            if flags&(1<<bit):out.append(data[pos]);pos+=1
            else:
                a,b=data[pos:pos+2];pos+=2;distance=((a&15)<<8|b)+1;length=a>>4
                if length:length+=2
                else:length=data[pos]+18;pos+=1
                if distance>len(out)or len(out)+length>size:raise ValueError('Yaz0 reference bounds')
                for _ in range(length):out.append(out[-distance])
    return bytes(out)

def encode_yaz0_literals(data):
    """Valid deterministic Yaz0 stream, trading compression ratio for simplicity."""
    if len(data)>32*1024*1024:raise ValueError('Yaz0 bound')
    out=bytearray(b'Yaz0'+len(data).to_bytes(4,'big')+bytes(8))
    for at in range(0,len(data),8):out.append(255);out.extend(data[at:at+8])
    return bytes(out)

def encode_yaz0_greedy(data):
    """Fast bounded Yaz0 for large glyph atlases; exact decode is verified."""
    from collections import defaultdict,deque
    positions=defaultdict(lambda:deque(maxlen=64));out=bytearray(b'Yaz0'+len(data).to_bytes(4,'big')+bytes(8));pos=0
    while pos<len(data):
        flag_at=len(out);out.append(0);flags=0
        for bit in range(7,-1,-1):
            if pos==len(data):break
            best=0;distance=0;limit=min(273,len(data)-pos)
            for previous in reversed(positions[data[pos:pos+3]]):
                if pos-previous>4096:break
                length=0
                while length<limit and data[previous+length]==data[pos+length]:length+=1
                if length>best:best=length;distance=pos-previous
                if best==limit:break
            if best>=3:
                ref=distance-1
                if best>=18:out.extend([ref>>8,ref&255,best-18])
                else:out.extend([((best-2)<<4)|(ref>>8),ref&255])
                step=best
            else:flags|=1<<bit;out.append(data[pos]);step=1
            for at in range(pos,pos+step):positions[data[at:at+3]].append(at)
            pos+=step
        out[flag_at]=flags
    if decode_yaz0(out)!=data:raise ValueError('Yaz0 roundtrip')
    return bytes(out)

def encode_yaz0(data,history_limit=4096):
    """Minimum byte cost Yaz0 parse, including flag-byte boundaries."""
    from collections import defaultdict,deque
    n=len(data)
    if n>1024*1024:raise ValueError('Optimal Yaz0 input bound')
    history=defaultdict(lambda:deque(maxlen=history_limit));matches=[]
    for pos in range(n):
        key=data[pos:pos+3];best=0;distance=0;limit=min(273,n-pos)
        for previous in reversed(history[key]):
            if pos-previous>4096:break
            length=0
            while length<limit and data[previous+length]==data[pos+length]:length+=1
            if length>best:best=length;distance=pos-previous
            if best==limit:break
        matches.append((best,distance));history[key].append(pos)
    costs=[[0]*8 for _ in range(n+1)];choices=[[1]*8 for _ in range(n)]
    for pos in range(n-1,-1,-1):
        longest,distance=matches[pos]
        for mod in range(8):
            nxt=(mod+1)%8;flag=int(mod==0);best=1+flag+costs[pos+1][nxt];choice=1
            for length in range(3,longest+1):
                cost=(2 if length<18 else 3)+flag+costs[pos+length][nxt]
                if cost<best:best=cost;choice=length
            costs[pos][mod]=best;choices[pos][mod]=choice
    out=bytearray(b'Yaz0'+n.to_bytes(4,'big')+bytes(8));pos=0;mod=0
    while pos<n:
        if mod==0:flag_at=len(out);out.append(0)
        length=choices[pos][mod]
        if length==1:out[flag_at]|=1<<(7-mod);out.append(data[pos])
        else:
            ref=matches[pos][1]-1
            if length>=18:out.extend([ref>>8,ref&255,length-18])
            else:out.extend([((length-2)<<4)|(ref>>8),ref&255])
        pos+=length;mod=(mod+1)%8
    if decode_yaz0(out)!=data:raise ValueError('Yaz0 roundtrip')
    return bytes(out)

def bmg_sections(data):
    if data[:8]!=b'MESGbmg1' or data[16]!=2:raise ValueError('Expected UTF16 BMG')
    if int.from_bytes(data[8:12],'big')!=len(data):raise ValueError('BMG size')
    pos=32;sections=[]
    for _ in range(int.from_bytes(data[12:16],'big')):
        size=int.from_bytes(data[pos+4:pos+8],'big')
        if size<8 or pos+size>len(data):raise ValueError('BMG section bounds')
        sections.append(data[pos:pos+size]);pos+=size
    if pos!=len(data):raise ValueError('BMG trailing bytes')
    return sections

def bmg_message(data,offset):
    start=pos=offset
    while pos+2<=len(data):
        unit=data[pos:pos+2]
        if unit==b'\0\0':return data[start:pos]
        if unit==b'\0\x1a':
            length=data[pos+2]
            if length<4 or length%2 or pos+length>len(data):raise ValueError('BMG control bounds')
            pos+=length
        else:pos+=2
    raise ValueError('Unterminated BMG message')

def translate_bmg(data,mapping):
    sections=bmg_sections(data);inf=bytearray(next(s for s in sections if s[:4]==b'INF1'));dat=next(s for s in sections if s[:4]==b'DAT1')
    count=int.from_bytes(inf[8:10],'big');stride=int.from_bytes(inf[10:12],'big');payload=bytearray(b'\0\0');changed=0
    if stride<4 or 16+count*stride>len(inf):raise ValueError('BMG index bounds')
    for i in range(count):
        at=16+i*stride;offset=int.from_bytes(inf[at:at+4],'big');old=bmg_message(dat,8+offset)
        if str(i)in mapping:
            value=render_bmg_translation(old,mapping[str(i)]);changed+=1
        else:value=old
        inf[at:at+4]=len(payload).to_bytes(4,'big');payload.extend(value+b'\0\0')
    rebuilt=bytearray(b'DAT1'+bytes(4)+payload);rebuilt.extend(bytes(-len(rebuilt)%32));rebuilt[4:8]=len(rebuilt).to_bytes(4,'big')
    out=bytearray(data[:32]+b''.join(bytes(inf)if s[:4]==b'INF1'else bytes(rebuilt)if s[:4]==b'DAT1'else s for s in sections));out[8:12]=len(out).to_bytes(4,'big');bmg_sections(out)
    return bytes(out),changed


def render_bmg_translation(old,text):
    controls=[];pos=0
    while pos<len(old):
        if old[pos:pos+2]==b'\0\x1a':
            size=old[pos+2];controls.append(old[pos:pos+size]);pos+=size
        else:pos+=2
    value=text.encode('utf-16-be')
    for i,control in enumerate(controls):
        token=('{CTRL'+str(i)+'}').encode('utf-16-be')
        if value.count(token)!=1:raise ValueError('Control placeholder missing or duplicated')
        value=value.replace(token,control)
    return value

def encode_yaz0_lean(data,candidates=96):
    """Minimum byte-cost Yaz0 parse for large inputs (array-backed, bounded candidate list)."""
    from array import array
    from collections import defaultdict,deque
    n=len(data);history=defaultdict(lambda:deque(maxlen=candidates))
    best_len=array('H',bytes(2*n));best_dist=array('H',bytes(2*n))
    for pos in range(n):
        key=data[pos:pos+3];best=0;distance=0;limit=min(273,n-pos)
        for previous in reversed(history[key]):
            if pos-previous>4096:break
            length=3 if data[previous:previous+3]==key and limit>=3 else 0
            if not length:continue
            while length<limit and data[previous+length]==data[pos+length]:length+=1
            if length>best:best=length;distance=pos-previous
            if best==limit:break
        best_len[pos]=best;best_dist[pos]=distance;history[key].append(pos)
    costs=array('I',bytes(4*8*(n+1)));choice=array('H',bytes(2*8*n))
    for pos in range(n-1,-1,-1):
        longest=best_len[pos];base=8*pos
        for mod in range(8):
            nxt=(mod+1)%8;flag=1 if mod==0 else 0;best=1+flag+costs[8*(pos+1)+nxt];pick=1
            for length in range(3,longest+1):
                cost=(2 if length<18 else 3)+flag+costs[8*(pos+length)+nxt]
                if cost<best:best=cost;pick=length
            costs[base+mod]=best;choice[base+mod]=pick
    out=bytearray(b'Yaz0'+n.to_bytes(4,'big')+bytes(8));pos=0;mod=0;flag_at=0
    while pos<n:
        if mod==0:flag_at=len(out);out.append(0)
        pick=choice[8*pos+mod]
        if pick==1:out[flag_at]|=1<<(7-mod);out.append(data[pos])
        else:
            ref=best_dist[pos]-1
            if pick>=18:out.extend([ref>>8,ref&255,pick-18])
            else:out.extend([((pick-2)<<4)|(ref>>8),ref&255])
        pos+=pick;mod=(mod+1)%8
    if decode_yaz0(out)!=data:raise ValueError('Yaz0 roundtrip')
    return bytes(out)
