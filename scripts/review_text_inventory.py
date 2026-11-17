"""Full-review step A: text inventory of the packaged Korean channels vs their originals.

  python scripts/review_text_inventory.py [--channel ID ...]

Uses the same resolver as export_rc_hardware.py (configs/rc-package.json pins). Writes
workspace/private/review/<id>-inventory.json (channel UI text only; ignored folder) and prints per channel:
containers changed/unchanged, non-Korean strings left in changed containers, unchanged containers that still
hold Japanese/English text, and Hangul used by changed text but missing from Hangul-bearing archive fonts.
"""
import argparse, json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from kwce.channels import load_library
from kwce import text_inventory as ti
import export_rc_hardware as ex
from kwce import rc_hardware

OUT = ROOT / 'workspace/private/review'


def hangul(s):
    return {ord(c) for c in s if '가' <= c <= '힣'}


def summarize(cid, report):
    states = Counter(c['state'] for c in report['containers'])
    touched = [c for c in report['containers'] if c['state'] != 'unchanged']
    left = Counter(i['cls'] for c in touched for i in c['items'])
    stale = [c for c in report['containers'] if c['state'] == 'unchanged' and any(i['cls'] in ('ja', 'en', 'mixed-ja') for i in c['items'])]
    used = set().union(*[hangul(i['text']) for c in touched for i in c['items']]) if touched else set()
    gaps = {}
    for path, chars in report['fonts'].items():
        have = {c for c in chars if 0xac00 <= c <= 0xd7a3}
        if len(have) >= 30:
            miss = used - have
            if miss:
                gaps[path] = ''.join(sorted(chr(c) for c in miss))
    line = (f'{cid:13s} containers {sum(states.values()):4d} (changed {states["changed"]}, new {states["new"]}, unchanged {states["unchanged"]})'
            f' | touched strings ko {left["ko"]} en {left["en"]} ja {left["ja"]} mixed {left["mixed-ja"]} other {left["other"]}'
            f' | unchanged w/ ja/en {len(stale)} | font gaps {len(gaps)}')
    return line, dict(states=dict(states), touched=dict(left), stale=[c['path'] for c in stale],
                      font_gaps={p: g[:200] for p, g in gaps.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--channel', nargs='*')
    a = ap.parse_args(); cfg = rc_hardware.config(); lib = load_library(); OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for ch in cfg['channels']:
        if a.channel and ch['id'] not in a.channel:
            continue
        kind, label, korean, original = ex.resolve(ch, lib)
        if korean is None:
            print(f"{ch['id']:13s} deferred: {label}"); continue
        report = ti.inventory(korean, original)
        fonts = {p: len(v) for p, v in report['fonts'].items()}
        (OUT / f"{ch['id']}-inventory.json").write_text(json.dumps(dict(channel=ch['id'], build=label, containers=report['containers'], fonts=fonts),
                                                                ensure_ascii=False, indent=1), encoding='utf-8')
        line, summary[ch['id']] = summarize(ch['id'], report); summary[ch['id']]['build'] = label
        print(line, flush=True)
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
