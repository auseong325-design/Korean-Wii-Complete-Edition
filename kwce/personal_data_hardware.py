"""Hardware WAD checks for the hidden Set Personal Data title (00010008-HCCJ) only.

kwce/hardware.py packages 00010001/00010002 channels and refuses hidden titles.
This module admits exactly 000100084843434a with the same rules: the Dolphin
local-address reference counts must equal the WiiLink original (both zero for
SPD), TMD header fields must equal WiiLink's (IOS58, access rights, region,
version, boot index), the title is fakesigned and contents round-trip.
System titles, IOS and any other hidden title are refused. By default the boot
DOL must have a branch at the 0x80003400 channel entry (kwce/personal_data_boot.py);
only the preserved, non-booting hardware-v1 reproduction opts out.
"""
from .channels import load_library
from .hardware import local_reference_counts
from .personal_data_boot import channel_entry
TITLE='000100084843434a'
HEADER=('ios_tid','region','title_version','boot_index','access_rights')

def header(tmd):return {k:getattr(tmd,k)for k in HEADER}

def hardware_wad(korean_bytes,wiilink_title,require_channel_entry=True):
    lib=load_library();title=lib.title.Title();title.load_wad(korean_bytes)
    if title.tmd.title_id.lower()!=TITLE or wiilink_title.tmd.title_id.lower()!=TITLE:raise ValueError('Only 00010008-HCCJ may be packaged here')
    if header(title.tmd)!=header(wiilink_title.tmd):raise ValueError('TMD header differs from WiiLink SPD')
    entry=channel_entry(title.get_content_by_index(title.tmd.boot_index))if require_channel_entry else None
    counts=local_reference_counts(title);original=local_reference_counts(wiilink_title)
    if counts!=original or any(counts.values()):raise ValueError('Local test address references present')
    title.fakesign()
    if not title.get_is_fakesigned():raise ValueError('Fakesign failed')
    wad=title.dump_wad();check=lib.title.Title();check.load_wad(wad)
    if any(check.get_content_by_index(i)!=title.get_content_by_index(i)for i in range(len(title.tmd.content_records))):raise ValueError('Content roundtrip')
    record=dict(title_id=TITLE,version=title.tmd.title_version,ios=title.tmd.ios_tid,access_rights=title.tmd.access_rights,
                region=title.tmd.region,contents=len(title.tmd.content_records),local_reference_counts=counts,fakesigned=True)
    if entry is not None:record['channel_entry']=entry
    return wad,record
