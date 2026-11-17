"""Preserve Nintendo Channel originals, separate from all previous channels."""
import acquire_forecast as acquisition
from pathlib import Path
acquisition.DEST=Path(__file__).resolve().parents[1]/'workspace/channels/nintendo/originals'
base='https://repo.mariocube.com/WADs/_WiiWare, VC, DLC, Channels & IOS/N/'
acquisition.FILES=[(f'nintendo-{r.lower()}-v1792.wad',base+f'Nintendo Channel ({r}) (v1792) (Channel).wad')for r in ['USA','Japan','Europe']]
acquisition.FILES.append(('nintendo-usa-wiilink-archive.wad','https://repo.mariocube.com/WADs/WiiLink/WAD/Nintendo Channel (USA) (WiiLink).wad'))
if __name__=='__main__':acquisition.main()
