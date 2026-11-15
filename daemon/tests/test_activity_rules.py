"""Local rules: boundaries, freshness, action distinctions, and aggregate consistency."""
import sqlite3,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from activity_rules import summarize

class RulesTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.now=2_000_000
        self.db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,timestamp REAL,app_id TEXT,exe_name TEXT,display_name TEXT,category TEXT,action TEXT)')
    def tearDown(self):self.db.close()
    def event(self,age=1,app='fixture.app',cat='network',act='data_task',name='Fixture'):
        self.db.execute('INSERT INTO events(timestamp,app_id,exe_name,display_name,category,action) VALUES(?,?,?,?,?,?)',(self.now-age,app,'FixtureBinary',name,cat,act))
    def summary(self,hours=24,app=None):return summarize(self.db,hours,app,self.now)
    def test_window_and_history_match_exactly(self):
        for age in (0,3599,3600,86399,86400,86401,-1):self.event(age)
        self.event(1,app='com.appmon.native')
        result=self.summary();self.assertEqual(result['total'],5)
        self.assertEqual(sum(b['count'] for b in result['history']),5)
        self.assertEqual(self.summary(1)['total'],3)
        self.assertEqual(result['app_count'],1)
    def test_rules_distinguish_permission_and_identifier_calls(self):
        for cat,act in [('camera','request_access'),('camera','capture_start'),('mic','request_access'),('mic','capture_start'),('clipboard','set_string'),('clipboard','get_string'),('tracking','identifierForVendor'),('tracking','advertisingIdentifier'),('tracking','check_att_status'),('location','req_always'),('location','start_updating')]:self.event(cat=cat,act=act)
        counts={s['id']:s['count'] for s in self.summary()['signals']}
        self.assertEqual(counts,dict(clipboard_reads=1,capture_starts=2,location_starts=1,ad_identifiers=1))
        self.assertEqual(self.summary()['total'],11)
    def test_app_filter_names_and_stale_activity(self):
        self.event(90000,name='Old name');self.event(10,app='other.app')
        result=self.summary(app='fixture.app');self.assertEqual(result['total'],0)
        self.assertEqual(result['latest_event'],self.now-90000)
        self.event(100,name='Good name');self.event(1,name='')
        result=self.summary(app='fixture.app');self.assertEqual(result['apps'][0]['name'],'Good name')
        self.assertEqual(result['total'],2);self.assertEqual(result['latest_event'],self.now-1)
    def test_live_summary_changes_without_saved_reviews(self):
        self.assertEqual(self.summary()['total'],0)
        self.event();self.assertEqual(self.summary()['total'],1)
        self.event(1,cat='clipboard',act='get_string');self.assertEqual(self.summary()['total'],2)
    def test_seven_day_boundaries_and_consistency(self):
        for age in (0,86400,172800,604800,604801):self.event(age)
        result=self.summary(168);self.assertEqual(result['total'],4)
        self.assertEqual(sum(b['count'] for b in result['history']),4)
        self.assertEqual(len(result['history']),7)
        self.assertEqual(sum(c['count'] for c in result['categories']),4)
    def test_invalid_ranges_and_app_arguments(self):
        for hours in (0,-1,25,169):
            with self.assertRaises(ValueError):self.summary(hours)
        with self.assertRaises(ValueError):self.summary(app='a'*256)
if __name__=='__main__':unittest.main()
