"""Compare Nintendo menu artwork without exporting channel content or identities.

The report describes the project's pinned WiiLink source and Korean candidate;
it does not read or infer anything about a console's installed title.

python scripts/audit_nintendo_menu_art.py [--build build-vN]
Default build: the nintendo entry of configs/rc-package.json (read only). The icon report also
names the texture of the pane the stock icon channel script turns on for a Korean console.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import ChannelArchive, layout_sections, load_library

# The icon channel script (content 2 arc/icon.cs.lz7, setRegionPanes; identical in the JP/US/WiiLink
# originals) shows this pane for SC_LANG_KOREAN -- not the KOR group (see RC6 W-Nintendo report).
KOREAN_SCRIPT_PANE = "P_logoJ_00"


def pane_texture(layout, pane):
    """Texture name of a picture pane's first material texture, or None."""
    sections = layout_sections(layout)
    mat1 = next(s for s in sections if s[:4] == b"mat1")
    offsets = struct.unpack_from(f">{struct.unpack_from('>H', mat1, 8)[0]}I", mat1, 12)
    txl1 = next(s for s in sections if s[:4] == b"txl1")
    count = struct.unpack_from(">H", txl1, 8)[0]
    names = []
    for i in range(count):
        at = 12 + struct.unpack_from(">I", txl1, 12 + 8 * i)[0]
        names.append(txl1[at:txl1.index(b"\0", at)].decode("ascii"))
    for s in sections:
        if s[:4] == b"pic1" and s[12:28].split(b"\0")[0].decode("ascii") == pane:
            mo = offsets[struct.unpack_from(">H", s, 0x5c)[0]]
            if struct.unpack_from(">I", mat1, mo + 0x3c)[0] & 15:
                return names[struct.unpack_from(">H", mat1, mo + 0x40)[0]]
    return None


def unpack(wrapped):
    if (wrapped[:4] != b"IMD5" or len(wrapped) < 32
            or int.from_bytes(wrapped[4:8], "big") != len(wrapped) - 32
            or hashlib.md5(wrapped[32:]).digest() != wrapped[16:32]):
        raise ValueError("Invalid menu resource wrapper")
    from libWiiPy.archive import decompress_lz77
    return ChannelArchive(decompress_lz77(wrapped[32:]))


def examine(source, translated):
    if source[:4] != translated[:4]:
        raise ValueError("Menu content format differs")
    a, b = ChannelArchive(source[0x640:]), ChannelArchive(translated[0x640:])
    report = {}
    for kind in ("banner", "icon"):
        name = f"meta/{kind}.bin"
        raw_a, raw_b = a.get(name), b.get(name)
        arc_a, arc_b = unpack(raw_a), unpack(raw_b)
        if set(arc_a.files) != set(arc_b.files):
            raise ValueError("Menu resource topology differs")
        layout = arc_b.get(f"arc/blyt/{kind}.brlyt")
        sections = layout_sections(layout)
        groups = [s[8:24].split(b"\0")[0].decode("ascii")
                  for s in sections if s[:4] == b"grp1"]
        report[kind] = {
            "resource_byte_identical": raw_a == raw_b,
            "layout_byte_identical": arc_a.get(f"arc/blyt/{kind}.brlyt") == layout,
            "animation_files": sum(p.endswith(".brlan") for p in arc_b.files),
            "animations_byte_identical": all(arc_a.get(p) == arc_b.get(p)
                                            for p in arc_b.files if p.endswith(".brlan")),
            "has_korean_group": "KOR" in groups,
            "has_japanese_group": "JPN" in groups,
            "logo_texture_count": sum("logo" in p.lower() and p.endswith(".tpl")
                                      for p in arc_b.files),
        }
        if kind == "icon":
            texture = pane_texture(layout, KOREAN_SCRIPT_PANE)
            report[kind]["korean_script_pane_texture"] = texture
            report[kind]["korean_script_pane_is_original_japanese_logo"] = (
                texture is not None and arc_b.get(f"arc/timg/{texture}") == arc_a.get("arc/timg/oh_proLogo_J_00.tpl"))
    report["sound_byte_identical"] = a.get("meta/sound.bin") == b.get("meta/sound.bin")
    report["menu_graphics_and_animation_preserved"] = all(
        report[kind]["resource_byte_identical"] for kind in ("banner", "icon"))
    return report


def current_build():
    """The Korean Nintendo WAD the RC package ships (configs/rc-package.json, read only)."""
    package = json.loads((ROOT / "configs/rc-package.json").read_text(encoding="utf-8"))
    return next(c["korean"] for c in package["channels"] if c["id"] == "nintendo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", help="build folder under workspace/channels/nintendo (default: RC package)")
    args = ap.parse_args()
    lib = load_library()
    base = ROOT / "workspace/channels/nintendo"
    wad = f"{args.build}/nintendo-ko-ui-test.wad" if args.build else current_build()
    source, korean = lib.title.Title(), lib.title.Title()
    source.load_wad((base / "originals/nintendo-usa-wiilink-archive.wad").read_bytes())
    korean.load_wad((base / wad).read_bytes())
    report = examine(source.get_content_by_index(0), korean.get_content_by_index(0))
    report["build"] = wad
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
