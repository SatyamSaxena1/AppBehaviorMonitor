"""Isolated migration, ingestion, and HTTP regression checks; no device events used."""
import json
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from urllib.request import urlopen
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
