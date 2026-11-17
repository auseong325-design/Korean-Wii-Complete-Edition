"""Build the HOME-dialog fix for the channels whose HOME message tables are still the original English.

    votes        build-v20 -> build-v21   (content 10  Channel/home_nosave.csv, Channel/home.csv)
    mii-contest  build-v30 -> build-v31   (content 4   content4/Basic/HBM/home_nosave.csv, home.csv)

Why: on a Korean console both channels run the executable's English fallback for the HOME Button Menu
(Votes 0x8003c09c: language >= 7 -> 1; Mii Contest 0x8027bf8c: 7/8/9 -> 1), i.e. the Korean HOME archive
that the Korean builds put in the English slot (Votes HomeButton3/LZ77_homeBtn_ENG.arc, Mii Contest
HBM/homeBtn_ENG.szs) together with message column 1 of the channel's own home_nosave.csv. That table was
still the original English text, and the Korean HOME font is a subset of Hangul plus "Wii" and "?", so
"Return to the Wii Menu?" showed as "Wii      ?" (real console, RC6).

What: kwce.home_menu.localize_dialog_csv is applied to the file the executable reads (home_nosave.csv)
and to home.csv, all seven legacy language columns, the same recipe the News/Forecast/Food/TV Guide
builds use. The new files are written over the old ones, the U8 size fields shrink and the freed bytes
are zeroed, so every other file keeps its offset and the content keeps its original length (a longer
Votes content 10 failed to initialise). Nothing else changes: the executable (content 1, including the
Votes country disguise) and all other contents are byte-identical to the parent build.

    build_votes_home.py                                  # votes: write build-v21 and verify
    build_votes_home.py --reproduce                      # rebuild into workspace/private, require identical bytes
    build_votes_home.py --channel mii-contest            # Mii Contest: write build-v31 and verify
    build_votes_home.py --channel mii-contest --reproduce

No Dolphin, no SD, no network. The message table is read by the executable at run time, so the lead
must still confirm the HOME confirmation dialog on screen (the executable is unchanged).
"""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce.home_menu import (korean_dialog_messages, localize_dialog_csv, KOREAN_CSV_SHA256,
                            replace_shrinking, home_font_mapping, missing_glyphs)

# Votes constants (kept: the tests import them).
VOTES = ROOT / 'workspace/channels/votes'
BASE_REVISION = 20
REVISION = 21
NAME = 'votes-ko-ui-test.wad'
NUM_CONTENTS = 14
HOME_CONTENT = 10
# (file, read by the executable?)  only home_nosave.csv has a string in the DOL (0x80205ec0)
CSV_FILES = (('Channel/home_nosave.csv', True), ('Channel/home.csv', False))
FONT_ARCHIVE = 'HomeButton3/LZ77_homeBtn_ENG.arc'   # the archive the executable loads for a Korean console
LEGACY_COLUMNS = tuple(range(7))
PROBLEM = 'HOME confirmation showed the original English text with the Korean subset font (only "Wii" and "?" drawn)'

