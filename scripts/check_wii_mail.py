"""Private synthetic mail round trip; never register or use a console account."""
import json,sys,threading,urllib.parse,urllib.request
from email import policy
from email.parser import BytesParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.wii_mail import MailConfig,MailReplay,cgi,korean_message,parse_cgi,synthetic_config,validate_synthetic_message,WIILINK_URLS
from kwce.wii_mail_http import server

def roundtrip():
    replay=MailReplay();credentials=replay.credentials();http=server(replay);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}/cgi-bin/'
    def post(operation,fields):
        request=urllib.request.Request(base+operation+'.cgi',data=urllib.parse.urlencode(fields).encode())
        with urllib.request.urlopen(request,timeout=5)as response:return response.headers.get('Content-Type'),response.read(1024*1024)
    try:
        _,registered=post('account',dict(mlid=credentials['mlid']))
        if parse_cgi(registered).get('cd')!='100':raise ValueError('Synthetic registration failed')
        original=korean_message('한국어 메일 시험','Wii 알림판의 한글 수신 시험입니다.\n직접 만든 예시 문장입니다.')
        replay.seed(original)
        _,checked=post('check',dict(mlchkid=credentials['mlchkid'],chlng='12345'))
        if not replay.verify_check('12345',checked):raise ValueError('Mail challenge verification failed')
        content_type,received=post('receive',dict(mlid=credentials['mlid'],passwd=credentials['passwd'],maxsize=200*1024))
        multipart=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+content_type+'\r\n\r\n').encode()+received)
        parts=list(multipart.iter_parts())
        if len(parts)!=2 or validate_synthetic_message(parts[1].get_payload(decode=True))!=validate_synthetic_message(original):raise ValueError('Korean MIME receive differs')
        _,deleted=post('delete',dict(mlid=credentials['mlid'],passwd=credentials['passwd'],delnum=1))
        if parse_cgi(deleted).get('deletenum')!='1'or replay.summary()['queued']!=0:raise ValueError('Mail acknowledgement failed')
        # Exercise native multipart send authentication and a second receive.
        boundary='kwce-post';auth=f'mlid={credentials["mlid"]}\r\npasswd={credentials["passwd"]}'.encode()
        body=b''.join(b'--'+boundary.encode()+b'\r\nContent-Disposition: form-data; name="'+name+b'"\r\n\r\n'+value+b'\r\n'for name,value in[(b'mlid',auth),(b'm1',original)])+b'--'+boundary.encode()+b'--\r\n'
        req=urllib.request.Request(base+'send.cgi',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
        with urllib.request.urlopen(req,timeout=5)as response:sent=response.read()
        if parse_cgi(sent).get('m1')!='100'or replay.summary()['queued']!=1:raise ValueError('Synthetic send failed')
        before=synthetic_config();after=before.with_endpoints(WIILINK_URLS)
        if before.raw[:156]!=after.raw[:156]or before.raw[796:1020]!=after.raw[796:1020]:raise ValueError('Endpoint patch altered identity/state')
        return dict(protocol_roundtrip=True,korean_mime_preserved=True,challenge_verified=True,acknowledgement_verified=True,synthetic_send_verified=True,endpoint_patch_preserves_identity_state=True,external_transport=False,dolphin_receive_supported=False,hardware_success_verified=False)
    finally:http.shutdown();http.server_close();thread.join(5)

def main():
    result=roundtrip();number=1
    while(ROOT/f'workspace/private/wii-mail-test-{number}.json').exists():number+=1
    (ROOT/f'workspace/private/wii-mail-test-{number}.json').write_text(json.dumps(result,indent=2))
    print('PASS: synthetic mail account/check/receive/delete/send, Korean MIME, challenge and config preservation; no external transport; hardware unverified')
if __name__=='__main__':main()
