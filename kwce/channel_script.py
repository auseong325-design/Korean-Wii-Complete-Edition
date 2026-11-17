"""Read-only parser/disassembler for Wii Menu channel scripts (RCHE, opcode version 3).

The System Menu runs these scripts for channel icons/banners whose IMET header
names an icon/banner CS content (``arc/icon.cs.lz7`` / ``arc/banner.cs.lz7``).
Encoding follows the decompiled VM in external/wii-ipl/src/channelScript/CHANSVm.c
(CHANSVmAddExe, CHANSVmLinkModules, CHANSVmStep, VmCallMethod):

* header ``RCHE``, opcode version 3 at 0x04, total size at 0x08, module type at 0x0C;
  the module block at 0x20 holds big-endian offsets relative to 0x20;
* every operand is big-endian (the VM_READ_LE_* macros read MSB first);
  execution starts at pc 1;
* 0x40-0x5F store the accumulator into a symbol, 0x60-0x7F load a symbol;
* 0x80/0xA0/0xC0/0xE0 classes are case / branch-false / branch-true / branch.

Only structure is decoded; nothing is executed.
"""
import struct

BASE = {
    0x00: ('ret', 1), 0x01: ('retv', 1), 0x02: ('new', 2), 0x03: ('newarray', 3),
    0x04: ('push', 1), 0x05: ('pop', 1),
    0x06: ('add', 1), 0x07: ('sub', 1), 0x08: ('mul', 1), 0x09: ('div', 1), 0x0A: ('mod', 1),
    0x0B: ('and', 1), 0x0C: ('or', 1), 0x0D: ('xor', 1), 0x0E: ('shl', 1), 0x0F: ('sar', 1),
    0x10: ('eq', 1), 0x11: ('ne', 1), 0x12: ('lt', 1), 0x13: ('gt', 1), 0x14: ('le', 1), 0x15: ('ge', 1),
    0x16: ('bnot', 1), 0x17: ('not', 1),
    0x18: ('ldi', 2), 0x19: ('addi', 2), 0x1A: ('subi', 2), 0x1B: ('muli', 2), 0x1C: ('divi', 2),
    0x1D: ('modi', 2), 0x1E: ('andi', 2), 0x1F: ('ori', 2), 0x20: ('xori', 2),
    0x21: ('eqi', 2), 0x22: ('nei', 2), 0x23: ('lti', 2), 0x24: ('gti', 2), 0x25: ('lei', 2), 0x26: ('gei', 2),
    0x27: ('ldi', 3), 0x28: ('ldi', 5), 0x29: ('ldi', 9), 0x2A: ('ldf', 9),
    0x2B: ('ldundef', 1), 0x2C: ('ldstr', 3), 0x2D: ('index', 1),
    0x30: ('callm', 4), 0x31: ('callf', 2), 0x32: ('pget', 3), 0x33: ('pset', 3),
    0x34: ('forin', 5), 0x35: ('jmp', 4), 0x36: ('delsym', 3), 0x37: ('delind', 1),
    0x3E: ('ldind', 1), 0x3F: ('stind', 1),
}
BRANCH = {0x00: 'case', 0x20: 'bf', 0x40: 'bt', 0x60: 'bra'}


def _u32(d, at):
    return struct.unpack_from('>I', d, at)[0]


def _names(d, table, count, first=0):
    out = []
    for i in range(count):
        word = _u32(d, table + 4 * i)
        length, offset = word >> 24, word & 0xFFFFFF
        if i < first or length == 0:
            out.append('')
            continue
        at = table + offset
        if at + length > len(d):
            raise ValueError('Channel script name out of bounds')
        out.append(d[at:at + length].decode('ascii'))
    return out


def parse(data):
    """Return the module tables of one RCHE executable."""
    d = bytes(data)
    if len(d) < 0x80 or d[:4] != b'RCHE' or d[4] != 3:
        raise ValueError('Not an RCHE opcode-version-3 channel script')
    size = _u32(d, 8)
    if size != len(d) or size & 0x1F:
        raise ValueError('Channel script size field differs')
    m = 0x20
    code_size, code = _u32(d, m + 0x0C), _u32(d, m + 0x10)
    module_count = _u32(d, m + 0x14)
    name_count, name_tbl = _u32(d, m + 0x20), _u32(d, m + 0x24)
    method_count, method_tbl = _u32(d, m + 0x28), _u32(d, m + 0x2C)
    string_count, string_tbl = _u32(d, m + 0x30), _u32(d, m + 0x34)
    dispatch = _u32(d, m + 0x40)
    if code < 0x60 or m + code + code_size > len(d):
        raise ValueError('Channel script code bounds')
    symbols = _names(d, m + dispatch, module_count)
    methods = _names(d, m + method_tbl, method_count, first=1)
    strings, at = [], m + string_tbl
    for _ in range(string_count):
        length = struct.unpack_from('>H', d, at)[0]
        at += 2
        if length & 1 or at + length > len(d):
            raise ValueError('Channel script string bounds')
        strings.append(d[at:at + length].decode('utf-16-be', 'replace'))
        at += length
    functions = []
    for i in range(name_count):
        addr, idx, push, headers = struct.unpack_from('>IHBB', d, m + name_tbl + 8 * i)
        functions.append(dict(index=i, code=addr, symbol=symbols[idx] if idx < module_count else f'#{idx}',
                              symbol_index=idx, args=push, locals=headers))
    return dict(code=d[m + code:m + code + code_size], symbols=symbols, methods=methods,
                strings=strings, functions=functions, module_count=module_count)


