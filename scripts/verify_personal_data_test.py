"""Read-only check of the pd.dat the Korean Set Personal Data build wrote in the test profile.

Run after a Dolphin review in which fictional values were saved with 완료.
Decrypts with Dolphin 2609a's public DEFAULT_DEVICE_ID (launch_dolphin.validate
refuses profiles holding keys.bin), checks the PDFF v2 / INFO / KANA layout the
Japanese channels' PD SDK reads, and prints per-field length and character
classes only (no values). Never point this at a real console's data.
"""
import json,sys
from audit_sd import ROOT
from prepare_channel_access import stopped
from prepare_personal_data_test import register,PROFILE,PD_DIR
import launch_dolphin as launcher
from kwce import personal_data_format as fmt
from kwce.personal_data_fork import SOURCE

def classes(text):
    out=set()
    for c in text:
        if '\uac00'<=c<='\ud7a3' or '\u3131'<=c<='\u318e':out.add('hangul')
        elif c.isascii()and c.isalpha():out.add('latin')
        elif c.isdigit():out.add('digit')
        else:out.add('other')
    return sorted(out)

def main():
    stopped();register();launcher.validate(PROFILE)
    path=PD_DIR/'pd.dat'
    if not path.exists():print('No pd.dat in the test profile yet (SPD writes it when 완료 is pressed)');return 1
    plain=fmt.decrypt(path.read_bytes(),fmt.DOLPHIN_DEFAULT_DEVICE_ID);fmt.check(plain)
    template,_=fmt.korean_template((SOURCE/'data/title/pd_decrypted.dat').read_bytes())
    allowed=[(a,a+s)for a,s in fmt.FIELDS.values()]+[(fmt.PIN_MAGIC[0],fmt.PIN_MAGIC[0]+fmt.PIN_MAGIC[1]),(fmt.PIN[0],fmt.PIN[0]+fmt.PIN[1])]
    outside=[i for i in range(fmt.LENGTH)if plain[i]!=template[i]and not any(a<=i<b for a,b in allowed)]
    fields=fmt.fields(plain)
    summary={k:dict(length=len(v),classes=classes(v))for k,v in fields.items()if isinstance(v,str)}
    print('layout PDFF v2 / INFO 0x256F / KANA 0x40C; bytes changed outside fields:',len(outside),'; PIN protected:',fields['pin_protected'])
    for name,row in summary.items():print(f'  {name}: {row["length"]} chars {"/".join(row["classes"])or "-"}')
    if outside:raise SystemExit('pd.dat differs from the template outside the person/address/PIN fields')
    if fields['kana_last_name']!=fields['last_name']or fields['kana_first_name']!=fields['first_name']:raise SystemExit('KANA names differ from INFO names')
    print('PASS: pd.dat has the PD SDK layout; only person/address/PIN fields differ from the template')
if __name__=='__main__':sys.exit(main())
