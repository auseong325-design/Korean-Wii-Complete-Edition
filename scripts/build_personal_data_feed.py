"""Synthetic fixtures for the Korean Set Personal Data test bed (create-once).

Set Personal Data has no network service, so routes.tsv is empty. The fixture
is a decrypted pd.dat image with obviously fictional Korean values, laid out
per WiiLink's pinned kaitai/pd_info offsets on top of the cleared Korean
template. install_personal_data_test.py --fictional-data can encrypt it for
the isolated profile (Dolphin's public default device ID only).
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce import personal_data_format as fmt
from kwce.personal_data_fork import SOURCE

def build():
    template,_=fmt.korean_template((SOURCE/'data/title/pd_decrypted.dat').read_bytes())
    plain=fmt.fictional_sample(template)
    files={'fictional-pd-plain.bin':plain,'routes.tsv':b''}
    manifest=dict(revision=1,local_only=True,synthetic=True,fictional=True,service='none: Set Personal Data has no network service',
        layout='WiiLink24/set-personal-data@18fa5a7d pd.ksy + pd_info.cpp offsets',values=fmt.FICTIONAL,
        device_id_policy='encrypted only for the isolated profile with Dolphin 2609a DEFAULT_DEVICE_ID; never a real console ID',
        files=[dict(path=n,bytes=len(d),sha256=hashlib.sha256(d).hexdigest())for n,d in files.items()])
    return files,manifest

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,choices=[1],default=1);args=ap.parse_args()
    out=ROOT/f'workspace/channels/personal-data/local-feed-v{args.revision}'
    if out.exists():raise SystemExit('Existing personal-data local feed preserved')
    files,manifest=build();out.mkdir(parents=True)
    for name,data in files.items():(out/name).write_bytes(data)
    (out/'fixture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('Created',out.relative_to(ROOT).as_posix(),': fictional pd.dat plaintext, empty routes; no service responses')
if __name__=='__main__':main()
