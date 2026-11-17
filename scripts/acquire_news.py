"""Preserve requested News originals separately; no console data transmitted."""
import acquire_forecast as acquisition
from pathlib import Path
acquisition.DEST=Path(__file__).resolve().parents[1]/'workspace/channels/news/originals'
base='https://repo.mariocube.com/WADs/_WiiWare, VC, DLC, Channels & IOS/N/'
acquisition.FILES=[(f'news-{r.lower()}-v7.wad',base+f'News Channel ({r}) (v7) (Channel).wad')for r in ['USA','Japan','Europe']]
acquisition.FILES.append(('news-usa-wiilink-archive.wad','https://repo.mariocube.com/WADs/WiiLink/WAD/News Channel (USA) (WiiLink).wad'))
if __name__=='__main__':acquisition.main()
