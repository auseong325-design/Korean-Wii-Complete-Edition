"""Expose only the approved TV Guide test title on page one; preserve all slots."""
import hashlib,struct
from audit_sd import ROOT,PRIVATE
from prepare_channel_access import stopped
from prepare_tvguide_test import BASE,PROFILE,register,TITLE
import launch_dolphin as launcher

def main():
    stopped();register();path=BASE/'user/Wii/title/00000001/00000002/data/iplsave.bin';raw=path.read_bytes()
    if len(raw)!=0x4c0 or raw[:4]!=b'RIPL'or struct.unpack_from('>II',raw,4)!=(0x4c0,3)or hashlib.md5(raw[:0x4b0]).digest()!=raw[0x4b0:]:raise ValueError('TV test menu layout identity')
    slots=[raw[0x10+16*i:0x20+16*i]for i in range(48)];matching=[i for i,s in enumerate(slots)if s[8:16]==bytes.fromhex(TITLE)]
    if len(matching)!=1:raise ValueError('Run the approved test menu once to discover the TV title')
    source=matching[0];destination=1
    if source==destination and struct.unpack_from('>I',raw,12)[0]==0:print('TV Guide already visible on first menu page');return
    number=1
    while(PRIVATE/f'tvguide-menu-before-{number}.bin').exists():number+=1
    (PRIVATE/f'tvguide-menu-before-{number}.bin').write_bytes(raw)
    result=bytearray(raw);slots[source],slots[destination]=slots[destination],slots[source]
    result[0x10:0x310]=b''.join(slots)
    cache=[raw[0x320+8*i:0x328+8*i]for i in range(48)];cache[source],cache[destination]=cache[destination],cache[source];result[0x320:0x4a0]=b''.join(cache)
    struct.pack_into('>I',result,12,0);result[0x4b0:]=hashlib.md5(result[:0x4b0]).digest()
    if sorted(slots)!=sorted(raw[0x10+16*i:0x20+16*i]for i in range(48)):raise ValueError('TV placement lost an existing slot')
    path.write_bytes(result);launcher.scrub_download_tasks(PROFILE);print('TV Guide first-page placement verified; all 48 channel slots preserved')
if __name__=='__main__':main()
