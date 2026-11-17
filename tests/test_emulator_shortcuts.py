import copy,json,tempfile,unittest
from pathlib import Path
from kwce.emulator_shortcuts import plans,expected_files,synchronize,FOLDER


class ShortcutTests(unittest.TestCase):
    def catalog(self):
        return dict(schema=2,channels=[dict(id='forecast',display_name_ko='날씨',stage='internal-review',installs=[
            dict(role='active',profile='forecast-v2',artifact='build-v98',launch='scripts/run_forecast_test.py --offline'),
            dict(role='preserved',profile='forecast-old',artifact='build-v999',launch='Dolphin.exe')])])

    def settings(self):return dict(schema=1,system_menu_profile='gc-native-v6-user',include_installer_emulator=False)

    def test_selects_active_not_highest_version_or_preserved(self):
        entries=plans(self.catalog(),self.settings())
        self.assertEqual(entries['Channel_forecast']['artifact'],'build-v98')
        self.assertEqual(entries['Menu_forecast']['argv'],['scripts/run_forecast_test.py','--offline','--menu'])
        self.assertEqual(entries['Forecast_Refresh']['argv'],['scripts/run_forecast_test.py'])
        self.assertNotIn('02_Installer_Emulator',entries)

    def test_new_build_and_menu_are_resolved_without_versioned_bat(self):
        catalog=self.catalog();settings=self.settings();first=expected_files(plans(catalog,settings))
        catalog['channels'][0]['installs'][0]['artifact']='build-v100'
        settings['system_menu_profile']='gc-native-v7-user'
        second=expected_files(plans(catalog,settings))
        self.assertEqual(first['Channel_forecast.bat'],second['Channel_forecast.bat'])
        self.assertNotEqual(first['README.md'],second['README.md'])
        self.assertEqual(plans(catalog,settings)['01_System_Menu']['argv'][2],'gc-native-v7-user')

    def test_unsafe_or_unreviewed_commands_and_aliases_refused(self):
        for command in ['Dolphin.exe --user personal','scripts/run_forecast_test.py --offline & echo unsafe',
                        '../scripts/run_forecast_test.py --offline','scripts/deploy_to_sd.py --drive H:']:
            with self.subTest(command=command):
                catalog=self.catalog();catalog['channels'][0]['installs'][0]['launch']=command
                with self.assertRaises(ValueError):plans(catalog,self.settings())
        catalog=self.catalog();catalog['channels'][0]['id']='../forecast'
        with self.assertRaises(ValueError):plans(catalog,self.settings())
        settings=self.settings();settings['system_menu_profile']='gc-native-v5-user'
        with self.assertRaises(ValueError):plans(self.catalog(),settings)

    def test_duplicate_active_install_refused(self):
        catalog=self.catalog();catalog['channels'][0]['installs'].append(copy.deepcopy(catalog['channels'][0]['installs'][0]))
        with self.assertRaises(ValueError):plans(catalog,self.settings())

    def test_hidden_or_menuless_channel_gets_no_menu_bat(self):
        catalog=self.catalog();catalog['channels'].append(dict(id='personal-data',display_name_ko='주소 설정',stage='internal-review',installs=[
            dict(role='active',profile='personal-data-test-v1',artifact='build-v2',launch='scripts/launch_personal_data.py')]))
        entries=plans(catalog,self.settings())
        self.assertEqual(entries['Channel_personal-data']['argv'],['scripts/launch_personal_data.py'])
        self.assertNotIn('Menu_personal-data',entries)
        self.assertIn('Menu_forecast',entries)

    def test_wiispeak_bed_only_when_explicitly_enabled(self):
        self.assertNotIn('06_WiiSpeak_Test',plans(self.catalog(),self.settings()))
        settings=self.settings();settings['include_wiispeak_test']='yes'
        self.assertNotIn('06_WiiSpeak_Test',plans(self.catalog(),settings))
        settings['include_wiispeak_test']=True;entries=plans(self.catalog(),settings)
        row=entries['06_WiiSpeak_Test']
        self.assertEqual((row['profile'],row['argv']),('wiispeak-test-v1',['scripts/launch_wiispeak.py']))
        self.assertIn('06_WiiSpeak_Test.bat',expected_files(entries))

    def prepare(self,root):
        (root/'configs').mkdir()
        for name,data in [('channels.catalog.json',self.catalog()),('emulator-launchers.json',self.settings())]:
            (root/'configs'/name).write_text(json.dumps(data),encoding='utf-8')

    def test_sync_idempotent_and_check_does_not_write(self):
        with tempfile.TemporaryDirectory(prefix='kwce-shortcuts-')as name:
            root=Path(name).resolve();self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            self.prepare(root);self.assertTrue(synchronize(root));self.assertEqual(synchronize(root),[])
            path=root/FOLDER/'README.md';path.write_bytes(path.read_bytes()+b'\n')
            before=(path.read_bytes(),path.stat().st_mtime_ns)
            self.assertEqual(synchronize(root,check=True),['README.md'])
            self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns),before)
            self.assertEqual(synchronize(root),['README.md'])

    def test_user_file_collision_is_preserved_before_any_write(self):
        with tempfile.TemporaryDirectory(prefix='kwce-shortcuts-')as name:
            root=Path(name).resolve();self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            self.prepare(root);folder=root/FOLDER;folder.mkdir();path=folder/'README.md';path.write_bytes(b'user notes')
            with self.assertRaises(ValueError):synchronize(root)
            self.assertEqual(list(folder.iterdir()),[path]);self.assertEqual(path.read_bytes(),b'user notes')
