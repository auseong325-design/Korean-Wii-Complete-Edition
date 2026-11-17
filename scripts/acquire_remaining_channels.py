"""Preserve official NUS originals and public WiiLink patch files, never install.

Downloads only public title data (TMD, the NUS common ticket where NUS offers
one, encrypted contents, certificate chain) and the WiiLink patcher's public
patch/TMD/ticket files. No console material is read or sent. Existing files
are never overwritten: a second run must reproduce the recorded hashes.
"""
import argparse
import datetime
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library  # noqa: E402

PATCHER = 'https://patcher.wiilink24.com'
CHANNELS = {
    'food': dict(titles=[('food-japan-v512.wad', '000100014843484a', 512, None)],
                 wiilink=['bsdiff/demae/Demae_1_Japan.bsdiff', 'bsdiff/demae/Demae_0_English.bsdiff',
                          'bsdiff/demae/Demae_1_English.bsdiff', 'bsdiff/demae/Demae_2_English.bsdiff', 'demae/Demae.tmd']),
    'photoprints': dict(titles=[('digicam-japan-v1024.wad', '000100014843444a', 1024, None)],
                        wiilink=['bsdiff/digicam/Digicam_1_Japan.bsdiff', 'bsdiff/digicam/Digicam_0_English.bsdiff',
                                 'bsdiff/digicam/Digicam_1_English.bsdiff', 'bsdiff/digicam/Digicam_2_English.bsdiff',
                                 'digicam/Digicam.tmd']),
    'kirbytv': dict(titles=[('kirbytv-europe-v257.wad', '0001000148434d50', 257, 'ktv/0001000148434d50.tik')],
                    wiilink=['bsdiff/ktv/ktv_2.bsdiff', 'ktv/ktv.tmd', 'ktv/0001000148434d50.tik']),
    'personal-data': dict(titles=[('personal-data-japan-v2.wad', '000100084843434a', 2, None)],
                          wiilink=['spd/WiiLink_SPD.wad']),
    'wiispeak': dict(titles=[('wiispeak-korea-v512.wad', '000100014843464b', 512, None),
                             ('wiispeak-japan-v512.wad', '000100014843464a', 512, None),
                             ('wiispeak-usa-v512.wad', '0001000148434645', 512, None)],
                     wiilink=['bsdiff/ws/WiiSpeak_1_Japan.bsdiff', 'bsdiff/ws/WiiSpeak_1_USA.bsdiff',
                              'bsdiff/ws/WiiSpeak_1_PAL.bsdiff']),
    'internet': dict(titles=[('internet-japan-v1024.wad', '000100014841444a', 1024, None),
                             ('internet-usa-v1024.wad', '0001000148414445', 1024, None)],
                     wiilink=[]),
}
LIMIT = 96 * 1024 * 1024


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'KWCE-local-research/0.1'})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read(LIMIT + 1)
    if len(payload) > LIMIT:
        raise ValueError('Download exceeds expected channel bounds')
    return payload


def keep(path, payload):
    """Write once; an existing file must be byte-identical."""
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError('Preserved file differs from new download: ' + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as file:
        file.write(payload)


def signatures(lib, title):
    cert = lib.title.cert
    chain = title.cert_chain
    tmd_ok = cert.verify_ca_cert(chain.ca_cert) and cert.verify_cert_sig(chain.ca_cert, chain.tmd_cert) and cert.verify_tmd_sig(chain.tmd_cert, title.tmd)
    try:
        ticket_ok = cert.verify_cert_sig(chain.ca_cert, chain.ticket_cert) and cert.verify_ticket_sig(chain.ticket_cert, title.ticket)
    except Exception:
        ticket_ok = False
    return bool(tmd_ok), bool(ticket_ok)


def acquire_title(lib, alias, title_id, version, ticket_path, dest):
    target = dest / alias
    if target.exists():
        title = lib.title.Title()
        title.load_wad(target.read_bytes())
        source = 'preserved'
    else:
        title = lib.title.Title()
        title.load_cert_chain(lib.title.download_cert_chain())
        title.load_tmd(lib.title.download_tmd(title_id, version))
        title.load_ticket(fetch(f'{PATCHER}/{ticket_path}') if ticket_path else lib.title.download_ticket(title_id))
        title.load_content_records()
        title.content.content_list = lib.title.download_contents(title_id, title.tmd)
        source = 'nus'
    if title.tmd.title_id != title_id or title.tmd.title_version != version:
        raise ValueError('Unexpected title identity/version for ' + alias)
    contents = [title.get_content_by_index(i) for i in range(title.tmd.num_contents)]  # SHA-1 checked
    wad = title.dump_wad()
    keep(target, wad)
    tmd_ok, ticket_ok = signatures(lib, title)
    if not tmd_ok:
        raise ValueError('TMD signature chain does not verify for ' + alias)
    return dict(alias=alias, title_id=title_id, version=version, source=source,
                ticket_source='WiiLink patcher (NUS has no common ticket)' if ticket_path else 'NUS cetk',
                size=len(wad), sha256=hashlib.sha256(wad).hexdigest(), contents=len(contents),
                boot_index=title.tmd.boot_index, region=title.tmd.region, ios=f'{title.tmd.ios_tid}',
                tmd_signature_valid=tmd_ok, ticket_signature_valid=ticket_ok,
                content_sha1_verified=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('channels', nargs='*', default=list(CHANNELS))
    args = parser.parse_args()
    lib = load_library()
    for channel in args.channels:
        spec = CHANNELS[channel]
        base = ROOT / 'workspace/channels' / channel
        dest = base / 'originals'
        rows = [acquire_title(lib, *row, dest) for row in spec['titles']]
        patches = []
        for rel in spec['wiilink']:
            path = base / 'references/wiilink-patcher' / rel.replace('/', '__')
            payload = path.read_bytes() if path.exists() else fetch(f'{PATCHER}/{rel}')
            keep(path, payload)
            patches.append(dict(url=f'{PATCHER}/{rel}', file=path.relative_to(ROOT).as_posix(), size=len(payload),
                                sha256=hashlib.sha256(payload).hexdigest()))
        record = dict(channel=channel, titles=[{k: v for k, v in r.items() if k != 'source'} for r in rows], wiilink_patcher=patches,
                      patcher_reference='WiiLink24/WiiLink-Patcher-GUI@2f27533 data/patches.json',
                      installs_performed=False, console_data_sent=False)
        manifest = dest / 'acquisition.json'
        if manifest.exists():
            previous = json.loads(manifest.read_text(encoding='utf-8'))
            if {k: v for k, v in previous.items() if k != 'acquired_utc'} != record:
                raise ValueError('Preserved channel sources differ from acquisition manifest: ' + channel)
        else:
            record['acquired_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            manifest.write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps(dict(channel=channel, titles=[(r['alias'], r['contents'], r['tmd_signature_valid'], r['ticket_signature_valid'], r['source']) for r in rows],
                              wiilink_files=len(patches))))


if __name__ == '__main__':
    main()
