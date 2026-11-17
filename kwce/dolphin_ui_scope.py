"""Pure, fail-closed target policy for the optional Windows UI helper."""
from dataclasses import dataclass
from pathlib import PureWindowsPath


class ScopeError(ValueError):
    pass


@dataclass(frozen=True)
class Process:
    pid: int
    executable: str
    argv: tuple[str, ...]
    created: int


@dataclass(frozen=True)
class Target:
    profile: str
    executable: str
    user: str


def path_key(value):
    path = PureWindowsPath(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ScopeError('Absolute canonical project paths required')
    return str(path).casefold()


def match(process, targets):
    """Require the exact executable AND one explicit matching --user option."""
    try:
        executable = path_key(process.executable)
        if not process.created or not process.argv or path_key(process.argv[0]) != executable:
            return None
        users = []
        for i, arg in enumerate(process.argv[1:], 1):
            if arg in ('--user', '-u'):
                if i + 1 >= len(process.argv):
                    return None
                users.append(path_key(process.argv[i + 1]))
            elif arg.startswith(('--user=', '-u=')):
                users.append(path_key(arg.split('=', 1)[1]))
            elif arg.startswith('-u'):
                # Reject compact/ambiguous alternatives rather than guessing.
                return None
        if len(users) != 1:
            return None
        hits = [t for t in targets if path_key(t.executable) == executable and path_key(t.user) == users[0]]
        return hits[0] if len(hits) == 1 else None
    except ScopeError:
        return None


def select(processes, targets, pid=None):
    candidates = [(p, t) for p in processes if (t := match(p, targets)) is not None]
    if pid is not None:
        candidates = [(p, t) for p, t in candidates if p.pid == pid]
    if len(candidates) != 1:
        raise ScopeError('Expected one approved project Dolphin; use --pid when multiple are running')
    return candidates[0]


def revalidate(original, current, targets, window_pid, foreground=True, unobscured=True):
    if original != current or match(current, targets) is None or window_pid != original.pid:
        raise ScopeError('Target process or window identity changed; select again')
    if not foreground or not unobscured:
        raise ScopeError('Render window is not foreground and unobscured; input/capture refused')


def capture_name(name):
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name):
        raise ScopeError('Capture name must be a simple private-folder basename')
    if name.upper()in {'CON','PRN','AUX','NUL',*[f'COM{i}'for i in range(1,10)],*[f'LPT{i}'for i in range(1,10)]}:
        raise ScopeError('Windows device names are not capture files')
    return name + '.png'


def overlaps(first, second):
    return (max(first[0], second[0]) < min(first[2], second[2]) and
            max(first[1], second[1]) < min(first[3], second[3]))
