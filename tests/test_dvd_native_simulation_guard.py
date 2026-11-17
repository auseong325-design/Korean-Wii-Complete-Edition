"""Prevent emulator-only forced drive states from reaching an installation."""
import unittest
from pathlib import Path
from kwce.dvd_native_hardware import entry
ROOT=Path(__file__).resolve().parents[1]
class SimulationGuardTests(unittest.TestCase):
 def test_simulated_drive_hook_is_never_packaged(self):
  manifest=ROOT/'workspace/experiments/dvd-native-hook-v26/manifest.json'
  if not manifest.exists():self.skipTest('local diagnostic fixture absent')
  with self.assertRaisesRegex(ValueError,'Diagnostic drive simulation'):
   entry(b'',{'hook':'dvd-native-hook-v26'})

 def test_new_simulated_drive_hook_is_never_packaged(self):
  manifest=ROOT/'workspace/experiments/dvd-native-hook-v33/manifest.json'
  if not manifest.exists():self.skipTest('local diagnostic fixture absent')
  with self.assertRaisesRegex(ValueError,'Diagnostic drive simulation'):
   entry(b'',{'hook':'dvd-native-hook-v33'})

 def test_retained_disc_simulation_is_never_packaged(self):
  manifest=ROOT/'workspace/experiments/dvd-native-hook-v35/manifest.json'
  if not manifest.exists():self.skipTest('local diagnostic fixture absent')
  with self.assertRaisesRegex(ValueError,'Diagnostic drive simulation'):
   entry(b'',{'hook':'dvd-native-hook-v35'})

 def test_frame_comparison_simulations_are_never_packaged(self):
  for revision in (37,39,40):
   manifest=ROOT/f'workspace/experiments/dvd-native-hook-v{revision}/manifest.json'
   if not manifest.exists():self.skipTest('local diagnostic fixture absent')
   with self.subTest(revision=revision),self.assertRaisesRegex(ValueError,'Diagnostic drive simulation'):
    entry(b'',{'hook':f'dvd-native-hook-v{revision}'})
