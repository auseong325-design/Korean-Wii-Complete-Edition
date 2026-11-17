"""Inventory user-facing text of the pinned WiiLink Set Personal Data source.

Tokenizes C/C++ (comments, char and string literals, adjacent-literal
concatenation) and classifies each literal by the call that receives it:
gettext (`_()`), GuiText (its constructors call gettext themselves),
WindowPrompt/MessageWindow/KeyboardDataEntry (labels passed on to GuiText),
printf (libogc console), or other (paths, formats). Output is a summary;
`--write` stores workspace/channels/personal-data/text-inventory-v1.json once.
"""
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'workspace/channels/personal-data/references/set-personal-data-18fa5a7d'
OUT=ROOT/'workspace/channels/personal-data/text-inventory-v1.json'
GUI_CALLS={'_':'gettext','GuiText':'GuiText','WindowPrompt':'GuiText-arg','MessageWindow':'GuiText-arg','KeyboardDataEntry':'GuiText-arg','OnScreenKeyboard':'GuiText-arg'}
CONSOLE={'printf':'console','sprintf':'format','swprintf':'format','fprintf':'console'}

def tokens(text):
    """Yield (kind, value, offset); kinds: str, id, punct. Comments/char literals skipped."""
    i=0;n=len(text)
    while i<n:
        c=text[i]
        if text.startswith('//',i):i=text.find('\n',i);i=n if i<0 else i;continue
        if text.startswith('/*',i):j=text.find('*/',i+2);i=n if j<0 else j+2;continue
        if c=="'":
            j=i+1
            while j<n and text[j]!="'":j+=2 if text[j]=='\\' else 1
            i=j+1;continue
        if c=='"' or(c=='L'and i+1<n and text[i+1]=='"'):
            start=i;i+=1 if c=='"' else 2;buf=[]
            while i<n and text[i]!='"':
                if text[i]=='\\':buf.append(text[i:i+2]);i+=2
                else:buf.append(text[i]);i+=1
            yield('wstr'if c=='L'else'str',''.join(buf),start);i+=1;continue
        if c.isalpha()or c=='_':
            j=i
            while j<n and(text[j].isalnum()or text[j]=='_'):j+=1
            yield('id',text[i:j],i);i=j;continue
        if c.isspace():i+=1;continue
        yield('punct',c,i);i+=1

def literals(text):
    """Return [(literal, call, decl_type, offset)] with adjacent literals joined."""
    out=[];stack=[];prev=[];pending=None
    def flush():
        nonlocal pending
        if pending:out.append(pending);pending=None
    for kind,value,at in tokens(text):
        if kind in('str','wstr'):
            if pending and pending[4]==kind:pending=(pending[0]+value,)+pending[1:]
            else:
                flush();call,decl=stack[-1]if stack else(None,None);pending=(value,call,decl,at,kind)
            continue
        flush()
        if kind=='punct'and value=='(':
            name=prev[-1][1]if prev and prev[-1][0]=='id'else None
            decl=prev[-2][1]if len(prev)>1 and prev[-2][0]=='id'else None
            stack.append((name,decl))
        elif kind=='punct'and value==')'and stack:stack.pop()
        elif kind=='punct'and value==';':stack.clear()
        prev=(prev+[(kind,value)])[-3:]
    flush();return out

def classify(call,decl):
    for name in(call,decl):
        if name in GUI_CALLS:return GUI_CALLS[name]
    if call in CONSOLE:return CONSOLE[call]
    return 'other'

def survey(source=SOURCE):
    rows={};console=[];other=0
    for path in sorted(source.glob('source/**/*')):
        if path.suffix not in('.c','.cpp','.h'):continue
        text=path.read_bytes().decode('latin-1');rel=path.relative_to(source).as_posix()
        for value,call,decl,at,kind in literals(text):
            if not re.search('[A-Za-z]',value):continue
            how=classify(call,decl)
            if how in('gettext','GuiText','GuiText-arg'):
                row=rows.setdefault(value,dict(msgid=value,via=set(),files=set(),occurrences=0))
                row['via'].add(how);row['files'].add(rel);row['occurrences']+=1
            elif how=='console':console.append(dict(file=rel,text=value))
            else:other+=1
    msgids=[dict(r,via=sorted(r['via']),files=sorted(r['files']))for r in sorted(rows.values(),key=lambda r:r['msgid'])]
    return dict(source='WiiLink24/set-personal-data@18fa5a7d',msgids=msgids,console_messages=console,other_literals=other)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');args=ap.parse_args()
    result=survey()
    print('UI msgids:',len(result['msgids']),'console printf strings:',len(result['console_messages']),'other literals:',result['other_literals'])
    for row in result['msgids']:print(' ',json.dumps(row['msgid'],ensure_ascii=False),'/'.join(row['via']),row['occurrences'])
    if args.write:
        raw=json.dumps(result,ensure_ascii=False,indent=1)+'\n'
        if OUT.exists():
            if OUT.read_text(encoding='utf-8')!=raw:raise SystemExit('Existing inventory preserved and differs')
        else:OUT.write_text(raw,encoding='utf-8')
if __name__=='__main__':sys.exit(main())
