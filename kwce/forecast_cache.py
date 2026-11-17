"""Immutable, bounded public Forecast snapshots; no console credentials."""
import datetime,hashlib,json,re,struct,zlib
from .channels import ROOT,load_library

REFERENCES=ROOT/'workspace/channels/forecast/references'

def valid_at(record,instant):
    if instant.tzinfo is None:raise ValueError('Forecast validity requires an aware UTC instant')
    return datetime.datetime.fromisoformat(record['opened_utc'])<=instant<datetime.datetime.fromisoformat(record['closed_utc'])

def inspect_public_download(raw,kind):
    if kind not in ['forecast','short']or not 320<len(raw)<=1024*1024:raise ValueError('Public Forecast download bounds')
    payload=raw[320:]
    if len(payload)<4 or payload[0]!=16 or int.from_bytes(payload[1:4],'little')>4*1024*1024:raise ValueError('Public Forecast LZ10 bounds')
    load_library();from libWiiPy.archive import decompress_lz77
    data=decompress_lz77(payload);minimum=88 if kind=='forecast'else 36
    if len(data)<minimum or struct.unpack_from('>II',data,0)!=(0,len(data))or data[20]!=136 or data[24]!=1:raise ValueError('Public Forecast header identity')
    if zlib.crc32(data[12:])&0xffffffff!=struct.unpack_from('>I',data,8)[0]:raise ValueError('Public Forecast CRC differs')
    opened,closed=struct.unpack_from('>II',data,12)
    if not opened<closed<=opened+90:raise ValueError('Public Forecast validity interval')
    epoch=datetime.datetime(2000,1,1,tzinfo=datetime.timezone.utc)
    return dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),decompressed_size=len(data),country=136,data_language=1,opened_utc=(epoch+datetime.timedelta(minutes=opened)).isoformat(),closed_utc=(epoch+datetime.timedelta(minutes=closed)).isoformat(),CRC_valid=True,RSA_signature_independently_verified=False)

def public_source(kind,binding=None):
    if kind not in ['forecast','short']:raise ValueError('Unsupported public source')
    pointer=REFERENCES/'active-public-snapshot.json'
    if binding is None and not pointer.exists():return REFERENCES/f'http-public-{kind}-136.bin'
    active=binding if binding is not None else json.loads(pointer.read_text());name=active.get('snapshot','')
    if not re.fullmatch(r'public-\d{8}T\d{6}Z',name):raise ValueError('Public snapshot alias')
    folder=REFERENCES/name;path=folder/f'{kind}.bin'
    if folder.is_symlink()or folder.is_junction()or path.is_symlink()or path.is_junction()or not path.resolve().is_relative_to(REFERENCES.resolve()):raise ValueError('Indirect public snapshot')
    manifest=json.loads((folder/'manifest.json').read_text())
    if hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()!=active['manifest_sha256']:raise ValueError('Public snapshot manifest differs')
    if inspect_public_download(path.read_bytes(),kind)!=manifest['files'][kind]:raise ValueError('Public snapshot content differs')
    return path
