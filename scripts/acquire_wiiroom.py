"""Preserve Wii Room source WADs locally; transmit no console material."""
import acquire_forecast as acquisition
from pathlib import Path

acquisition.DEST=Path(__file__).resolve().parents[1]/'workspace/channels/wiiroom/originals'
base='https://repo.mariocube.com/WADs/'
acquisition.FILES=[
 ('wiiroom-japan-v1025.wad',base+'_WiiWare, VC, DLC, Channels & IOS/W/Wii no Ma (Japan) (v1025) (Channel).wad'),
 ('wiiroom-english-wiilink-archive.wad',base+'WiiLink/WAD/Wii Room (English) (WiiLink).wad'),
 ('wiiroom-japanese-wiilink-archive.wad',base+'WiiLink/WAD/Wii no Ma (Japanese) (WiiLink).wad'),
]

if __name__=='__main__':acquisition.main()
