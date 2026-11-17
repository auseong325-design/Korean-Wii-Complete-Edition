"""Acquire Mii Contest sources; originals remain local and immutable."""
import acquire_forecast as acquisition
from pathlib import Path
acquisition.DEST=Path(__file__).resolve().parents[1]/'workspace/channels/mii-contest/originals'
root='https://repo.mariocube.com/WADs/'
acquisition.FILES=[('mii-contest-usa-v512.wad',root+'_WiiWare, VC, DLC, Channels & IOS/C/Check Mii Out Channel (USA) (v512) (Channel).wad')]
acquisition.FILES += [(f'mii-contest-{r.lower()}-v512.wad',root+f'_WiiWare, VC, DLC, Channels & IOS/M/Mii Contest Channel ({r}) (v512) (Channel).wad')for r in ['Japan','Europe']]
acquisition.FILES.append(('mii-contest-usa-wiilink-archive.wad',root+'WiiLink/WAD/Check Mii Out Channel (USA) (WiiLink).wad'))
if __name__=='__main__':acquisition.main()
