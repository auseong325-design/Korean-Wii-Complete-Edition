"""Optional render-window helper; only catalog-approved project processes.

Use the app's builtin computer-use first. Commands: focus, shot, point,
click, b, key, log, stop. --pid disambiguates multiple approved processes;
--profile selects pointer calibration, not the target NAND. No personal or
preserved profiles are targeted. Captures are private and never overwritten.
"""
import argparse
import ctypes
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from ctypes import wintypes as W
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.dolphin_ui_scope import Process, Target, ScopeError, select, revalidate, capture_name, overlaps

CAPTURES = ROOT / 'workspace/private/captures'
KEYS = {'space': 32, 'return': 13, 'z': 90, 'x': 88, 'up': 38, 'down': 40, 'left': 37,
        'right': 39, 'escape': 27, 'e': 69, 'q': 81, 'p': 80, '1': 49, '2': 50, '1+2': (49,50),
        'f7': 118, 'f8': 119}
SERVER_LOGS = {'votes': 'votes-test-v1', 'nintendo': 'nintendo-test-v1',
               'mii-contest': 'mii-contest-test-v1', 'wiiroom': 'wiiroom-test-v1', 'tvguide': 'tvguide-test-v1'}


def approved_targets():
    catalog = json.loads((ROOT/'configs/channels.catalog.json').read_text(encoding='utf-8'))
    profiles = {'gc-v6', 'gc-v7', 'gc-v8'} | {i['profile'] for c in catalog['channels'] for i in c['installs']
                            if i['role'] in ('active', 'manual-capture', 'verification')}
    profiles |= {t['profile'] for t in catalog.get('test_beds', [])}
    targets = []
    for profile in profiles:
        if not re.fullmatch(r'[a-z0-9-]+', profile): raise ScopeError('Invalid profile alias')
        runtime = ROOT/'workspace/sandbox'/profile
        for folder in ('Dolphin-x64', 'Dolphin-replay-x64'):
            exe, user = runtime/folder/'Dolphin.exe', runtime/'user'
            if not exe.is_file() or not user.is_dir(): continue
            for path in (exe, user):
                for part in (path, *path.parents):
                    if part == ROOT.parent: break
                    if part.is_symlink() or part.is_junction(): raise ScopeError('Indirect target refused')
            targets.append(Target(profile, str(exe.resolve()), str(user.resolve())))
    return targets


