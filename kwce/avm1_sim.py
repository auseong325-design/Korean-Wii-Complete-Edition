"""Minimal AVM1 (ActionScript 2) evaluator for unit-testing SWF action patches.

It runs action lists parsed by kwce.kirbytv_swf.parse: a class's DoInitAction
code (which defines the class) and the functions that code defines. Only the
actions and built-ins used by the Kirby TV classes under test are implemented;
anything else raises Unsupported, so a test cannot pass by silently skipping
code. This is not a Flash Player: there is no display list, timer, event or
network, and local time equals UTC.
"""
import math
import struct
from datetime import datetime, timedelta, timezone

from . import kirbytv_swf as S


class Unsupported(Exception):
    """An action or built-in the evaluator does not implement."""


class _Undefined:
    __slots__ = ()

    def __repr__(self):
        return 'undefined'


class _Null:
    __slots__ = ()

    def __repr__(self):
        return 'null'


UNDEF = _Undefined()
NULL = _Null()
NAN = float('nan')


class Obj:
    def __init__(self, proto=None, props=None):
        self.proto = proto
        self.props = dict(props or {})
        self.accessors = {}

    def __repr__(self):
        return f'Obj({sorted(self.props)[:8]})'


class Arr(Obj):
    def __init__(self, items=None, proto=None):
        super().__init__(proto)
        self.items = list(items or [])


class Func(Obj):
    """A function defined by DefineFunction/DefineFunction2 in a parsed action list."""

    def __init__(self, code, start, end, name, params, registers, flags, v2):
        super().__init__()
        self.code, self.start, self.end = code, start, end
        self.name, self.params, self.registers, self.flags, self.v2 = name, params, registers, flags, v2
        self.props['prototype'] = Obj(props={'constructor': self})


class Native(Obj):
    def __init__(self, fn, name=''):
        super().__init__()
        self.fn, self.name = fn, name
        self.props['prototype'] = Obj(props={'constructor': self})

    def __repr__(self):
        return f'Native({self.name})'


class DateObj(Obj):
    def __init__(self, ms, proto=None):
        super().__init__(proto)
        self.ms = ms


class Code:
    """A parsed action list with its constant pool and an action -> index map."""

    def __init__(self, raw):
        self.acts = S.parse(raw)
        self.pool = S.pool(self.acts)
        self.index = {id(a): i for i, a in enumerate(self.acts)}

    def at(self, ref):
        return len(self.acts) if ref is S.END else self.index[id(ref)]


class _Return(Exception):
    def __init__(self, value):
        self.value = value


# ------------------------------------------------------------------ values

def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def to_number(v):
    if is_number(v):
        return float(v)
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, str):
        text = v.strip()
        if not text:
            return 0.0
        try:
            if text.lower().startswith('0x'):
                return float(int(text, 16))
            return float(text)
        except ValueError:
            return NAN
    if isinstance(v, DateObj):
        return v.ms
    return NAN


def number_to_str(x):
    if math.isnan(x):
        return 'NaN'
    if math.isinf(x):
        return 'Infinity' if x > 0 else '-Infinity'
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def to_bool(v):
    if v is UNDEF or v is NULL:
        return False
    if isinstance(v, bool):
        return v
    if is_number(v):
        return not (v == 0 or math.isnan(v))
    if isinstance(v, str):
        return len(v) > 0
    return True


def type_of(v):
    if v is UNDEF:
        return 'undefined'
    if v is NULL:
        return 'null'
    if isinstance(v, bool):
        return 'boolean'
    if is_number(v):
        return 'number'
    if isinstance(v, str):
        return 'string'
    if isinstance(v, (Func, Native)):
        return 'function'
    return 'object'


def _strict_eq(a, b):
    if type_of(a) != type_of(b):
        return False
    if is_number(a):
        return float(a) == float(b)
    if isinstance(a, (str, bool)):
        return a == b
    return a is b


# ---------------------------------------------------------------- evaluator

