"""Merge a worker's workspace/channels/<id>/catalog-entry.json into the catalog.

Validates the row shape against existing rows, refuses duplicates and
role=active rows whose artifact folder is missing. Writes the catalog in the
existing style (indent=1, UTF-8, trailing newline). Use --replace to update
an existing row of the same id (e.g. after a new active build).
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'configs/channels.catalog.json'
REQUIRED = {'id', 'display_name_ko', 'title_id', 'base_region', 'base_version', 'stage', 'full_localization_complete',
            'installs', 'status_doc', 'run_doc', 'remaining', 'installer_selectable', 'public_WAD_distribution',
            'hardware_validation', 'emulator_live_service_verified'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('channel')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    entry = json.loads((ROOT / 'workspace/channels' / args.channel / 'catalog-entry.json').read_text(encoding='utf-8'))
    missing = REQUIRED - set(entry)
    if missing or entry['id'] != args.channel:
        raise SystemExit(f'Catalog entry shape/id differs: missing={sorted(missing)}')
    if entry['full_localization_complete'] or entry['public_WAD_distribution'] or entry['hardware_validation']:
        raise SystemExit('Entry claims completion/distribution/hardware validation')
    for install in entry['installs']:
        folder = ROOT / 'workspace/channels' / args.channel / install['artifact']
        if not folder.is_dir() or not (ROOT / 'workspace/sandbox' / install['profile']).is_dir():
            raise SystemExit('Install artifact/profile missing: ' + install['artifact'])
        launch = install['launch'].split()[0]
        if not (ROOT / launch).is_file():
            raise SystemExit('Launch script missing: ' + launch)
    for doc in (entry['status_doc'], entry['run_doc']):
        if doc and not (ROOT / doc).is_file():
            raise SystemExit('Document missing: ' + doc)
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    ids = [row['id'] for row in catalog['channels']]
    if args.channel in ids:
        if not args.replace:
            raise SystemExit('Channel already in catalog (use --replace)')
        catalog['channels'][ids.index(args.channel)] = entry
    else:
        catalog['channels'].append(entry)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(('Replaced' if args.channel in ids else 'Added'), args.channel, 'with', len(entry['installs']), 'install(s)')


if __name__ == '__main__':
    main()
