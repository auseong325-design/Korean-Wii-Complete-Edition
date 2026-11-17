"""Full-review fixes (kwce/review_fixes_1117.py): Korean HOME guide + quit prompt (+ Nintendo movie prompt).

  python scripts/build_review_fixes_1117.py --channel nintendo|food [--reproduce]

nintendo build-v21 -> build-v25 (v22-v24 superseded: the HOME prompt shows text only up to its first '?' line): content 5 (Promotion fonts E/F/S, HomeButton3/network.csv,
    HomeButton3/Wiiware_guid_jpn.jpg), content 6 (HOME subset fonts), content 8 (LZ77_homeBtn_nwm_jpn.arc).
food hardware-v18 -> hardware-v22 (v19-v21 superseded): content 2 (Dtest/Home/Demae_guide-00.jpg, network_nosave.csv),
    content 4 (HOME subset fonts), content 6 (LZ77_homeBtn_nwm_jpn.arc).
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce import review_fixes_1117 as rf

PINS = dict(nintendo=('build-v21', 'build-v25', 'nintendo-ko-ui-test.wad', 4),
            food=('hardware-v18', 'hardware-v22', 'food-ko-hardware-test.wad', 4),
            internet=('hardware-v12', 'hardware-v13', 'internet-ko-hardware-candidate.wad', 0),
            kirbytv=('hardware-v11', 'hardware-v13', 'kirbytv-ko-hardware-test.wad', 0),
            **{'nintendo-v24': ('build-v21', 'build-v24', 'nintendo-ko-ui-test.wad', 3),
               'food-v21': ('hardware-v18', 'hardware-v21', 'food-ko-hardware-test.wad', 3)},
            # v23 / v20: two-line prompt whose long second line the HOME dialog drops (reproduce only)
            **{'nintendo-v23': ('build-v21', 'build-v23', 'nintendo-ko-ui-test.wad', 2),
               'food-v20': ('hardware-v18', 'hardware-v20', 'food-ko-hardware-test.wad', 2)},
            # first versions: three-line quit prompt, the HOME dialog drops the third line (reproduce only)
            **{'nintendo-v22': ('build-v21', 'build-v22', 'nintendo-ko-ui-test.wad', 1),
               'food-v19': ('hardware-v18', 'hardware-v19', 'food-ko-hardware-test.wad', 1)})


def edit(channel, contents, version):
    record = {}
    message = rf.QUIT_MESSAGES.get(version)
    if channel == 'nintendo':
        c5 = ChannelArchive(contents[5])
        c5, record['promotion_fonts'] = rf.promotion_fonts(c5)
        c5 = ChannelArchive(c5.replace('HomeButton3/network.csv', rf.quit_csv(c5.get('HomeButton3/network.csv'), message)))
        c5 = ChannelArchive(c5.replace('HomeButton3/Wiiware_guid_jpn.jpg', rf.guide_picture(c5.get('HomeButton3/Wiiware_guid_jpn.jpg'), 'nintendo')))
        contents[5] = c5.compact()
        c6, record['home_fonts'] = rf.home_fonts(ChannelArchive(contents[6]), message=message)
        contents[6] = c6.compact()
        c8 = ChannelArchive(contents[8])
        contents[8] = ChannelArchive(c8.replace('HomeButton3/LZ77_homeBtn_nwm_jpn.arc', rf.nwm_archive(c8.get('HomeButton3/LZ77_homeBtn_nwm_jpn.arc')))).compact()
        changed = [5, 6, 8]
    elif channel == 'kirbytv':
        import json as _json
        v4 = {e['id']: e['ko'] for e in _json.loads((ROOT / 'configs/kirbytv-ui-v4-ko.json').read_text(encoding='utf-8'))['entries']}
        v5 = {e['id']: e['ko'] for e in _json.loads((ROOT / 'configs/kirbytv-ui-v5-ko.json').read_text(encoding='utf-8'))['entries']}
        mapping = {v4[k]: v5[k] for k in v5 if v4.get(k) != v5[k]}
        arc = ChannelArchive(contents[2]); path = 'trusted/Gumball2.12.RC-1.swf'
        swf, tags_changed = rf.kirbytv_swf(arc.get(path), mapping)
        contents[2] = ChannelArchive(arc.replace(path, swf)).compact()
        return [2], dict(ui_table='configs/kirbytv-ui-v5-ko.json', replaced=mapping, swf_tags=tags_changed)
    elif channel == 'internet':
        for i in (2, 6):
            arc = ChannelArchive(contents[i])
            contents[i] = ChannelArchive(arc.replace('english.lng', rf.internet_lng(arc.get('english.lng')))).compact()
        return [2, 6], dict(english_lng=rf.INTERNET_LNG)
    else:
        c2 = ChannelArchive(contents[2])
        c2 = ChannelArchive(c2.replace('Dtest/Home/network_nosave.csv', rf.quit_csv(c2.get('Dtest/Home/network_nosave.csv'), message)))
        c2 = ChannelArchive(c2.replace('Dtest/Home/Demae_guide-00.jpg', rf.guide_picture(c2.get('Dtest/Home/Demae_guide-00.jpg'), 'food')))
        contents[2] = c2.compact()
        c4, record['home_fonts'] = rf.home_fonts(ChannelArchive(contents[4]), message=message)
        contents[4] = c4.compact()
        c6 = ChannelArchive(contents[6])
        contents[6] = ChannelArchive(c6.replace('HomeButton3/LZ77_homeBtn_nwm_jpn.arc', rf.nwm_archive(c6.get('HomeButton3/LZ77_homeBtn_nwm_jpn.arc')))).compact()
        changed = [2, 4, 6]
    if version == 3:
        splits = []
        for i in changed:
            arc = ChannelArchive(contents[i])
            for name in sorted(arc.files):
                if name.lower().endswith('.csv') and ('HomeButton' in name or 'Dtest/Home' in name):
                    data, count = rf.split_save_warning(arc.get(name))
                    if count:
                        arc = ChannelArchive(arc.replace(name, data)); splits.append(dict(content=i, file=name, lines=count))
            contents[i] = arc.compact()
        if not splits: raise ValueError('No save warning lines found')
        record['save_warning_split'] = splits
    record.update(quit_message=message, quit_message_version=version, guide=dict(title=rf.GUIDE_TITLE, note=rf.GUIDE_NOTE, button=rf.GUIDE_BUTTON, body=rf.GUIDES[channel]))
    return changed, record


def build(key):
    parent, child, name, version = PINS[key]; channel = key.split('-v')[0]
    src = ROOT / f'workspace/channels/{channel}/{parent}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (src / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta['wad_sha256']: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    contents = list(original); changed, record = edit(channel, contents, version)
    for i in changed: title.set_content(contents[i], i)
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != changed: raise ValueError('Unexpected content change')
    meta = dict(meta); meta.update(revision=int(child.rsplit('v', 1)[1]), parent_revision=int(parent.rsplit('v', 1)[1]),
                                   parent_wad_sha256=meta['wad_sha256'], wad_sha256=hashlib.sha256(wad).hexdigest(),
                                   changed_from_parent=changed, runtime_verified=False, review_fixes_1117=record)
    if isinstance(meta.get('content_sha256'), dict):
        meta['content_sha256'] = dict(meta['content_sha256'], **{str(i): hashlib.sha256(contents[i]).hexdigest() for i in changed})
    if 'wad_size' in meta: meta['wad_size'] = len(wad)
    if isinstance(meta.get('wads'), dict) and 'personal' in meta['wads']:
        meta['wads'] = dict(meta['wads'], personal=dict(meta['wads']['personal'], sha256=meta['wad_sha256'], size=len(wad)))
    return child, name, wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--channel', choices=sorted(PINS), required=True)
    ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    child, name, wad, meta = build(a.channel); out = ROOT / f'workspace/channels/{a.channel.split("-v")[0]}/{child}'
    if '-v' in a.channel and not a.reproduce: raise SystemExit(f'{child} is superseded; reproduce only')
    if a.reproduce:
        if (out / name).read_bytes() != wad: raise SystemExit('reproduction differs')
        print(f'PASS: {a.channel} {child} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / name).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {a.channel} {child}, contents {meta["changed_from_parent"]}, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()
