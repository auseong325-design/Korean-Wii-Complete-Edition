"""Prepare actual local Dolphin UI captures for the manual's screenshot slots."""
import hashlib,json
from audit_sd import ROOT,PRIVATE
from kwce.channels import load_library

def main():
    load_library()
    from PIL import Image
    base=ROOT/'workspace/channels/mii-contest/work/manual-captures'
    if base.exists():raise SystemExit('Existing manual capture set preserved')
    older=PRIVATE/'evidence/mii-v10';newer=PRIVATE/'evidence/mii-v10-runtime'
    shots={3:('main-menu',newer,[288,24,522,196]),4:('plaza',older,[17,64,251,240]),
           6:('plaza-callout',older,[288,64,522,240]),7:('artisan-ranking',older,[288,24,522,196]),
           8:('mii-detail',newer,[17,26,251,202]),9:('contest-list',older,[17,84,251,260]),
           11:('judging-selection',older,[17,24,251,196])}
    path=ROOT/'configs/mii-contest-manual-images-ko.json';config=json.loads(path.read_text(encoding='utf-8'))
    backup=PRIVATE/'mii-manual-images-before-captures-v11.json'
    if backup.exists():raise SystemExit('Previous manual image configuration preserved')
    backup.write_bytes(path.read_bytes());base.mkdir(parents=True);record={}
    for page,(name,source,box)in shots.items():
        source=source/(name+'.jpg');image=Image.open(source)
        if image.size!=(642,512):raise ValueError('Capture geometry changed; review crop again')
        # Exclude native window chrome and the black aspect-ratio bars.
        image.crop((1,96,641,446)).save(base/(name+'.png'))
        spec=config['images'][f'ukv/page_{page:02}/page{page}.png'];spec['shots']=[dict(box=box,capture=name+'.png',keep_red=True)]
        record[name]=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),capture_sha256=hashlib.sha256((base/(name+'.png')).read_bytes()).hexdigest(),page=page)
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (base/'capture-manifest.json').write_text(json.dumps(dict(synthetic_local_test=True,captures=record,preserved_original_diagram_pages=[2,12],full_localization_complete=False),indent=2))
    print(f'Prepared {len(shots)} actual Korean UI captures; pages 2/12 retained for separate scene verification')

if __name__=='__main__':main()
