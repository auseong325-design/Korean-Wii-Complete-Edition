"""Restore GC management icons from the same local 43K resource archive.

No texture decoding, redraw, or foreign-region asset is needed: setupSel and
setupSel2 differ in exactly these three TPLs. Keep the Korean layout/text.
"""
import hashlib
from .formats import U8,ash_decompress,ash_compress

ICONS={
 'arc/timg/it_DataManage_a.tpl':('2e81ad38ce039c343efc470eb8aee4476fdee752e92b9b3b7a42e700ff434c9f','25b60bed64b47f37da07985bc6f63674e8acd1eb1fb3a1500313e4b4481cf5a6'),
 'arc/timg/it_Savedata_a.tpl':('67063faff2b4d60372c37d56fb3f4f896cc2564fcaaa86b5978f3826668e0908','11818269de94a85da018e379508d7f3d6254f80fc818ed71df25c5b569d09031'),
 'arc/timg/it_Savedata_d.tpl':('874556f0fd4c3da18bafb8982a6dd16c4469f8b3212385c59ce977099807a0ee','e3bf8575e42c19325eb216d3c09dc3feb49dc4fa7a890a6e73a64c2e8cce7152'),
}

def patch_gc_icons(data):
    outer=U8(data);source=U8(ash_decompress(outer.get('layout/common/setupSel.ash')))
    target_raw=ash_decompress(outer.get('layout/common/setupSel2.ash'));target=U8(target_raw)
    if set(source.files)!=set(target.files):raise ValueError('Unexpected settings archive tree')
    differences={p for p in source.files if source.get(p)!=target.get(p)}
    if differences!=set(ICONS):raise ValueError('Unexpected settings archive differences')
    for path,(a,b) in ICONS.items():
        if hashlib.sha256(source.get(path)).hexdigest()!=a or hashlib.sha256(target.get(path)).hexdigest()!=b:raise ValueError('Unsupported 43K settings texture')
        if len(source.get(path))!=len(target.get(path)):raise ValueError('Texture size mismatch')
        target_raw=U8(target_raw).replace(path,source.get(path))
    final=U8(target_raw)
    if any(final.get(p)!=(source.get(p) if p in ICONS else target.get(p)) for p in target.files):raise ValueError('Unrelated settings resource changed')
    compressed=ash_compress(target_raw)
    if ash_decompress(compressed)!=target_raw:raise ValueError('Settings ASH round-trip failed')
    result=outer.replace('layout/common/setupSel2.ash',compressed);after=U8(result)
    if any(after.get(p)!=outer.get(p) for p in outer.files if p!='layout/common/setupSel2.ash'):raise ValueError('Unrelated outer file changed')
    return result,dict(textures_restored=sorted(ICONS),source='same 43K setupSel archive',unrelated_settings_files_unchanged=len(target.files)-3,unrelated_outer_files_unchanged=len(outer.files)-1,Korean_layout_preserved=True)