class Driver:
    def __init__(self, pid=None):
        self.u, self.k = ctypes.windll.user32, ctypes.windll.kernel32
        self.u.GetForegroundWindow.restype = W.HWND
        self.u.SetWindowPos.argtypes=[W.HWND,W.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.UINT]
        self.u.SetWindowPos.restype=W.BOOL
        self.u.SetForegroundWindow.argtypes=[W.HWND];self.u.SetForegroundWindow.restype=W.BOOL
        self.u.ShowWindow.argtypes=[W.HWND,ctypes.c_int]
        self.u.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
        self.u.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
        self.u.GetWindowRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
        self.u.GetClientRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
        self.u.ClientToScreen.argtypes=[W.HWND,ctypes.POINTER(W.POINT)]
        self.u.IsWindowVisible.argtypes=[W.HWND];self.u.IsIconic.argtypes=[W.HWND]
        self.u.GetWindow.argtypes = [W.HWND,W.UINT]; self.u.GetWindow.restype = W.HWND
        self.u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
        self.u.WindowFromPoint.argtypes = [W.POINT]; self.u.WindowFromPoint.restype = W.HWND
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; self.k.OpenProcess.restype = W.HANDLE
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.k.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)]*4
        self.k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        self.k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
        shell = ctypes.windll.shell32
        shell.CommandLineToArgvW.argtypes = [W.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(W.LPWSTR)
        self.k.LocalFree.argtypes = [ctypes.c_void_p]
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError): self.u.SetProcessDPIAware()
        self.targets = approved_targets()
        self.process, self.target = select(self.processes(), self.targets, pid)
        self.check_container()
        # An embedded renderer can share the main window with log widgets.
        # Reject explicitly enabled embedding before any window input/capture.
        import configparser
        for name in ('Dolphin.ini','Qt.ini'):
            path=Path(self.target.user)/'Config'/name
            if not path.exists():continue
            for part in(path,*path.parents):
                if part==ROOT.parent:break
                if part.is_symlink()or part.is_junction():raise ScopeError('Indirect UI configuration refused')
            c=configparser.ConfigParser(strict=False,interpolation=None);c.read(path,encoding='utf-8-sig')
            for section in c.sections():
                for key,value in c[section].items():
                    if key.lower().replace('_','')in('rendertomain','rendertomainwindow')and value.strip().lower()in('true','1','yes'):
                        raise ScopeError('Embedded rendering refused: main/log windows must stay separate')

    def check_container(self):
        adv=ctypes.windll.advapi32
        adv.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,ctypes.POINTER(W.HANDLE)]
        adv.GetTokenInformation.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD)]
        process=self.k.OpenProcess(0x1000,False,self.process.pid);token=W.HANDLE()
        if not process:raise ScopeError('Selected process exited')
        try:
            if self.created(process)!=self.process.created or not adv.OpenProcessToken(process,8,ctypes.byref(token)):
                raise ScopeError('Cannot verify sandbox token')
            length=W.DWORD();container=W.DWORD()
            if not adv.GetTokenInformation(token,29,ctypes.byref(container),4,ctypes.byref(length))or container.value!=1:
                raise ScopeError('Project process is not an AppContainer')
            adv.GetTokenInformation(token,30,None,0,ctypes.byref(length))
            if not 4<=length.value<=65536:raise ScopeError('Invalid capability information')
            data=ctypes.create_string_buffer(length.value)
            if not adv.GetTokenInformation(token,30,data,length.value,ctypes.byref(length))or int.from_bytes(data.raw[:4],'little')!=0:
                raise ScopeError('Project process has network capabilities')
        finally:
            if token:self.k.CloseHandle(token)
            self.k.CloseHandle(process)

    def created(self, handle):
        times = [W.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            raise ScopeError('Cannot establish process identity')
        return times[0].dwLowDateTime | times[0].dwHighDateTime << 32

    def processes(self):
        # Command lines are captured locally and never printed, even on failure.
        script = "Get-CimInstance Win32_Process -Filter \"Name='Dolphin.exe'\" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        done = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        if done.returncode: raise ScopeError('Process discovery failed')
        rows = json.loads(done.stdout.strip() or '[]')
        if isinstance(rows, dict): rows = [rows]
        result = []
        for row in rows:
            if not row.get('ExecutablePath') or not row.get('CommandLine'): continue
            handle = self.k.OpenProcess(0x1000, False, row['ProcessId'])
            if not handle: continue
            try: created = self.created(handle)
            finally: self.k.CloseHandle(handle)
            count = ctypes.c_int()
            argv = ctypes.windll.shell32.CommandLineToArgvW(row['CommandLine'], ctypes.byref(count))
            if not argv: continue
            try: args = tuple(argv[i] for i in range(count.value))
            finally: self.k.LocalFree(argv)
            result.append(Process(row['ProcessId'], row['ExecutablePath'], args, created))
        return result

    def windows(self, render=True):
        found = []
        @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        def visit(hwnd, _):
            pid = W.DWORD(); self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.process.pid and self.u.IsWindowVisible(hwnd):
                if render:
                    title = ctypes.create_unicode_buffer(512)
                    self.u.GetWindowTextW(hwnd, title, 512)
                    if ' | ' not in title.value: return True
                found.append(hwnd)
            return True
        self.u.EnumWindows(visit, 0)
        return found

    def current(self):
        handle = self.k.OpenProcess(0x1000,False,self.process.pid)
        if not handle: raise ScopeError('Selected process exited')
        try:
            size = W.DWORD(32768); name = ctypes.create_unicode_buffer(size.value)
            if not self.k.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)):
                raise ScopeError('Cannot verify selected executable')
            if self.created(handle) != self.process.created or name.value.casefold() != self.process.executable.casefold():
                raise ScopeError('Selected process identity changed')
            return self.process
        finally: self.k.CloseHandle(handle)

    def rect(self, hwnd):
        rect, origin = W.RECT(), W.POINT(0, 0)
        if not self.u.GetClientRect(hwnd, ctypes.byref(rect)) or rect.right <= 0 or rect.bottom <= 0:
            raise ScopeError('Render rectangle unavailable')
        if not self.u.ClientToScreen(hwnd, ctypes.byref(origin)): raise ScopeError('Render origin unavailable')
        return origin.x, origin.y, origin.x+rect.right, origin.y+rect.bottom

    def guard(self, hwnd, screen=True):
        pid = W.DWORD(); self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        current = self.current()
        visible = bool(self.u.IsWindowVisible(hwnd)) and not bool(self.u.IsIconic(hwnd))
        clear = True
        if screen and visible:
            x0,y0,x1,y1 = self.rect(hwnd)
            above = self.u.GetWindow(hwnd,3)  # GW_HWNDPREV: every window higher in z-order.
            seen = set()
            while above:
                if above in seen: raise ScopeError('Unstable window stacking order')
                seen.add(above)
                if self.u.IsWindowVisible(above) and not self.u.IsIconic(above):
                    rect = W.RECT()
                    if not self.u.GetWindowRect(above,ctypes.byref(rect)): raise ScopeError('Cannot verify occlusion')
                    if overlaps((x0,y0,x1,y1),(rect.left,rect.top,rect.right,rect.bottom)): clear = False
                above = self.u.GetWindow(above,3)
            for x in (x0+2, (x0+x1)//2, x1-3):
                for y in (y0+2, (y0+y1)//2, y1-3):
                    if self.u.WindowFromPoint(W.POINT(x,y)) != hwnd: clear = False
        revalidate(self.process, current, self.targets, pid.value,
                   foreground=not screen or (visible and self.u.GetForegroundWindow() == hwnd), unobscured=clear)

    def focus(self, maximize=True, on_top=False):
        windows = self.windows()
        if len(windows) != 1: raise ScopeError('Expected one render window')
        hwnd = windows[0]; self.guard(hwnd, False)
        self.u.ShowWindow(hwnd, 3 if maximize else 9)
        if on_top and not self.u.SetWindowPos(hwnd,-1,0,0,0,0,0x3):raise ScopeError('Render raise failed')
        # Do not send Alt or borrow another app's input queue to defeat
        # Windows foreground restrictions. Failed activation is refused.
        self.u.SetForegroundWindow(hwnd)
        time.sleep(.4); self.guard(hwnd)
        return hwnd

    def compact(self, on_top=False):
        windows=self.windows()
        if len(windows)!=1:raise ScopeError('Expected one render window')
        hwnd=windows[0];self.guard(hwnd,False)
        self.u.ShowWindow(hwnd,9)  # Restore only this render window.
        if not self.u.SetWindowPos(hwnd,-1 if on_top else None,100,100,800,600,0 if on_top else 0x4):raise ScopeError('Render resize failed')
        self.guard(hwnd,False)

    def move(self, hwnd, fx, fy, profile):
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in (fx,fy)): raise ScopeError('Invalid pointer fraction')
        table = json.loads((ROOT/'configs/dolphin-ui.json').read_text(encoding='utf-8'))['profiles']
        if profile not in table: raise ScopeError('Unknown pointer calibration')
        c = table[profile]; x0,y0,x1,y1 = self.rect(hwnd)
        mx,my = (fx-c['bx'])/c['ax'], (fy-c['by'])/c['ay']
        self.guard(hwnd)
        if not self.u.SetCursorPos(int(x0+min(max(mx,0),1)*(x1-x0)), int(y0+min(max(my,0),1)*(y1-y0))):
            raise ScopeError('Pointer movement failed')
        time.sleep(.5); self.guard(hwnd)

    def button(self, hwnd, down, up, hold):
        self.guard(hwnd); self.u.mouse_event(down,0,0,0,0)
        try: time.sleep(hold/1000)
        finally: self.u.mouse_event(up,0,0,0,0)

    def shot(self, hwnd, scale, name):
        if not math.isfinite(scale) or not .1 <= scale <= 2: raise ScopeError('Invalid capture scale')
        filename = capture_name(name or time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000000))
        from kwce.channels import load_library
        load_library()
        from PIL import ImageGrab
        self.guard(hwnd); image = ImageGrab.grab(bbox=self.rect(hwnd), all_screens=True); self.guard(hwnd)
        if scale != 1: image = image.resize((max(1,int(image.width*scale)),max(1,int(image.height*scale))))
        for part in (CAPTURES, *CAPTURES.parents):
            if part == ROOT.parent: break
            if part.is_symlink() or part.is_junction(): raise ScopeError('Indirect capture folder refused')
        CAPTURES.mkdir(parents=True, exist_ok=True)
        path = CAPTURES/filename
        with path.open('xb') as stream: image.save(stream, format='PNG')
        print('workspace/private/captures/'+filename, f'{image.width}x{image.height}')

    def owned_dialog(self):
        fg=self.u.GetForegroundWindow(); pid=W.DWORD(); self.u.GetWindowThreadProcessId(fg,ctypes.byref(pid))
        cls=ctypes.create_unicode_buffer(64); self.u.GetClassNameW(fg,cls,64)
        return fg if pid.value==self.process.pid and cls.value=='#32770' else None

    def owned_dialogs(self):
        """Visible #32770 windows of the selected PID: (hwnd, has file name box cmb13)."""
        found=[]
        @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        def visit(h, _):
            pid=W.DWORD(); self.u.GetWindowThreadProcessId(h,ctypes.byref(pid))
            cls=ctypes.create_unicode_buffer(64); self.u.GetClassNameW(h,cls,64)
            if pid.value==self.process.pid and self.u.IsWindowVisible(h) and cls.value=='#32770':found.append(h)
            return True
        self.u.EnumWindows(visit,0)
        return [(h,self.file_name_box(h)) for h in found]

    def file_name_box(self, dialog):
        edits=[]
        @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        def visit(child, _):
            cls=ctypes.create_unicode_buffer(64); self.u.GetClassNameW(child,cls,64)
            if cls.value=='Edit' and self.u.GetDlgCtrlID(child)==1148:  # cmb13 file name
                pcls=ctypes.create_unicode_buffer(64); self.u.GetClassNameW(self.u.GetParent(child),pcls,64)
                if pcls.value=='ComboBox': edits.append(child)
            return True
        self.u.EnumChildWindows(dialog, visit, 0)
        return edits[0] if len(edits)==1 else None

    def insert_staged_disc(self, hwnd, key_hold, name='GALJ01.iso'):
        """Change Disc (F8 hotkey of the GC sandbox profile) and enter only its staged disc path.

        Dialog contents are never captured or read. The file dialog is the #32770 of the
        selected PID that owns the cmb13 file name box. A shell task dialog it raises
        (the sandbox cannot open the last folder) is closed with Cancel.
        """
        runtime = Path(self.target.user).parent
        if Path(name).name != name or not name.lower().endswith('.iso'):raise ScopeError('Disc name must be a staged .iso file name')
        disc = runtime/'disc'/name
        if not runtime.resolve().is_relative_to((ROOT/'workspace/sandbox').resolve()) or not disc.is_file():
            raise ScopeError('Selected profile has no staged test disc')
        if name != 'GALJ01.iso':
            meta = json.loads(disc.with_suffix('.json').read_text(encoding='utf-8'))
            if not meta.get('synthetic') or hashlib.sha256(disc.read_bytes()).hexdigest() != meta['sha256']:raise ScopeError('Staged disc is not a verified synthetic test disc')
        if not self.owned_dialogs():
            self.guard(hwnd); vk=KEYS['f8']; scan=self.u.MapVirtualKeyW(vk,0)
            self.u.keybd_event(vk,scan,0,0); time.sleep(key_hold/1000); self.u.keybd_event(vk,scan,2,0)
        dialog=box=None
        for _ in range(100):
            time.sleep(.1); rows=self.owned_dialogs(); files=[(h,e) for h,e in rows if e]
            for h,e in rows:
                if not e and self.u.GetWindow(h,4) in [f for f,_ in files]:
                    self.u.PostMessageW(h,0x0111,2,0)  # IDCANCEL on the shell task dialog
            if len(files)==1 and len(rows)==1: dialog,box=files[0]; break
        else: raise ScopeError('Change Disc dialog not ready (F8 hotkey bound?)')
        self.u.SetForegroundWindow(dialog); time.sleep(.3)
        if self.owned_dialog()!=dialog: raise ScopeError('Dialog is not in front')
        self.current()
        self.u.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPCWSTR]
        self.u.SendMessageW(box,0x000C,0,str(disc))  # WM_SETTEXT
        time.sleep(.2); self.u.PostMessageW(dialog,0x0111,1,0)  # WM_COMMAND IDOK
        for _ in range(50):
            time.sleep(.1)
            if not self.u.IsWindow(dialog) or not self.u.IsWindowVisible(dialog): break
        else: raise ScopeError('Change Disc dialog stayed open')
        time.sleep(.5)
        if self.owned_dialogs(): raise ScopeError('A dialog appeared after the disc change; not handled')
        print('staged disc path accepted by the Change Disc dialog')

    def stop(self):
        # Keep the kernel handle open throughout shutdown, including forced exit.
        handle = self.k.OpenProcess(0x100001|0x1000, False, self.process.pid)
        if not handle: raise ScopeError('Cannot open selected process')
        try:
            if self.created(handle) != self.process.created: raise ScopeError('Process identity changed')
            current = next((p for p in self.processes() if p.pid == self.process.pid), None)
            if current != self.process: raise ScopeError('Process changed before shutdown')
            # Ask only windows owned by the held process to close normally.
            for hwnd in self.windows(render=False):
                if self.k.WaitForSingleObject(handle,0)==0:
                    print('selected project Dolphin stopped');return
                try:self.current()
                except ScopeError:
                    if self.k.WaitForSingleObject(handle,0)==0:
                        print('selected project Dolphin stopped');return
                    raise
                self.u.PostMessageW(hwnd,0x10,0,0)  # WM_CLOSE
            if self.k.WaitForSingleObject(handle,8000) == 0: print('selected project Dolphin stopped'); return
            if not self.k.TerminateProcess(handle,1): raise ScopeError('Selected shutdown failed')
            if self.k.WaitForSingleObject(handle,3000) != 0: raise ScopeError('Selected process still running')
            print('selected project Dolphin forced stop')
        finally: self.k.CloseHandle(handle)


