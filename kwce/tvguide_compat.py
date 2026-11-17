"""Emulator-only TV Guide access to local fixtures, without registering WC24."""
import hashlib
def local_registration_check(raw):
    # NWC24Check(usage): after NWC24GetCreationStage, cmpwi state,2;
    # beq skips the -109144 error. Ignore only that comparison in the local
    # experiment. The real cfg stays Initial, all other checks stay intact.
    at=0x14adf4;before=bytes.fromhex('2c000002418200143c60fffe380355a8')
    if raw[at:at+len(before)]!=before:raise ValueError('TV registration-check instruction identity differs')
    out=bytearray(raw);out[at+4:at+8]=bytes.fromhex('48000014')
    return bytes(out),dict(emulator_only=True,registration_state_written=False,check='NWC24Check creation-stage comparison',original_region_sha256=hashlib.sha256(before).hexdigest(),patched_instructions=1)

def local_plain_downloads(raw):
    # Only the all-loopback TV emulator WAD calls this. NWC24 flags 0x06 mean
    # ordinary unsigned, unencrypted payloads instead of game-key envelopes.
    # The IOS/Dolphin signature checks and other channels remain unchanged.
    at=0x39c654;before=bytes.fromhex('387e00043880000a4bdb9b29')
    if raw[at:at+12]!=before:raise ValueError('TV download flags identity differs')
    out=bytearray(raw);out[at+4:at+8]=bytes.fromhex('38800006')
    return bytes(out),dict(emulator_only=True,synthetic_plaintext_downloads=True,original_flags=10,local_flags=6,patched_instructions=1,hardware_compatible=False)
