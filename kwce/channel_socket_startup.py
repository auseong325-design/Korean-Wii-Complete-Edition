"""Use the SDK's own finite SOStartupEx deadline; preserve its cleanup/errors."""
import hashlib,json,struct
from pathlib import Path
from .ppc_patch import to_file

ROOT=Path(__file__).resolve().parents[1]
def patch(raw,channel):
    cfg=json.loads((ROOT/'configs/channel-socket-startup-v1.lock.json').read_text())
    row=cfg['channels'][channel];site=int(row['wrapper'],16);off=to_file(raw,site,12)
    if hashlib.sha256(raw[off:off+12]).hexdigest()!=row['wrapper_sha256']:raise ValueError('SOStartup wrapper identity differs')
    if hashlib.sha256(raw[off+12:off+12+0x330]).hexdigest()!=row['native_ex_window_sha256']:raise ValueError('Native SOStartupEx changed')
    if not 0<cfg['timeout_ms']<32768:raise ValueError('Reviewed socket startup deadline range')
    out=bytearray(raw);out[off:off+8]=struct.pack('>II',0x38600000|cfg['timeout_ms'],0x60000000)
    return bytes(out),dict(wrapper=hex(site),original_timeout_ms=row['original_timeout_ms'],timeout_ms=cfg['timeout_ms'],
        native_timeout_cleanup_and_errors_preserved=True,ios_sync_calls_not_globally_preempted=True,
        service_urls_credentials_signature_time_checks_unchanged=True,hardware_verified=False)
