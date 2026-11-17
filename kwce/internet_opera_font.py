"""Korean Opera font (content 4) that keeps each ORIGINAL face's name records.

kwce.opera_font.korean_opera_font gives both TTC faces the Korean TTF's own
name ('Wii-kr_Round Gothic B'). Chrome dialogs still render because the engine
registers the faces under the executable's hard-coded family names, but web
content (the manual and remote pages) matches 'Wii NTLG PGothic Regular' by the
font's own name records and finds nothing, so it renders blank. This builds the
same Korean TTC but transplants each original face's `name` table onto the
matching Korean face, so face 0 is 'Wii NTLG Gothic' and face 1
'Wii NTLG PGothic' by family, full and PostScript name, exactly as the CSS and
defaults reference them.
"""
import hashlib
import io

from .channels import ChannelArchive, load_library
from .opera_font import KOREAN_SHARED, NAME


def _names(font):
    return {r.nameID: str(r) for r in font['name'].names if r.platformID == 3 and r.nameID in (1, 2, 4, 6)}


def korean_opera_font(content):
    load_library()
    from fontTools.ttLib import TTFont, TTCollection
    raw = KOREAN_SHARED.read_bytes()
    korean = ChannelArchive(raw).get('Wii-kr_Round Gothic B.ttf')
    archive = ChannelArchive(content)
    original = TTCollection(io.BytesIO(archive.get(NAME)))
    faces = len(original.fonts)
    collection = TTCollection()
    collection.fonts = []
    records = []
    for i in range(faces):
        face = TTFont(io.BytesIO(korean), recalcTimestamp=False)  # keep builds reproducible
        face['name'] = original.fonts[i]['name']  # adopt the original face's names
        collection.fonts.append(face)
        records.append(_names(face))
    out = io.BytesIO()
    collection.save(out)
    data = out.getvalue()
    check = TTCollection(io.BytesIO(data))
    for i in range(faces):
        if 0xAC00 not in check.fonts[i].getBestCmap():
            raise ValueError('Korean font lacks Hangul')
        if _names(check.fonts[i]) != _names(original.fonts[i]):
            raise ValueError(f'Face {i} name records not applied')
    return ChannelArchive(archive.replace(NAME, data)).compact(), dict(
        file=NAME, faces=faces, korean_source='console shared1 content 0x1e',
        korean_source_sha256=hashlib.sha256(raw).hexdigest(), size=len(data),
        face_names=records, names_from_original=True)
