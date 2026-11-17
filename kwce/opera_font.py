"""Korean font for the Opera-based channel manuals.

The USA executables load the manual font by the fixed archive name
WiiNTLG-Regular.ttc, whose faces have no Hangul. The Korean console ships
"Wii-kr_Round Gothic B.ttf" in its own shared content; it is wrapped into a
collection with the original face count and stored under the original name.
"""
import hashlib,io
from .channels import ROOT,ChannelArchive,load_library

KOREAN_SHARED=ROOT/'workspace/extracted-system/nand-current/shared1/0000001e.app'
NAME='WiiNTLG-Regular.ttc'

def korean_opera_font(content):
    load_library()
    from fontTools.ttLib import TTFont,TTCollection
    raw=KOREAN_SHARED.read_bytes();korean=ChannelArchive(raw).get('Wii-kr_Round Gothic B.ttf')
    archive=ChannelArchive(content);original=TTCollection(io.BytesIO(archive.get(NAME)))
    faces=len(original.fonts)
    collection=TTCollection();collection.fonts=[TTFont(io.BytesIO(korean),recalcTimestamp=False)for _ in range(faces)]  # keep builds reproducible
    out=io.BytesIO();collection.save(out);data=out.getvalue()
    if 0xAC00 not in TTCollection(io.BytesIO(data)).fonts[0].getBestCmap():raise ValueError('Korean font lacks Hangul')
    return ChannelArchive(archive.replace(NAME,data)).compact(),dict(file=NAME,faces=faces,korean_source='console shared1 content 0x1e',korean_source_sha256=hashlib.sha256(raw).hexdigest(),size=len(data))
