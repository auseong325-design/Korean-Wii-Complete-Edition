"""Match the Korean HOME library's ten language slots in its network prompt."""
import re
from .channels import ChannelArchive
from .wiiroom_manual_v40 import PROMPT

def korean_network_slots(content):
    archive=ChannelArchive(content);path='hbm/HomeButton3/network.csv';raw=archive.get(path)
    if not raw.startswith(b'\xfe\xff'):raise ValueError('Network prompt encoding')
    cells=re.findall(r'"([^"]*)"',raw[2:].decode('utf-16-be'))
    if cells!=[PROMPT]*7:raise ValueError('Expected reviewed seven-column guide prompt')
    home=archive.get('hbm/HomeButton3/home.csv')[2:].decode('utf-16-be')
    if len(re.findall(r'"([^"]*)"',home))!=40:raise ValueError('Expected four by ten runtime HOME messages')
    result=b'\xfe\xff'+('\t'.join('"'+PROMPT+'"'for _ in range(10))+'\r\n').encode('utf-16-be')
    archive=ChannelArchive(archive.replace(path,result))
    return archive.compact()
