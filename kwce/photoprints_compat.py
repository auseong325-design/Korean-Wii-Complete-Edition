"""Title-local Korean-area bridge for the Japan-only Photo Prints Channel.

Root cause (confirmed with the 주소 설정 worker): the channel's SCGetArea-
equivalent area getter at 0x800d0978 reads SYSCONF IPL.AR and maps the area
string to a numeric code via its own table at 0x80303ca0 (JPN0 USA1 EUR2 AUS3
BRA4 TWN/ROC5 KOR6 HKG7 ...). The PD library's save-path selector at 0x802a81a8
and the HCCx title-ID builder at 0x80093774 switch on that code and handle only
JPN/USA/EUR; on a Korean console the getter returns 6, so the pd.dat path and
HCCx title fall into a default/NULL branch -- Digicam gets no personal-data
path, exactly the issue kwce/wiiroom_compat.patch_korean_area fixes for Wii no
Ma (KOR6->JPN0 at its SCGetArea return, title-local).

This is the equivalent title-local bridge: flip only this title's KOR table
code from 6 to 0 at 0x80303cc3 (file 0x2ffdc3), so the getter at 0x800d0978
returns JPN(0) for a Korean console and the PD path selector resolves the HCCJ
(00010008-4843434a) pd.dat path and area-0 resources -- consistent with the
WiiLink Japan patch. It is applied in BOTH the local and hardware builds,
operates on the decompressed DOL, preserves size, and changes no console
setting (SYSCONF untouched) or personal-data byte.
"""
from .channels import sha256
from .ppc_patch import to_file

TABLE_VA=0x80303ca0            # area name/code table, 5-byte entries code+3char+NUL
GETTER_VA=0x800d0978           # SCGetArea-equivalent (reads SYSCONF IPL.AR)
PD_PATH_SELECTOR_VA=0x802a81a8 # consumes the getter; NULL pd.dat path on KOR before the bridge
KOR_ENTRY=b'\x06KOR\x00'
KOR_ENTRY_KO=b'\x00KOR\x00'


def patch_korean_area(dol):
    at=to_file(dol,TABLE_VA,0x40)
    region=bytes(dol[at:at+0x40])
    pos=region.find(KOR_ENTRY)
    if pos<0:raise ValueError('KOR area-table entry not found')
    if region.count(KOR_ENTRY)!=1:raise ValueError('Ambiguous KOR area-table entry')
    out=bytearray(dol);out[at+pos:at+pos+len(KOR_ENTRY)]=KOR_ENTRY_KO
    return bytes(out),dict(table=hex(TABLE_VA),kor_entry_address=hex(0x80303cc3),getter=hex(GETTER_VA),
        pd_path_selector=hex(PD_PATH_SELECTOR_VA),title_id_builder=hex(0x80093774),
        entry='KOR',source_area=6,resource_area=0,applied_in=['local','hardware'],
        scope='Photo Prints SCGetArea-equivalent getter only; SYSCONF unchanged',
        console_setting_unchanged=True,personal_data_unchanged=True,bytes_changed=1,
        sibling='kwce/wiiroom_compat.patch_korean_area (Wii no Ma SCGetArea return)',
        note='Secondary 2-letter area getter (KR=4 at 0x80303ce8) left as-is; '
             'revisit if a residual KR gate appears in testing.')
