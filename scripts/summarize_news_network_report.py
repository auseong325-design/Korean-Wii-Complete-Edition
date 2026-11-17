"""Output only allowlisted numeric fields from a KWCE News diagnostic report."""
import argparse
import json
import re
import time
from pathlib import Path

FIELDS = {'cache_isfs_init', 'cache_open', 'cache_stat', 'cache_read', 'cache_parse',
          'cache_entries', 'cache_parsed', 'cache_fresh', 'cache_expired', 'cache_future',
          'cache_country_49', 'cache_country_136', 'cache_english', 'cache_unrecognized', 'cache_crc_ok', 'cache_crc_bad', 'cache_structural_bad', 'cache_language_empty', 'cache_expired_utc9', 'cache_topic_bad', 'cache_source_bad', 'cache_location_bad', 'cache_image_bad',
          'net_init_start', 'net_init_completed', 'net_init_result', 'news_dns_ok',
          'forecast_dns_ok', 'dns_first_ipv4_equal', 'news_socket', 'news_nonblocking',
          'news_connect', 'news_request', 'news_http_status', 'news_response_result',
          'forecast_socket', 'forecast_nonblocking', 'forecast_connect', 'forecast_request',
          'forecast_http_status', 'forecast_response_result', 'kd_time_open', 'kd_time_ioctl',
          'kd_time_result', 'cache_clock_is_kd', 'kd_diff_before', 'kd_diff_after'}


def summarize(path, now=None):
    path = Path(path)
    if not re.fullmatch(r'news-net-\d{2}\.txt', path.name) or path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('Unexpected report path or size')
    lines = path.read_text(encoding='ascii').splitlines()
    if not lines or lines[0] != 'KWCE_NEWS_NETWORK_V1':
        raise ValueError('Unexpected report type')
    values = {}
    for line in lines[1:]:
        if '=' not in line:
            raise ValueError('Malformed report')
        key, value = line.split('=', 1)
        if key in FIELDS or key in ('clock_unix', 'kd_time_seconds', 'kd_derived_before', 'kd_derived_after'):
            if key in values or not re.fullmatch(r'-?\d{1,12}', value):
                raise ValueError('Invalid numeric field')
            values[key] = int(value)
        elif key == 'stage':
            if value not in ('start', 'complete'):
                raise ValueError('Invalid stage')
            values[key] = value
        else:
            raise ValueError('Unexpected field')
    derived_before = values.pop('kd_derived_before', None)
    derived_after = values.pop('kd_derived_after', None)
    clock = values.pop('clock_unix', None)
    kd_time = values.pop('kd_time_seconds', None)
    current = time.time() if now is None else now
    if clock is not None:
        # Report file times are FAT timestamps written by the Wii, and their
        # timezone may not equal the PC's; this is only age-at-reading evidence.
        current = time.time() if now is None else now
        values['wii_clock_vs_pc_read_minutes'] = round((clock - current) / 60)
    if derived_before is not None:
        values['kd_derived_before_vs_pc_minutes'] = round((derived_before - current) / 60)
    if derived_after is not None:
        values['kd_derived_after_vs_pc_minutes'] = round((derived_after - current) / 60)
    if kd_time is not None:
        current = time.time() if now is None else now
        if kd_time < 946684800:
            kd_time += 946684800
        values['kd_utc_vs_pc_read_minutes'] = round((kd_time - current) / 60)
    values['complete'] = values.pop('stage', None) == 'complete'
    return values


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('report', type=Path)
    args = ap.parse_args()
    try:
        print(json.dumps(summarize(args.report), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, UnicodeError):
        raise SystemExit('Report unavailable or invalid; no raw fields printed.') from None


if __name__ == '__main__':
    main()
