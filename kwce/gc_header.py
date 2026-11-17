"""Exact 43K/v5 Korean GC header line break; no added symbols or assets."""
import hashlib
from .formats import U8

SOURCE_SHA256='1ac2812bdec15dcef4757740e3f13b1f21cf717c07707b828e3328b25df859b2'
MESSAGE='message/kor/ipl_common.bmg'
BMG_SHA256='b019d8e1c1a7735ae8f37e3c47cef5ccf36b41e4cd4da5fe75d82871f6830d88'
OFFSET=11676

def patch_gc_header(data):
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA256:raise ValueError('Only verified v5 43K resource supported')
    outer=U8(data);before=outer.get(MESSAGE)
    if hashlib.sha256(before).hexdigest()!=BMG_SHA256:raise ValueError('Korean BMG guard mismatch')
    old='닌텐도  게임큐브'.encode('utf-16-be')
    new='닌텐도 \n게임큐브'.encode('utf-16-be')
    if before[OFFSET:OFFSET+len(old)]!=old or before.count(old)!=1:raise ValueError('GC label guard mismatch')
    after=before[:OFFSET]+new+before[OFFSET+len(old):]
    if len(before)!=len(after):raise ValueError('Message offsets would change')
    result=outer.replace(MESSAGE,after)
    changed=[i for i,(a,b)in enumerate(zip(data,result))if a!=b]
    if len(changed)!=1:raise ValueError('Expected one UTF-16 separator byte change')
    return result,dict(source_sha256=SOURCE_SHA256,output_sha256=hashlib.sha256(result).hexdigest(),message=MESSAGE,message_offset=OFFSET,bytes_changed=1,unrelated_outer_files_unchanged=len(outer.files)-1,lines=['닌텐도','게임큐브'],symbol_added=False)
