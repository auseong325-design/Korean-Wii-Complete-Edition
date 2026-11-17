"""WiiLink mail configuration audit and isolated synthetic protocol replay.

No production client, SMTP connection, console identifiers or credentials are
logged. Configuration patching returns bytes and never writes a NAND file.
"""
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import hashlib,hmac,json,re,secrets,struct
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
OPERATIONS=('account','check','receive','delete','send')
WIILINK_URLS=tuple(f'http://mtw.rc24.xyz/cgi-bin/{name}.cgi'for name in OPERATIONS)

def checksum(data):return sum(struct.unpack('>255I',data[:1020]))&0xffffffff

@dataclass(frozen=True)
class MailConfig:
    raw:bytes
    def __post_init__(self):
        if len(self.raw)!=1024 or self.raw[:8]!=bytes.fromhex('5763436600000008'):raise ValueError('Invalid WC24 config header')
        if checksum(self.raw)!=int.from_bytes(self.raw[1020:],'big'):raise ValueError('WC24 checksum mismatch')
        if int.from_bytes(self.raw[16:20],'big')>31 or self.stage not in(0,1,2):raise ValueError('Invalid WC24 registration state')
        for url in self.urls:
            parsed=urlsplit(url)
            if parsed.scheme not in('http','https')or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:raise ValueError('Invalid WC24 URL')
    @property
    def stage(self):return int.from_bytes(self.raw[20:24],'big')
    @property
    def urls(self):
        return tuple(self.raw[156+128*i:284+128*i].split(b'\0')[0].decode('ascii')for i in range(5))
    def summary(self):
        return dict(valid=True,registration_stage=('Initial','Generated','Registered')[self.stage],
                    wiilink_endpoints=self.urls==WIILINK_URLS,
                    credentials_present=bool(self.raw[88:120].strip(b'\0'))and bool(self.raw[120:156].strip(b'\0')),
                    live_registration_tested=False)
    def with_endpoints(self,urls):
        if len(urls)!=5:raise ValueError('Expected five mail endpoints')
        result=bytearray(self.raw)
        for i,url in enumerate(urls):
            encoded=url.encode('ascii')
            if len(encoded)>127 or b'\0'in encoded or any(c<32 for c in encoded):raise ValueError('Mail endpoint exceeds fixed field')
            result[156+128*i:284+128*i]=encoded+bytes(128-len(encoded))
        struct.pack_into('>I',result,1020,checksum(result))
        return MailConfig(bytes(result))

def synthetic_config():
    raw=bytearray(1024);struct.pack_into('>II',raw,0,0x57634366,8)
    raw[24:40]=b'@offline.invalid'
    for i in range(5):
        value=f'http://127.0.0.1:9/mail-disabled/{i}'.encode();raw[156+128*i:156+128*i+len(value)]=value
    struct.pack_into('>I',raw,1020,checksum(raw));return MailConfig(bytes(raw))

