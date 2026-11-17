"""Check the local Mii replay schema without exporting any payload bytes."""
import binascii,hashlib,hmac,struct
from make_channel_access_fixtures import ROOT,source_array,load_library
from kwce.channel_access import validate_fixtures

def main():
    load_library()
    from Crypto.Cipher import AES
    from libWiiPy.archive import decompress_lz77
    root=ROOT/'workspace/sandbox/mii-contest-test-v1/local-feed'
    validate_fixtures(root,'mii-contest')
    source=(ROOT/'workspace/channels/mii-contest/references/server-source/common/writer.go').read_text()
    key,iv,mac=(source_array(source,n)for n in ['aesKey','aesIv','hmacKey'])
    def read(name):
        raw=(root/name).read_bytes()
        assert raw[:4]==b'MC\0\1' and hmac.compare_digest(raw[4:24],hmac.new(mac,raw[24:],hashlib.sha1).digest())
        return decompress_lz77(b'LZ77'+AES.new(key,AES.MODE_CBC,iv).decrypt(raw[24:]))
    def avatar(data):
        assert len(data)==76 and binascii.crc_hqx(data[:74],0)==int.from_bytes(data[74:],'big')
    details=pages=entries=0
    for name in sorted(root.glob('contest_*_con_detail1.ces')):
        data=read(name.name);assert len(data)==168 and data[:2]==b'CD'
        cid=struct.unpack_from('>I',data,4)[0];status=data[44];count=struct.unpack_from('>I',data,48)[0]
        for start,size in [(72,32),(104,64)]:
            text=data[start:start+size].split(b'\0')[0].decode('utf-8')
            assert text and any('\uac00'<=c<='\ud7a3'for c in text)
        details+=1
        if status==8:
            actual=0
            for page in range(1,(count+9)//10+1):
                body=read(f'contest_{cid}_entry_list{page}.ces')
                assert body[:2]==b'EL' and struct.unpack_from('>II',body,4)==(cid,page)
                assert (len(body)-32)%88==0 and 0<(len(body)-32)//88<=10
                for at in range(32,len(body),88):
                    assert body[at:at+2]==b'CM' and int.from_bytes(body[at+2:at+4],'big')==88
                    avatar(body[at+12:at+88]);actual+=1
                pages+=1
            assert actual==count;entries+=actual
    assert details==9 and pages==9 and entries==72
    print(f'PASS: {details} UTF-8 contest details, {pages} complete entry pages, {entries} CRC-valid synthetic entries; fixture integrity valid')

if __name__=='__main__':main()
