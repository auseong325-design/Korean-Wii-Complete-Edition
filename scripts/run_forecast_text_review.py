"""Batch native textbox observations in the isolated diagnostic profile.

The screenshots must subsequently be inspected; this script does not claim
visual success. Every build, installation backup and capture is preserved.
"""
import argparse,json,subprocess,sys,time
from audit_sd import ROOT,PRIVATE
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.forecast_text_review import CASES


def run(*args):
    result=subprocess.run([sys.executable,*args],cwd=ROOT,capture_output=True,text=True)
    if result.returncode:
        if args[0]=='scripts/dolphin_ui.py':
            print((result.stderr or result.stdout).strip().splitlines()[-1],flush=True)
        raise SystemExit('Review step failed: '+args[0]+' (details kept private)')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--first',type=int,default=0);ap.add_argument('--last',type=int,default=len(CASES)-1);ap.add_argument('--current-style',action='store_true');ap.add_argument('--launch-only',action='store_true',help='one case only; inspect/capture with native app computer-use');args=ap.parse_args()
    if not 0<=args.first<=args.last<len(CASES):raise SystemExit('Invalid case range')
    if args.launch_only and args.first!=args.last:raise SystemExit('Native observation mode takes one case')
    stopped()
    for case in range(args.first,args.last+1):
        revision=(62 if args.current_style else 39)+case;report=PRIVATE/f'forecast-text-review-{"final-"if args.current_style else""}case-{case}.json'
        if report.exists():raise SystemExit('Existing review case preserved')
        build=ROOT/f'workspace/channels/forecast/build-v{revision}'
        if not build.exists():run('scripts/build_forecast_text_review.py',str(case),*(['--current-style']if args.current_style else[]))
        active=ROOT/'workspace/sandbox/forecast-review-v1/active-build.json'
        if json.loads(active.read_text())['revision']!=revision:
            tag=[]
            backup=PRIVATE/f'forecast-review-before-install-v{revision}'
            if backup.exists():
                number=1
                while backup.with_name(backup.name+f'-native-review-{number}').exists():number+=1
                tag=['--snapshot-tag',f'native-review-{number}']
            run('scripts/install_forecast.py','--review','--revision',str(revision),*tag)
        p=ROOT/'configs/channels.catalog.json';catalog=json.loads(p.read_text(encoding='utf-8'))
        row=next(i for c in catalog['channels']if c['id']=='forecast'for i in c['installs']if i['profile']=='forecast-review-v1')
        row['artifact']=f'build-v{revision}';p.write_text(json.dumps(catalog,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
        run('scripts/prepare_forecast_scenario.py','no-service')
        run('scripts/launch_forecast.py','--review','--cache-preview')
        # First compilation can leave only the main window for >22 seconds.
        # Inspect only scoped process/window metadata until a render exists;
        # no guessed window receives input.
        from dolphin_ui import Driver,ScopeError
        deadline=time.monotonic()+55
        while True:
            try:ready=len(Driver().windows())==1
            except ScopeError:ready=False
            if ready:break
            if time.monotonic()>=deadline:raise SystemExit('Review render did not become ready')
            time.sleep(2)
        time.sleep(8)
        if args.launch_only:
            Driver().compact()
            time.sleep(1)
            print('Native observation pending for case',case,'/'.join(CASES[case]),flush=True);return
        run('scripts/dolphin_ui.py','shot','--name',f'forecast-native-text-{case:02}')
        run('scripts/dolphin_ui.py','stop')
        report.write_text(json.dumps(dict(case=case,source='/'.join(CASES[case]),revision=revision,
            captured=True,visually_reviewed=False,diagnostic='Original text style in native error presenter; no NAND fault created')))
        print('CAPTURED case',case,'/'.join(CASES[case]),'visual inspection pending',flush=True)


if __name__=='__main__':main()