class VM:
    def __init__(self, now_ms=0.0):
        self.now_ms = now_ms
        self.object_proto = Obj()
        self.array_proto = Obj(self.object_proto)
        self.date_proto = Obj(self.object_proto)
        self.string_proto = Obj(self.object_proto)
        self.globals = Obj(self.object_proto)
        self.calls = []          # (name, args) of recorded mock calls, for tests
        self._builtins()

    # ---- built-ins
    def native(self, fn, name=''):
        return Native(fn, name)

    def _builtins(self):
        g = self.globals.props
        g['_global'] = self.globals

        def make_object(vm, this, args):
            return Obj(self.object_proto)
        obj_ctor = self.native(make_object, 'Object')
        obj_ctor.props['prototype'] = self.object_proto
        g['Object'] = obj_ctor

        def make_array(vm, this, args):
            if len(args) == 1 and is_number(args[0]):
                return Arr([UNDEF] * int(args[0]), self.array_proto)
            return Arr(args, self.array_proto)
        arr_ctor = self.native(make_array, 'Array')
        arr_ctor.props['prototype'] = self.array_proto
        g['Array'] = arr_ctor

        def make_date(vm, this, args):
            if not args:
                return DateObj(self.now_ms, self.date_proto)
            if len(args) == 1:
                value = args[0]
                return DateObj(to_number(value) if not isinstance(value, DateObj) else value.ms, self.date_proto)
            parts = [to_number(a) for a in args] + [1, 0, 0, 0, 0][len(args) - 2:]
            return DateObj(_utc_ms(*parts[:7]), self.date_proto)
        date_ctor = self.native(make_date, 'Date')
        date_ctor.props['prototype'] = self.date_proto
        date_ctor.props['UTC'] = self.native(
            lambda vm, this, args: _utc_ms(*([to_number(a) for a in args] + [1, 0, 0, 0, 0])[:7]) if len(args) >= 2 else NAN, 'Date.UTC')
        g['Date'] = date_ctor
        self._date_methods()

        math_obj = Obj(self.object_proto)
        for name, fn in (('floor', math.floor), ('ceil', math.ceil), ('abs', abs)):
            math_obj.props[name] = self.native(
                (lambda f: lambda vm, this, args: _num_call(f, args))(fn), 'Math.' + name)
        math_obj.props['round'] = self.native(lambda vm, this, args: _num_call(lambda x: math.floor(x + 0.5), args), 'Math.round')
        math_obj.props['max'] = self.native(lambda vm, this, args: max(to_number(a) for a in args), 'Math.max')
        math_obj.props['min'] = self.native(lambda vm, this, args: min(to_number(a) for a in args), 'Math.min')
        math_obj.props['pow'] = self.native(lambda vm, this, args: to_number(args[0]) ** to_number(args[1]), 'Math.pow')
        g['Math'] = math_obj
        g['isNaN'] = self.native(lambda vm, this, args: math.isnan(to_number(args[0] if args else UNDEF)), 'isNaN')
        g['String'] = self.native(lambda vm, this, args: self.to_str(args[0]) if args else '', 'String')
        g['Number'] = self.native(lambda vm, this, args: to_number(args[0]) if args else 0.0, 'Number')
        g['ASSetPropFlags'] = self.native(lambda vm, this, args: UNDEF, 'ASSetPropFlags')

        def add_property(vm, this, args):
            name = self.to_str(args[0])
            getter = args[1] if len(args) > 1 else UNDEF
            setter = args[2] if len(args) > 2 else UNDEF
            this.accessors[name] = (getter, setter)
            return True
        self.object_proto.props['addProperty'] = self.native(add_property, 'addProperty')
        self.object_proto.props['hasOwnProperty'] = self.native(
            lambda vm, this, args: isinstance(this, Obj) and self.to_str(args[0]) in this.props, 'hasOwnProperty')

        def arr_push(vm, this, args):
            this.items.extend(args)
            return float(len(this.items))

        def arr_join(vm, this, args):
            sep = ',' if not args or args[0] is UNDEF else self.to_str(args[0])
            return sep.join('' if v is UNDEF or v is NULL else self.to_str(v) for v in this.items)

        def arr_slice(vm, this, args):
            n = len(this.items)
            a = _index_arg(args, 0, 0, n)
            b = _index_arg(args, 1, n, n)
            return Arr(this.items[a:b], self.array_proto)

        def arr_splice(vm, this, args):
            n = len(this.items)
            a = _index_arg(args, 0, 0, n)
            count = n - a if len(args) < 2 else max(0, int(to_number(args[1])))
            removed = this.items[a:a + count]
            this.items[a:a + count] = list(args[2:])
            return Arr(removed, self.array_proto)

        def arr_pop(vm, this, args):
            return this.items.pop() if this.items else UNDEF
        for name, fn in (('push', arr_push), ('join', arr_join), ('slice', arr_slice), ('splice', arr_splice), ('pop', arr_pop)):
            self.array_proto.props[name] = self.native(fn, 'Array.' + name)

    def _date_methods(self):
        p = self.date_proto.props

        def getter(field):
            def fn(vm, this, args):
                if math.isnan(this.ms):
                    return NAN
                d = _dt(this.ms)
                return float({'year': d.year, 'month': d.month - 1, 'date': d.day, 'hours': d.hour, 'minutes': d.minute,
                              'seconds': d.second, 'day': (d.weekday() + 1) % 7, 'yearAS': d.year - 1900}[field])
            return fn
        for names, field in ((('getUTCFullYear', 'getFullYear'), 'year'), (('getUTCMonth', 'getMonth'), 'month'),
                             (('getUTCDate', 'getDate'), 'date'), (('getUTCHours', 'getHours'), 'hours'),
                             (('getUTCMinutes', 'getMinutes'), 'minutes'), (('getUTCSeconds', 'getSeconds'), 'seconds'),
                             (('getUTCDay', 'getDay'), 'day'), (('getYear',), 'yearAS')):
            for name in names:
                p[name] = self.native(getter(field), 'Date.' + name)
        p['getTime'] = p['valueOf'] = self.native(lambda vm, this, args: this.ms, 'Date.getTime')

        def setter(kind):
            def fn(vm, this, args):
                values = [to_number(a) for a in args]
                if math.isnan(this.ms) and kind not in ('time', 'fullyear'):
                    return NAN
                base = _dt(0 if math.isnan(this.ms) else this.ms)
                y, mo, d, h, mi, s = base.year, base.month - 1, base.day, base.hour, base.minute, base.second
                frac = (0 if math.isnan(this.ms) else this.ms) - math.floor((0 if math.isnan(this.ms) else this.ms) / 1000) * 1000
                if kind == 'time':
                    this.ms = values[0] if values else NAN
                    return this.ms
                if kind == 'fullyear':
                    y = values[0]
                    mo = values[1] if len(values) > 1 else mo
                    d = values[2] if len(values) > 2 else d
                elif kind == 'month':
                    mo = values[0]
                    d = values[1] if len(values) > 1 else d
                elif kind == 'date':
                    d = values[0]
                elif kind == 'hours':
                    h = values[0]
                    mi = values[1] if len(values) > 1 else mi
                    s = values[2] if len(values) > 2 else s
                    frac = values[3] if len(values) > 3 else frac
                this.ms = _utc_ms(y, mo, d, h, mi, s, frac)
                return this.ms
            return fn
        for names, kind in ((('setUTCFullYear', 'setFullYear'), 'fullyear'), (('setUTCMonth', 'setMonth'), 'month'),
                            (('setUTCDate', 'setDate'), 'date'), (('setUTCHours', 'setHours'), 'hours'), (('setTime',), 'time')):
            for name in names:
                p[name] = self.native(setter(kind), 'Date.' + name)

        def to_string(vm, this, args):
            if math.isnan(this.ms):
                return 'Invalid Date'
            return _dt(this.ms).strftime('%a %b %d %H:%M:%S GMT+0000 %Y')
        p['toString'] = self.native(to_string, 'Date.toString')

    # ---- conversions needing the VM
    def to_str(self, v):
        if isinstance(v, str):
            return v
        if v is UNDEF:
            return 'undefined'
        if v is NULL:
            return 'null'
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if is_number(v):
            return number_to_str(float(v))
        if isinstance(v, DateObj):
            return self.call(self.get(v, 'toString'), v, [])
        if isinstance(v, Arr):
            return self.call(self.array_proto.props['join'], v, [])
        if isinstance(v, (Func, Native)):
            return '[type Function]'
        method = self.get(v, 'toString')
        if isinstance(method, (Func, Native)) and method is not self.object_proto.props.get('toString'):
            return self.to_str(self.call(method, v, []))
        return '[object Object]'

    def to_primitive(self, v, hint=None):
        if isinstance(v, DateObj):
            return v.ms if hint == 'number' else self.to_str(v)
        if isinstance(v, Obj) and not isinstance(v, (Func, Native)):
            value_of = self.get(v, 'valueOf')
            if isinstance(value_of, (Func, Native)):
                result = self.call(value_of, v, [])
                if not isinstance(result, Obj):
                    return result
            return self.to_str(v)
        return v

    def loose_eq(self, a, b):
        if type_of(a) == type_of(b):
            return _strict_eq(a, b)
        if a in (UNDEF, NULL) and b in (UNDEF, NULL):
            return True
        if a in (UNDEF, NULL) or b in (UNDEF, NULL):
            return False
        if isinstance(a, bool):
            return self.loose_eq(to_number(a), b)
        if isinstance(b, bool):
            return self.loose_eq(a, to_number(b))
        if is_number(a) and isinstance(b, str) or isinstance(a, str) and is_number(b):
            return to_number(a) == to_number(b)
        if isinstance(a, Obj) and not isinstance(b, Obj):
            return self.loose_eq(self.to_primitive(a), b)
        if isinstance(b, Obj) and not isinstance(a, Obj):
            return self.loose_eq(a, self.to_primitive(b))
        return False

    def less(self, a, b):
        pa, pb = self.to_primitive(a, 'number'), self.to_primitive(b, 'number')
        if isinstance(pa, str) and isinstance(pb, str):
            return pa < pb
        x, y = to_number(pa), to_number(pb)
        if math.isnan(x) or math.isnan(y):
            return UNDEF
        return x < y

    # ---- members
    def get(self, obj, name):
        if not isinstance(name, str):
            name = self.to_str(name)
        if isinstance(obj, str):
            return self._string_member(obj, name)
        if is_number(obj) or isinstance(obj, bool):
            if name == 'toString':
                return self.native(lambda vm, this, args: self.to_str(obj), 'Number.toString')
            return UNDEF
        if not isinstance(obj, Obj):
            return UNDEF
        if isinstance(obj, Arr):
            if name == 'length':
                return float(len(obj.items))
            if name.isdigit():
                i = int(name)
                return obj.items[i] if i < len(obj.items) else UNDEF
        o = obj
        while o is not None:
            if name in o.accessors:
                getter = o.accessors[name][0]
                return self.call(getter, obj, []) if isinstance(getter, (Func, Native)) else UNDEF
            if name in o.props:
                return o.props[name]
            o = o.proto
        return UNDEF

    def set(self, obj, name, value):
        if not isinstance(name, str):
            name = self.to_str(name)
        if not isinstance(obj, Obj):
            return
        if isinstance(obj, Arr) and name.isdigit():
            i = int(name)
            while len(obj.items) <= i:
                obj.items.append(UNDEF)
            obj.items[i] = value
            return
        if isinstance(obj, Arr) and name == 'length':
            del obj.items[int(to_number(value)):]
            return
        o = obj
        while o is not None:
            if name in o.accessors:
                setter = o.accessors[name][1]
                if isinstance(setter, (Func, Native)):
                    self.call(setter, obj, [value])
                return
            o = o.proto
        obj.props[name] = value

    def _string_member(self, s, name):
        if name == 'length':
            return float(len(s))
        vm = self

        def method(fn):
            return self.native(lambda _vm, this, args: fn(*args), 'String.' + name)
        if name == 'charAt':
            return method(lambda i=0.0, *_: s[int(to_number(i))] if 0 <= int(to_number(i)) < len(s) else '')
        if name == 'charCodeAt':
            return method(lambda i=0.0, *_: float(ord(s[int(to_number(i))])) if 0 <= int(to_number(i)) < len(s) else NAN)
        if name == 'slice':
            return method(lambda a=0.0, b=UNDEF, *_: s[_index_arg([a], 0, 0, len(s)):_index_arg([b], 0, len(s), len(s))])
        if name == 'substring':
            def substring(a=0.0, b=UNDEF, *_):
                x = max(0, min(len(s), int(to_number(a)) if not math.isnan(to_number(a)) else 0))
                y = len(s) if b is UNDEF else max(0, min(len(s), int(to_number(b)) if not math.isnan(to_number(b)) else 0))
                return s[min(x, y):max(x, y)]
            return method(substring)
        if name == 'substr':
            def substr(a=0.0, n=UNDEF, *_):
                x = _index_arg([a], 0, 0, len(s))
                return s[x:] if n is UNDEF else s[x:x + max(0, int(to_number(n)))]
            return method(substr)
        if name == 'indexOf':
            return method(lambda sub, start=0.0, *_: float(s.find(vm.to_str(sub), int(to_number(start)))))
        if name == 'split':
            def split(sep=UNDEF, *_):
                if sep is UNDEF:
                    return Arr([s], vm.array_proto)
                sep = vm.to_str(sep)
                return Arr(list(s) if sep == '' else s.split(sep), vm.array_proto)
            return method(split)
        if name == 'toUpperCase':
            return method(lambda *_: s.upper())
        if name == 'toLowerCase':
            return method(lambda *_: s.lower())
        if name == 'toString':
            return method(lambda *_: s)
        return self.get(self.string_proto, name)

    # ---- calls
    def call(self, func, this, args):
        if isinstance(func, Native):
            return func.fn(self, this, list(args))
        if not isinstance(func, Func):
            raise Unsupported(f'call of a non-function {func!r}')
        return self._invoke(func, this, list(args))

    def construct(self, ctor, args):
        if isinstance(ctor, Native):
            result = ctor.fn(self, UNDEF, list(args))
            if isinstance(result, Obj):
                return result
            obj = Obj(self.get(ctor, 'prototype'))
            return obj
        if not isinstance(ctor, Func):
            raise Unsupported(f'new of a non-constructor {ctor!r}')
        obj = Obj(self.get(ctor, 'prototype'))
        result = self._invoke(ctor, obj, list(args))
        return result if isinstance(result, Obj) else obj

    def _invoke(self, func, this, args):
        regs = [UNDEF] * max(func.registers, 4)
        local = {}
        if func.v2:
            n = 1
            flags = func.flags
            if flags & 0x01:
                regs[n] = this
                n += 1
            if flags & 0x04:
                regs[n] = Arr(args, self.array_proto)
                n += 1
            if flags & 0x10:
                regs[n] = UNDEF
                n += 1
            if flags & 0x40:
                regs[n] = UNDEF
                n += 1
            if flags & 0x80:
                regs[n] = UNDEF
                n += 1
            if flags & 0x100:
                regs[n] = self.globals
                n += 1
            for i, (register, name) in enumerate(func.params):
                value = args[i] if i < len(args) else UNDEF
                if register:
                    regs[register] = value
                else:
                    local[name] = value
        else:
            for i, name in enumerate(func.params):
                local[name] = args[i] if i < len(args) else UNDEF
            local['this'] = this
        return self.run(func.code, func.start, func.end, regs, local, this)

    # ---- execution
    def run_class(self, raw):
        """Execute a DoInitAction body (without the sprite id)."""
        code = Code(raw)
        return self.run(code, 0, len(code.acts), [UNDEF] * 4, {}, UNDEF)

    def lookup(self, name, local, this):
        if name in local:
            return local[name]
        if name == 'this':
            return this
        return self.get(self.globals, name)

    def run(self, code, start, end, regs, local, this):
        acts, stack = code.acts, []
        pool = code.pool
        pc = start

        def pop():
            # Flash Player returns undefined for an empty stack; the class
            # definitions rely on it (an extra Pop after each package check).
            return stack.pop() if stack else UNDEF
        while pc < end:
            act = acts[pc]
            op = act.op
            pc += 1
            if op == 0x88:          # ConstantPool
                pool = S.pool([act])
            elif op == 0x96:        # Push
                for kind, value in S.push_values(act.payload, pool):
                    if kind == 'str':
                        stack.append(value)
                    elif kind in ('float', 'double', 'int'):
                        stack.append(float(value))
                    elif kind == 'null':
                        stack.append(NULL)
                    elif kind == 'undef':
                        stack.append(UNDEF)
                    elif kind == 'reg':
                        stack.append(regs[value])
                    elif kind == 'bool':
                        stack.append(bool(value))
            elif op == 0x17:        # Pop
                pop()
            elif op == 0x4C:        # PushDuplicate
                stack.append(stack[-1])
            elif op == 0x4D:        # StackSwap
                a, b = pop(), pop()
                stack += [a, b]
            elif op == 0x87:        # StoreRegister
                regs[act.payload[0]] = stack[-1]
            elif op == 0x1C:        # GetVariable
                stack.append(self.lookup(self.to_str(pop()), local, this))
            elif op == 0x1D:        # SetVariable
                value, name = pop(), self.to_str(pop())
                if name in local:
                    local[name] = value
                else:
                    self.set(self.globals, name, value)
            elif op in (0x3C, 0x41):  # DefineLocal / DefineLocal2
                if op == 0x3C:
                    value, name = pop(), self.to_str(pop())
                    local[name] = value
                else:
                    local[self.to_str(pop())] = UNDEF
            elif op == 0x4E:        # GetMember
                name, obj = pop(), pop()
                stack.append(self.get(obj, name))
            elif op == 0x4F:        # SetMember
                value, name, obj = pop(), pop(), pop()
                self.set(obj, name, value)
            elif op == 0x3A:        # Delete
                name, obj = self.to_str(pop()), pop()
                found = isinstance(obj, Obj) and name in obj.props
                if found:
                    del obj.props[name]
                stack.append(found)
            elif op == 0x3B:        # Delete2
                name = self.to_str(pop())
                found = name in local or name in self.globals.props
                local.pop(name, None)
                stack.append(found)
            elif op in (0x52, 0x53):  # CallMethod / NewMethod
                name, obj = pop(), pop()
                count = int(to_number(pop()))
                args = [pop() for _ in range(count)]
                if name is UNDEF or name == '':
                    func, target = obj, UNDEF
                else:
                    func, target = self.get(obj, name), obj
                if op == 0x52:
                    if func is UNDEF:
                        stack.append(UNDEF)  # Flash ignores calls of missing methods
                        continue
                    stack.append(self.call(func, target, args))
                else:
                    stack.append(self.construct(func, args))
            elif op in (0x3D, 0x40):  # CallFunction / NewObject
                name = self.to_str(pop())
                count = int(to_number(pop()))
                args = [pop() for _ in range(count)]
                func = self.lookup(name, local, this)
                if op == 0x3D:
                    if func is UNDEF:
                        stack.append(UNDEF)
                        continue
                    stack.append(self.call(func, UNDEF, args))
                else:
                    stack.append(self.construct(func, args))
            elif op == 0x43:        # InitObject
                count = int(to_number(pop()))
                obj = Obj(self.object_proto)
                for _ in range(count):
                    value, name = pop(), self.to_str(pop())
                    obj.props[name] = value
                stack.append(obj)
            elif op == 0x42:        # InitArray
                count = int(to_number(pop()))
                stack.append(Arr([pop() for _ in range(count)], self.array_proto))
            elif op in (0x8E, 0x9B):  # DefineFunction2 / DefineFunction
                func = self._define(code, act)
                pc = code.at(act.ends[0])
                if func.name:
                    local[func.name] = func
                else:
                    stack.append(func)
            elif op == 0x3E:        # Return
                return pop()
            elif op == 0x00:        # End
                return UNDEF
            elif op == 0x99:        # Jump
                pc = code.at(act.target)
            elif op == 0x9D:        # If
                if to_bool(pop()):
                    pc = code.at(act.target)
            elif op == 0x12:        # Not
                stack.append(not to_bool(pop()))
            elif op == 0x47:        # Add2
                b, a = pop(), pop()
                pa, pb = self.to_primitive(a), self.to_primitive(b)
                if isinstance(pa, str) or isinstance(pb, str):
                    stack.append(self.to_str(pa) + self.to_str(pb))
                else:
                    stack.append(to_number(pa) + to_number(pb))
            elif op in (0x0B, 0x0C, 0x0D, 0x3F):  # Subtract Multiply Divide Modulo
                b, a = to_number(pop()), to_number(pop())
                if op == 0x0B:
                    stack.append(a - b)
                elif op == 0x0C:
                    stack.append(a * b)
                elif op == 0x0D:
                    stack.append(NAN if b == 0 and (a == 0 or math.isnan(a)) else (a / b if b else math.copysign(math.inf, a)))
                else:
                    stack.append(NAN if b == 0 or math.isnan(a) or math.isnan(b) else math.fmod(a, b))
            elif op in (0x50, 0x51):  # Increment / Decrement
                stack.append(to_number(pop()) + (1 if op == 0x50 else -1))
            elif op == 0x48:        # Less2
                b, a = pop(), pop()
                stack.append(self.less(a, b))
            elif op == 0x67:        # Greater
                b, a = pop(), pop()
                stack.append(self.less(b, a))
            elif op == 0x49:        # Equals2
                b, a = pop(), pop()
                stack.append(self.loose_eq(a, b))
            elif op == 0x66:        # StrictEquals
                b, a = pop(), pop()
                stack.append(_strict_eq(a, b))
            elif op == 0x44:        # TypeOf
                stack.append(type_of(pop()))
            elif op == 0x4A:        # ToNumber
                stack.append(to_number(pop()))
            elif op == 0x4B:        # ToString
                stack.append(self.to_str(pop()))
            elif op == 0x18:        # ToInteger
                x = to_number(pop())
                stack.append(0.0 if math.isnan(x) else float(math.trunc(x)))
            elif op == 0x55:        # Enumerate2
                obj = pop()
                stack.append(NULL)
                if isinstance(obj, Arr):
                    stack.extend(str(i) for i in range(len(obj.items)))
                elif isinstance(obj, Obj):
                    stack.extend(reversed(list(obj.props)))
            elif op == 0x69:        # Extends
                superclass, subclass = pop(), pop()
                super_proto = self.get(superclass, 'prototype') if isinstance(superclass, Obj) else UNDEF
                if not isinstance(super_proto, Obj):
                    super_proto = self.object_proto   # e.g. a MovieClip base the evaluator does not model
                proto = Obj(super_proto, {'__constructor__': superclass})
                subclass.props['prototype'] = proto
            elif op == 0x2C:        # ImplementsOp: constructor, count, interfaces (no runtime effect here)
                pop()
                for _ in range(int(to_number(pop()))):
                    pop()
            elif op == 0x2B:        # CastOp
                obj, ctor = pop(), pop()
                stack.append(obj if self.instance_of(obj, ctor) else NULL)
            elif op == 0x54:        # InstanceOf
                ctor, obj = pop(), pop()
                stack.append(self.instance_of(obj, ctor))
            else:
                raise Unsupported(f'AVM1 action {op:#04x} at index {pc - 1}')
        return UNDEF

    def instance_of(self, obj, ctor):
        if not isinstance(obj, Obj):
            return False
        proto = self.get(ctor, 'prototype')
        o = obj.proto
        while o is not None:
            if o is proto:
                return True
            o = o.proto
        return False

    def _define(self, code, act):
        p = act.payload
        name, at = S.cstr(p, 0)
        if act.op == 0x8E:
            count, registers, flags = struct.unpack_from('<HBH', p, at)
            at += 5
            params = []
            for _ in range(count):
                register = p[at]
                pname, at = S.cstr(p, at + 1)
                params.append((register, pname))
            v2 = True
        else:
            count = struct.unpack_from('<H', p, at)[0]
            at += 2
            params = []
            for _ in range(count):
                pname, at = S.cstr(p, at)
                params.append(pname)
            registers, flags, v2 = 4, 0, False
        start = code.index[id(act)] + 1
        func = Func(code, start, code.at(act.ends[0]), name, params, registers, flags, v2)
        func.props['prototype'].proto = self.object_proto
        func.proto = self.object_proto
        return func

    # ---- helpers for tests
    def path(self, dotted, create=False):
        obj = self.globals
        for name in dotted.split('.'):
            nxt = self.get(obj, name)
            if nxt is UNDEF:
                if not create:
                    return UNDEF
                nxt = Obj(self.object_proto)
                self.set(obj, name, nxt)
            obj = nxt
        return obj

    def obj(self, **props):
        return Obj(self.object_proto, props)


