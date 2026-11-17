"""Summarize a KWCE RC WiiConnect24 report without exposing report contents.

Read-only: outputs only numeric status and Nintendo task fields. The source
report and all other lines (including host names) are never printed.
"""
import argparse
import json
import re
from pathlib import Path

FIELDS = ('flags', 'remaining_downloads', 'error_count', 'retry_minutes', 'error_code', 'subtask_mask')


def summarize(report):
    pairs = {}
    for line in report.splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key in pairs:
            raise ValueError('Duplicate field in report')
        pairs[key] = value.strip()
    if not report.startswith('KWCE_RC_WC24_REPORT_V1'):
        raise ValueError('Not a KWCE WiiConnect24 report')

    def number(key, *, stage=False):
        value = pairs.get(key)
        if value is None:
            return None
        pattern = r'(-?\d+)(?: \([^\r\n]*\))?' if stage else r'(-?\d+)'
        match = re.fullmatch(pattern, value)
        if not match:
            raise ValueError('Malformed numeric field')
        return int(match.group(1))

    tasks = []
    for key, value in pairs.items():
        match = re.fullmatch(r'task_(\d+)_channel', key)
        if match and value == 'nintendo':
            prefix = f'task_{int(match.group(1))}_'
            tasks.append({name: number(prefix + name) for name in FIELDS})
    return {'report_format_valid': pairs.get('dllist_format') == 'recognized_v1',
            'isfs_init': number('isfs_init'),
            'dllist_read_result': number('dllist_read_result'),
            'wc24_enabled': number('wc24_enabled'),
            'id_creation_stage': number('id_creation_stage', stage=True),
            'tasks_used': number('tasks_used'), 'tasks_free': number('tasks_free'),
            'nintendo_tasks': tasks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='KWCE-generated wc24-NN.txt report')
    args = parser.parse_args()
    try:
        result = summarize(args.report.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        raise SystemExit('Could not read a valid KWCE report; no report content was printed.') from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
