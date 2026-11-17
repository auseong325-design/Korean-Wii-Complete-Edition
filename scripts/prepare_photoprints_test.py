"""Isolated Korean Photo Prints test profile + capability-0 read-only helper.

Clones the sanitized votes test profile, forces Korean locale with SD and
WiiLink disabled, installs build-v1 into a private EmuNAND, and compiles a
zero-capability helper: a runner derived from the shared FeedRunner plus a
dedicated operation-routing server that serves ONLY the read-only catalog/notice
operations and refuses every order/upload/payment operation. No Dolphin is run.
"""
import configparser,json,os,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce import photoprints_fixtures as fx
import launch_dolphin as launcher

PROFILE='photoprints-test-v1-user';TITLE='000100014843444a'
BASE=ROOT/'workspace/sandbox/photoprints-test-v1';HELPER=ROOT/'tools/photoprints-sandbox/v1/bin'

SERVER_CS=r'''// Local Photo Prints fixture server: routes by the Operation header, serves only
// read-only catalog/notice responses, refuses every order/upload operation, and
// never logs or persists a request body. No proxying.
using System;using System.IO;using System.Net;using System.Net.Sockets;using System.Text;
using System.Threading;using System.Collections.Generic;using System.Text.RegularExpressions;
class PhotoPrintsServer {
 static string root,feed,log;static readonly object mutex=new object();
 static readonly HashSet<string> ReadOnly=new HashSet<string>(){"getItemInformation","getExemptionInformation"};
 static void Finish(TcpClient c,NetworkStream s){try{c.Client.Shutdown(SocketShutdown.Send);s.ReadTimeout=500;byte[] b=new byte[4096];int t=0,n;while(t<1048576&&(n=s.Read(b,0,b.Length))>0)t+=n;}catch(IOException){}catch(SocketException){}}
 static byte[] LocalNas(byte[] body,bool profanity){
  string form=Encoding.ASCII.GetString(body);string action="";
  Match m=Regex.Match(form,@"(?:^|&)action=([^&]*)");
  if(m.Success){try{string v=Uri.UnescapeDataString(m.Groups[1].Value).Replace('-','+').Replace('_','/').Replace('*','=');action=Encoding.ASCII.GetString(Convert.FromBase64String(v));}catch{return null;}}
  var f=new Dictionary<string,string>{{"retry","0"},{"datetime",DateTime.UtcNow.ToString("yyyyMMddHHmmss")}};
  if(profanity){f.Add("returncd","000");f.Add("prwords","0");}
  else if(action=="login"){f.Add("returncd","001");f.Add("locator","127.0.0.2");f.Add("challenge","LOCALTEST");f.Add("token","LOCAL-TEST-TOKEN");}
  else if(action=="svcloc"){f.Add("returncd","007");f.Add("statusdata","Y");f.Add("servicetoken","LOCAL-TEST-TOKEN");f.Add("token","LOCAL-TEST-TOKEN");f.Add("svchost","127.0.0.2");}
  else return null;
  var parts=new List<string>();foreach(var p in f)parts.Add(p.Key+"="+Convert.ToBase64String(Encoding.ASCII.GetBytes(p.Value)).Replace('+','-').Replace('/','_').Replace('=','*'));
  return Encoding.ASCII.GetBytes(String.Join("&",parts.ToArray())+"\0");
 }
 static void Reply(NetworkStream s,int status,byte[] data,bool head){
  byte[] h=Encoding.ASCII.GetBytes("HTTP/1.1 "+status+(status==200?" OK":" Not Found")+"\r\nContent-Type: application/octet-stream\r\nContent-Length: "+data.Length+"\r\nConnection: close\r\n\r\n");
  s.Write(h,0,h.Length);if(!head)s.Write(data,0,data.Length);s.Flush();
 }
 static void Handle(TcpClient client){
  using(client){NetworkStream s=client.GetStream();s.ReadTimeout=10000;s.WriteTimeout=10000;
   MemoryStream head=new MemoryStream();uint last=0;
   try{while(true){int b=s.ReadByte();if(b<0)return;head.WriteByte((byte)b);last=(last<<8)|(byte)b;if(last==0x0d0a0d0a)break;if(head.Length>16384)return;}}catch(IOException){if(head.Length==0)throw;}
   string[] lines=Encoding.ASCII.GetString(head.ToArray()).Split(new string[]{"\r\n"},StringSplitOptions.None);
   string[] req=lines[0].Split(' ');if(req.Length!=3)return;
   if(req[0]!="GET"&&req[0]!="HEAD"&&req[0]!="POST")return;
   string path=req[1].Split('?')[0];if(path.Contains("://")){Uri u;if(!Uri.TryCreate(path,UriKind.Absolute,out u))return;path=u.AbsolutePath;}
   string op="";foreach(string line in lines){if(line.StartsWith("Operation:",StringComparison.OrdinalIgnoreCase))op=line.Substring(10).Trim();}
   int length=0;foreach(string line in lines)if(line.StartsWith("Content-Length:",StringComparison.OrdinalIgnoreCase))int.TryParse(line.Substring(15).Trim(),out length);
   if(length<0||length>1048576)return;
   bool nas=path=="/ac"||path=="/pr";MemoryStream nasBody=nas?new MemoryStream():null;
   byte[] discard=new byte[4096];while(length>0){int n=s.Read(discard,0,Math.Min(length,discard.Length));if(n<=0)return;if(nas)nasBody.Write(discard,0,n);length-=n;}
   string tag=Regex.Replace(op,"[^A-Za-z]","");
   if(nas){byte[] r=LocalNas(nasBody.ToArray(),path=="/pr");nasBody.Dispose();Array.Clear(discard,0,discard.Length);Reply(s,r==null?404:200,r??new byte[0],false);lock(mutex)File.AppendAllText(log,"nas\t"+(r==null?404:200)+"\n");Finish(client,s);return;}
   bool allowed=path.EndsWith("WPOperationServlet")&&ReadOnly.Contains(op);
   string file=allowed?Path.GetFullPath(Path.Combine(feed,"op_"+tag+".bin")):null;
   bool ok=file!=null&&file.StartsWith(feed+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)&&File.Exists(file);
   byte[] data=ok?File.ReadAllBytes(file):new byte[0];
   lock(mutex)File.AppendAllText(log,"op\t"+tag+"\t"+(ok?200:404)+"\n");
   Reply(s,ok?200:404,data,req[0]=="HEAD");Finish(client,s);
  }
 }
 static int Main(string[] args){try{
  root=Path.GetFullPath(args[0]);feed=Path.Combine(root,"local-feed");log=Path.Combine(root,"access-http.tsv");
  TcpListener l=new TcpListener(IPAddress.Parse("127.0.0.2"),80);l.Start();File.WriteAllText(Path.Combine(root,"feed-ready.txt"),"listening");
  while(true){TcpClient c=l.AcceptTcpClient();Thread t=new Thread(()=>{try{Handle(c);}catch(Exception e){lock(mutex)File.AppendAllText(log,"request-failed\t"+e.GetType().Name+"\n");}});t.IsBackground=true;t.Start();}
 }catch(Exception e){try{File.WriteAllText(Path.Combine(root,"feed-server-error.txt"),e.GetType().Name+": "+e.Message);}catch{}return 3;}}
}
'''


