"""Korean channel manuals (Opera HTML in a U8 archive).

Text nodes are matched after trimming whitespace and the original leading and
trailing whitespace is kept, so tag topology, scripts and links are unchanged.
Images listed in the config are rebuilt by kwce.manual_images; every other
asset must stay byte-identical.
"""
import re
from html import escape
from html.parser import HTMLParser
from .channels import ROOT,ChannelArchive
from . import manual_images

KOREAN_MANUAL=ROOT/'workspace/channels/_shared/korean-manual-havk/html/common_data'

class _Localizer(HTMLParser):
    def __init__(self,mapping,used):
        super().__init__(convert_charrefs=False);self.mapping=mapping;self.used=used;self.out=[];self.skip=0;self.structure=[]
    def handle_starttag(self,tag,attrs):
        self.out.append(self.get_starttag_text());self.structure.append(('start',tag,tuple(attrs)))
        if tag in['script','style']:self.skip+=1
    def handle_startendtag(self,tag,attrs):
        self.out.append(self.get_starttag_text());self.structure.append(('empty',tag,tuple(attrs)))
    def handle_endtag(self,tag):
        self.out.append('</'+tag+'>');self.structure.append(('end',tag))
        if tag in['script','style']:self.skip-=1
    def handle_data(self,text):
        key=' '.join(text.split())
        if not self.skip and key and key in self.mapping:
            self.used.add(key);lead=text[:len(text)-len(text.lstrip())];trail=text[len(text.rstrip()):]
            self.out.append(lead+escape(self.mapping[key],quote=False)+trail)
        else:self.out.append(text)
    def handle_entityref(self,name):self.out.append('&'+name+';')
    def handle_charref(self,name):self.out.append('&#'+name+';')
    def handle_comment(self,text):self.out.append('<!--'+text+'-->')
    def handle_decl(self,text):self.out.append('<!'+text+'>')

def localize(data,config,captures=None,prefix='html/'):
    original=ChannelArchive(data);archive=original;used=set();html=0
    # Keys match with all whitespace runs collapsed (sources mix CRLF and tabs).
    mapping={' '.join(k.split()):v for k,v in config['translations'].items()}
    targets=config['html']
    for name in original.files:
        rel=name[len(prefix):]if name.startswith(prefix)else name
        if not name.endswith('.html')or not any(rel==t or(t.endswith('/')and rel.startswith(t))for t in targets):continue
        parser=_Localizer(mapping,used);parser.feed(original.get(name).decode('utf-8'));parser.close()
        target=''.join(parser.out);check=_Localizer({},set());check.feed(target);check.close()
        if parser.structure!=check.structure:raise ValueError('Manual HTML topology changed: '+name)
        archive=ChannelArchive(archive.replace(name,target.encode('utf-8')));html+=1
    missing=set(mapping)-used
    if missing:raise ValueError(f'Unmatched manual text: {sorted(missing)[:5]}')
    images={}
    for name,spec in config.get('images',{}).items():
        path=prefix+name;old=original.get(path);kind=spec['type']
        if kind=='korean_button':new=manual_images.padded_button(old,(KOREAN_MANUAL/spec['source']).read_bytes(),spec.get('align','right'))
        elif kind=='text':new=manual_images.text_image(old,spec)
        elif kind=='diagram':new=manual_images.compose(old,spec,captures)
        else:raise ValueError('Unknown manual image type')
        archive=ChannelArchive(archive.replace(path,new));images[name]=kind
    changed=set(prefix+n for n in images)
    for name in original.files:
        if not name.endswith('.html')and name not in changed and archive.get(name)!=original.get(name):raise ValueError('Manual asset changed: '+name)
    return archive.compact(),dict(html_files=html,text_nodes=len(used),images=images)
