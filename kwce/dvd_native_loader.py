"""Offline relocation preflight for a channel-independent DVD loader.

This is NOT a loader or an installable hack. Addresses are cached PPC virtual
addresses. A staging candidate still needs a runtime allocator/reservation;
being outside DOL sections does not make memory free in a running menu.
"""
from dataclasses import dataclass
import hashlib
import struct


@dataclass(frozen=True)
class Region:
    start: int
    size: int
    label: str

    @property
    def end(self):
        return self.start + self.size

    def overlaps(self, other):
        return self.start < other.end and other.start < self.end


def _ram(region):
    # Reserve low memory and the upper MEM2 area used by IOS. The latter is
    # deliberately conservative; actual arena limits must be checked at runtime.
    return region.size > 0 and any(
        low <= region.start < region.end <= high
        for low, high in ((0x80003400, 0x81800000), (0x90000000, 0x93400000))
    )


def inspect_dol(data, *, resident=False):
    if len(data) < 0x100:
        raise ValueError('Truncated DOL header')
    regions, files, texts = [], [], []
    for i in range(18):
        offset = struct.unpack_from('>I', data, i * 4)[0]
        address = struct.unpack_from('>I', data, 0x48 + i * 4)[0]
        size = struct.unpack_from('>I', data, 0x90 + i * 4)[0]
        if not size:
            continue
        region = Region(address, size, f'{"text" if i < 7 else "data"}{i}')
        source = Region(offset, size, region.label)
        if offset < 0x100 or offset + size > len(data):
            raise ValueError('DOL section outside file')
        if not _ram(region):
            raise ValueError('DOL section outside allowed PPC RAM')
        if i < 7 and (address % 4 or size % 4):
            raise ValueError('Unaligned DOL text')
        if any(region.overlaps(r) for r in regions):
            raise ValueError('Overlapping DOL destinations')
        if any(source.overlaps(r) for r in files):
            raise ValueError('Overlapping DOL file sections')
        regions.append(region)
        files.append(source)
        if i < 7:
            texts.append(region)
    address, size, entry = struct.unpack_from('>III', data, 0xd8)
    if size:
        bss = Region(address, size, 'bss')
        if not _ram(bss):
            raise ValueError('BSS outside allowed PPC RAM')
        # Some valid DOLs have a broad BSS range overlapping loaded sections.
        # This experimental loader refuses these until zero/copy order is defined.
        if not resident and any(bss.overlaps(r) for r in regions):
            raise ValueError('BSS overlaps loaded section; unsupported layout')
        regions.append(bss)
    # Nintendo menu boot headers may express the low-memory entry as physical.
    # Only normalize the already-resident reference; player entry remains strict.
    if resident and 0x3400 <= entry < 0x1800000:
        entry |= 0x80000000
    if entry % 4 or not any(r.start <= entry < r.end for r in texts):
        raise ValueError('Entry point is not inside executable text')
    return entry, regions


def preflight(player, menu, *, staging=None, trampoline=None):
    entry, target = inspect_dol(player)
    _, resident = inspect_dol(menu, resident=True)
    collisions = [dict(player=p.label, menu=m.label,
                       start=hex(max(p.start, m.start)), end=hex(min(p.end, m.end)))
                  for p in target for m in resident if p.overlaps(m)]
    if (staging is None) != (trampoline is None):
        raise ValueError('Staging and trampoline must be supplied together')
    if staging is not None:
        if staging.size < len(player):
            raise ValueError('Staging cannot hold entire DOL')
        for region in (staging, trampoline):
            if not _ram(region) or region.start % 32 or region.size % 32:
                raise ValueError('Invalid or unaligned loader allocation')
            if any(region.overlaps(r) for r in target + resident):
                raise ValueError('Loader allocation overlaps player or menu')
        if staging.overlaps(trampoline):
            raise ValueError('Staging overlaps trampoline')
    return dict(schema=1, status='offline-preflight-only',
                player_sha256=hashlib.sha256(player).hexdigest(),
                menu_sha256=hashlib.sha256(menu).hexdigest(),
                entry=hex(entry), dol_bytes=len(player),
                target_regions=[dict(label=r.label, start=hex(r.start), end=hex(r.end)) for r in target],
                menu_collisions=collisions,
                static_destination_overlap=bool(collisions),
                runtime_heap_and_threads_checked=False,
                allocations_checked=staging is not None,
                runtime_memory_reservation_verified=False,
                boot_verified=False, installable=False)
