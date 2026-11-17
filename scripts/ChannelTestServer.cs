// Local fixture server: no proxying, no request/body/identity persistence.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Text.RegularExpressions;
class ChannelTestServer {
 static string root,feed,log;
 static Dictionary<string,string> routes=new Dictionary<string,string>();
 static readonly object mutex=new object();
 static void Finish(TcpClient c,NetworkStream s) {
  // Closing a socket with unread request bytes sends RST on Windows. Native
  // Host rewrites may leave trailing bytes, and the Wii rejects that reset even
  // after reading a complete successful response. Half-close then drain, bounded.
  try{c.Client.Shutdown(SocketShutdown.Send);s.ReadTimeout=500;byte[] buffer=new byte[4096];int total=0,n;
   while(total<1048576&&(n=s.Read(buffer,0,buffer.Length))>0)total+=n;
  }catch(IOException){}catch(SocketException){}
 }
 static byte[] LocalNas(byte[] body,bool profanity) {
  // Decode only the protocol action; no identity is parsed, stored or reflected.
  string form=Encoding.ASCII.GetString(body);string action="";
  Match m=Regex.Match(form,@"(?:^|&)action=([^&]*)");
  if(m.Success){try{string value=Uri.UnescapeDataString(m.Groups[1].Value).Replace('-','+').Replace('_','/').Replace('*','=');action=Encoding.ASCII.GetString(Convert.FromBase64String(value));}catch{return null;}}
  var fields=new Dictionary<string,string>{{"retry","0"},{"datetime",DateTime.UtcNow.ToString("yyyyMMddHHmmss")}};
  if(profanity){fields.Add("returncd","000");fields.Add("prwords","0");}
  else if(action=="acctcreate"){fields.Add("returncd","002");fields.Add("userid","1");}
  else if(action=="login"){fields.Add("returncd","001");fields.Add("locator","127.0.0.2");fields.Add("challenge","LOCALTEST");fields.Add("token","LOCAL-TEST-TOKEN");}
  else if(action=="svcloc"){fields.Add("returncd","007");fields.Add("statusdata","Y");fields.Add("servicetoken","LOCAL-TEST-TOKEN");fields.Add("token","LOCAL-TEST-TOKEN");fields.Add("svchost","127.0.0.2");}
  else return null;
  var parts=new List<string>();foreach(var p in fields)parts.Add(p.Key+"="+Convert.ToBase64String(Encoding.ASCII.GetBytes(p.Value)).Replace('+','-').Replace('/','_').Replace('=','*'));
  return Encoding.ASCII.GetBytes(String.Join("&",parts.ToArray())+"\0");
 }
 static void Reply(NetworkStream s,int status,byte[] data,bool head) {
  // Successful reference responses omit X-RESULT; its presence denotes an
  // application error and zero is not a success response in Mii's HTTP client.
  byte[] h=Encoding.ASCII.GetBytes("HTTP/1.1 "+status+(status==200?" OK":" Not Found")+"\r\nContent-Type: application/octet-stream\r\nContent-Length: "+data.Length+"\r\nConnection: close\r\n\r\n");
  s.Write(h,0,h.Length);if(!head)s.Write(data,0,data.Length);s.Flush();
 }
 static void Handle(TcpClient client) {
  using(client){NetworkStream s=client.GetStream();s.ReadTimeout=10000;s.WriteTimeout=10000;
   MemoryStream head=new MemoryStream();uint last=0;bool compat=false;
   try{while(true){int b=s.ReadByte();if(b<0)return;head.WriteByte((byte)b);s.ReadTimeout=1000;last=(last<<8)|(byte)b;if(last==0x0d0a0d0a)break;if(head.Length>16384)return;}}
   catch(IOException){if(head.Length==0)throw;string partial=Encoding.ASCII.GetString(head.ToArray());if(!partial.Contains("\r\n"))throw;compat=true;lock(mutex)File.AppendAllText(log,"compat-partial-header\tbytes="+head.Length+"\n");}
   string[] lines=Encoding.ASCII.GetString(head.ToArray()).Split(new string[]{"\r\n"},StringSplitOptions.None);
   string[] req=lines[0].Split(' ');if(req.Length!=3)return;
   if(req[0]!="GET"&&req[0]!="HEAD"&&req[0]!="POST")return;
   // Query and body can contain synthetic console data. Never log or persist them.
   string path=req[1].Split('?')[0];if(path.Contains("://")){Uri u;if(!Uri.TryCreate(path,UriKind.Absolute,out u))return;path=u.AbsolutePath;}
   string safe=Regex.Replace(path,@"[0-9]{6,}","ID");safe=Regex.Replace(safe,@"[^A-Za-z0-9/_\.\-]","_");
   lock(mutex)File.AppendAllText(log,"received\t"+req[0]+"\t"+safe+"\n");
   foreach(string line in lines)if(line.StartsWith("Expect:",StringComparison.OrdinalIgnoreCase)&&line.IndexOf("100-continue",StringComparison.OrdinalIgnoreCase)>=0){byte[] interim=Encoding.ASCII.GetBytes("HTTP/1.1 100 Continue\r\n\r\n");s.Write(interim,0,interim.Length);s.Flush();}
   int length=0;foreach(string line in lines)if(line.StartsWith("Content-Length:",StringComparison.OrdinalIgnoreCase))int.TryParse(line.Substring(15).Trim(),out length);
   bool chunked=Array.Exists(lines,line=>line.StartsWith("Transfer-Encoding:",StringComparison.OrdinalIgnoreCase)&&line.IndexOf("chunked",StringComparison.OrdinalIgnoreCase)>=0);
   lock(mutex)File.AppendAllText(log,"request-framing\tlength="+length+"\tchunked="+chunked+"\tcompat="+compat+"\n");
   if(length<0||length>1048576)return;
   // With the native Host-rewrite compatibility path, all available bytes
   // have already been consumed. Never retain or attempt to parse that body.
   if(compat)length=0;
   bool nas=path=="/ac"||path=="/pr";MemoryStream nasBody=nas?new MemoryStream():null;
   byte[] discard=new byte[4096];while(length>0){int n=s.Read(discard,0,Math.Min(length,discard.Length));if(n<=0)return;if(nas)nasBody.Write(discard,0,n);length-=n;}
   if(nas){byte[] reply=LocalNas(nasBody.ToArray(),path=="/pr");nasBody.Dispose();Array.Clear(discard,0,discard.Length);Reply(s,reply==null?404:200,reply??new byte[0],false);lock(mutex)File.AppendAllText(log,"local-nas-response\t"+(reply==null?404:200)+"\n");Finish(client,s);return;}
   string mapped;bool found=routes.TryGetValue(req[0]+" "+path,out mapped)||routes.TryGetValue("* "+path,out mapped);
   string file=found?Path.GetFullPath(Path.Combine(feed,mapped)):null;
   if(file!=null&&!file.StartsWith(feed+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))return;
   bool exists=file!=null&&File.Exists(file);byte[] data=exists?File.ReadAllBytes(file):new byte[0];
   lock(mutex)File.AppendAllText(log,DateTime.UtcNow.ToString("o")+"\t"+req[0]+"\t"+safe+"\t"+(exists?200:404)+"\t"+data.Length+"\n");
   Reply(s,exists?200:404,data,req[0]=="HEAD");
   Finish(client,s);
  }
 }
 static int Main(string[] args){try{
  root=Path.GetFullPath(args[0]);feed=Path.Combine(root,"local-feed");log=Path.Combine(root,"access-http.tsv");
  foreach(string line in File.ReadAllLines(Path.Combine(feed,"routes.tsv"))){if(line.Length==0||line.StartsWith("#"))continue;string[] r=line.Split('\t');if(r.Length!=2)throw new Exception("Route format");routes.Add(r[0],r[1]);}
  TcpListener listener=new TcpListener(IPAddress.Parse("127.0.0.2"),80);listener.Start();File.WriteAllText(Path.Combine(root,"feed-ready.txt"),"listening");
  while(true){TcpClient c=listener.AcceptTcpClient();Thread t=new Thread(()=>{try{Handle(c);}catch(Exception e){lock(mutex)File.AppendAllText(log,"request-failed\t"+e.GetType().Name+"\n");}});t.IsBackground=true;t.Start();}
 }catch(Exception e){try{File.WriteAllText(Path.Combine(root,"feed-server-error.txt"),e.GetType().Name+": "+e.Message);}catch{}return 3;}}
}
