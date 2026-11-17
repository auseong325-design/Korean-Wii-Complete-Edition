"""Compile the local SD-service research component, never a console image.

The address is a Unicorn fixture arena, NOT an approved menu code cave.
This module provides no installation, DOL patching or SD export API.
"""
from pathlib import Path
import subprocess
import tempfile

from .toolchain import tool

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'homebrew/kwce-disc-menu/sd-service-v1'
FIXTURE_BASE = 0x80600000


def compile_service():
    with tempfile.TemporaryDirectory() as temp:
        tmp = Path(temp)

        def run(name, *args):
            result = subprocess.run([str(tool(name)), *args], cwd=tmp,
                                    capture_output=True, text=True)
            if result.returncode or 'warning:' in result.stderr:
                raise ValueError(result.stderr)
            return result.stdout

        run('powerpc-eabi-gcc.exe', '-Os', '-mcpu=750', '-meabi', '-msdata=none',
            '-fno-pic', '-fno-common', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-unwind-tables',
            '-fno-asynchronous-unwind-tables', '-std=c99', '-Wall', '-Wextra',
            '-Werror', '-c', str(SOURCE / 'service.c'), '-o', 'service.o')
        libgcc = run('powerpc-eabi-gcc.exe', '-print-libgcc-file-name').strip()
        (tmp / 'link.ld').write_text(f'''SECTIONS {{
          . = {FIXTURE_BASE:#x};
          .probe : {{ *(.text*) *(.rodata*) *(.data*) *(.bss*) *(COMMON) }}
          /DISCARD/ : {{ *(.comment) *(.eh_frame*) *(.gnu.attributes) }}
        }}''', encoding='ascii')
        run('powerpc-eabi-ld.exe', '--no-undefined', '-T', 'link.ld',
            'service.o', libgcc, '-o', 'service.elf')
        symbols = {parts[-1]: int(parts[0], 16)
                   for line in run('powerpc-eabi-nm.exe', '-S', 'service.elf').splitlines()
                   if len(parts := line.split()) == 4}
        run('powerpc-eabi-objcopy.exe', '-O', 'binary', '-j', '.probe',
            'service.elf', 'service.bin')
        blob = (tmp / 'service.bin').read_bytes()
        if len(blob) > 16384:
            raise ValueError('SD service exceeds the local test arena')
        return blob, symbols
