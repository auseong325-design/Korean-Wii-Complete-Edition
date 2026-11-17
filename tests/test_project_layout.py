import json,re,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ProjectLayoutTests(unittest.TestCase):
    def test_single_instruction_file(self):
        self.assertTrue((ROOT/'AGENTS.md').is_file())
        self.assertFalse((ROOT/'CLAUDE.md').exists())

    def test_markdown_links_resolve(self):
        files=[ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'scripts/README.md',*(ROOT/'docs').rglob('*.md')]
        broken=[]
        for f in files:
            for m in re.finditer(r'\]\(([^)#:]+\.md)(#[^)]*)?\)',f.read_text(encoding='utf-8')):
                if not(f.parent/m.group(1)).exists():broken.append(f'{f.relative_to(ROOT)} -> {m.group(1)}')
        self.assertEqual(broken,[])

    def test_catalog_installs_and_docs(self):
        catalog=json.loads((ROOT/'configs/channels.catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['schema'],2)
        for channel in catalog['channels']:
            self.assertTrue(channel['installs'])
            self.assertEqual(sum(i['role']=='active'for i in channel['installs']),1,channel['id'])
            for install in channel['installs']:
                native = channel['id'] == 'dvd-player' and bool(install.get('native_package'))
                pattern = r'^wad-v\d+$' if channel['id'] == 'dvd-player' and not native else r'^(access-)?build-v\d+$'
                self.assertRegex(install['artifact'], pattern)
                if native:
                    self.assertRegex(install['native_package'], r'^kwce-rc-sd-v\d+$')
                if install.get('launch'):
                    script=ROOT/install['launch'].split()[0]
                    self.assertTrue(script.exists(),install['launch'])
                else:
                    self.assertEqual(install['role'], 'preserved')
            for key in('status_doc','run_doc'):
                if channel[key]:self.assertTrue((ROOT/channel[key]).exists(),channel[key])

    def test_pointer_calibrations(self):
        profiles=json.loads((ROOT/'configs/dolphin-ui.json').read_text(encoding='utf-8'))['profiles']
        self.assertIn('default',profiles)
        for name,c in profiles.items():
            self.assertTrue(0.5<c['ax']<2 and 0.5<c['ay']<2,name)
            # The window centre must stay reachable inside the client area.
            self.assertTrue(0<=(0.5-c['bx'])/c['ax']<=1 and 0<=(0.5-c['by'])/c['ay']<=1,name)

if __name__=='__main__':unittest.main()
