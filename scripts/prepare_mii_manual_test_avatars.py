"""Populate only a stopped channel test NAND with derived synthetic avatars.

Usage: prepare_mii_manual_test_avatars.py [channel]  (default mii-contest)."""
import binascii,json,shutil,sys
from make_channel_access_fixtures import ROOT,mii_variants
from prepare_channel_access import stopped
from audit_sd import PRIVATE,sha256

def main():
    stopped();channel=sys.argv[1]if len(sys.argv)>1 else'mii-contest'
    if channel not in('mii-contest','votes'):raise SystemExit('Unsupported test NAND')
    path=ROOT/f'workspace/sandbox/{channel}-test-v1/user/Wii/shared2/menu/FaceLib/RFL_DB.dat'
    data=bytearray(path.read_bytes());backup=PRIVATE/('mii-test-before-manual-avatars.dat'if channel=='mii-contest'else f'{channel}-test-before-manual-avatars.dat')
    if backup.exists():raise SystemExit('Previous synthetic-avatar snapshot preserved')
    assert len(data)==779968 and binascii.crc_hqx(data[:127454],0)==int.from_bytes(data[127454:127456],'big')
    occupied=[i for i in range(100)if any(data[4+74*i:78+74*i])]
    assert len(occupied)==1
    at=4+74*occupied[0];base=bytes(data[at:at+74]);assert base[2:22].decode('utf-16-be').rstrip('\0')=='test'
    variants=mii_variants(base)
    for i,slot in enumerate([i for i in range(100)if i not in occupied][:23]):
        record=bytearray(variants[i%12][:74])
        if i>=12:
            name=record[2:22].decode('utf-16-be').rstrip('\0')+'2';record[2:22]=name.encode('utf-16-be').ljust(20,b'\0')
        record[0x1b]=(base[0x1b]+i+1)&255
        data[4+74*slot:78+74*slot]=record
    data[127454:127456]=binascii.crc_hqx(data[:127454],0).to_bytes(2,'big')
    shutil.copy2(path,backup);path.write_bytes(data)
    (PRIVATE/('mii-manual-test-avatars.json'if channel=='mii-contest'else f'{channel}-manual-test-avatars.json')).write_text(json.dumps(dict(synthetic=True,count=24,original_test_avatar_preserved=True,sha256=sha256(path)),indent=2))
    print(f'{channel} test NAND: preserved original synthetic test avatar; added 23 local derived avatars, database CRC valid')

if __name__=='__main__':main()
