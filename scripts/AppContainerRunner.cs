// Per-session no-capability AppContainer. Ref: Microsoft LaunchAppContainer sample.
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.ComponentModel;
using System.Net;
using System.Net.Sockets;
class AppContainerRunner {
 [StructLayout(LayoutKind.Sequential)] struct SC {public IntPtr Sid,Capabilities;public uint Count,Reserved;}
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct SI {public int cb;public string reserved,desktop,title;public int x,y,xs,ys,xc,yc,fill,flags;public short show,cb2;public IntPtr reserved2,input,output,error;}
 [StructLayout(LayoutKind.Sequential)] struct SIX {public SI si;public IntPtr attributes;}
 [StructLayout(LayoutKind.Sequential)] struct PI {public IntPtr process,thread;public int pid,tid;}
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)] static extern int CreateAppContainerProfile(string n,string d,string desc,IntPtr caps,uint count,out IntPtr sid);
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)] static extern int DeleteAppContainerProfile(string n);
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool ConvertSidToStringSid(IntPtr sid,out IntPtr text);
 [DllImport("advapi32.dll",SetLastError=true)] static extern IntPtr FreeSid(IntPtr sid);
 [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr p);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr type,IntPtr value,IntPtr size,IntPtr prev,IntPtr ret);
 [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr p);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string exe,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref SIX si,out PI pi);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr h);
 [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr h,out uint code);
 [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr a,string name);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr h,int c,IntPtr info,uint length);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr token);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr t,int c,IntPtr b,int n,out int needed);
 static string Quote(string s) {return "\""+s.Replace("\"","\\\"")+"\"";}
 static void Check(bool ok){if(!ok)throw new Win32Exception(Marshal.GetLastWin32Error());}
 static int Acl(string root,string arg) {
  ProcessStartInfo info=new ProcessStartInfo("icacls.exe",Quote(root)+" "+arg+" /T /Q");info.UseShellExecute=false;info.CreateNoWindow=true;info.RedirectStandardOutput=true;info.RedirectStandardError=true;
  using(Process p=Process.Start(info)){p.StandardOutput.ReadToEnd();p.StandardError.ReadToEnd();p.WaitForExit();return p.ExitCode;}
 }
 static int Run(IntPtr sid,string exe,string arguments,string cwd) {
  IntPtr size=IntPtr.Zero,list=IntPtr.Zero,value=IntPtr.Zero,token=IntPtr.Zero,job=IntPtr.Zero;PI pi=new PI();bool resumed=false;
  try {
   InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);list=Marshal.AllocHGlobal(size);Check(InitializeProcThreadAttributeList(list,1,0,ref size));
   SC sc=new SC();sc.Sid=sid;value=Marshal.AllocHGlobal(Marshal.SizeOf(sc));Marshal.StructureToPtr(sc,value,false);
   Check(UpdateProcThreadAttribute(list,0,(IntPtr)0x20009,value,(IntPtr)Marshal.SizeOf(sc),IntPtr.Zero,IntPtr.Zero));
   SIX si=new SIX();si.si.cb=Marshal.SizeOf(si);si.attributes=list;
   Check(CreateProcess(exe,new StringBuilder(Quote(exe)+" "+arguments),IntPtr.Zero,IntPtr.Zero,false,0x80000|4|0x08000000,IntPtr.Zero,cwd,ref si,out pi));
   Check(OpenProcessToken(pi.process,8,out token));IntPtr buf=Marshal.AllocHGlobal(4096);
   try {int needed;Check(GetTokenInformation(token,29,buf,4096,out needed));if(Marshal.ReadInt32(buf)!=1)throw new Exception("Child is not AppContainer");Check(GetTokenInformation(token,30,buf,4096,out needed));if(Marshal.ReadInt32(buf)!=0)throw new Exception("Child has capabilities");}finally{Marshal.FreeHGlobal(buf);}
   // KILL_ON_JOB_CLOSE prevents a detached emulator if the helper disappears.
   job=CreateJobObject(IntPtr.Zero,null);Check(job!=IntPtr.Zero);IntPtr limits=Marshal.AllocHGlobal(144);
   try {for(int i=0;i<144;i++)Marshal.WriteByte(limits,i,0);Marshal.WriteInt32(limits,16,0x2000);Check(SetInformationJobObject(job,9,limits,144));Check(AssignProcessToJobObject(job,pi.process));}finally{Marshal.FreeHGlobal(limits);}
   ResumeThread(pi.thread);resumed=true;WaitForSingleObject(pi.process,0xffffffff);uint code;GetExitCodeProcess(pi.process,out code);return (int)code;
  }finally {
   if(pi.process!=IntPtr.Zero&&!resumed)TerminateProcess(pi.process,10);
   if(job!=IntPtr.Zero)CloseHandle(job);if(token!=IntPtr.Zero)CloseHandle(token);if(pi.thread!=IntPtr.Zero)CloseHandle(pi.thread);if(pi.process!=IntPtr.Zero)CloseHandle(pi.process);
   if(list!=IntPtr.Zero){DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);}if(value!=IntPtr.Zero)Marshal.FreeHGlobal(value);
  }
 }
 static int Main(string[] args) {
  string name="kwce.gc."+Guid.NewGuid().ToString("N");IntPtr sid=IntPtr.Zero,sidText=IntPtr.Zero;string root=null,sidString=null;bool registered=false;
  try {
   if(args.Length<2)throw new Exception("Expected runtime root and probe/menu mode");root=Path.GetFullPath(args[0]);
   string project=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"../../.."));
   bool approved=false;foreach(string revision in new string[]{"gc-v2","gc-v3","gc-v4","gc-v5"})if(String.Equals(root,Path.Combine(project,"workspace","sandbox",revision),StringComparison.OrdinalIgnoreCase))approved=true;
   if(!approved||!Directory.Exists(root))throw new Exception("Runtime outside approved workspace");
   int hr=CreateAppContainerProfile(name,name,"Offline Korean Wii local GC experiment",IntPtr.Zero,0,out sid);if(hr<0)Marshal.ThrowExceptionForHR(hr);registered=true;
   Check(ConvertSidToStringSid(sid,out sidText));sidString=Marshal.PtrToStringUni(sidText);
   // Include DELETE_CHILD for atomic replacement within the runtime only.
   if(Acl(root,"/grant "+Quote("*"+sidString+":(OI)(CI)(RD,WD,AD,REA,WEA,X,DC,RA,WA,D,RC,S)"))!=0)throw new Exception("Runtime ACL failed");
   string temp=Path.Combine(root,"temp");Directory.CreateDirectory(temp);Environment.SetEnvironmentVariable("TEMP",temp);Environment.SetEnvironmentVariable("TMP",temp);
   File.WriteAllText(Path.Combine(temp,"atomic-old.txt"),"old");File.WriteAllText(Path.Combine(temp,"atomic-new.txt"),"new");
   string report=Path.Combine(root,"network-probe.json");if(File.Exists(report))File.Delete(report);
   // Positive-control a local UDP receiver outside the container. Successful
   // send() inside a container is not proof of network delivery.
   int rc;bool udpBlocked;
   using(UdpClient receiver=new UdpClient(new IPEndPoint(IPAddress.Loopback,0))) {
    int port=((IPEndPoint)receiver.Client.LocalEndPoint).Port;receiver.Client.ReceiveTimeout=1000;
    using(UdpClient control=new UdpClient()){control.Send(new byte[]{67},1,new IPEndPoint(IPAddress.Loopback,port));}
    IPEndPoint peer=new IPEndPoint(IPAddress.Any,0);byte[] controlData=receiver.Receive(ref peer);if(controlData.Length!=1||controlData[0]!=67)throw new Exception("UDP positive control failed");
    rc=Run(sid,Path.Combine(root,"NetProbe.exe"),Quote(report)+" "+port,root);
    try {receiver.Receive(ref peer);udpBlocked=false;}catch(SocketException e){if(e.SocketErrorCode!=SocketError.TimedOut)throw;udpBlocked=true;}
   }
   if(!udpBlocked)throw new Exception("AppContainer UDP reached loopback receiver");
   if(rc!=0||!File.Exists(report)||!File.ReadAllText(report).Contains("\"passed\":true"))throw new Exception("OS network probe did not pass");
   string probeText=File.ReadAllText(report);File.WriteAllText(report,probeText.Substring(0,probeText.Length-1)+",\"udp_loopback_positive_control\":true,\"udp_loopback_delivery_blocked\":true}");
   Console.WriteLine("PASS: OS AppContainer token, zero capabilities, TCP access denied; UDP API result is diagnostic only");
   if(args[1]=="probe")return 0;
   if(args[1]!="menu"&&args[1]!="disc")throw new Exception("Only probe/menu/disc supported");
   if(args[1]!="menu"&&!root.EndsWith("gc-v5",StringComparison.OrdinalIgnoreCase))throw new Exception("GC diagnostics require v5");
   string exe=Path.Combine(root,"Dolphin-x64","Dolphin.exe");string user=Path.Combine(root,"user");
   string boot=args[1]=="disc"?" --exec "+Quote(Path.Combine(root,"disc/GALJ01.iso")):" --nand_title 0000000100000002";
   int childCode=Run(sid,exe,"--user "+Quote(user)+boot,Path.GetDirectoryName(exe));
   File.WriteAllText(Path.Combine(root,"child-exit.json"),"{\"exit_code_hex\":\""+((uint)childCode).ToString("x8")+"\"}");return childCode;
  }catch(Exception e){Console.Error.WriteLine("Sandbox refused: "+e.GetType().Name+": "+e.Message);return 1;}
  finally {
   if(root!=null&&sidString!=null)Acl(root,"/remove:g "+Quote("*"+sidString));
   if(sidText!=IntPtr.Zero)LocalFree(sidText);if(sid!=IntPtr.Zero)FreeSid(sid);if(registered)DeleteAppContainerProfile(name);
  }
 }
}
