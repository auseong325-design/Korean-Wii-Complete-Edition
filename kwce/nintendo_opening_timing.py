"""Nintendo Channel in-channel opening (content 5, layout/option.arc opening_00): even letter timing.

User report 2026-11-17 (showcase recording): the Korean opening logo looked cut. Cause: the five
syllables sit on the US letter panes N, n, e, C, h and inherit their staggered starts 0/6/12/24/27
(of 15 US letters, last at 42) with a 45-frame flip-in each (rotY 64->0, scale 1.5->1, alpha 0->255;
reflection alpha 0->64). The channel switches to opening_00_out as soon as it has loaded; in Dolphin
that is ~60 frames after the logo appears, so 'chae'/'neol' left the screen still edge-on (thin
vertical strokes). The US title (original YouTube capture on the console) shows every letter settled
with its reflection.

Fix: only the ten Korean letter panes (front + reflection) in opening_00_in/_loop are retimed: starts
0/3/6/12/15 frames after the first letter (word gap +3) and a 36-frame flip-in (hermite slopes scaled
so the curve keeps its shape), so the wordmark is settled 51 frames (0.85 s) after it appears. Key
values, layouts, textures and every other pane are unchanged.
"""
import struct

from .channels import ChannelArchive
from .disk_dvd_anim import _contents
from .nintendo_menu_art_v9 import TITLE

STARTS = (0, 3, 6, 12, 15)
ORIGINAL_DURATION = 45
DURATION = 36
ANIMS = ('arc/anim/opening_00_in.brlan', 'arc/anim/opening_00_loop.brlan')


def retime(raw):
    """Return (brlan, record) with the Korean title panes retimed."""
    d = bytearray(raw)
    entries = {name: tags for name, material, tags in _contents(raw) if not material}
    panes = [(i, p) for i, t in enumerate(TITLE) for p in (t[1], t[2])]
    if any(p not in entries for _, p in panes):
        raise ValueError('Korean title pane missing from animation')

    def frames(tags):
        return [struct.unpack_from('>f', raw, k)[0] for _, _, tracks in tags for _, _, _, keys in tracks for k in keys]

    base = min(frames(entries[TITLE[0][1]]))
    record = {}
    scale = DURATION / ORIGINAL_DURATION
    for index, pane in panes:
        tags = entries[pane]
        old_start = min(frames(tags))
        new_start = base + STARTS[index]
        for _, kind, tracks in tags:
            for _, _, curve, keys in tracks:
                for k in keys:
                    f = struct.unpack_from('>f', raw, k)[0]
                    struct.pack_into('>f', d, k, float(new_start + (f - old_start) * scale))
                    if curve == 2:
                        slope = struct.unpack_from('>f', raw, k + 8)[0]
                        struct.pack_into('>f', d, k + 8, float(slope / scale))
        record[pane] = dict(start=[old_start, new_start], end=[max(frames(tags)), new_start + (max(frames(tags)) - old_start) * scale])
    return bytes(d), record


def opening_timing(content5):
    """Content 5 with the retimed opening animations; same length (zero padded) as the input."""
    archive = ChannelArchive(content5)
    member = 'layout/option.arc'
    inner = ChannelArchive(archive.get(member))
    before = inner
    record = {}
    for path in ANIMS:
        new, rec = retime(inner.get(path))
        inner = ChannelArchive(inner.replace(path, new))
        record[path] = rec
    if any(inner.get(p) != before.get(p) for p in before.files if p not in ANIMS):
        raise ValueError('Opening timing changes escaped the two animations')
    out = ChannelArchive(archive.replace(member, inner.compact())).compact()
    if len(out) > len(content5):
        raise ValueError('Nintendo content 5 capacity exceeded')
    if any(ChannelArchive(out).get(p) != archive.get(p) for p in archive.files if p != member):
        raise ValueError('Content 5 changes escaped option.arc')
    return out + bytes(len(content5) - len(out)), record
