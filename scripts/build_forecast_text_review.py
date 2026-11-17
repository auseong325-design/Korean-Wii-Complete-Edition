"""Transplant one original-style textbox into a native error presenter.

Coordinates, font table, font size, wrapping, color and text are copied
unchanged from the selected translated pane. Only its lookup name changes
to the currently displayed error0 pane. No executable or NAND fault changes.
"""
import argparse,json,sys,struct
from pathlib import Path
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox,rebuild_layout,compress_lz10
from kwce.forecast_text_review import CASES


def main():
    ap=argparse.ArgumentParser();ap.add_argument('case',type=int,choices=range(len(CASES)));ap.add_argument('--current-style',action='store_true');args=ap.parse_args()
    source_revision=61 if args.current_style else 30
    revision=(62 if args.current_style else 39)+args.case;source=ROOT/f'workspace/channels/forecast/build-v{source_revision}';out=ROOT/f'workspace/channels/forecast/build-v{revision}'
    if out.exists():raise SystemExit('Existing text-style diagnostic preserved')
    meta=json.loads((source/'build-manifest.json').read_text(encoding='utf-8'));wad=source/'forecast-ko-personal-test.wad'
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Source identity differs')
    lib=load_library();from libWiiPy.archive import decompress_lz77
    title=lib.title.Title();title.load_wad(wad.read_bytes());original=title.get_content_by_index(9)
    archive=ChannelArchive(original);layouts=ChannelArchive(decompress_lz77(archive.get('weather_layout.arc.LZ')))
    stem,pane=CASES[args.case];target_path=next(n for n in layouts.files if Path(n).stem=='error0')
    source_path=next(n for n in layouts.files if Path(n).stem==stem)
    target_data=layouts.get(target_path);target_sections=layout_sections(target_data);source_sections=layout_sections(layouts.get(source_path))
    if [s for s in source_sections if s[:4]==b'fnl1']!=[s for s in target_sections if s[:4]==b'fnl1']:
        raise ValueError('Native font table differs')
    selected=next(s for s in source_sections if textbox(s)and textbox(s)[0]==pane)
    replacement=bytearray(selected);replacement[12:28]=b'textTUS5'+bytes(8)
    if args.current_style:
        def materials(section):
            count=struct.unpack_from('>H',section,8)[0]
            if count>1000 or 12+4*count>len(section):raise ValueError('Material table bounds')
            offsets=list(struct.unpack_from('>'+str(count)+'I',section,12))+[len(section)]
            if offsets[0]<12+4*count or offsets!=sorted(set(offsets)):raise ValueError('Material offsets')
            return [section[offsets[i]:offsets[i+1]]for i in range(count)]
        source_mat=next(s for s in source_sections if s[:4]==b'mat1')
        source_records=materials(source_mat);index=struct.unpack_from('>H',selected,80)[0]
        chosen=source_records[index]
        # Font materials have no static texture-map references to remap.
        if len(chosen)<64 or struct.unpack_from('>I',chosen,60)[0]&15:
            raise ValueError('Font material has static texture references')
        at=next(i for i,s in enumerate(target_sections)if s[:4]==b'mat1')
        records=materials(target_sections[at]);new_index=len(records);records.append(chosen)
        head=bytearray(12+4*len(records));head[:4]=b'mat1';struct.pack_into('>H',head,8,len(records));body=bytearray()
        for i,record in enumerate(records):
            struct.pack_into('>I',head,12+4*i,len(head)+len(body));body.extend(record)
        material= head+body;struct.pack_into('>I',material,4,len(material));target_sections[at]=bytes(material)
        struct.pack_into('>H',replacement,80,new_index)
    matched=0
    for i,s in enumerate(target_sections):
        if textbox(s)and textbox(s)[0]=='textTUS5':target_sections[i]=bytes(replacement);matched+=1
    if matched!=1:raise ValueError('Native target identity differs')
    layouts=ChannelArchive(layouts.replace(target_path,rebuild_layout(target_data,target_sections)))
    archive=ChannelArchive(archive.replace('weather_layout.arc.LZ',compress_lz10(layouts.compact())))
    title.set_content(archive.compact(),9);out.mkdir();(out/'forecast-ko-personal-test.wad').write_bytes(title.dump_wad())
    meta.update(revision=revision,wad_sha256=sha256(out/'forecast-ko-personal-test.wad'),visual_diagnostic_only=True,
        source_build=source_revision,review_case=f'{stem}/{pane}',native_text_style_preserved=True,native_material_preserved=args.current_style,actual_NAND_fault=False,
        incomplete=['Text-style visual diagnostic, not a release build'],full_localization_complete=False)
    (out/'build-manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Built native text-style case',args.case,stem+'/'+pane,'revision',revision)


if __name__=='__main__':main()
