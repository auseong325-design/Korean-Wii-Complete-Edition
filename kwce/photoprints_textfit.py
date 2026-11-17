"""Static text-fit checks for Photo Prints BRLYT textboxes (FOT-Rodan metrics).

The channel's text writer wraps at the textbox width: a Korean line wider than
the box breaks mid-word and the extra line overlaps the pane below (lead's
v6 Dolphin review, PD_Dialog_Update). Widths are computed like nw4r's
TextWriter: sum(charWidth * fontSize.width / FINF.width) + charSpace*(n-1);
line height = linefeed * fontSize.height / FINF.height + lineSpace.
"""
import re,struct
from .channels import ChannelArchive,layout_sections,textbox
from .photoprints_font import find_glyph,_parse_rfna

PLACEHOLDER=re.compile(r'%[-+ #0-9.*]*(?:ls|l?[dsuxXf]|%)')
INDENT='\u3000'
MIN_SCALE=0.80        # narrowest horizontal font scale accepted for long lines
MARGIN=1.0            # layout units kept free at the right edge (rounding safety)


class Metrics:
    def __init__(self,rfna):
        P=_parse_rfna(rfna);finf=P['blocks'][1][1]+8;self.f=rfna
        self.linefeed=struct.unpack_from('>b',rfna,finf+1)[0]
        self.alter=struct.unpack_from('>H',rfna,finf+2)[0]
        self.default=struct.unpack_from('>bBb',rfna,finf+4)
        self.height,self.width=rfna[finf+0x14],rfna[finf+0x15]
        pw=struct.unpack_from('>I',rfna,finf+0x0c)[0];self.cwdh=[]
        while pw:
            begin,end,nxt=struct.unpack_from('>HHI',rfna,pw);self.cwdh.append((begin,end,pw+8));pw=nxt
        self.cache={}

    def char(self,ch):
        """(advance, mapped) in font units; unmapped characters use the alternate glyph."""
        code=ord(ch)
        if code not in self.cache:
            g=find_glyph(self.f,code);mapped=g is not None
            if not mapped:g=self.alter
            adv=self.default[2]
            for begin,end,at in self.cwdh:
                if begin<=g<=end:adv=struct.unpack_from('>bBb',self.f,at+3*(g-begin))[2];break
            self.cache[code]=(adv,mapped)
        return self.cache[code]

    def unmapped(self,text):
        return sorted({c for c in text if c not in '\n\r' and not self.char(c)[1]})


class Box:
    def __init__(self,file,pane,section):
        self.file=file;self.pane=pane
        self.w,self.h=struct.unpack_from('>ff',section,68)
        self.fw,self.fh,self.cs,self.ls=struct.unpack_from('>ffff',section,100)

    def line_height(self,m):return m.linefeed*self.fh/m.height+self.ls


def width(m,box,line,fw=None,placeholder=''):
    text=PLACEHOLDER.sub(placeholder,line)
    if not text:return 0.0
    scale=(fw or box.fw)/m.width
    return sum(m.char(c)[0] for c in text)*scale+box.cs*(len(text)-1)


def wrapped_lines(m,box,text,fw=None):
    """Lines after the writer's character wrap at the box width."""
    total=0
    for line in text.split('\n'):
        n=1;run=''
        for c in PLACEHOLDER.sub('',line):
            if run and width(m,box,run+c,fw)>box.w:n+=1;run=c
            else:run+=c
        total+=n
    return total


def overflow_lines(m,box,text,fw=None):
    return [line for line in text.split('\n') if width(m,box,line,fw)>box.w-MARGIN]


def capacity(m,box,jp):
    """Lines a pane may use: what the Japanese occupied there. Box height is not
    trusted (PD_Dialog_Update TextA is 3 lines tall, yet a pane sits under line 1)."""
    return max(wrapped_lines(m,box,jp),1)


def _split(m,box,line,limit):
    """Greedy break of one line at spaces; continuation lines keep a note indent."""
    indent=INDENT if line.startswith(('※',INDENT)) else ''
    words=line.split(' ');out=[];cur=''
    for word in words:
        trial=word if not cur else cur+' '+word
        if width(m,box,trial)<=limit or not cur:cur=trial
        else:out.append(cur);cur=(indent if not word.startswith(INDENT) else '')+word
    out.append(cur)
    return out


