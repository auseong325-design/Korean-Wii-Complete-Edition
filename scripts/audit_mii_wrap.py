"""Run the static Mii Contest wrap/width + glyph-coverage audit and write the report.

  audit_mii_wrap.py          # write workspace/channels/mii-contest/wave3-wrap-audit.json and summarise

No Dolphin, no install, read-only on build-v25.  Exit status is non-zero if any localized message
overflows the widest message pane or any glyph is missing (a real defect), zero otherwise.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import mii_contest_textfit as mt


def main():
    report = mt.audit(ROOT)
    coverage = mt.glyph_coverage(ROOT)
    report['glyph_coverage'] = {k: ''.join(v) for k, v in coverage.items()}
    out = ROOT / 'workspace/channels/mii-contest/wave3-wrap-audit.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    missing_any = any(coverage.values()) or bool(report['missing_glyphs'])
    print(json.dumps(dict(
        build=report['build'], font=report['font'], messages=report['message_count'],
        message_panes=report['message_panes'],
        line_overflow_every_pane=report['line_overflow_every_pane'],
        long_paginated_or_scrolled_count=len(report['long_paginated_or_scrolled']),
        missing_glyphs=report['missing_glyphs'],
        glyph_gaps={k: v for k, v in report['glyph_coverage'].items() if v},
        report=str(out.relative_to(ROOT)),
    ), ensure_ascii=False, indent=1))
    if report['line_overflow_every_pane'] or missing_any:
        raise SystemExit('AUDIT FAIL: a line fits no message pane, or a glyph is missing (see report)')


if __name__ == '__main__':
    main()
