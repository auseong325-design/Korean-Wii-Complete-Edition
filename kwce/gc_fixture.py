"""New synthetic GC card header/save; contains no commercial game save data."""
import struct

def checksum(b):
    words=struct.unpack('>'+str(len(b)//2)+'H',b)
    return tuple(0 if n==65535 else n for n in (sum(words)&65535,sum(x^65535 for x in words)&65535))

def card_header(encoding=0,mbits=4):
    # Deterministic test flash ID and format time zero. Never a console ID.
    h=bytearray(b'\xff'*8192);h[:0x26]=bytes(0x26)
    struct.pack_into('>HH',h,0x22,mbits,encoding)
    struct.pack_into('>HH',h,0x1fc,*checksum(h[:0x1fc]));return bytes(h)

def gci_fixture():
    entry=bytearray(b'\xff'*64);entry[:6]=b'KWCE00';entry[7]=0
    entry[8:40]=b'KWCE-SYNTH-TEST'.ljust(32,b'\0')
    struct.pack_into('>IIHHBBHH',entry,40,0,0,2,1,4,0,5,1)
    struct.pack_into('>I',entry,60,2048)
    body=bytearray(8192);body[:2048]=b'\x80\x1f'*1024
    body[2048:2112]=b'KWCE SYNTHETIC TEST'.ljust(32,b'\0')+b'LOCAL TEST DATA ONLY'.ljust(32,b'\0')
    return bytes(entry+body)

def raw_card(with_save=False,encoding=0,mbits=4):
    if mbits not in [4,8,16,32,64,128]:raise ValueError('Invalid card size')
    data=bytearray(b'\xff'*(mbits*131072));data[:8192]=card_header(encoding,mbits)
    directory=bytearray(b'\xff'*8192);struct.pack_into('>H',directory,0x1ffa,0)
    bat=bytearray(8192);struct.pack_into('>HHH',bat,4,0,mbits*16-5-int(with_save),5 if with_save else 4)
    if with_save:
        save=gci_fixture();directory[:64]=save[:64];data[5*8192:6*8192]=save[64:]
        struct.pack_into('>H',bat,10,65535)
    struct.pack_into('>HH',directory,0x1ffc,*checksum(directory[:0x1ffc]));struct.pack_into('>HH',bat,0,*checksum(bat[4:]))
    for index,block in [(1,directory),(2,directory),(3,bat),(4,bat)]:data[index*8192:(index+1)*8192]=block
    return bytes(data)


def raw_card_saves(saves, encoding=0, mbits=4):
    """Synthetic card with one-block saves: [(game_code6, file_name, comment_bytes64)].

    Project-authored names and comments only; no commercial save data.
    """
    if mbits not in [4,8,16,32,64,128]:raise ValueError('Invalid card size')
    if not 0 < len(saves) <= 8:raise ValueError('1..8 saves')
    data=bytearray(b'\xff'*(mbits*131072));data[:8192]=card_header(encoding,mbits)
    directory=bytearray(b'\xff'*8192);struct.pack_into('>H',directory,0x1ffa,0)
    bat=bytearray(8192)
    for index,(code,name,comment) in enumerate(saves):
        if len(code)!=6 or len(comment)!=64:raise ValueError('Bad fixture save')
        block=5+index
        entry=bytearray(b'\xff'*64);entry[:6]=code;entry[7]=0
        entry[8:40]=name.ljust(32,b'\0')
        struct.pack_into('>IIHHBBHH',entry,40,0,0,2,1,4,0,block,1)
        struct.pack_into('>I',entry,60,2048)
        body=bytearray(8192);body[:2048]=b'\x80\x1f'*1024;body[2048:2112]=comment
        directory[index*64:(index+1)*64]=entry;data[block*8192:(block+1)*8192]=body
        struct.pack_into('>H',bat,10+2*(block-5),65535)
    struct.pack_into('>HHH',bat,4,0,mbits*16-5-len(saves),4+len(saves))
    struct.pack_into('>HH',directory,0x1ffc,*checksum(directory[:0x1ffc]));struct.pack_into('>HH',bat,0,*checksum(bat[4:]))
    for index,block in [(1,directory),(2,directory),(3,bat),(4,bat)]:data[index*8192:(index+1)*8192]=block
    return bytes(data)
