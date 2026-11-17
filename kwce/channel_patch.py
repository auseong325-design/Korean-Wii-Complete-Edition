"""Hash-guarded local content deltas. Binary outputs stay in ignored storage."""
import hashlib,json,struct,zlib
MAGIC=b'KWCP1\0';LIMIT=64*1024*1024

def make_patch(before,after):
    if max(len(before),len(after))>LIMIT:raise ValueError('Channel delta size limit')
    chunks=[];payload=bytearray()
    for at in range(0,len(after),4096):
        part=after[at:at+4096]
        if before[at:at+len(part)]==part:continue
        chunks.append([at,len(part)]);payload.extend(part)
    meta=dict(base_sha256=hashlib.sha256(before).hexdigest(),output_sha256=hashlib.sha256(after).hexdigest(),output_size=len(after),literal_size=len(payload),chunks=chunks)
    header=json.dumps(meta,separators=(',',':'),sort_keys=True).encode()
    result=MAGIC+struct.pack('>I',len(header))+header+zlib.compress(payload,9)
    if apply_patch(before,result)!=after:raise ValueError('Channel delta roundtrip')
    return result

def apply_patch(before,patch):
    if patch[:6]!=MAGIC or len(patch)<10:raise ValueError('Channel delta magic')
    size=struct.unpack_from('>I',patch,6)[0]
    if not 0<size<=1024*1024 or 10+size>=len(patch):raise ValueError('Channel delta metadata bounds')
    meta=json.loads(patch[10:10+size]);out_size=meta['output_size'];literal_size=meta['literal_size']
    if hashlib.sha256(before).hexdigest()!=meta['base_sha256']:raise ValueError('Channel delta base changed')
    if not 0<=out_size<=LIMIT or not 0<=literal_size<=LIMIT:raise ValueError('Channel delta output bounds')
    decoder=zlib.decompressobj();literals=decoder.decompress(patch[10+size:],literal_size+1)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(literals)!=literal_size:raise ValueError('Channel delta compressed payload bounds')
    out=bytearray(before[:out_size]);out.extend(bytes(out_size-len(out)));position=0;end=0
    for at,length in meta['chunks']:
        if not 0<=end<=at or not 0<length<=4096 or at+length>out_size or position+length>len(literals):raise ValueError('Channel delta chunk bounds')
        out[at:at+length]=literals[position:position+length];position+=length;end=at+length
    if position!=len(literals)or hashlib.sha256(out).hexdigest()!=meta['output_sha256']:raise ValueError('Channel delta output differs')
    return bytes(out)
