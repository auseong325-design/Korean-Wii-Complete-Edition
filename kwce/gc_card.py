"""Read-only raw GC card validation. Never exports names or save contents."""
import hashlib,struct
from .gc_fixture import checksum

def inspect_card(data):
    if len(data)<5*8192 or len(data)%8192:raise ValueError('Invalid card size')
    mbits,encoding=struct.unpack_from('>HH',data,0x22)
    if mbits not in [4,8,16,32,64,128] or len(data)!=mbits*131072:raise ValueError('Card header size mismatch')
    if struct.unpack_from('>HH',data,0x1fc)!=checksum(data[:0x1fc]):raise ValueError('Header checksum mismatch')
    def latest(rows,counter,valid):
        rows=[r for r in rows if valid(r)]
        if not rows:raise ValueError('No valid redundant card metadata')
        selected=rows[0]
        for r in rows[1:]:
            delta=(counter(r)-counter(selected))&65535
            if 0<delta<32768:selected=r
        return selected
    directory=latest([data[8192:16384],data[16384:24576]],lambda r:int.from_bytes(r[0x1ffa:0x1ffc],'big'),lambda r:struct.unpack_from('>HH',r,0x1ffc)==checksum(r[:0x1ffc]))
    bat=latest([data[24576:32768],data[32768:40960]],lambda r:int.from_bytes(r[4:6],'big'),lambda r:struct.unpack_from('>HH',r)==checksum(r[4:]))
    entries=[];used=set();blocks=len(data)//8192
    for i in range(127):
        e=directory[64*i:64*(i+1)]
        if e[:4]==b'\xff'*4:continue
        block,count=struct.unpack_from('>HH',e,0x36)
        if not count or count>blocks-5:raise ValueError('Invalid file block count')
        payload=bytearray();chain=set()
        for _ in range(count):
            if not 5<=block<blocks or block in used or block in chain:raise ValueError('Invalid/shared/cyclic card chain')
            chain.add(block);payload.extend(data[block*8192:(block+1)*8192])
            block=int.from_bytes(bat[0xa+2*(block-5):0xc+2*(block-5)],'big')
        if block!=0xffff:raise ValueError('Card chain length mismatch')
        used.update(chain)
        # An internal comparison key only; callers must not print this key.
        key=hashlib.sha256(e[:6]+e[8:40]).hexdigest()
        entries.append(dict(key=key,blocks=count,payload_sha256=hashlib.sha256(payload).hexdigest()))
    free=int.from_bytes(bat[6:8],'big')
    if free!=blocks-5-len(used):raise ValueError('Card free block mismatch')
    return dict(encoding=encoding,entries=entries,free_blocks=free,allocated_blocks=len(used),checksums_valid=True)
