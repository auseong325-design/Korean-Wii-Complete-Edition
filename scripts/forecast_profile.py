"""Channel-only task policy: preserve two public Forecast URLs for cache identity.

All other tasks remain scrubbed. The channel runner still has zero network
capabilities. This policy is never registered in the GC launcher CLI.
"""
import re,struct
import launch_dolphin as launcher

def public_forecast_task(entry):
    if len(entry)!=512:return False
    title=set(struct.unpack_from('>II',entry,8))
    if title!={0x00010002,0x48414645}:return False
    url=entry[180:416].split(b'\0')[0]
    return re.fullmatch(rb'http://fore\.wiilink24\.com/+1/136/(forecast|short)\.bin',url)is not None

def validate_channel():
    try:return launcher.validate('forecast-v1-user')
    except SystemExit as error:
        if str(error)!='A scheduled task must be scrubbed before launch':raise
    # The preceding shared validator has already checked locale, credentials,
    # identity, checksums and the download-list header before this exact error.
    user=launcher.user_path('forecast-v1-user');data=(user/'Wii/shared2/wc24/nwc24dl.bin').read_bytes()
    from urllib.parse import urlparse
    for i in range(120):
        entry=data[2048+512*i:2560+512*i]
        if not int.from_bytes(entry[12:16],'big'):continue
        if public_forecast_task(entry):continue
        url=urlparse(entry[180:416].split(b'\0')[0].decode('ascii'))
        if url.scheme!='http'or url.hostname!='127.0.0.1'or url.port!=9 or not int.from_bytes(entry[4:8],'big')&32:raise SystemExit('Non-Forecast external task refused')
    return user

def scrub_channel():
    p=launcher.user_path('forecast-v1-user')/'Wii/shared2/wc24/nwc24dl.bin';data=bytearray(p.read_bytes())
    if len(data)!=0xf800 or data[:8]!=bytes.fromhex('5763446c00000001'):raise ValueError('Invalid channel download list')
    for i in range(120):
        off=2048+512*i;entry=data[off:off+512]
        if not int.from_bytes(entry[12:16],'big')or public_forecast_task(entry):continue
        struct.pack_into('>I',data,off+4,int.from_bytes(entry[4:8],'big')|32)
        url=f'http://127.0.0.1:9/phase0-disabled/task-{i}'.encode();data[off+180:off+416]=url+bytes(236-len(url))
    p.write_bytes(data)