def reflow(m,boxes,ko):
    """Insert line breaks at spaces so every line fits the narrowest box."""
    narrow=min(boxes,key=lambda b:b.w)
    lines=[]
    for line in ko.split('\n'):
        if width(m,narrow,line)<=narrow.w-MARGIN:lines.append(line);continue
        lines.extend(_split(m,narrow,line,narrow.w-MARGIN))
    return '\n'.join(lines)


def fit_scale(m,box,text):
    """Horizontal font scale (<=1) that makes every explicit line fit the box."""
    limit=box.w-MARGIN
    worst=max((width(m,box,line) for line in text.split('\n')),default=0.0)
    if worst<=limit:return 1.0
    # charSpace is unscaled; solve sum*scale*k + cs*(n-1) <= limit for k.
    line=max(text.split('\n'),key=lambda l:width(m,box,l))
    n=len(PLACEHOLDER.sub('',line));base=width(m,box,line)-box.cs*max(n-1,0)
    return max(0.0,(limit-box.cs*max(n-1,0))/base) if base else 1.0


def boxes_by_text(layout_bytes,texts):
    """{original text: [Box,...]} for every txt1 pane whose string is in texts."""
    out={};archive=ChannelArchive(layout_bytes)
    for name in sorted(archive.files):
        if not name.endswith('.brlyt'):continue
        for sec in layout_sections(archive.get(name)):
            tb=textbox(sec)
            if tb and tb[1] in texts:out.setdefault(tb[1],[]).append(Box(name,tb[0],sec))
    return out



def budget(mj,box,jp):
    """Lines a Korean string may use in this pane: the Japanese explicit lines,
    or the Japanese wrapped lines when the Japanese itself relied on wrapping
    (a line more than 15% wider than the pane)."""
    lines=jp.split('\n')
    if any(width(mj,box,l)>box.w*1.15 for l in lines):return max(1,wrapped_lines(mj,box,jp))
    return max(1,len(lines))


DEBUG_LAYOUTS=('A_FrontEnd.brlyt',)


def translate_fitted(data,messages,m,mj,debug=DEBUG_LAYOUTS):
    """Translate txt1 panes and make every line fit (rev>=8 builds).

    Lines are already broken by the v8 table; a pane whose line is still wider
    than the box gets its horizontal font size reduced (never below MIN_SCALE).
    Raises if a pane would need more lines than its Japanese budget.
    """
    from .channels import replace_textbox,rebuild_layout
    archive=ChannelArchive(data);changed=0;squeezed=[]
    for name in list(archive.files):
        if not name.endswith('.brlyt'):continue
        sections=layout_sections(archive.get(name));touched=False
        for i,sec in enumerate(sections):
            tb=textbox(sec)
            if tb is None or tb[1] not in messages:continue
            jp,ko=tb[1],messages[tb[1]];box=Box(name,tb[0],sec)
            new=replace_textbox(sec,ko)
            if name.split('/')[-1] not in debug:
                if len(ko.split('\n'))>budget(mj,box,jp):raise ValueError(f'{name}:{tb[0]} exceeds its Japanese line budget')
                scale=fit_scale(m,box,ko)
                if scale<1.0:
                    if scale<MIN_SCALE:raise ValueError(f'{name}:{tb[0]} needs horizontal scale {scale:.3f}')
                    fw=box.fw*scale;out=bytearray(new)
                    while True:
                        struct.pack_into('>f',out,100,fw);fw32=struct.unpack_from('>f',out,100)[0]
                        if not overflow_lines(m,box,ko,fw=fw32):break
                        fw*=0.999
                    new=bytes(out);squeezed.append(dict(pane=f"{name.split('/')[-1]}:{tb[0]}",scale=round(fw32/box.fw,3)))
                if overflow_lines(m,box,ko,fw=struct.unpack_from('>f',new,100)[0]):raise ValueError(f'{name}:{tb[0]} still overflows')
            sections[i]=new;touched=True;changed+=1
        if touched:archive=ChannelArchive(archive.replace(name,rebuild_layout(archive.get(name),sections)))
    scales=[s['scale'] for s in squeezed]
    return archive.data,changed,dict(squeezed_panes=len(squeezed),min_scale=min(scales) if scales else 1.0,squeezed=squeezed)