def protocol_key():
    """Read a pinned public protocol constant locally; never emit its bytes."""
    lock=json.loads((ROOT/'configs/mail-tvguide-references.lock.json').read_text())
    row=next(r for r in lock['files']if r['repository']=='WiiLink24/Mail-Server'and r['upstream_path']=='check.go')
    raw=(ROOT/row['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Mail protocol source differs')
    match=re.search(rb'var MailHMACKey\s*=\s*\[\]byte\{([^}]+)\}',raw)
    if not match:raise ValueError('Public mail protocol key unavailable')
    key=bytes(int(v.strip(),0)for v in match[1].split(b',')if v.strip())
    if len(key)!=20:raise ValueError('Public mail protocol constant size')
    return key

def cgi(code=100,**fields):
    return ('cd='+str(code)+'\r\n'+'\r\n'.join(k+'='+str(v)for k,v in fields.items())+'\r\n').encode('ascii')

def parse_cgi(raw):
    result={}
    for line in raw.decode('ascii').splitlines():
        if '='in line:
            key,value=line.split('=',1)
            if key in result:raise ValueError('Duplicate mail response field')
            result[key]=value
    return result

def korean_message(subject,body):
    if any(c in subject for c in '\r\n'):raise ValueError('Invalid mail subject')
    message=EmailMessage(policy=policy.SMTP)
    message['From']='sender@kwce.invalid';message['To']='receiver@kwce.invalid';message['Subject']=subject
    message['X-KWCE-Synthetic']='1';message.set_content(body,charset='utf-8',cte='base64')
    return message.as_bytes()

def validate_synthetic_message(raw):
    if not 0<len(raw)<=200*1024:raise ValueError('Synthetic mail size')
    message=BytesParser(policy=policy.default).parsebytes(raw)
    if message.defects or message.get('X-KWCE-Synthetic')!='1':raise ValueError('Only own synthetic messages are accepted')
    for field in('From','To'):
        value=message.get(field)
        if not value or len(value.addresses)!=1 or value.addresses[0].domain!='kwce.invalid':raise ValueError('External mail recipient refused')
    if message.get_content_type()!='text/plain'or message.get_content_charset()!='utf-8':raise ValueError('Only synthetic Korean text mail is supported')
    body=message.get_content();return str(message['Subject']),body

class MailReplay:
    """In-memory account/check/receive/delete/send, with no external transport."""
    def __init__(self):
        self._id='w'+str(10**15+secrets.randbelow(10**15));self._password=secrets.token_hex(12);self._checkid=secrets.token_hex(16)
        self._key=protocol_key();self._messages={};self._delivered=set();self._next=1;self._flag='kwce-empty'.ljust(22,'0');self._registered=False
    def credentials(self):return dict(mlid=self._id,passwd=self._password,mlchkid=self._checkid)
    def account(self,fields):
        if not hmac.compare_digest(fields.get('mlid',''),self._id):return cgi(610)
        if self._registered:return cgi(211)
        self._registered=True;return cgi(**self.credentials())
    def seed(self,raw):
        validate_synthetic_message(raw);number=self._next;self._next+=1;self._messages[number]=raw
        self._flag=secrets.token_hex(11);return number
    def auth(self,fields):return hmac.compare_digest(fields.get('mlid',''),self._id)and hmac.compare_digest(fields.get('passwd',''),self._password)
    def check(self,fields):
        if not hmac.compare_digest(fields.get('mlchkid',''),self._checkid):return cgi(321)
        challenge=fields.get('chlng','')
        if not challenge.isdecimal()or len(challenge)>20:return cgi(320)
        flag=self._flag;interval='10';message=f'{challenge}\n{self._id}\n{flag}\n{interval}'.encode()
        digest=hmac.new(self._key,message,hashlib.sha1).hexdigest()
        return cgi(res=digest,**{'mail.flag':flag,'interval':interval})
    def verify_check(self,challenge,response):
        fields=parse_cgi(response)
        if fields.get('cd')!='100':return False
        data=f'{challenge}\n{self._id}\n{fields.get("mail.flag","")}\n{fields.get("interval","")}'.encode()
        return hmac.compare_digest(fields.get('res',''),hmac.new(self._key,data,hashlib.sha1).hexdigest())
    def receive(self,fields):
        if not self.auth(fields):return 'text/plain',cgi(250)
        try:limit=int(fields.get('maxsize',''))
        except ValueError:return 'text/plain',cgi(330)
        if not 1<=limit<=1024*1024:return 'text/plain',cgi(330)
        boundary='kwce-synthetic-mail';parts=[];count=0;size=0
        for number,raw in self._messages.items():
            part=b'\r\n--'+boundary.encode()+b'\r\nContent-Type: text/plain\r\n\r\n'+raw
            if size+len(part)>limit:break
            parts.append(part);size+=len(part);count+=1;self._delivered.add(number)
        head=b'--'+boundary.encode()+b'\r\nContent-Type: text/plain\r\n\r\nThis part is ignored.\r\n\r\n'+cgi(mailnum=count,mailsize=size,allnum=len(self._messages))
        return f'multipart/mixed; boundary={boundary}',head+b''.join(parts)+b'\r\n--'+boundary.encode()+b'--\r\n'
    def delete(self,fields):
        if not self.auth(fields):return cgi(250)
        try:count=int(fields.get('delnum',''))
        except ValueError:return cgi(340)
        if count<0 or count>len(self._delivered):return cgi(340)
        for number in sorted(self._delivered)[:count]:self._messages.pop(number);self._delivered.remove(number)
        self._flag=secrets.token_hex(11);return cgi(deletenum=count)
    def send(self,fields):
        # Native KD packs the auth pair into the multipart mlid field.
        auth=dict(line.split('=',1)for line in fields.get('mlid','').splitlines()if '='in line)
        if not self.auth(auth):return cgi(250)
        messages={key:value for key,value in fields.items()if re.fullmatch(r'm\d+',key)}
        if not 1<=len(messages)<=16:return cgi(351)
        checked=[]
        for name,value in messages.items():
            raw=value if isinstance(value,bytes)else value.encode('utf-8')
            # Wii's optional envelope is separated from the MIME payload by DATA.
            if b'\r\nDATA\r\n'in raw:raw=raw.split(b'\r\nDATA\r\n',1)[1]
            try:validate_synthetic_message(raw)
            except ValueError:return cgi(350)
            checked.append((name,raw))
        for _,raw in checked:self.seed(raw)
        return cgi(**{name:100 for name,_ in checked})
    def summary(self):return dict(synthetic=True,queued=len(self._messages),delivered_pending_ack=len(self._delivered),external_transport=False)
