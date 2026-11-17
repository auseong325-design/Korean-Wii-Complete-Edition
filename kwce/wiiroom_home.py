"""Room's embedded HOME text uses ten columns, unlike older seven-column channels."""
import re
from .channels import ChannelArchive
from .home_menu import korean_dialog_messages,SAVE_WARNING

def korean_runtime_home(content):
    archive=ChannelArchive(content);messages=korean_dialog_messages();records=[]
    for path in ['hbm/HomeButton3/home.csv','hbm/HomeButton3/home_nosave.csv']:
        raw=archive.get(path)
        if not raw.startswith(b'\xfe\xff'):raise ValueError('Room HOME encoding')
        text=raw[2:].decode('utf-16-be');matches=list(re.finditer(r'"([^"]*)"',text))
        if len(matches)!=40 or not matches[21].group(1).startswith('Return to the Wii Menu?')or not matches[31].group(1).startswith('Reset the software?'):raise ValueError('Room HOME ten-column identity')
        targets=list(messages)
        if path.endswith('/home.csv'):
            for i in(2,3):targets[i]+='\r\n'+SAVE_WARNING
        for i in reversed(range(40)):
            start,end=matches[i].span(1);text=text[:start]+targets[i//10]+text[end:]
        if len(re.findall(r'"([^"]*)"',text))!=40:raise ValueError('Room HOME ABI changed')
        archive=ChannelArchive(archive.replace(path,b'\xfe\xff'+text.encode('utf-16-be')))
        records.append(dict(file=path,rows=4,columns=10))
    return archive.compact(),records
