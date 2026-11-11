from contextlib import closing
import importlib.util, json, sqlite3, subprocess, sys, tempfile, time, unittest
from pathlib import Path

SERVER = Path(__file__).with_name('mcp_server.py')
spec = importlib.util.spec_from_file_location('privacy_mcp', SERVER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class MCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/'events.db'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL, app_id TEXT, exe_name TEXT, display_name TEXT, category TEXT, action TEXT, detail TEXT, extra_json TEXT)')
            db.execute('INSERT INTO events VALUES (1,?,?,?,?,?,?,?,?)', (time.time(),'test.app','Test','Test','network','data_task','https://example.com/private?token=secret',json.dumps({'host':'example.com'})))
            db.execute('INSERT INTO events VALUES (2,?,?,?,?,?,?,?,?)', (time.time(),'test.app','Test','Test','clipboard','get_string','PRIVATE CLIPBOARD',None))
            db.commit()
        self.server = module.ActivityServer(self.db)
    def tearDown(self): self.tmp.cleanup()
    def test_metadata_redaction_and_domains(self):
        output=json.dumps(self.server.call('recent_activity',{}))
        self.assertNotIn('PRIVATE',output)
        self.assertNotIn('token',output)
        self.assertEqual(len(json.loads(output)['events']),2)
        domains=self.server.call('contacted_domains',{})
        self.assertEqual(domains['domains'],[{'domain':'example.com','observed_events':1}])
        self.assertFalse(domains['truncated'])
    def test_window_filters_and_argument_rejection(self):
        self.assertEqual(len(self.server.call('activity_summary',{})['groups']),2)
        self.assertEqual(len(self.server.call('recent_activity',{'category':'clipboard'})['events']),1)
        for arguments in [{'hours':169},{'limit':True},{'category':'bad'},{'sql':'DELETE FROM events'},{'hours':0}]:
            with self.assertRaises(ValueError): self.server.call('recent_activity',arguments)
    def test_missing_database_is_not_created(self):
        path=Path(self.tmp.name)/'missing.db'
        server=module.ActivityServer(path)
        result=server.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'activity_summary'}})
        self.assertTrue(result['result']['isError'])
        self.assertFalse(path.exists())
    def test_stdio_handshake_discovery_and_call(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'recent_activity','arguments':{'limit':1}}}]
        result=subprocess.run([sys.executable,str(SERVER),'--db',str(self.db)],input='\n'.join(json.dumps(r) for r in requests)+'\n',text=True,capture_output=True,check=True)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r['id'] for r in responses],[1,2,3])
        self.assertEqual(len(responses[1]['result']['tools']),3)
        self.assertFalse(responses[2]['result']['isError'])
        self.assertEqual(len(json.loads(responses[2]['result']['content'][0]['text'])['events']),1)

if __name__=='__main__': unittest.main()
