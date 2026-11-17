"""Translate only the two guarded English wind direction tables in Forecast v7."""
import hashlib

DIRECTIONS='NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW N'.split()
OFFSETS=(0x1d2fe8,0x1d3370)
CALM=0x1957b8
SOURCE=b''.join(s.encode('utf-16-be')+bytes(8-len(s)*2)for s in DIRECTIONS)
TRANSLATION=str.maketrans(dict(N='북',E='동',S='남',W='서'))


def korean_wind(executable):
    original=bytes(executable)
    if any(original[at:at+len(SOURCE)]!=SOURCE for at in OFFSETS):raise ValueError('Unknown Forecast direction tables')
    if original[CALM:CALM+10]!='Calm\0'.encode('utf-16-be'):raise ValueError('Unknown Forecast calm label')
    result=bytearray(original)
    for at in OFFSETS:
        for i,direction in enumerate(DIRECTIONS):
            label=direction.translate(TRANSLATION).encode('utf-16-be')
            result[at+8*i:at+8*(i+1)]=label+bytes(8-len(label))
    label='무풍'.encode('utf-16-be');result[CALM:CALM+8]=label+bytes(8-len(label))
    return bytes(result),dict(english_tables=2,directions_per_table=16,calm='무풍',
        source_table_sha256=hashlib.sha256(SOURCE).hexdigest(),fixed_slots_and_pointers_preserved=True)