def _num_call(fn, args):
    x = to_number(args[0]) if args else NAN
    return NAN if math.isnan(x) or math.isinf(x) and fn is not abs else float(fn(x))


def _index_arg(args, i, default, n):
    if len(args) <= i or args[i] is UNDEF:
        return default
    x = to_number(args[i])
    if math.isnan(x):
        return 0
    x = int(x)
    return max(0, n + x) if x < 0 else min(x, n)


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _utc_ms(y, mo=0, d=1, h=0, mi=0, s=0, ms=0):
    values = [y, mo, d, h, mi, s, ms]
    if any(math.isnan(v) or math.isinf(v) for v in values):
        return NAN
    y, mo = int(y), int(mo)
    y += mo // 12
    mo %= 12
    day0 = datetime(y, mo + 1, 1, tzinfo=timezone.utc)
    total = (day0 - _EPOCH) / timedelta(milliseconds=1)
    return float(total + ((d - 1) * 86400 + h * 3600 + mi * 60 + s) * 1000 + ms)


def _dt(ms):
    return _EPOCH + timedelta(milliseconds=math.floor(ms))


def date_ms(y, mo, d, h=0, mi=0, s=0):
    """UTC milliseconds for a calendar date (month 1-12), for tests."""
    return _utc_ms(y, mo - 1, d, h, mi, s, 0)
