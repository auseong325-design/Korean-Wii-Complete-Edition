"""Korean Set Personal Data (SPD) + fictional pd.dat for the Photo Prints test bed.

Digicam requires the SPD title 00010008-4843434a (HCCJ) on the console (else the
'주소 정보를 설정할 수 없습니다 / 본체 업데이트' dialog, PD_Dialog_Update) and
reads /title/00010008/4843434a/data/nocopy/pd.dat for the order address.
This reuses, read-only, the personal-data worker's Korean local build-v2
(pinned by SHA-256) and fictional sample (kwce/personal_data_format, local-feed-v1).
pd.dat is encrypted only for Dolphin's public DEFAULT_DEVICE_ID; the launcher's
validate() refuses any profile holding keys.bin, so no real console ID applies.
"""
import hashlib,json
from .channels import ROOT,load_library
from . import personal_data_format as fmt

SPD_TITLE='000100084843434a'
SPD_WAD=ROOT/'workspace/channels/personal-data/build-v2/personal-data-ko-local-test.wad'
SPD_SHA256='db968ff1e21d54c12f396d99270f7a4249076fd9ea56b2fbe4f4b606fc06ffcb'
SPD_IOS='000000010000003a'
FICTIONAL_PLAIN=ROOT/'workspace/channels/personal-data/local-feed-v1/fictional-pd-plain.bin'
FICTIONAL_SHA256='311f1927cdea95fb9909b1f815055b6331f4aba9a32b8e0bba386b4cab6bd2c9'
PD_REL='title/00010008/4843434a/data/nocopy/pd.dat'
IOS58_DIR='title/00000001/0000003a/content'


def _sha(data):return hashlib.sha256(data).hexdigest()


def spd_title():
    raw=SPD_WAD.read_bytes()
    if _sha(raw)!=SPD_SHA256:raise ValueError('Korean SPD build-v2 differs from the pinned SHA-256')
    meta=json.loads(SPD_WAD.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if not meta.get('local_only') or meta.get('title_id')!=SPD_TITLE or meta.get('wad_sha256')!=SPD_SHA256:raise ValueError('SPD build scope/identity')
    title=load_library().title.Title();title.load_wad(raw)
    if title.tmd.title_id.lower()!=SPD_TITLE or title.tmd.ios_tid.lower()!=SPD_IOS:raise ValueError('SPD WAD title/IOS differs')
    return title


def ios58_record(wii):
    folder=wii/IOS58_DIR
    if not (folder/'title.tmd').is_file():raise ValueError('Profile lacks IOS58 required by the SPD TMD; clone it from workspace/sandbox/personal-data-test-v1')
    return {p.name:_sha(p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()}


def fictional_plain():
    plain=FICTIONAL_PLAIN.read_bytes()
    if _sha(plain)!=FICTIONAL_SHA256:raise ValueError('Fictional pd.dat sample differs from its pinned SHA-256')
    fmt.check(plain);return plain


def install(wii,data='keep'):
    """Install the pinned SPD title; data: keep | fictional | clear. Returns the lock record."""
    lib=load_library();title=spd_title();lib.nand.EmuNAND(wii).install_title(title)
    record=dict(spd_title=SPD_TITLE,spd_wad=SPD_WAD.relative_to(ROOT).as_posix(),spd_wad_sha256=SPD_SHA256,
        spd_tmd_sha256=_sha(title.tmd.dump()),spd_title_version=title.tmd.title_version,
        ios58=ios58_record(wii),pd_path='/'+PD_REL)
    target=wii/PD_REL
    if data=='fictional':
        plain=fictional_plain();target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(fmt.encrypt(plain,fmt.DOLPHIN_DEFAULT_DEVICE_ID))
        if fmt.decrypt(target.read_bytes(),fmt.DOLPHIN_DEFAULT_DEVICE_ID)!=plain:raise ValueError('pd.dat encryption roundtrip failed')
    elif data=='clear' and target.exists():target.unlink()
    if target.exists():
        record.update(pd_installed=True,pd_sha256=_sha(target.read_bytes()),fictional_plain_sha256=FICTIONAL_SHA256,
            device_id='Dolphin public DEFAULT_DEVICE_ID',fictional=True)
    else:record.update(pd_installed=False)
    return record


def verify(wii,record):
    """--check side: installed SPD TMD/contents, IOS58 and pd.dat match the lock."""
    from .channel_validation import verify_installed_title
    title=spd_title()
    if _sha(title.tmd.dump())!=record['spd_tmd_sha256']:raise ValueError('Pinned SPD TMD differs')
    verify_installed_title(wii,SPD_TITLE,title.tmd.dump())
    if ios58_record(wii)!=record['ios58']:raise ValueError('IOS58 contents changed')
    target=wii/PD_REL
    if record.get('pd_installed'):
        if not target.is_file() or _sha(target.read_bytes())!=record['pd_sha256']:raise ValueError('Fictional pd.dat differs from the lock')
        if fmt.decrypt(target.read_bytes(),fmt.DOLPHIN_DEFAULT_DEVICE_ID)!=fictional_plain():raise ValueError('pd.dat is not the fictional sample')
    elif target.exists():raise ValueError('Unexpected pd.dat in the profile')
    return True
