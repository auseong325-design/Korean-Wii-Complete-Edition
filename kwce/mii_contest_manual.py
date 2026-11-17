"""Rebuild reviewed English manual text while preserving tags and image links."""
import json,re
from html.parser import HTMLParser
from html import escape
from .channels import ChannelArchive
from .votes_resources import decode_yaz0,encode_yaz0


def localize_manual(outer, config, images=None, captures=None):
    """images: optional {path under US/: spec} (korean_button / diagram) from
    configs/mii-contest-manual-images-ko.json; other assets stay byte-identical."""
    path='content4/Basic/VCMV/US.szs'
    original=ChannelArchive(decode_yaz0(outer.get(path)));archive=original
    mapping=config['translations'];changed=0;used=set()
    class Localizer(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=False);self.out=[];self.skip=0;self.structure=[]
        def handle_starttag(self,tag,attrs):
            text=self.get_starttag_text()
            if tag=='meta':text=re.sub(r'charset=[\w-]+','charset=UTF-8',text,flags=re.I)
            self.out.append(text);self.structure.append(('start',tag,tuple((k,v)for k,v in attrs if k not in ['content'])))
            if tag in ['script','style']:self.skip+=1
        def handle_startendtag(self,tag,attrs):
            self.out.append(self.get_starttag_text());self.structure.append(('empty',tag,tuple(attrs)))
        def handle_endtag(self,tag):
            self.out.append('</'+tag+'>');self.structure.append(('end',tag))
            if tag in ['script','style']:self.skip-=1
        def handle_data(self,text):
            if not self.skip and text in mapping:
                used.add(text);self.out.append(escape(mapping[text],quote=False))
            else:self.out.append(text)
        def handle_entityref(self,name):self.out.append('&'+name+';')
        def handle_charref(self,name):self.out.append('&#'+name+';')
        def handle_comment(self,text):self.out.append('<!--'+text+'-->')
        def handle_decl(self,text):self.out.append('<!'+text+'>')
    for name in archive.files:
        if not name.endswith('.html'):continue
        source=original.get(name).decode('utf-8');parser=Localizer();parser.feed(source);parser.close()
        target=''.join(parser.out);check=Localizer();check.feed(target);check.close()
        if parser.structure!=check.structure:raise ValueError('Manual HTML topology changed')
        archive=ChannelArchive(archive.replace(name,target.encode('utf-8')));changed+=1
    if used!=set(mapping):raise ValueError('Unmatched reviewed manual text')
    from . import manual_images
    from .channel_manual import KOREAN_MANUAL
    done={}
    for name,spec in(images or {}).items():
        old=original.get('US/'+name)
        if spec['type']=='korean_button':new=manual_images.padded_button(old,(KOREAN_MANUAL/spec['source']).read_bytes(),spec.get('align','right'))
        elif spec['type']=='diagram':new=manual_images.compose(old,spec,captures)
        else:raise ValueError('Unknown manual image type')
        archive=ChannelArchive(archive.replace('US/'+name,new));done['US/'+name]=spec['type']
    for name in archive.files:
        if not name.endswith('.html')and name not in done and archive.get(name)!=original.get(name):raise ValueError('Manual asset changed')
    packed=encode_yaz0(archive.compact())
    record=dict(html_files=changed,reviewed_text_nodes=len(used),image_and_script_assets_preserved=not done,embedded_image_translation_complete=False)
    if done:
        from .channels import sha256
        captured={shot['capture']:sha256((captures/shot['capture']).read_bytes())for spec in images.values()for shot in spec.get('shots',[])}
        record.update(images=done,screenshot_ui_text_translated=False,korean_capture_files=captured,korean_capture_slots=sum(len(spec.get('shots',[]))for spec in images.values()))
    return ChannelArchive(outer.replace(path,packed)),record
