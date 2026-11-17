"""Acquire separate Everybody Votes working sources; never sends console data."""
import acquire_forecast as acquisition
from pathlib import Path
acquisition.DEST=Path(__file__).resolve().parents[1]/'workspace/channels/votes/originals'
base='https://repo.mariocube.com/WADs/_WiiWare, VC, DLC, Channels & IOS/E/'
acquisition.FILES=[(f'votes-{r.lower()}-v512.wad',base+f'Everybody Votes Channel ({r}) (v512) (Channel).wad')for r in ['USA','Japan','Europe']]
acquisition.FILES.append(('votes-usa-wiilink-archive.wad','https://repo.mariocube.com/WADs/WiiLink/WAD/Everybody Votes Channel (USA) (WiiLink).wad'))
if __name__=='__main__':acquisition.main()
