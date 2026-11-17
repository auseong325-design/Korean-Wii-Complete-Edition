"""Add reliable mouse A and HOME aliases in the stopped News profile only."""
import configparser
import shutil
import subprocess
from audit_sd import ROOT, PRIVATE


def main():
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True)
    if 'dolphin.exe' in running.stdout.lower():
        raise SystemExit('Close Dolphin first')
    path = ROOT / 'workspace/sandbox/news-v1/user/Config/WiimoteNew.ini'
    cfg = configparser.ConfigParser(strict=False)
    cfg.optionxform = str
    cfg.read(path, encoding='utf-8-sig')
    current = cfg['Wiimote1'].get('Buttons/Home')
    expected = 'RETURN | `Click 2`'
    minimum_a='`Click 0` | pulse(`Click 0`, 0.25)'
    section=cfg['Wiimote1']
    shakes=['Shake/'+axis for axis in 'XYZ']+['Nunchuk/Shake/'+axis for axis in 'XYZ']
    if current==expected and section.get('Buttons/A')==minimum_a and all(not section.get(key,'').strip()for key in shakes):
        print('News minimum A and HOME aliases already configured');return
    if current not in ['RETURN',expected]or section.get('Buttons/A')not in ['`Click 0`',minimum_a]:
        raise SystemExit('Unexpected HOME mapping; preserve and review')
    if any(section.get(key,'').strip()not in ['', '`Click 2`']for key in shakes):raise SystemExit('Unexpected shake mapping')
    backup = PRIVATE / 'news-before-menu-mouse-input-WiimoteNew.ini'
    if backup.exists():
        raise SystemExit('Existing input snapshot preserved')
    shutil.copy2(path, backup)
    cfg['Wiimote1']['Buttons/Home'] = expected
    cfg['Wiimote1']['Buttons/A']=minimum_a
    for key in shakes:
        if key in section:section[key]=''
    with path.open('w', encoding='utf-8') as stream:
        cfg.write(stream)
    print('News HOME: Return/middle; left A held input plus 250ms minimum; middle shake collision removed')


if __name__ == '__main__':
    main()