def register():
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/photoprints-test-v1'
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)


def main():
    stopped()
    if BASE.exists() or HELPER.exists():raise SystemExit('Existing Photo Prints profile/helper preserved')
    source=ROOT/'workspace/sandbox/votes-test-v1';before=snapshot(source)
    (PRIVATE/'photoprints-template-before-v1.json').write_text(json.dumps(before,indent=2));BASE.mkdir(parents=True)
    for name in ['user','Dolphin-x64']:shutil.copytree(source/name,BASE/name,ignore=shutil.ignore_patterns('Logs','Cache','ScreenShots','StateSaves'))
    shutil.copy2(source/'NetProbe.exe',BASE/'NetProbe.exe')
    path=BASE/'user/Config/Dolphin.ini';cfg=configparser.ConfigParser(strict=False);cfg.optionxform=str;cfg.read(path,encoding='utf-8-sig')
    for section in cfg.sections():
        for key,value in cfg[section].items():cfg[section][key]=value.replace(str(source),str(BASE)).replace(source.as_posix(),BASE.as_posix())
    cfg['Core']['DefaultISO']='';cfg['Core']['EnableWiiLink']='False';cfg['Core']['OverrideRegionSettings']='True'
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:cfg['Core'][key]='False'
    with path.open('w',encoding='utf-8') as f:cfg.write(f)
    lib=load_library();title=lib.title.Title();wad=ROOT/'workspace/channels/photoprints/build-v1/photoprints-ko-local-test.wad'
    title.load_wad(wad.read_bytes());lib.nand.EmuNAND(BASE/'user/Wii').install_title(title)
    # Digicam needs the SPD title (00010008-HCCJ) and IOS58; reuse the Korean SPD build read-only.
    from kwce import photoprints_personal_data as pdata
    personal=pdata.install(BASE/'user/Wii','keep')
    register();launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    # Local feed: read-only responses only.
    feed=BASE/'local-feed';feed.mkdir()
    for op,body in fx.responses().items():(feed/f'op_{op}.bin').write_bytes(body)
    (feed/'fixture-manifest.json').write_text(json.dumps(fx.manifest(),ensure_ascii=False,indent=2))
    # Capability-0 helper: runner (from shared FeedRunner) + read-only server.
    runner=(ROOT/'scripts/FeedRunner.cs').read_text()
    runner=(runner.replace('"news-v1"','"photoprints-test-v1"')
        .replace('0001000248414745',TITLE).replace('class FeedRunner','class PhotoPrintsRunner')
        .replace('FeedServer.exe','PhotoPrintsServer.exe'))
    if '"photoprints-test-v1"' not in runner or TITLE not in runner:raise ValueError('Runner derivation failed')
    HELPER.mkdir(parents=True)
    (HELPER/'PhotoPrintsRunner.cs').write_text(runner,encoding='utf-8')
    (HELPER/'PhotoPrintsServer.cs').write_text(SERVER_CS,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    for src in sorted(HELPER.glob('*.cs')):
        subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(src.with_suffix('.exe')),str(src)],check=True,capture_output=True)
    locked=[BASE/'Dolphin-x64/Dolphin.exe',BASE/'NetProbe.exe',*(p for p in sorted(HELPER.iterdir()) if p.suffix in('.cs','.exe')),feed/'fixture-manifest.json']
    manifest=json.loads((wad.with_name('build-manifest.json')).read_text(encoding='utf-8'))
    (ROOT/'configs/photoprints-runtime.lock.json').write_text(json.dumps(dict(profile=PROFILE,title_id=TITLE,capability_count=0,
        external_network_allowed=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p)) for p in locked],
        builds={'1':manifest['wad_sha256']},personal_data=personal),indent=2))
    (ROOT/'workspace/channels/photoprints/active-build.json').write_text(json.dumps(dict(revision=1,wad_sha256=manifest['wad_sha256']),indent=2))
    if snapshot(source)!=before:raise ValueError('Photo Prints template changed')
    print('Installed Photo Prints v1 in isolated Korean profile; capability-0 read-only helper ready (no order/upload operations)')
if __name__=='__main__':main()
