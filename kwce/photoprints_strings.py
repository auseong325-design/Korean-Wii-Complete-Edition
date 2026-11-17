"""Photo Prints Channel DOL text + endpoint edits (content 1, LZ11).

All edits operate on the decompressed main DOL and preserve its raw size so the
stream can be re-encoded with reencode_lz11_same_size. Fixed UTF-16BE slots are
written in place and zero-padded (never truncated); a Korean string that does not
fit its slot is skipped and reported. The local endpoint rewrite rebuilds the
service URL C-strings to http://127.0.0.2 so nothing leaves the emulator.
"""
import json,re
from pathlib import Path
from .channels import ROOT,sha256
from .ppc_patch import to_file

CONFIG=ROOT/'configs/photoprints-executable-v1-ko.json'
HOSTS=(b'wch.fdinet.fujifilm.co.jp',b'cam-prod.wiilink24.com',b'211.14.18.202')
# NAND-error messages drawn before resources load with the tiny font embedded in
# the DOL (RFNT at 0x802deb00, "font_photo_error.brfnt"), which holds only the
# Japanese glyphs of these messages and no Hangul. From v6 they stay Japanese.
ERROR_FONT_LITERALS=('0x802ddae8','0x802de6d0','0x802de880','0x802de950','0x802dea3c')


def _slot(dol,va):
    at=to_file(dol,va,2);end=at
    while dol[end:end+2]!=b'\0\0':end+=2
    slot=end
    while dol[slot:slot+2]==b'\0\0' and slot-at<4096:slot+=2
    return at,end,slot


def translate_executable(dol,skip=()):
    """Apply the Korean DOL literal slots. Returns (dol, record).

    skip: addresses (hex strings) left Japanese (e.g. ERROR_FONT_LITERALS)."""
    config=json.loads(CONFIG.read_text(encoding='utf-8'))
    out=bytearray(dol);applied=[];skipped=[];kept=[]
    for row in config['rows']:
        va=int(row['address'],16);at,end,slot=_slot(out,va)
        if out[at:end].decode('utf-16-be')!=row['expected']:
            raise ValueError('Unexpected DOL literal at '+row['address'])
        if row['address'] in skip:kept.append(row['address']);continue
        data=row['ko'].encode('utf-16-be')+b'\0\0'
        if re.findall(r'%[-+ #0-9.*hlLzjt]*[a-zA-Z%]',row['expected'])!=re.findall(r'%[-+ #0-9.*hlLzjt]*[a-zA-Z%]',row['ko']):
            raise ValueError('Format token mismatch at '+row['address'])
        if len(data)>slot-at:skipped.append(row['address']);continue
        out[at:slot]=data+bytes(slot-at-len(data));applied.append(dict(address=row['address'],ko=row['ko']))
    record=dict(applied=len(applied),skipped=skipped,messages=applied)
    if skip:record['kept_japanese_error_font']=kept
    return bytes(out),record


def rewrite_local_endpoints(dol):
    """Point every service URL C-string at http://127.0.0.2 (local build only).

    The host placeholder forms are collapsed to a literal http://127.0.0.2 URL,
    dropping the scheme/host arguments, so the SSL flag and configured IP are
    irrelevant and all traffic reaches the loopback fixture server over http.
    """
    out=bytearray(dol);count=0;hosts=set()
    # Rewrite only the endpoint templates whose host is a concrete name/IP (the
    # active cam-prod.wiilink24.com slot after the WiiLink patch, plus the fixed
    # IP slot). The %s/%d.%d.%d.%d placeholder templates serve the unused custom
    # host modes and are too short for a literal loopback URL, so leave them.
    for m in re.finditer(rb'(?:%s|https?)://([A-Za-z0-9][A-Za-z0-9.\-]{2,})/wii_svr/WP[A-Za-z]+Servlet', bytes(dol)):
        s=m.group();at=m.start();hosts.add(m.group(1).decode())
        new=b'http://127.0.0.2'+s[s.index(b'/wii_svr'):]
        if len(new)>len(s):raise ValueError('Local endpoint exceeds original slot')
        out[at:at+len(s)]=new+bytes(len(s)-len(new));count+=1
    if not count:raise ValueError('No concrete-host service endpoints found to localize')
    return bytes(out),dict(local_endpoints=count,redirected_hosts=sorted(hosts),target='http://127.0.0.2')


def loopback_reference_count(dol):
    return bytes(dol).count(b'127.0.0.2')
