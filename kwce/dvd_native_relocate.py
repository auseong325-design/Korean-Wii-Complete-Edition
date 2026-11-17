"""Build a position-independent MEM2 relocator for reviewed MEM1 DOLs."""
from pathlib import Path
from .dvd_native_loader import inspect_dol
from .ppc_patch import assemble
from .ppc_patch import sections
from .dvd_native_loader import Region

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'homebrew/kwce-disc-menu/native-v1/relocate.s'


def validate_payload(data):
    entry, regions = inspect_dol(data)
    if any(not 0x80003400 <= r.start < r.end <= 0x81300000 for r in regions):
        raise ValueError('Native v1 supports only MEM1 payloads below resident menu')
    return entry, regions


def validate_ash_mapping(data):
    validate_payload(data)
    base=0x80003e00
    if base+len(data)>0x81300000:raise ValueError('Expanded DOL overlaps resident menu')
    rows=sections(data)
    for at,(_,offset,address,size) in enumerate(rows):
        source=base+offset
        if address>source:raise ValueError('ASH loader cannot copy a section upwards')
        target=Region(address,size,'destination')
        if any(target.overlaps(Region(base+o,n,'future source')) for _,o,a,n in rows[at+1:]):
            raise ValueError('ASH relocation overwrites an unread source section')
    return base


def compile_relocator(*, ash=False):
    source=SOURCE.read_text(encoding='ascii')
    if ash:
        # Reviewed R31 has a flat file mapping: DOL offset + 0x80003e00.
        # The SDK decoder is resident above all player destinations and runs
        # using the MEM2 stack installed by the caller, after device shutdown.
        source=source.replace('kwce_relocate:\n', '''kwce_relocate:
    mr r4,r3
    lis r3,0x8000
    ori r3,r3,0x3e00
    lis r12,0x8133
    ori r12,r12,0x17c0
    mtctr r12
    bctrl
    lis r3,0x8000
    ori r3,r3,0x3e00
''')
    return assemble(source, 0, {})
