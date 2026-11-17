"""Local Python fallback following Dolphin's NANDImporter layout.

Does not claim to be the official Dolphin GUI importer and does not export
network certificates. Refuses an existing extraction target.
"""
import json
from audit_nand import examine
from audit_sd import ROOT, PRIVATE

if __name__=='__main__':
    src=ROOT/'workspace/console-baseline/import/nand.bin'
    dest=ROOT/'workspace/extracted-system/nand-current'
    result=examine(src,[],extract_root=dest)
    (PRIVATE/'extraction-metadata.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(extracted_files=result['filesystem_files'],menu=result['system_menu'],method='Python fallback; official GUI import unverified')))
