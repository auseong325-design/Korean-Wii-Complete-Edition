"""Stage a region-4 Mii Contest build as a numbered hardware install candidate.

  .venv\\Scripts\\python.exe scripts\\build_mii_contest_hardware.py --hardware 2 [--reproduce]

hardware-v1 wraps build-v26 (kept; build-v26 panics at boot in Dolphin) and hardware-v2 wraps
build-v27 (in-place cave rework). The on-console build already carries TMD region 4 (KOR), which the
Korean System Menu accepts (__OSCheckTmdCountryCode requires region 3 or 4). This wraps that exact WAD,
unchanged, into a new numbered hardware candidate with an allowed-fields manifest (title id / version /
IOS / TMD region / per-content index,size,hash only -- never key/ticket/console bytes). It preserves the
WAD byte for byte (copy + re-read hash). --reproduce rebuilds into workspace/private and requires the
WAD and manifest to be byte-identical. It performs NO SD write and NO install; HBC/SD packaging is the
lead's step (export_channel_hardware_package.py).
"""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,sha256

SOURCES={1:26,2:27}   # hardware-vN -> build-vM

def _layout(wad):
    t=load_library().title.Title();t.load_wad(wad);dol=t.get_content_by_index(1)
    from kwce.mii_contest_runtime import dol_layout
    return dol_layout(dol)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--hardware',type=int,choices=sorted(SOURCES),default=1)
    ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    build=SOURCES[args.hardware];base=ROOT/'workspace/channels/mii-contest'
    src=base/f'build-v{build}/mii-contest-ko-ui-test.wad'
    meta=json.loads((base/f'build-v{build}/build-manifest.json').read_text())
    if sha256(src.read_bytes())!=meta['wad_sha256']:raise ValueError(f'build-v{build} WAD differs from its manifest')
    out=base/f'hardware-v{args.hardware}';expected=None
    if args.reproduce:
        expected=((out/'mii-contest-ko-hardware.wad').read_bytes(),(out/'hardware-manifest.json').read_bytes());n=1
        while(ROOT/f'workspace/private/mii-contest-hardware-reproduce-v{args.hardware}-{n}').exists():n+=1
        out=ROOT/f'workspace/private/mii-contest-hardware-reproduce-v{args.hardware}-{n}'
    if out.exists():raise SystemExit('Existing Mii Contest hardware candidate preserved')
    lib=load_library();t=lib.title.Title();t.load_wad(src.read_bytes())
    if t.tmd.region!=4:raise ValueError(f'Hardware candidate must be TMD region 4, got {t.tmd.region}')
    contents=[dict(index=r.index,size=r.content_size,
                   sha1=r.content_hash.decode('ascii')if isinstance(r.content_hash,(bytes,bytearray))else str(r.content_hash))
              for r in t.tmd.content_records]
    extra={}
    if args.hardware>=2:
        # The boot path reads the content-1 DOL header: it must match build-v25 (boots in Dolphin).
        mine=_layout(src.read_bytes());ref=_layout((base/'build-v25/mii-contest-ko-ui-test.wad').read_bytes())
        if mine!=ref:raise ValueError('Content-1 DOL layout differs from build-v25')
        extra=dict(dol_layout_equals_build_v25=True,dol_section_count=mine['section_count'],
                   dol_image=f"{mine['image_lo']:#x}..{mine['image_hi']:#x}",
                   dol_bss=f"{mine['bss']:#x}..{mine['bss']+mine['bss_size']:#x}",
                   specialty_cave=meta['specialty_runtime']['cave_va']+'..'+meta['specialty_runtime']['cave_end'])
    out.mkdir(parents=True);dst=out/'mii-contest-ko-hardware.wad';shutil.copyfile(src,dst)
    if sha256(dst.read_bytes())!=meta['wad_sha256']:raise ValueError('Copied hardware WAD differs')
    record=dict(candidate=f'mii-contest hardware-v{args.hardware}',source_build=f'build-v{build}',
                wad_sha256=sha256(dst.read_bytes()),title_id=t.tmd.title_id,
                title_version=t.tmd.title_version,ios=t.tmd.ios_tid[-2:],tmd_region=t.tmd.region,
                region_name='KOR',contents=contents,source_service_addresses_preserved=True,
                sd_written=False,installed=False,hardware_verified=False,
                note=f'Region 4 native to build-v{build}; Korean System Menu accepts region 3/4. '
                     'Lead packages for HBC/SD via export_channel_hardware_package.py; no SD write here.',
                **extra)
    (out/'hardware-manifest.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
    if expected is not None:
        if((out/'mii-contest-ko-hardware.wad').read_bytes(),(out/'hardware-manifest.json').read_bytes())!=expected:raise ValueError('Mii Contest hardware reproduction differs')
        print(f'Reproduced byte-identically: hardware-v{args.hardware} (WAD + manifest) in {out}')
if __name__=='__main__':main()
