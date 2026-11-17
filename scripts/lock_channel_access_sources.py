"""Pin newly fetched public protocol references, with no generated inputs."""
import json,subprocess
from audit_sd import ROOT,sha256

SOURCES={
 'workspace/channels/mii-contest/references/access-nas-source':'https://github.com/WiiLink24/wfc-server.git',
 'workspace/channels/nintendo/references/access-web-source':'https://github.com/WiiLink24/NintendoChannelWeb.git',
 'workspace/channels/nintendo/references/access-wc24crypt-source':'https://github.com/SketchMaster2001/libwc24crypt.git',
 'workspace/channels/mii-contest/references/access-mii-db-source':'https://github.com/Alex9303/Mii-Database-Editor.git',
}

def main():
 for rel,url in SOURCES.items():
  folder=ROOT/rel;out=folder.with_name(folder.name+'-lock.json')
  revision=subprocess.run(['git','-C',str(folder),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
  if subprocess.run(['git','-C',str(folder),'status','--porcelain'],capture_output=True,text=True,check=True).stdout.strip():raise ValueError('Public source checkout is modified')
  result=dict(repository=url,revision=revision,files=[dict(path=p.relative_to(folder).as_posix(),sha256=sha256(p))for p in sorted(folder.rglob('*'))if p.is_file()and'.git'not in p.relative_to(folder).parts])
  if out.exists():
   if json.loads(out.read_text())!=result:raise ValueError('Existing public reference lock differs')
  else:out.write_text(json.dumps(result,indent=2))
  print(f'Pinned {folder.name}: {revision}, {len(result["files"])} public files')

if __name__=='__main__':main()
