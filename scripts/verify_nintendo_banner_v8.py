"""Verify the US-derived menu artwork without exposing source assets."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce.nintendo_menu_art_v8 import korean_menu_art, swap_names

def main():
    lib = load_library()
    from libWiiPy.archive import decompress_lz77
    root = ROOT / "workspace/channels/nintendo"
    def title(path):
        t = lib.title.Title()
        t.load_wad(path.read_bytes())
        return t
    source = title(root / "build-v4/nintendo-ko-ui-test.wad")
    built = title(root / "build-v8/nintendo-ko-ui-test.wad")
    content, _ = korean_menu_art(source.get_content_by_index(0))
    assert content == built.get_content_by_index(0), "Artwork differs on rebuild"
    source.set_content(content, 0)
    assert source.dump_wad() == (root / "build-v8/nintendo-ko-ui-test.wad").read_bytes(), "UI WAD differs on rebuild"
    access = title(root / "access-build-v5/nintendo-local-test.wad")
    access.set_content(content, 0)
    assert access.dump_wad() == (root / "access-build-v9/nintendo-local-test.wad").read_bytes(), "Access WAD differs on rebuild"
    def nested(t, kind):
        outer = ChannelArchive(t.get_content_by_index(0)[0x640:])
        return ChannelArchive(decompress_lz77(outer.get("meta/" + kind + ".bin")[32:]))
    # Applying the same name permutation again must recover the original animation bytes.
    original = title(root / "build-v4/nintendo-ko-ui-test.wad")
    for kind in ("banner", "icon"):
        before, after = nested(original, kind), nested(built, kind)
        pairs = [("N_logoJS_00", "N_logoES_00")] if kind == "banner" else [("P_logoJ_00", "P_logoE_00"), ("P_logoJ_01", "P_logoE_01")]
        animations = [name for name in before.files if name.endswith(".brlan")]
        assert animations
        for name in animations:
            assert swap_names(after.get(name), pairs, 20) == before.get(name), (kind, name)
        print(kind, "animation files:", len(animations), "original bytes recovered")
    print("PASS: both WADs reproduce byte-for-byte; animation tracks preserved")

if __name__ == "__main__":
    main()
