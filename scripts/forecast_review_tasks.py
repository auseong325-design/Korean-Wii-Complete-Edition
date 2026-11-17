"""Restore deleted local test tasks from a hash-guarded sanitized snapshot."""
import json,shutil
from audit_sd import ROOT,PRIVATE,sha256
from forecast_profile import public_forecast_task


def review_tasks(check=False,profile='forecast-review-v1'):
    if profile not in('forecast-review-v1','forecast-v2'):raise SystemExit('Unsupported local weather profile')
    target=ROOT/'workspace/sandbox'/profile/'user/Wii/shared2/wc24/nwc24dl.bin'
    current=target.read_bytes()
    def allowed(data):return all(public_forecast_task(data[2048+512*i:2560+512*i])for i in (3,4))
    if allowed(current):return current
    # A failed channel run can unregister its tasks. Refuse to replace an
    # unrelated active task in these slots; missing/deactivated slots only.
    for i in (3,4):
        entry=current[2048+512*i:2560+512*i]
        if int.from_bytes(entry[12:16],'big') and not int.from_bytes(entry[4:8],'big')&32:
            raise SystemExit('Review task slots contain an unexpected active title')
    relative='user/Wii/shared2/wc24/nwc24dl.bin'
    source=ROOT/'workspace/sandbox/forecast-manual-v1'/relative
    before=json.loads((PRIVATE/'forecast-before-review-v1.json').read_text())['forecast-manual-v1']
    record=next(r for r in before if r['path']==relative)
    if sha256(source)!=record['sha256']:raise SystemExit('Sanitized task source changed')
    restored=source.read_bytes()
    if not allowed(restored):raise SystemExit('Expected two approved public test tasks')
    if not check:
        prefix='forecast-current'if profile=='forecast-v2'else'forecast-review';n=1
        while (PRIVATE/f'{prefix}-tasks-before-restore-{n}.bin').exists():n+=1
        shutil.copy2(target,PRIVATE/f'{prefix}-tasks-before-restore-{n}.bin')
        target.write_bytes(restored)
    return restored
