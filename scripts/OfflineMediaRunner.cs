// Per-session no-capability AppContainer running Dolphin plus the local FeedServer
// (same container, so 127.0.0.2 loopback works while outside networks stay blocked).
// Derived from the News runner; ref: Microsoft LaunchAppContainer sample.
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.ComponentModel;
using System.Net;
using System.Net.Sockets;
class OfflineMediaRunner {
 static IntPtr serverJob=IntPtr.Zero;
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
   ResumeThread(pi.thread);resumed=true;if(WaitForSingleObject(pi.process,60000)==258){TerminateProcess(pi.process,12);throw new Exception("Encoder timeout");}uint code;GetExitCodeProcess(pi.process,out code);return (int)code;
  }finally {
   if(pi.process!=IntPtr.Zero&&!resumed)TerminateProcess(pi.process,10);
   if(job!=IntPtr.Zero)CloseHandle(job);if(token!=IntPtr.Zero)CloseHandle(token);if(pi.thread!=IntPtr.Zero)CloseHandle(pi.thread);if(pi.process!=IntPtr.Zero)CloseHandle(pi.process);
   if(list!=IntPtr.Zero){DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);}if(value!=IntPtr.Zero)Marshal.FreeHGlobal(value);
  }
 }


 static int Main(string[] args) {
  string name="kwce.media."+Guid.NewGuid().ToString("N");IntPtr sid=IntPtr.Zero,sidText=IntPtr.Zero;string sidString=null;
  string work=AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
  if(Path.GetFileName(work)!="wiiroom-video-v2")return 2;
  string project=Path.GetFullPath(Path.Combine(work,"../../.."));string bin=Path.Combine(project,"tools/mobipeg-v2.3/bin");
  try {
   if(args.Length!=1||Path.GetFileName(args[0])!=args[0])throw new Exception("Expected local argument file");
   string cmd=File.ReadAllText(Path.Combine(work,args[0]));
   if(cmd.Contains("http:")||cmd.Contains("https:")||cmd.Contains("tcp:")||cmd.Contains("udp:"))throw new Exception("No network inputs");
   int hr=CreateAppContainerProfile(name,name,"Offline synthetic Room media",IntPtr.Zero,0,out sid);if(hr<0)Marshal.ThrowExceptionForHR(hr);
   Check(ConvertSidToStringSid(sid,out sidText));sidString=Marshal.PtrToStringUni(sidText);
   if(Acl(work,"/grant:r "+Quote("*"+sidString+":(OI)(CI)F"))!=0||Acl(bin,"/grant:r "+Quote("*"+sidString+":(OI)(CI)RX"))!=0)throw new Exception("Sandbox ACL");
   Environment.SetEnvironmentVariable("SENTRY_DSN","");
   int result=Run(sid,Path.Combine(bin,"ffmpeg.exe"),cmd,work);
   Console.WriteLine("Media capability0 child exit="+((uint)result).ToString("x8"));return result;
  }catch(Exception e){Console.Error.WriteLine("Media refused: "+e.GetType().Name+": "+e.Message);return 1;}
  finally{if(sidString!=null){Acl(work,"/remove:g "+Quote("*"+sidString));Acl(bin,"/remove:g "+Quote("*"+sidString));}if(sidText!=IntPtr.Zero)LocalFree(sidText);if(sid!=IntPtr.Zero){FreeSid(sid);DeleteAppContainerProfile(name);}}
 }
}
