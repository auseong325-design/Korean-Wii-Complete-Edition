import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from summarize_nintendo_wc24_report import summarize


class NintendoReportTest(unittest.TestCase):
    def test_only_numeric_nintendo_fields_are_exposed(self):
        report = '''KWCE_RC_WC24_REPORT_V1
wc24_enabled=1
id_creation_stage=2 (registered)
tasks_used=3
tasks_free=117
mail_domain=private.example
task_0_channel=news
task_0_error_code=99
task_1_channel=nintendo
task_1_flags=32
task_1_remaining_downloads=1
task_1_error_count=4
task_1_retry_minutes=10
task_1_error_code=-5
task_1_subtask_mask=0
private_key=do-not-print
'''
        out = summarize(report)
        self.assertEqual(out['nintendo_tasks'][0]['error_code'], -5)
        self.assertEqual(out['id_creation_stage'], 2)
        self.assertEqual(len(out['nintendo_tasks']), 1)
        self.assertNotIn('private', json.dumps(out))
        self.assertNotIn('99', json.dumps(out))

    def test_rejects_nonreport_and_malformed_numeric_fields(self):
        with self.assertRaises(ValueError):
            summarize('not a report')
        with self.assertRaises(ValueError):
            summarize('KWCE_RC_WC24_REPORT_V1\nwc24_enabled=1 secret')
        with self.assertRaises(ValueError):
            summarize('KWCE_RC_WC24_REPORT_V1\nwc24_enabled=1\nwc24_enabled=2')


if __name__ == '__main__':
    unittest.main()
