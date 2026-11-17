"""339293 bisection diagnostic WAD (build-v5). WiiLink Demae_1_Japan executable
+ loopback endpoint redirect + Korea-area bridge ONLY. Stock banner, content 2
(layouts/textures), fonts and HOME Menu are UNCHANGED (still Japanese). This
isolates the shop_list 339293 failure from all Korean localization: if the lead
sees 339293 opening a category with this WAD too, the cause is independent of
our Korean strings/content-2/fonts (feed or page-renderer/emulation); if it
works, our localization is implicated. local_only; not a shipping build.
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, sha256
from kwce.wiiroom_formats import decompress_lz11, compress_lz11_optimal
from kwce import bspatch
from build_food import redirect_wiilink_endpoints, WIILINK_PATCH, TITLE, BOOT


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reproduce', action='store_true'); args = ap.parse_args()
    base = ROOT / 'workspace/channels/food'; out = base / 'build-v5'; expected = None
    if args.reproduce:
        expected = (out / 'food-ko-local-test.wad').read_bytes(); n = 1
        while (ROOT / f'workspace/private/food-diag-reproduce-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/food-diag-reproduce-{n}'
    if out.exists():
        raise SystemExit('Existing Food build-v5 preserved')
    source = (base / 'originals/food-japan-v512.wad').read_bytes()
    lib = load_library(); title = lib.title.Title(); title.load_wad(source)
    if title.tmd.title_id != TITLE or title.tmd.boot_index != BOOT:
        raise ValueError('Food source identity differs')
    original = [title.get_content_by_index(i) for i in range(title.tmd.num_contents)]
    dol = bspatch.apply(original[1], (ROOT / WIILINK_PATCH).read_bytes())
    dol, ep = redirect_wiilink_endpoints(dol)
    from kwce.food_compat import patch_korean_area
    dol, area = patch_korean_area(dol)
    packed = compress_lz11_optimal(dol)
    if decompress_lz11(packed) != dol:
        raise ValueError('diagnostic LZ11 roundtrip failed')
    title.set_content(packed, 1); title.tmd.region = 4
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    changed = [i for i in range(title.tmd.num_contents) if check.get_content_by_index(i) != original[i]]
    if changed != [1]:
        raise ValueError('Diagnostic must change only content 1: ' + str(changed))
    out.mkdir(parents=True); (out / 'food-ko-local-test.wad').write_bytes(wad)
    manifest = dict(revision=5, channel='food', diagnostic='339293 bisection', title_id=title.tmd.title_id,
                    boot_index=BOOT, wad_sha256=sha256(wad), executable_base='WiiLink Demae_1_Japan',
                    endpoints=ep, korean_area_bridge=area, changed_contents=changed,
                    localization='NONE (stock banner/content2/fonts/HOME, Japanese on screen)',
                    local_only=True, full_localization_complete=False, hardware_success_verified=False)
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if expected is not None and expected != wad:
        raise ValueError('diagnostic reproduction differs')
    print(('Reproduced byte-identically' if expected else 'Built'), 'Food diagnostic build-v5: WiiLink DOL + 127.0.0.2 + area bridge only, wad', sha256(wad)[:12])


if __name__ == '__main__':
    main()
