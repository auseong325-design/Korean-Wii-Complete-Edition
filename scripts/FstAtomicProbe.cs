// Synthetic v6-only replacement diagnostics. Never reads console/NAND data.
using System;
using System.IO;
using System.Runtime.InteropServices;
partial class NetProbe {
 static string FstAtomicProbe(string folder,out bool passed) {
  string dir=Path.Combine(folder,"temp","fst-atomic-probe");Directory.CreateDirectory(dir);
  string dest=Path.Combine(dir,"synthetic-fst.bin"),temp=dest+".xxx";
  File.WriteAllText(dest,"synthetic old");int success=0,firstError=0;
  for(int i=0;i<20;i++) {
   File.WriteAllText(temp,"synthetic "+i);
   if(MoveFileEx(temp,dest,1))success++;else if(firstError==0)firstError=Marshal.GetLastWin32Error();
  }
  File.WriteAllText(temp,"synthetic held-reader replacement");bool heldResult;int heldError;
  using(FileStream reader=new FileStream(dest,FileMode.Open,FileAccess.Read,FileShare.ReadWrite)) {
   heldResult=MoveFileEx(temp,dest,1);heldError=heldResult?0:Marshal.GetLastWin32Error();
  }
  // A failed replacement leaves the source intact. Retry only our synthetic
  // source after closing the deliberately held reader.
  if(heldResult)File.WriteAllText(temp,"synthetic after-reader replacement");
  bool after=MoveFileEx(temp,dest,1);int afterError=after?0:Marshal.GetLastWin32Error();
  passed=success==20&&!heldResult&&(heldError==5||heldError==32||heldError==33)&&after;
  return "{\"attempts\":20,\"successes\":"+success+",\"first_error\":"+firstError+",\"held_reader_rename_succeeded\":"+heldResult.ToString().ToLower()+",\"held_reader_error\":"+heldError+",\"after_reader_close_succeeded\":"+after.ToString().ToLower()+",\"after_reader_close_error\":"+afterError+",\"passed\":"+passed.ToString().ToLower()+"}";
 }
}
