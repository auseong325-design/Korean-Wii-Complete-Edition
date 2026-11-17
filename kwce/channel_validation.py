"""Read-only installed title verification, including shared content resolution."""
import hashlib,re,struct

def verify_installed_title(wii,title_id,expected_tmd):
    if not re.fullmatch('[0-9a-f]{16}',title_id):raise ValueError('Title identity')
    folder=wii/'title'/title_id[:8]/title_id[8:]/'content'
    tmd=(folder/'title.tmd').read_bytes()
    if tmd!=expected_tmd or len(tmd)<0x1e4:raise ValueError('Installed title TMD differs')
    count=struct.unpack_from('>H',tmd,0x1de)[0]
    if len(tmd)!=0x1e4+36*count:raise ValueError('Installed TMD bounds')
    content_map=(wii/'shared1/content.map').read_bytes()
    if len(content_map)%28:raise ValueError('Installed shared map bounds')
    shared={}
    for at in range(0,len(content_map),28):
        name=content_map[at:at+8]
        if not re.fullmatch(b'[0-9a-f]{8}',name):raise ValueError('Invalid shared content name')
        digest=content_map[at+8:at+28]
        if digest in shared:raise ValueError('Duplicate shared content hash')
        shared[digest]=name.decode('ascii')
    for i in range(count):
        cid,index,kind,size=struct.unpack_from('>IHHQ',tmd,0x1e4+36*i);digest=tmd[0x1f4+36*i:0x208+36*i]
        if kind==1:path=folder/f'{cid:08x}.app'
        elif kind==0x8001:
            if digest not in shared:raise ValueError('Installed shared content missing')
            path=wii/'shared1'/f'{shared[digest]}.app'
        else:raise ValueError('Unsupported installed content type')
        if not path.resolve().is_relative_to(wii.resolve())or path.is_symlink()or path.is_junction():raise ValueError('Indirect installed content')
        data=path.read_bytes()
        if len(data)!=size or hashlib.sha1(data).digest()!=digest:raise ValueError('Installed content size/hash differs')
    return count
