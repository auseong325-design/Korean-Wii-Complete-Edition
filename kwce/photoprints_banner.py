"""Korean IMET channel name for the Photo Prints banner (content 0).

Sets all ten IMET language-name slots to the Korean display name and fixes the
IMET MD5 (bytes 0x40..0x640 with the 16-byte hash field zeroed). The banner/icon
layout textures themselves (meta/banner.bin, meta/icon.bin wordmarks) are visual
assets handled separately; this only rewrites the launch-menu channel name.
"""
import hashlib

DISPLAY_NAME='디지털 카메라 프린트 채널'


def korean_banner_name(content,name=DISPLAY_NAME):
    banner=bytearray(content)
    if banner[0x80:0x84]!=b'IMET':raise ValueError('Photo Prints banner IMET missing')
    text=name.encode('utf-16-be')
    if len(text)>84:raise ValueError('IMET name exceeds slot')
    for i in range(10):
        at=0x40+0x5c+84*i;banner[at:at+84]=text+bytes(84-len(text))
    banner[0x630:0x640]=bytes(16)
    banner[0x630:0x640]=hashlib.md5(bytes(banner[0x40:0x640])).digest()
    return bytes(banner),dict(imet_name=name,languages=10,md5_range='0x40:0x640')