CHANNELS = {
    'votes': dict(
        dir='votes', name=NAME, base=BASE_REVISION, revision=REVISION, contents=NUM_CONTENTS,
        home_content=HOME_CONTENT, csv_files=CSV_FILES,
        font_content=4, font_archive=FONT_ARCHIVE,
        executable_reads='/Channel/home_nosave.csv (content 10) column 1; archive HomeButton3/LZ77_homeBtn_ENG.arc (content 4)',
        unchanged_contents=(1, 4),            # reported as untouched in the manifest
        reproduce_prefix='votes-home-reproduce'),
    'mii-contest': dict(
        dir='mii-contest', name='mii-contest-ko-ui-test.wad', base=30, revision=31, contents=8,
        home_content=4,
        csv_files=(('content4/Basic/HBM/home_nosave.csv', True), ('content4/Basic/HBM/home.csv', False)),
        font_content=4, font_archive='content4/Basic/HBM/homeBtn_ENG.szs',
        executable_reads='HBM/home_nosave.csv (content 4, content4/Basic) column 1; archive HBM/homeBtn_ENG.szs (content 4)',
        unchanged_contents=(1,),
        reproduce_prefix='mii-contest-home-reproduce'),
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _identity(title):
    tmd = title.tmd
    return tmd.region, tmd.title_id, tmd.title_version, tmd.ios_tid, len(tmd.content_records)


def hangul_font_mapping(content, spec=CHANNELS['votes']):
    """Code points of the Korean HOME font the executable loads (the _ENG archive of the font content)."""
    return home_font_mapping(ChannelArchive(content).get(spec['font_archive']))


def build(channel='votes'):
    spec = CHANNELS[channel]
    home, base_revision, revision = spec['home_content'], spec['base'], spec['revision']
    base_dir = ROOT / 'workspace/channels' / spec['dir'] / f'build-v{base_revision}'
    base_meta = json.loads((base_dir / 'build-manifest.json').read_text(encoding='utf-8'))
    base_wad = (base_dir / spec['name']).read_bytes()
    if _sha(base_wad) != base_meta['wad_sha256']:
        raise ValueError(f'build-v{base_revision} WAD differs from its manifest; refusing to build on it')

    lib = load_library()
    title = lib.title.Title()
    title.load_wad(base_wad)
    original = [title.get_content_by_index(i) for i in range(spec['contents'])]
    if len(title.tmd.content_records) != spec['contents']:
        raise ValueError('Unexpected number of contents')

    messages = korean_dialog_messages()          # the console's own Korean HOME text (sha-checked)
    mapping = hangul_font_mapping(original[spec['font_content']], spec)
    archive = ChannelArchive(original[home])
    records = []
    for name, read_by_executable in spec['csv_files']:
        before = archive.get(name)
        changed, targets = localize_dialog_csv(before, messages, LEGACY_COLUMNS)
        missing = missing_glyphs(targets, mapping)
        if missing:
            raise ValueError(f'{name}: Korean HOME text has glyphs the HOME font lacks: {missing}')
        archive = ChannelArchive(replace_shrinking(archive, name, changed))
        records.append(dict(file=name, read_by_executable=read_by_executable, translated_columns=list(LEGACY_COLUMNS),
                            translated_rows=4, bytes_before=len(before), bytes_after=len(changed),
                            sha256_before=_sha(before), sha256_after=_sha(changed), font_coverage_verified=True))
    content = archive.data
    if len(content) != len(original[home]):
        raise ValueError(f'Content {home} length changed')
    title.set_content(content, home)
    wad = title.dump_wad()

    check = lib.title.Title()
    check.load_wad(wad)
    changed_contents = [i for i in range(spec['contents']) if check.get_content_by_index(i) != original[i]]
    if changed_contents != [home]:
        raise ValueError(f'Expected only content {home} to change, got {changed_contents}')
    parent = lib.title.Title()
    parent.load_wad(base_wad)
    if _identity(check) != _identity(parent):
        raise ValueError('TMD identity changed')
    new_home, old_home = ChannelArchive(check.get_content_by_index(home)), ChannelArchive(original[home])
    touched = {n for n in old_home.files if new_home.get(n) != old_home.get(n)}
    if touched != {n for n, _ in spec['csv_files']}:
        raise ValueError(f'Unexpected content {home} files changed: {sorted(touched)}')

    updates = {
        'revision': revision,
        'parent_revision': base_revision,
        'wad_sha256': _sha(wad),
        'runtime_verified': False,
        'installed': False,
        f'content_{home}_original_size_preserved': True,
        'changed_from_parent': [home],
        'home_dialog_fix': {
            'problem': PROBLEM,
            'executable_reads': spec['executable_reads'],
            'files': records,
            'source_csv_sha256': KOREAN_CSV_SHA256,
            'korean_messages': len(messages),
            f'other_content_{home}_files_unchanged': True,
            f'content_{home}_length': len(content),
            **{f'content_{n}_unchanged': True for n in spec['unchanged_contents']},
            'hardware_verified': False,
        },
    }
    meta = copy.deepcopy(base_meta)
    meta.update(updates)
    return wad, meta, base_meta['wad_sha256']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--channel', choices=sorted(CHANNELS), default='votes')
    ap.add_argument('--reproduce', action='store_true',
                    help='rebuild into workspace/private and require identical WAD + manifest')
    args = ap.parse_args()
    spec = CHANNELS[args.channel]
    revision, base_revision = spec['revision'], spec['base']

    wad, meta, base_sha = build(args.channel)

    out = ROOT / 'workspace/channels' / spec['dir'] / f'build-v{revision}'
    expected = None
    if args.reproduce:
        if not out.exists():
            raise SystemExit(f'build-v{revision} does not exist yet; run without --reproduce first')
        expected = ((out / spec['name']).read_bytes(), (out / 'build-manifest.json').read_bytes())
        n = 1
        while (ROOT / f"workspace/private/{spec['reproduce_prefix']}-{n}").exists():
            n += 1
        out = ROOT / f"workspace/private/{spec['reproduce_prefix']}-{n}"

    if out.exists():
        raise SystemExit('Existing build preserved')

    manifest_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    if expected is not None and (wad, manifest_bytes) != expected:
        raise SystemExit(f'build-v{revision} reproduction differs from the stored build')

    out.mkdir(parents=True)
    (out / spec['name']).write_bytes(wad)
    (out / 'build-manifest.json').write_bytes(manifest_bytes)

    where = 'reproduced into ' + str(out.relative_to(ROOT)) if args.reproduce else 'built'
    print(json.dumps(dict(status=where, channel=args.channel, revision=revision, base=f'build-v{base_revision}',
                          base_wad_sha256=base_sha[:16], wad_sha256=meta['wad_sha256'],
                          changed_contents=meta['changed_from_parent'],
                          csv=[(r['file'], r['bytes_before'], r['bytes_after']) for r in meta['home_dialog_fix']['files']]),
                     indent=2))


if __name__ == '__main__':
    main()
