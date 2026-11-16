"""Smoke-test the extracted collector with isolated storage and a synthetic event."""
import json, os, socket, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import urlopen

root=Path(__file__).resolve().parents[1]
collector=root/'distribution/build/collector/var/jb/usr/libexec/privacy-monitor/collector.py'
with tempfile.TemporaryDirectory(prefix='appmon-test-',dir='/var/jb/tmp') as temp:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1',0));udp_port=probe.getsockname()[1]
    env=dict(os.environ, APPMON_DATA_DIR=temp, APPMON_PORT=str(port), APPMON_UDP_PORT=str(udp_port))
    process=subprocess.Popen([sys.executable,str(collector)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        def get(route):
            with urlopen(f'http://127.0.0.1:{port}'+route,timeout=2) as response:
                assert response.status==200
                return json.load(response)
        for _ in range(60):
            try:
                assert get('/api/health')['activity']=='waiting'
                break
            except (OSError,ValueError):time.sleep(.1)
        else:raise AssertionError('Packaged collector failed to start')
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sender:
            sender.sendto(json.dumps(dict(ts=time.time(),pid=1,app='fixture.app',exe='Fixture',name='Fixture App',cat='network',act='data_task',detail='GET https://example.test',extra='{"host":"example.test"}')).encode(),str(Path(temp)/'appmon.sock'))
        for _ in range(40):
            events=get('/api/events')
            if events:break
            time.sleep(.1)
        assert events[0]['display_name']=='Fixture App'
        assert get('/api/apps')[0]['event_count']==1
        assert get('/api/health')['activity']=='recent'
        activity=get('/api/activity?hours=24')
        assert activity['total']==1 and activity['app_count']==1
        assert activity['apps'][0]['name']=='Fixture App'
        assert sum(b['count'] for b in activity['history'])==1
        assert activity['categories'][0]['id']=='network'
        assert not collector.with_name('mcp_server.py').exists()
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
            # Bad local datagrams cannot poison the batch/flush thread.
            for invalid in [b'[]',b'{"app":{}}',b'bad-json',b'x'*4097]:sender.sendto(invalid,('127.0.0.1',udp_port))
            sender.sendto(json.dumps(dict(ts=time.time(),pid=2,app='fixture.sandbox',exe='Sandbox',name='Sandbox App',cat='monitor',act='loaded')).encode(),('127.0.0.1',udp_port))
        for _ in range(40):
            activity=get('/api/activity?hours=24')
            if any(a['app_id']=='fixture.sandbox' for a in activity['apps']):break
            time.sleep(.1)
        else:raise AssertionError('Loopback instrumentation status missing')
        assert activity['total']==1 and activity['app_count']==1
        status=next(a for a in activity['apps'] if a['app_id']=='fixture.sandbox')
        assert status['count']==0 and status['latest_event'] is None and status['engine_seen_at']
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
            sender.sendto(json.dumps(dict(ts=time.time(),pid=2,app='fixture.sandbox',exe='Sandbox',name='Sandbox App',cat='network',act='socket_connect',extra='{"host":"192.0.2.1","port":443}')).encode(),('127.0.0.1',udp_port))
        for _ in range(40):
            activity=get('/api/activity?hours=24')
            if activity['total']==2:break
            time.sleep(.1)
        else:raise AssertionError('Loopback network event missing')
        assert activity['app_count']==2 and sum(b['count'] for b in activity['history'])==2
        assert len(get('/api/events'))==2  # Status is never a fake activity event.
        print('Packaged collector: Unix + localhost UDP, malformed packets, separate engine status, exact activity/history passed.')
    finally:
        process.terminate()
        out,err=process.communicate(timeout=10)
        if process.returncode:raise AssertionError(err.decode())
    assert not (Path(temp)/'appmon.sock').exists()
    assert (Path(temp)/'appmon.db').exists()
    print('Graceful shutdown removed socket and preserved history.')
