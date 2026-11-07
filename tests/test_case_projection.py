import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from api_test.case_projection import CaseProjectionCache, read_case_url
from api_test.services import studio


class CaseProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.root = self.temp / 'case'
        self.group = self.root / 'tag' / 'api'
        self.group.mkdir(parents=True)
        self.ref = 'tag/api/file.json'
        self.path = self.root / self.ref
        self.cache = CaseProjectionCache(max_entries=1)
        self.clock = self.enterContext(patch('api_test.case_projection.time_ns', side_effect=lambda: time.time_ns() + 3_000_000_000))

    def write(self, path, url):
        path.write_text(json.dumps({'request': {'url': url}}), encoding='utf-8')

    def urls(self, refs, read=read_case_url):
        return self.cache.summaries(self.root, refs, studio.safe_file, read)

    def test_freshness_for_replacement_invalid_missing_and_long_urls(self):
        self.write(self.path, '/old')
        self.assertEqual(self.urls([self.ref])[self.ref], {'url': '/old'})
        replacement = self.path.with_suffix('.new')
        self.write(replacement, '/new')
        os.replace(replacement, self.path)
        self.assertEqual(self.urls([self.ref])[self.ref], {'url': '/new'})
        for url in ('/' + 'x' * 4096, '/items?access_%74oken=PRIVATE', 'https://u:p@example.test/a', '/page#private'):
            with self.subTest(url_kind=url[:12]):
                self.write(self.path, url)
                reader = Mock(side_effect=read_case_url)
                for _ in range(2):
                    self.assertEqual(self.urls([self.ref], reader)[self.ref]['url'], url)
                self.assertEqual(reader.call_count, 2)
        self.path.write_text('{', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            self.urls([self.ref])
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.urls([self.ref])

    def test_fresh_file_is_reread_until_its_change_timestamp_is_stable(self):
        self.write(self.path, '/first')
        self.clock.side_effect = None
        self.clock.return_value = self.path.stat().st_ctime_ns
        reader = Mock(side_effect=read_case_url)
        for _ in range(2):
            self.assertEqual(self.urls([self.ref], reader)[self.ref]['url'], '/first')
        self.assertEqual(reader.call_count, 2)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink and fingerprint reuse')
    def test_warm_leaf_and_directory_cannot_be_redirected_outside_scope(self):
        self.write(self.path, '/safe')
        self.urls([self.ref])
        outside = self.temp / 'outside.json'
        self.write(outside, '/private')
        self.path.unlink()
        self.path.symlink_to(outside)
        with self.assertRaises(studio.ApiError):
            self.urls([self.ref])
        self.path.unlink()
        self.write(self.path, '/safe')
        self.urls([self.ref])
        moved = self.temp / 'moved'
        self.group.rename(moved)
        self.group.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(studio.ApiError):
            self.urls([self.ref])

    @unittest.skipUnless(os.name == 'posix', 'POSIX fingerprint reuse')
    def test_eviction_and_late_reader_do_not_reintroduce_old_metadata(self):
        self.write(self.path, '/old')
        entered, resume = threading.Event(), threading.Event()

        def old_reader(source):
            url = read_case_url(source)
            entered.set()
            self.assertTrue(resume.wait(3))
            return url

        with ThreadPoolExecutor(1) as pool:
            old = pool.submit(self.urls, [self.ref], old_reader)
            try:
                self.assertTrue(entered.wait(2))
                replacement = self.path.with_suffix('.new')
                self.write(replacement, '/new')
                replacement.replace(self.path)
                self.assertEqual(self.urls([self.ref])[self.ref]['url'], '/new')
            finally:
                resume.set()
            self.assertEqual(old.result()[self.ref]['url'], '/old')
        self.assertEqual(self.urls([self.ref])[self.ref]['url'], '/new')
        second = 'tag/api/second.json'
        self.write(self.root / second, '/other')
        self.urls([second])
        reader = Mock(side_effect=read_case_url)
        self.urls([self.ref], reader)
        self.urls([self.ref], reader)
        self.assertEqual(reader.call_count, 1)
