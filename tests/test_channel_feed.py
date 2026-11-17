import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from kwce.channel_feed import validate_news_tasks, normalize_news_tasks, validate_feed, NEWS_URL


class ChannelFeedTests(unittest.TestCase):
    def task_list(self):
        data = bytearray(0xf800)
        data[:8] = bytes.fromhex('5763446c00000001')
        struct.pack_into('>II', data, 2048+8, 0x00010002, 0x48414745)
        data[2048+180:2048+180+len(NEWS_URL)] = NEWS_URL
        return data

    def test_only_one_unencrypted_news_task_can_bypass_scrub(self):
        data = self.task_list()
        self.assertEqual(validate_news_tasks(data), 1)
        for offset, value in [(2048+4, 8), (2048+4, 32), (2048+12, 0x48414a45)]:
            changed = bytearray(data)
            struct.pack_into('>I', changed, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                validate_news_tasks(changed)
        changed = bytearray(data)
        changed[2560:3072] = data[2048:2560]
        with self.assertRaises(ValueError):
            validate_news_tasks(changed)

    def test_other_host_and_legacy_file_url_are_refused(self):
        for url in [b'http://unexpected.invalid/news.bin', b'file:///private/news.bin']:
            data = self.task_list()
            data[2048+180:2048+416] = url + bytes(236-len(url))
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_news_tasks(data)

    def test_menu_jobs_are_disabled_without_changing_news_or_other_metadata(self):
        data=self.task_list();at=2560
        struct.pack_into('>III',data,at+4,1,0x00010002,0x48414645)
        url=b'https://unapproved.invalid/download';data[at+180:at+416]=url+bytes(236-len(url))
        before=bytes(data);after,count=normalize_news_tasks(before)
        self.assertEqual(count,1);self.assertEqual(validate_news_tasks(after),1)
        self.assertEqual(after[2048:2560],before[2048:2560])
        self.assertEqual(after[at:at+4],before[at:at+4])
        self.assertEqual(after[at+8:at+180],before[at+8:at+180])
        self.assertEqual(after[at+416:],before[at+416:])
        self.assertEqual(int.from_bytes(after[at+4:at+8],'big'),33)
        self.assertTrue(after[at+180:at+416].startswith(b'http://127.0.0.1:9/phase0-disabled/'))
        self.assertEqual(normalize_news_tasks(after),(after,0))

    def test_normalization_does_not_repair_unapproved_news_or_duplicate_jobs(self):
        data=self.task_list();url=b'http://unapproved.invalid';data[2048+180:2048+416]=url+bytes(236-len(url))
        with self.assertRaises(ValueError):normalize_news_tasks(data)
        data=self.task_list();data[2560:3072]=data[2048:2560]
        with self.assertRaises(ValueError):normalize_news_tasks(data)

    def test_feed_requires_all_hours_and_unchanged_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for hour in range(24):
                rel = f'news.wiilink.ca/v2/1/136/news.bin.{hour:02d}'
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                data = bytes(320) + bytes([hour])*20
                p.write_bytes(data)
                rows.append(dict(path=rel, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
            manifest = root / 'feed-manifest.json'
            manifest.write_text(json.dumps(dict(channel='news', host='news.wiilink.ca', files=rows)))
            self.assertEqual(validate_feed(root), 24)
            (root / rows[0]['path']).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                validate_feed(root)
            rows[0]['path'] = '../outside.bin'
            manifest.write_text(json.dumps(dict(channel='news', host='news.wiilink.ca', files=rows)))
            with self.assertRaises(ValueError):
                validate_feed(root)


if __name__ == '__main__':
    unittest.main()
