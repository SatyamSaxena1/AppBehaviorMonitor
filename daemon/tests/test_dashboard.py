"""Isolated migration, ingestion, and HTTP regression checks; no device events used."""
import json
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import threading
import unittest
from http.server import HTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch('logging.FileHandler', return_value=logging.NullHandler()):
    import collector
import dashboard


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = str(Path(self.tmp.name) / 'old.db')
        old = sqlite3.connect(path)
        old.execute('CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, pid INTEGER NOT NULL, app_id TEXT NOT NULL, exe_name TEXT NOT NULL, category TEXT NOT NULL, action TEXT NOT NULL, detail TEXT, extra_json TEXT)')
        old.commit()
        old.close()
        self.db = collector.init_db(path)
        self.lock = threading.Lock()
        with patch.object(collector, 'DB_PATH', path):
            ingest = collector.Collector()
        for name in ('', 'My Planner', ''):
            ingest._batch.append(dict(ts=1, pid=1, app='test.planner', exe='PlannerBinary', name=name,
                                     cat='network', act='data_task', detail='GET https://example.test', extra='{}'))
        ingest._flush()
        ingest.db.close()
        self.server = HTTPServer(('127.0.0.1', 0), dashboard.DashboardServer(self.db, self.lock)._make_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.db.close()
        self.tmp.cleanup()

    def get(self, path):
        with urlopen(f'http://127.0.0.1:{self.server.server_port}{path}') as response:
            self.assertEqual(response.status, 200)
            return response.read().decode()

    def test_health_distinguishes_idle_recent_and_empty(self):
        self.assertEqual(json.loads(self.get('/api/health'))['activity'], 'idle')
        with self.lock:
            self.db.execute('UPDATE events SET timestamp = ?', (time.time(),))
            self.db.commit()
        self.assertEqual(json.loads(self.get('/api/health'))['activity'], 'recent')
        with self.lock:
            self.db.execute('DELETE FROM events')
            self.db.commit()
        health = json.loads(self.get('/api/health'))
        self.assertEqual(health['activity'], 'waiting')
        self.assertIsNone(health['seconds_since_event'])
        self.assertIn('Ready when you are', self.get('/'))

    def test_offline_setup_and_live_recovery(self):
        home = self.get('/')
        self.assertNotIn('fonts.googleapis.com', home)
        self.assertNotIn('maximum-scale', home)
        self.assertIn('apple-mobile-web-app-capable', home)
        self.assertIn('Collector online', home)
        self.assertIn('Add to Home Screen', self.get('/help'))
        live = self.get('/live')
        self.assertIn('AbortController', live)
        self.assertIn('visibilitychange', live)
        self.assertIn('Connection lost', live)
        self.assertNotIn('setInterval', live)

    def test_technical_details_escape_app_controlled_content(self):
        with self.lock:
            self.db.execute("UPDATE events SET detail = '<script>bad()</script>'")
            self.db.commit()
        page = self.get('/category/network')
        self.assertIn('Technical details', page)
        self.assertNotIn('<script>bad()</script>', page)
        self.assertIn('&lt;script&gt;', page)

    def test_native_download_available_and_missing(self):
        package = Path(self.tmp.name) / 'PrivacyMonitor-App.deb'
        with patch.object(dashboard, 'APP_PACKAGE', package):
            with self.assertRaises(HTTPError) as error:
                self.get('/download/app')
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
            package.write_bytes(b'!<arch>\nfixture')
            with urlopen(f'http://127.0.0.1:{self.server.server_port}/download/app') as response:
                self.assertEqual(response.headers['Content-Type'], 'application/vnd.debian.binary-package')
                self.assertIn('PrivacyMonitor-App.deb', response.headers['Content-Disposition'])
                self.assertEqual(response.read(), package.read_bytes())

    def test_migration_and_ingestion(self):
        self.assertIn('display_name', [row[1] for row in self.db.execute('PRAGMA table_info(events)')])
        self.assertEqual(self.db.execute("SELECT display_name FROM events WHERE display_name != ''").fetchone()[0], 'My Planner')

    def test_app_names_and_counts_survive_blank_latest_event(self):
        apps = json.loads(self.get('/api/apps'))
        self.assertEqual(apps[0]['display_name'], 'My Planner')
        self.assertEqual(apps[0]['event_count'], 3)
        self.assertIn('My Planner', self.get('/'))
        self.assertIn('My Planner', self.get('/app/test.planner'))

    def test_search_name_friendly_action_and_no_match(self):
        self.assertIn('1 results', self.get('/search?q=My%20Planner'))
        self.assertIn('3 results', self.get('/search?q=Sent%20a%20request'))
        self.assertIn('0 results', self.get('/search?q=no-such-value'))

    def test_routes_filters_and_live_name_propagation(self):
        for path in ('/app/test.planner?cat=network', '/category/network', '/api/stats', '/live'):
            self.get(path)
        events = json.loads(self.get('/api/events?cat=network&app=test.planner'))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[1]['display_name'], 'My Planner')
        self.assertEqual(json.loads(self.get('/api/events?cat=clipboard')), [])
        live = self.get('/live')
        self.assertIn('e.display_name', live)
        self.assertIn('escapeHTML(detail)', live)


if __name__ == '__main__':
    unittest.main()
