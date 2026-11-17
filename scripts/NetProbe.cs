// Synthetic OS isolation probe. No console data, DNS or real service endpoints.
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Principal;
class NetProbe {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool MoveFileEx(string a,string b,uint flags);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr t,int c,IntPtr b,int n,out int needed);
 static int TokenValue(int type) { int needed;IntPtr p=Marshal.AllocHGlobal(4096);try {if(!GetTokenInformation(WindowsIdentity.GetCurrent().Token,type,p,4096,out needed))throw new Exception("Token query failed");return Marshal.ReadInt32(p);}finally{Marshal.FreeHGlobal(p);} }
 static bool Denied(SocketType type,ProtocolType protocol,string host) {
  using(Socket s=new Socket(AddressFamily.InterNetwork,type,protocol)) {
   s.SendTimeout=1500;s.ReceiveTimeout=1500;
   try { if(type==SocketType.Dgram){s.Connect(new IPEndPoint(IPAddress.Parse(host),9));s.Send(new byte[]{80});byte[] response=new byte[16];s.Receive(response);}
    else {IAsyncResult a=s.BeginConnect(host,9,null,null);if(!a.AsyncWaitHandle.WaitOne(2000))return false;s.EndConnect(a);}
   }catch(SocketException e){return e.SocketErrorCode==SocketError.AccessDenied;}
   return false;
  }
 }
 static int Main(string[] args) {
  try {
   bool ac=TokenValue(29)!=0;int caps=TokenValue(30);
   bool tcp=Denied(SocketType.Stream,ProtocolType.Tcp,"192.0.2.1");
   bool udp=Denied(SocketType.Dgram,ProtocolType.Udp,"198.51.100.1");
   bool loop=Denied(SocketType.Stream,ProtocolType.Tcp,"127.0.0.1");
   string folder=Path.GetDirectoryName(args[0]);string old=Path.Combine(folder,"temp","atomic-old.txt"),fresh=Path.Combine(folder,"temp","atomic-new.txt");
   bool atomicReplace=MoveFileEx(fresh,old,1);int atomicError=atomicReplace?0:Marshal.GetLastWin32Error();
   if(args.Length>1)using(UdpClient sender=new UdpClient()){try{sender.Send(new byte[]{80},1,new IPEndPoint(IPAddress.Loopback,int.Parse(args[1])));}catch(SocketException e){if(e.SocketErrorCode!=SocketError.AccessDenied)throw;}}
   // UDP send is asynchronous: API success/timeout is not delivery evidence.
   // The security boundary is the OS token with no network capabilities.
   // Keep UDP's observed result, rather than falsely claiming WSAEACCES.
   bool pass=ac&&caps==0&&tcp;
   string report="{\"passed\":"+pass.ToString().ToLower()+",\"app_container\":"+ac.ToString().ToLower()+",\"capabilities\":"+caps+",\"tcp_access_denied\":"+tcp.ToString().ToLower()+",\"udp_access_denied\":"+udp.ToString().ToLower()+",\"loopback_access_denied\":"+loop.ToString().ToLower()+",\"atomic_replace\":"+atomicReplace.ToString().ToLower()+",\"atomic_replace_win32_error\":"+atomicError+"}";
   File.WriteAllText(args[0],report);return pass?0:2;
  }catch(Exception e){try{File.WriteAllText(args[0],"{\"passed\":false,\"error_type\":\""+e.GetType().Name+"\"}");}catch{}return 3;}
 }
}