def log(channel, count):
    path = ROOT/('workspace/sandbox/news-v1/feed-log-v2.tsv' if channel == 'news' else
                 'workspace/sandbox/'+SERVER_LOGS[channel]+'/access-http.tsv')
    rows = [s for s in path.read_text(encoding='utf-8',errors='replace').splitlines() if s[:4].isdigit() and '\t' in s]
    count=max(0,min(count,100))
    if not count:return
    for line in rows[-count:]:
        stamp,method,route,status,size = (line.split('\t')+['']*5)[:5]
        print(f'{stamp[11:19]} {status} {method} {route} {size}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('focus')
    p = sub.add_parser('compact');p.add_argument('--on-top',action='store_true',help='temporarily raise only the selected render above other windows; does not change saved Dolphin settings')
    p = sub.add_parser('shot'); p.add_argument('--scale',type=float,default=.5); p.add_argument('--name')
    p = sub.add_parser('burst');p.add_argument('--name',required=True);p.add_argument('--frames',type=int,default=60);p.add_argument('--interval',type=int,default=150);p.add_argument('--trigger-a',action='store_true')
    for name in ('point','click'):
        p = sub.add_parser(name); p.add_argument('fx',type=float); p.add_argument('fy',type=float)
        p.add_argument('--profile',default='default'); p.add_argument('--hold',type=int,default=300)
    p = sub.add_parser('b'); p.add_argument('--hold',type=int,default=300)
    p = sub.add_parser('key'); p.add_argument('name',choices=sorted(KEYS)); p.add_argument('--hold',type=int,default=250)
    p = sub.add_parser('log'); p.add_argument('channel',choices=sorted([*SERVER_LOGS,'news'])); p.add_argument('-n',type=int,default=10)
    sub.add_parser('stop')
    p = sub.add_parser('insert-disc'); p.add_argument('--hold',type=int,default=150); p.add_argument('--disc',default='GALJ01.iso')
    for name, p in sub.choices.items():
        if name != 'log':
            p.add_argument('--pid',type=int,help='explicit approved project process PID')
            p.add_argument('--keep-size',action='store_true',help='keep the current render size; pointer calibration must match this size')
            if name!='compact':p.add_argument('--on-top',action='store_true',help='temporarily raise only the selected render; saved settings are unchanged')
    args = parser.parse_args()
    if args.command == 'log': log(args.channel,args.n); return
    if hasattr(args,'hold') and not 1 <= args.hold <= 3000: raise ScopeError('Hold must be 1..3000 ms')
    if args.command == 'stop' and not (subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True).stdout or b'').lower().startswith(b'"dolphin.exe"'):
        print('not running'); return
    driver = Driver(args.pid)
    print('selected project profile',driver.target.profile,'PID',driver.process.pid)
    if args.command == 'stop': driver.stop(); return
    if args.command == 'compact':driver.compact(on_top=args.on_top);print('selected render window restored to 800x600');return
    if args.command == 'insert-disc' and driver.owned_dialogs():
        # A Change Disc dialog is already open (modal): fill it without refocusing the render.
        driver.insert_staged_disc(driver.windows()[0], args.hold, args.disc); return
    hwnd = driver.focus(maximize=not args.keep_size,on_top=args.on_top)
    if args.command == 'focus': print('render client rect',driver.rect(hwnd))
    elif args.command == 'shot': driver.shot(hwnd,args.scale,args.name)
    elif args.command == 'burst':
        if not 2<=args.frames<=60 or not 100<=args.interval<=1000 or args.frames*args.interval>12000:raise ScopeError('Burst must be 2..60 frames and at most 12 seconds')
        capture_name(args.name+'-000')
        driver.shot(hwnd,.5,args.name+'-000')
        if args.trigger_a:
            driver.guard(hwnd);vk=KEYS['space'];scan=driver.u.MapVirtualKeyW(vk,0)
            driver.u.keybd_event(vk,scan,0,0)
            try:time.sleep(.12)
            finally:driver.u.keybd_event(vk,scan,2,0)
        for i in range(1,args.frames):
            time.sleep(args.interval/1000)
            driver.shot(hwnd,.5,f'{args.name}-{i:03d}')
    elif args.command in ('point','click'):
        driver.move(hwnd,args.fx,args.fy,args.profile)
        if args.command == 'click': driver.button(hwnd,2,4,args.hold)
    elif args.command == 'b': driver.button(hwnd,8,16,args.hold)
    elif args.command == 'insert-disc': driver.insert_staged_disc(hwnd,args.hold,args.disc)
    elif args.command == 'key':
        driver.guard(hwnd); keys=KEYS[args.name];keys=keys if isinstance(keys,tuple)else(keys,);pressed=[]
        try:
            for vk in keys:
                driver.guard(hwnd);scan=driver.u.MapVirtualKeyW(vk,0);driver.u.keybd_event(vk,scan,1 if vk in (37,38,39,40) else 0,0);pressed.append((vk,scan))
            time.sleep(args.hold/1000)
        finally:
            for vk,scan in reversed(pressed):driver.u.keybd_event(vk,scan,2 | (1 if vk in (37,38,39,40) else 0),0)


if __name__ == '__main__':
    try: main()
    except ScopeError as error:
        raise SystemExit('UI operation refused: '+str(error))from None
    except (OSError,subprocess.SubprocessError,ValueError):
        raise SystemExit('UI operation refused or failed; reobserve and check the approved project profile.') from None
