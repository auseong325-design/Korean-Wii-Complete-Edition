"""Run the Forecast local text audit (supply coverage + glyph coverage + channel-string status).

  audit_forecast_text.py     # write workspace/channels/forecast/wave3-text-audit.json and summarise

No Dolphin, no network, no new build, no in-channel supply conversion.  Exit status is non-zero if
a real-payload string is uncovered (would stay English) or a mapped glyph is missing (tofu).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import forecast_textaudit as fa


def main():
    supply = fa.supply_coverage()
    glyphs = fa.glyph_coverage()
    status = fa.channel_text_status()
    report = dict(build='build-v103', supply_coverage=supply, glyph_coverage=glyphs,
                  channel_text_status=status)
    out = ROOT / 'workspace/channels/forecast/wave3-text-audit.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    uncovered = {c: v['uncovered'] for c, v in supply.items() if v['uncovered']}
    print(json.dumps(dict(
        build='build-v103',
        supply_coverage={c: dict(unique=v['unique'], covered=v['covered'], uncovered=len(v['uncovered']))
                         for c, v in supply.items()},
        uncovered_examples={c: v[:20] for c, v in uncovered.items()},
        glyph_gaps=glyphs['gaps'],
        channel_text_status=status,
        report=str(out.relative_to(ROOT)),
    ), ensure_ascii=False, indent=1))
    if uncovered or glyphs['gaps']:
        raise SystemExit('AUDIT FAIL: uncovered supply string or missing glyph (see report)')


if __name__ == '__main__':
    main()
