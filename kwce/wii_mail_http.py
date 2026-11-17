"""Loopback-only, in-memory WC24 CGI replay; no SMTP or production adapter."""
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import parse_qsl,urlsplit
from .wii_mail import MailReplay,cgi

def server(replay=None):
    replay=replay or MailReplay()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):self.send_error(405)
        def do_POST(self):
            if self.client_address[0]!='127.0.0.1':self.send_error(403);return
            parsed=urlsplit(self.path)
            paths={f'/cgi-bin/{p}.cgi':p for p in('account','check','receive','delete','send')}
            if parsed.path not in paths or parsed.query or parsed.netloc:self.send_error(404);return
            try:
                if self.headers.get('Transfer-Encoding'):raise ValueError('Chunked request refused')
                length=int(self.headers.get('Content-Length','-1'))
                if not 0<length<=1024*1024:raise ValueError('Request size')
                self.connection.settimeout(3);raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('Truncated request')
                content_type=self.headers.get('Content-Type','')
                if '\r'in content_type or'\n'in content_type:raise ValueError('Invalid MIME header')
                if content_type.startswith('application/x-www-form-urlencoded'):
                    pairs=parse_qsl(raw.decode('utf-8'),keep_blank_values=True,strict_parsing=True,max_num_fields=24)
                elif content_type.startswith('multipart/form-data'):
                    message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+content_type+'\r\n\r\n').encode()+raw)
                    if not message.is_multipart()or message.defects:raise ValueError('Invalid multipart')
                    pairs=[]
                    for part in message.iter_parts():
                        if part.get_filename()is not None or part.get_content_disposition()!='form-data':raise ValueError('File upload refused')
                        name=part.get_param('name',header='content-disposition');value=part.get_payload(decode=True)
                        if not name or value is None:raise ValueError('Invalid field')
                        pairs.append((name,value if name.startswith('m')and name[1:].isdecimal()else value.decode('utf-8')))
                else:raise ValueError('Unsupported request encoding')
                if len(pairs)>24 or len({k for k,_ in pairs})!=len(pairs):raise ValueError('Duplicate/excessive fields')
                fields=dict(pairs);operation=paths[parsed.path]
                response=getattr(replay,operation)(fields)
                response_type,response=response if operation=='receive'else('text/plain; charset=ascii',response)
            except(ValueError,UnicodeError,TimeoutError):response_type,response='text/plain',cgi(350)
            self.send_response(200);self.send_header('Content-Type',response_type);self.send_header('Content-Length',str(len(response)))
            self.send_header('X-Wii-Mail-Check-Span','10');self.send_header('X-Wii-Mail-Download-Span','10');self.send_header('X-Wii-Download-Span','10')
            self.end_headers();self.wfile.write(response)
    result=HTTPServer(('127.0.0.1',0),Handler);result.replay=replay;return result
