// Local News replay only. This process and Dolphin share one AppContainer.
// No proxying, remote fetches, request bodies, or directory enumeration.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

class FeedServer {
 static string root, feed, log;
 static readonly object LogLock=new object();
 static void Reply(NetworkStream s,int status,byte[] data,bool head) {
  string reason=status==200?"OK":status==404?"Not Found":"Bad Request";
  byte[] h=Encoding.ASCII.GetBytes("HTTP/1.1 "+status+" "+reason+"\r\nContent-Type: application/octet-stream\r\nContent-Length: "+data.Length+"\r\nConnection: close\r\n\r\n");
  s.Write(h,0,h.Length);if(!head)s.Write(data,0,data.Length);s.Flush();
 }
 static void Handle(TcpClient client) {
  using(client) {
   NetworkStream s=client.GetStream();s.ReadTimeout=10000;s.WriteTimeout=10000;
   MemoryStream head=new MemoryStream();uint last=0;
   while(true){int b=s.ReadByte();if(b<0)return;head.WriteByte((byte)b);last=(last<<8)|(byte)b;if(last==0x0d0a0d0a)break;if(head.Length>16384)return;}
   string[] lines=Encoding.ASCII.GetString(head.ToArray()).Split(new string[]{"\r\n"},StringSplitOptions.None);
   string[] req=lines[0].Split(' ');string host="";
   foreach(string l in lines)if(l.StartsWith("Host:",StringComparison.OrdinalIgnoreCase))host=l.Substring(5).Trim();
   if(req.Length!=3||(req[0]!="GET"&&req[0]!="HEAD")||(host!="127.0.0.2"&&host!="127.0.0.2:80"&&host!="news.wiilink.ca")) {Reply(s,400,new byte[0],false);return;}
   string path=req[1],prefix="/v2/1/136/news.bin.";bool valid=path.Length==prefix.Length+2&&path.StartsWith(prefix)&&char.IsDigit(path[prefix.Length])&&char.IsDigit(path[prefix.Length+1]);
   // Exact route whitelist also rejects traversal and query strings.
   int hour=0;if(valid)valid=int.TryParse(path.Substring(path.Length-2),out hour)&&hour>=0&&hour<24;
   string file=valid?Path.Combine(feed,"news.bin."+hour.ToString("00")):null;
   bool exists=file!=null&&File.Exists(file);byte[] data=exists?File.ReadAllBytes(file):new byte[0];
   lock(LogLock)File.AppendAllText(log,DateTime.UtcNow.ToString("o")+"\t"+req[0]+"\t"+(valid?hour.ToString("00"):"rejected-route")+"\t"+(exists?200:404)+"\t"+data.Length+"\n");
   Reply(s,exists?200:404,data,req[0]=="HEAD");
  }
 }
 static int Main(string[] args) {
  try {
  root=Path.GetFullPath(args[0]);feed=Path.Combine(root,"local-feed/news.wiilink.ca/v2/1/136");log=Path.Combine(root,"feed-log-v2.tsv");
  if(!Directory.Exists(feed))return 2;
  TcpListener listener=new TcpListener(IPAddress.Parse("127.0.0.2"),80);listener.Start();
  File.WriteAllText(Path.Combine(root,"feed-ready.txt"),"listening");
  while(true){TcpClient c=listener.AcceptTcpClient();Thread t=new Thread(()=>{try{Handle(c);}catch{lock(LogLock)File.AppendAllText(log,"request-failed\n");}});t.IsBackground=true;t.Start();}
  }catch(Exception e){try{File.WriteAllText(Path.Combine(root,"feed-server-error.txt"),e.GetType().Name+": "+e.Message);}catch{}return 3;}
 }
}