def _symbol(module, idx, frame=None):
    if idx < module['module_count']:
        return module['symbols'][idx] or f'sym{idx}'
    if frame:
        # VmPushFuncReturnInfo: frameBase = 0x2000 - (locals + args); locals
        # first, then arguments in reverse order (CHANSVm_81455654).
        args, local_count = frame
        slot = idx - (0x2000 - local_count - args)
        if 0 <= slot < local_count:
            return f'loc{slot}'
        if local_count <= slot < local_count + args:
            return f'arg{args - 1 - (slot - local_count)}'
    return f'v{idx}'


def decode(module):
    """Yield one dict per instruction (pc, op, size, mnemonic, text, target)."""
    code = module['code']
    starts = {f['code']: (f['args'], f['locals']) for f in module['functions']}
    pc, end, frame = 1, len(code), None
    while pc < end:
        frame = starts.get(pc, frame)
        op = code[pc]
        ins = dict(pc=pc, op=op, target=None)
        if op < 0x40:
            if op not in BASE:
                ins.update(size=1, mnemonic='db', text=f'db 0x{op:02x}')
                yield ins
                pc += 1
                continue
            name, size = BASE[op]
            raw = code[pc + 1:pc + size]
            text = name
            if name == 'ldi':
                # VmLoadImmInteger ORs masked bytes into an s64 that starts at 0.
                text = f'ldi {int.from_bytes(raw, "big", signed=len(raw) == 8)}'
            elif name == 'ldf':
                text = f'ldf {struct.unpack(">d", raw)[0]!r}'
            elif op in range(0x19, 0x27):
                text = f'{name} {raw[0]}'
            elif name == 'ldstr':
                i = struct.unpack('>H', raw)[0]
                s = module['strings'][i] if i < len(module['strings']) else '?'
                text = f'ldstr {s!r}'
                ins['string'] = i
            elif name in ('callm', 'pget', 'pset'):
                i = struct.unpack('>H', raw[:2])[0]
                meth = module['methods'][i] if i < len(module['methods']) else f'?{i}'
                text = f'{name} .{meth}' + (f' argc={raw[2]}' if name == 'callm' else '')
                ins['method'] = meth
            elif name in ('callf', 'new'):
                text = f'{name} argc={raw[0]}'
            elif name in ('newarray',):
                text = f'newarray {struct.unpack(">H", raw)[0]}'
            elif name == 'delsym':
                text = f'delsym {_symbol(module, struct.unpack(">H", raw)[0] & 0x1FFF, frame)}'
            elif name == 'jmp':
                v = int.from_bytes(raw, 'big')
                ins['target'] = pc + v - 0xFFFFFF if v & 0x800000 else pc + 4 + v
                text = f'jmp {ins["target"]:#06x}'
            elif name == 'forin':
                sym = struct.unpack('>H', raw[:2])[0]
                v = struct.unpack('>H', raw[2:])[0] & 0x1FFF
                ins['target'] = pc + v - 0x1FFC if v & 0x1000 else pc + 5 + v
                text = f'forin {_symbol(module, sym, frame)} else {ins["target"]:#06x}'
            ins.update(size=size, mnemonic=name, text=text)
        elif op < 0x80:
            idx = ((op << 8) | code[pc + 1]) & 0x1FFF
            # Bit 5 set stores the accumulator (VmOpcodes.h); the decompiled
            # VmStore call order reads reversed, the bytecode settles it
            # ('load print; callf' and 'load SaveData; new').
            name = 'store' if op & 0x20 else 'load'
            ins.update(size=2, mnemonic=name, text=f'{name} {_symbol(module, idx, frame)}', symbol=idx)
        else:
            v = ((op << 8) | code[pc + 1]) & 0x1FFF
            ins['target'] = pc + v - 0x1FFF if v & 0x1000 else pc + 2 + v
            name = BRANCH[op & 0x60]
            ins.update(size=2, mnemonic=name, text=f'{name} {ins["target"]:#06x}')
        yield ins
        pc += ins['size']


def listing(module):
    """Plain-text disassembly with function labels."""
    labels = {f['code']: f['symbol'] for f in module['functions']}
    lines = []
    for ins in decode(module):
        if ins['pc'] in labels:
            lines.append(f'\n{labels[ins["pc"]]}:')
        lines.append(f'  {ins["pc"]:04x}: {ins["text"]}')
    return '\n'.join(lines)
