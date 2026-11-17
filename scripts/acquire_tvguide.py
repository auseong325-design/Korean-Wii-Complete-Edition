"""Acquire a separately preserved Japanese TV Guide original, never install."""
import json,re,sys,urllib.parse,urllib.request
from html.parser import HTMLParser
from pathlib import Path
import acquire_forecast as acquisition
BASE='https://repo.mariocube.com/WADs/_WiiWare, VC, DLC, Channels & IOS/T/'
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.extend(v for k,v in attrs if k=='href')
def main():
    request=urllib.request.Request(urllib.parse.quote(BASE,safe=':/%&'),headers={'User-Agent':'KWCE-local-research/0.1'})
    parser=Links();parser.feed(urllib.request.urlopen(request,timeout=30).read().decode())
    matches=[urllib.parse.urljoin(BASE,p)for p in parser.links if'TV no Tomo'in urllib.parse.unquote(p)and'(Japan)'in urllib.parse.unquote(p)and p.lower().endswith('.wad')]
    if not matches:raise SystemExit('No matching TV Guide original in public source index')
    acquisition.DEST=Path(__file__).resolve().parents[1]/'workspace/channels/tvguide/originals'
    acquisition.FILES=[('tvguide-japan-original.wad',max(matches,key=lambda p:int(re.search(r'\(v(\d+)\)',urllib.parse.unquote(p))[1])if re.search(r'\(v(\d+)\)',urllib.parse.unquote(p))else 0))]
    acquisition.main()
if __name__=='__main__':main()
