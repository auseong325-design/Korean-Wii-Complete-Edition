"""Export private local deltas and reproduce the WAD; no installation/upload."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.channel_patch import make_patch,apply_patch

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
    if not 1<=args.revision<=1000:raise SystemExit('Revision bounds')
    base=ROOT/'workspace/channels/forecast';build=base/f'build-v{args.revision}';folder=base/f'patches/v{args.revision}'
    if folder.exists():raise SystemExit('Existing channel patch preserved')
    record=json.loads((build/'build-manifest.json').read_text(encoding='utf-8'));source=(base/'originals/forecast-usa-wiilink-archive.wad').read_bytes();target=(build/'forecast-ko-personal-test.wad').read_bytes()
    if sha(source)!=record['base_sha256']or sha(target)!=record['wad_sha256']:raise ValueError('Patch build source differs')
    lib=load_library();original=lib.title.Title();original.load_wad(source);translated=lib.title.Title();translated.load_wad(target)
    if original.tmd.title_id!=translated.tmd.title_id or translated.tmd.title_id!='0001000248414645':raise ValueError('Forecast patch identity')
    if original.tmd.region!=translated.tmd.region:
        if (original.tmd.region,translated.tmd.region)!=(record.get('TMD_region_before'),record.get('TMD_region_after'))or translated.tmd.region!=4:raise ValueError('Unexpected channel region metadata change')
        original.tmd.region=translated.tmd.region
    folder.mkdir(parents=True);rows=[]
    for index in range(12):
        before=original.get_content_by_index(index);after=translated.get_content_by_index(index)
        if before==after:continue
        patch=make_patch(before,after);name=f'content-{index:02d}.kwcp';(folder/name).write_bytes(patch);rebuilt=apply_patch(before,patch);original.set_content(rebuilt,index)
        rows.append(dict(index=index,file=name,patch_sha256=sha(patch),size=len(patch)))
    rebuilt=original.dump_wad()
    if rebuilt!=target:raise ValueError('Private patch WAD differs from built WAD')
    for name in ['forecast-ko.json','forecast-dynamic-ko.json','forecast-places-ko.json']:shutil.copy2(ROOT/'configs'/name,folder/name)
    manifest=dict(schema=1,channel='forecast',title_id='0001000248414645',revision=args.revision,base_sha256=sha(source),output_sha256=sha(target),contents=rows,byte_identical_WAD_rebuild_verified=True,redistribution='private local only; deltas may contain Nintendo data; Git ignored',installer_status='prototype; not offered as a completed selectable channel',scope='test NAND only; no hardware installer',preserve_console_locale=dict(region='KOR',language=9,country=136),live_compatibility_verified=False)
    manifest['channel_TMD_region']=translated.tmd.region
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))

if __name__=='__main__':main()
