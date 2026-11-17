"""Read only numeric/allowlisted fields from on-device KWCE diagnostic reports."""
import argparse,re
from pathlib import Path

PHASES={'before','after_news','after_room','other'}
BUILDS={'news_r20','news_r22','room_r51','unknown','unavailable','allocation_failed'}
CHANNELS={'news','wii_room','forecast'}
ROUTES={'known_136','known_049','other_or_unrecognized'}
STAGES={'start','config','title_versions','installed_builds','isfs_init','wc24_list','news_cache','channel_directories','complete'}

def number(text):
    return int(text) if re.fullmatch(r'-?\d{1,12}',text or '') else None

def summarize(path):
    if not re.fullmatch(r'diag-\d{4}\.txt',path.name) or path.is_symlink() or path.stat().st_size>131072:raise ValueError('Invalid report path/size')
    rows=path.read_text(encoding='ascii').splitlines()
    if not rows or rows[0]!='KWCE_DIAGNOSTIC_V1':raise ValueError('Unknown report version')
    data={}
    for line in rows[1:]:
        if '=' not in line:raise ValueError('Malformed report')
        key,value=line.split('=',1)
        if re.fullmatch(r'[a-z0-9_]+',key):data[key]=value
    phase=data.get('phase');stage=data.get('stage')
    if phase not in PHASES or stage not in STAGES:raise ValueError('Unknown phase/stage')
    out=[f'{path.name}: phase={phase}, last_stage={stage}']
    for k in ('news_installed_build','room_installed_build'):
        v=data.get(k)
        if v in BUILDS:out.append(f'  {k}={v} (TMD match)')
    for k in ('isfs_init_result','wc24_list_open_result','wc24_list_read_result','matched_task_count'):
        v=number(data.get(k))
        if v is not None:out.append(f'  {k}={v}')
    for i in range(120):
        ch=data.get(f'task_{i}_channel')
        if ch not in CHANNELS:continue
        err=number(data.get(f'task_{i}_error_code'));count=number(data.get(f'task_{i}_error_count'))
        route=data.get(f'task_{i}_route');route=route if route in ROUTES else 'not_recorded'
        out.append(f'  task={ch}, error_code={err}, error_count={count}, news_route={route}')
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--directory',type=Path,default=Path('H:/kwce/diagnostics'));args=ap.parse_args()
    folder=args.directory
    if not folder.is_dir():raise SystemExit('Diagnostic folder missing')
    files=sorted(folder.glob('diag-*.txt'))
    if not files:print('No diagnostic reports found');return
    for p in files:
        try:print('\n'.join(summarize(p)))
        except (ValueError,UnicodeError,OSError):print(p.name+': report invalid or unavailable')
    print('Note: saved WC24 state after the run; this does not trace live HTTP calls.')
if __name__=='__main__':main()
