"""Only the isolated Dolphin hardware test NAND; synthesize scheduler rows."""
import shutil,struct,sys
from audit_sd import ROOT
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
    stopped();bed=(ROOT/'workspace/sandbox/hardware-test-v1').resolve()
    if bed!=(ROOT/'workspace/sandbox/hardware-test-v1').resolve() or not (bed/'user/Wii').is_dir():raise ValueError('Unexpected test bed')
    wii=bed/'user/Wii';dl=wii/'shared2/wc24/nwc24dl.bin';raw=bytearray(dl.read_bytes())
    if len(raw)!=0xf800 or raw[:8]!=bytes.fromhex('5763446c00000001'):raise ValueError('Unexpected test scheduler')
    backup=ROOT/'workspace/private/diagnostic-testbed-before-v1'
    if backup.exists():raise ValueError('Existing test evidence preserved')
    backup.mkdir();shutil.copy2(dl,backup/'nwc24dl.bin')
    lib=load_library();nand=lib.nand.EmuNAND(wii)
    rows=[('news',ROOT/'workspace/channels/news/build-v22/news-ko-personal.wad','0001000248414745'),('room',ROOT/'workspace/hardware/kwce-loading-news20-room51-v1/kwce/wiiroom/korean.wad','000100014843494a')]
    for _,path,tid in rows:
        t=lib.title.Title();t.load_wad(path.read_bytes())
        if t.tmd.title_id.lower()!=tid:raise ValueError('Wrong test title')
        nand.install_title(t)
    pairs=[(0x00010002,0x48414745,7,-106,b'http://127.0.0.1:9/news-test'),(0x00010001,0x4843494a,3,-42,b'http://127.0.0.1:9/room-test')]
    slots=[i for i in range(120) if not int.from_bytes(raw[2048+512*i+12:2048+512*i+16],'big')]
    if len(slots)<len(pairs):raise ValueError('No free synthetic task slots')
    for i,(hi,lo,count,err,url) in zip(slots,pairs):
        at=2048+512*i;row=bytearray(512);struct.pack_into('>HBBIII',row,0,i,3,0,0x20,hi,lo)
        struct.pack_into('>H',row,26,count);struct.pack_into('>i',row,32,err);struct.pack_into('>H',row,30,10)
        row[180:180+len(url)]=url;raw[at:at+512]=row
    dl.write_bytes(raw);print('PASS: isolated test NAND has two known channels and two fictional task records')
if __name__=='__main__':main()
