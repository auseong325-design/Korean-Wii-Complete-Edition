// Local Food (Demae) fixture server. Dispatches /nwapi.php on the plain `action`
// parameter (helper v2; v1 wrongly base64-decoded it) and serves pre-generated
// Shift-JIS XML from local-feed/nwapi.
// Browse actions only; cart/order/auth actions are intentionally unmapped (404),
// so no order-accepting endpoint exists even locally. No proxying, no request/
// body/identity persistence (the log keeps action, sanitized area code and
// parameter names only). Derived from scripts/ChannelTestServer.cs.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Text.RegularExpressions;
class FoodServer {
 static string root,feed,log;
 static readonly object mutex=new object();
 static readonly HashSet<string> served=new HashSet<string>(new string[]{
  "webApi_document_template","webApi_area_list","webApi_category_list","webApi_shop_list",
  "webApi_area_shopinfo","webApi_shop_one","webApi_menu_list","webApi_item_list","webApi_item_one"});
 static void Finish(TcpClient c,NetworkStream s) {
  try{c.Client.Shutdown(SocketShutdown.Send);s.ReadTimeout=500;byte[] buffer=new byte[4096];int total=0,n;
   while(total<1048576&&(n=s.Read(buffer,0,buffer.Length))>0)total+=n;
  }catch(IOException){}catch(SocketException){}
 }
 static void Reply(NetworkStream s,int status,byte[] data,bool head,string type) {
  byte[] h=Encoding.ASCII.GetBytes("HTTP/1.1 "+status+(status==200?" OK":" Not Found")+"\r\nContent-Type: "+type+"\r\nContent-Length: "+data.Length+"\r\nConnection: close\r\n\r\n");
  s.Write(h,0,h.Length);if(!head)s.Write(data,0,data.Length);s.Flush();
 }
 static string Param(string hay,string key) {
  Match m=Regex.Match(hay,@"(?:^|[?&])"+Regex.Escape(key)+@"=([^&\s]*)");
  return m.Success?m.Groups[1].Value:null;
 }
 static string DecodeAction(string raw) {
  if(raw==null)return null;
  try{string v=Uri.UnescapeDataString(raw).Replace('-','+').Replace('_','/').Replace('*','=');
   return Encoding.ASCII.GetString(Convert.FromBase64String(v));}catch{return null;}
 }
 // Helper v2: the channel sends `action` as a plain webApi_* name, which is how the
 // pinned WiiLink food-server reads it (request.args/form["action"]). v1 base64-decoded
 // it and answered 404 (channel error 333404). Base64 stays only as a fallback whose
 // result must still be a webApi_* name.
 static readonly Regex ActionName=new Regex(@"^webApi_[A-Za-z_]{1,48}$");
 static string ResolveAction(string raw) {
  if(raw==null)return null;
  string plain;try{plain=Uri.UnescapeDataString(raw);}catch{return null;}
  if(ActionName.IsMatch(plain))return plain;
  string decoded=DecodeAction(raw);
  return decoded!=null&&ActionName.IsMatch(decoded)?decoded:null;
 }
 // Parameter NAMES only (never values), for diagnosing unmapped requests.
 static string Keys(string hay) {
  List<string> keys=new List<string>();
  if(!string.IsNullOrEmpty(hay))foreach(string part in hay.Split('&')){int eq=part.IndexOf('=');string k=eq<0?part:part.Substring(0,eq);
   if(Regex.IsMatch(k,@"^[A-Za-z0-9_]{1,32}$")&&!keys.Contains(k))keys.Add(k);}
  return keys.Count==0?"-":string.Join(",",keys.ToArray());
 }
 static void Handle(TcpClient client) {
  using(client){NetworkStream s=client.GetStream();s.ReadTimeout=10000;s.WriteTimeout=10000;
   MemoryStream head=new MemoryStream();uint last=0;
   try{while(true){int b=s.ReadByte();if(b<0)return;head.WriteByte((byte)b);last=(last<<8)|(byte)b;if(last==0x0d0a0d0a)break;if(head.Length>16384)return;}}catch(IOException){if(head.Length==0)return;}
   string[] lines=Encoding.ASCII.GetString(head.ToArray()).Split(new string[]{"\r\n"},StringSplitOptions.None);
   string[] req=lines[0].Split(' ');if(req.Length!=3)return;
   if(req[0]!="GET"&&req[0]!="HEAD"&&req[0]!="POST")return;
   string full=req[1];string path=full.Split('?')[0];string query=full.Contains("?")?full.Substring(full.IndexOf('?')+1):"";
   if(path.Contains("://")){Uri u;if(Uri.TryCreate(path,UriKind.Absolute,out u)){path=u.AbsolutePath;query=u.Query.TrimStart('?');}}
   int length=0;foreach(string line in lines)if(line.StartsWith("Content-Length:",StringComparison.OrdinalIgnoreCase))int.TryParse(line.Substring(15).Trim(),out length);
   if(length<0||length>1048576)return;
   byte[] body=new byte[0];
   if(length>0){MemoryStream bs=new MemoryStream();byte[] buf=new byte[4096];int remain=length,n;while(remain>0&&(n=s.Read(buf,0,Math.Min(remain,buf.Length)))>0){bs.Write(buf,0,n);remain-=n;}body=bs.ToArray();}
   string safe=Regex.Replace(path,@"[^A-Za-z0-9/_\.\-]","_");
   // Images: serve one placeholder for any item/logo request.
   if(path.StartsWith("/itemimg/")||path.StartsWith("/logoimg2/")){
    string img=Path.Combine(feed,"img","placeholder.jpg");
    bool ex=File.Exists(img);byte[] data=ex?File.ReadAllBytes(img):new byte[0];
    lock(mutex)File.AppendAllText(log,"image\t"+safe+"\t"+(ex?200:404)+"\n");
    Reply(s,ex?200:404,data,req[0]=="HEAD","image/jpeg");Finish(client,s);return;
   }
   if(path=="/nwapi.php"){
    string bodyText=Encoding.ASCII.GetString(body);
    bool post=req[0]=="POST";
    string raw=post?Param(bodyText,"action"):Param(query,"action");
    // WiiLink treats a POST without a form `action` as the channel's error report and
    // answers with the document template; nothing from the report is stored here.
    bool report=post&&raw==null;
    string action=report?"webApi_document_template":ResolveAction(raw);
    string areaCode=Param(query,"areaCode")??Param(bodyText,"areaCode");
    string area=areaCode==null?"-":Regex.Replace(areaCode.Length>16?areaCode.Substring(0,16):areaCode,@"[^0-9A-Za-z_\-]","_");
    lock(mutex)File.AppendAllText(log,"nwapi\t"+req[0]+"\t"+(report?"error-report":(action??"?"))+"\tarea="+area+"\tkeys="+Keys(query)+";"+Keys(bodyText)+"\n");
    if(action!=null&&served.Contains(action)){
     string file=null;
     if(areaCode!=null){string cand=Path.Combine(feed,"nwapi",action+"_"+area+".xml");if(File.Exists(cand))file=cand;}
     if(file==null)file=Path.Combine(feed,"nwapi",action+".xml");
     if(File.Exists(file)){byte[] data=File.ReadAllBytes(file);Reply(s,200,data,req[0]=="HEAD","text/xml; charset=Shift_JIS");Finish(client,s);return;}
    }
    // Unknown or deliberately blocked (cart/order/auth) action.
    Reply(s,404,new byte[0],req[0]=="HEAD","text/xml");Finish(client,s);return;
   }
   lock(mutex)File.AppendAllText(log,"unmapped\t"+safe+"\n");
   Reply(s,404,new byte[0],req[0]=="HEAD","text/plain");Finish(client,s);
  }
 }
 static int Main(string[] args){try{
  root=Path.GetFullPath(args[0]);feed=Path.Combine(root,"local-feed");log=Path.Combine(root,"access-http.tsv");
  TcpListener listener=new TcpListener(IPAddress.Parse("127.0.0.2"),80);listener.Start();File.WriteAllText(Path.Combine(root,"feed-ready.txt"),"listening");
  while(true){TcpClient c=listener.AcceptTcpClient();Thread t=new Thread(()=>{try{Handle(c);}catch(Exception e){lock(mutex)File.AppendAllText(log,"request-failed\t"+e.GetType().Name+"\n");}});t.IsBackground=true;t.Start();}
 }catch(Exception e){try{File.WriteAllText(Path.Combine(root,"feed-server-error.txt"),e.GetType().Name+": "+e.Message);}catch{}return 3;}}
}
