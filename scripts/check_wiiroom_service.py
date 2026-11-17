"""Anonymous static bootstrap checks; no console headers, registration or uploads."""
import ast,datetime,json,sys,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree.ElementTree import fromstring
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,sha256

def main():
    load_library();from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    source=ROOT/'external/channel-tools/WiiRoom-reference/first.py'
    lock=json.loads((ROOT/'configs/wiiroom-server-references.lock.json').read_text())
    expected=next(r['sha256']for r in lock['files']if r['path']=='first.py')
    if sha256(source.read_bytes())!=expected:raise ValueError('Pinned bootstrap protocol changed')
    constants={}
    for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name)and target.id in('FIRST_BIN_KEY','FIRST_BIN_IV'):constants[target.id]=ast.literal_eval(node.value)
    def get(url):
        request=urllib.request.Request(url,headers={'User-Agent':'KWCE-anonymous-static-check/1'})
        with urllib.request.urlopen(request,timeout=15)as reply:
            body=reply.read(1024*1024+1)
            if len(body)>1024*1024:raise ValueError('Static response size')
            return reply.status,body,reply.geturl()!=url
    status,encrypted,redirect=get('http://prod.wiilink24.com/conf/first.bin')
    plain=unpad(AES.new(constants['FIRST_BIN_KEY'],AES.MODE_CBC,iv=constants['FIRST_BIN_IV']).decrypt(encrypted),16)
    fields={n.tag:n.text for n in fromstring(plain)}
    bases={}
    for name in('url1','url2','url3'):
        value=fields[name];parsed=urlsplit(value)
        if parsed.scheme!='http'or parsed.hostname!=name+'.prod.wiilink24.com'or parsed.username or parsed.password:raise ValueError('Unexpected static service origin')
        bases[name]=value
    paths=[('url1','conf/eula.xml'),('url1','conf/datetime.xml'),('url1','event/today.xml'),('url1','special/all.xml'),('url2','reginfo.cgi'),('url3','pay/event/today.xml')]
    rows=[]
    for host,path in paths:
        try:
            code,body,redirected=get(bases[host]+path)
            rows.append(dict(service=host,path=path,status=code,xml_root=fromstring(body).tag,redirected=redirected))
        except Exception as error:rows.append(dict(service=host,path=path,error=type(error).__name__))
    result=dict(checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),anonymous=True,bootstrap_status=status,bootstrap_redirected=redirect,maintenance=fields.get('maint'),routes=rows,hardware_success_verified=False)
    number=1
    while(ROOT/f'workspace/private/wiiroom-service-check-v{number}.json').exists():number+=1
    (ROOT/f'workspace/private/wiiroom-service-check-v{number}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Room anonymous bootstrap HTTP',status,'; static XML routes',sum(r.get('status')==200 for r in rows),'/',len(rows),'; hardware success unverified')
if __name__=='__main__':main()
