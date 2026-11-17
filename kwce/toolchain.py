"""Select the separately pinned host toolchain without global PATH changes."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DKP = ROOT / ('tools/devkitpro-root/opt/devkitpro' if sys.platform == 'win32'
              else 'tools/linux/devkitpro-root/opt/devkitpro')
BIN = DKP / 'devkitPPC/bin'


def tool(name, folder=BIN):
    if sys.platform != 'win32' and name.endswith('.exe'):
        name = name[:-4]
    return folder / name
