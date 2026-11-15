"""Deterministic summaries over recorded events. Counts are observations, not risk scores."""
import time

CATEGORIES = {
    'network': ('Connections', 'network'), 'file': ('Files', 'folder.fill'),
    'keychain': ('Credentials', 'key.fill'), 'clipboard': ('Clipboard', 'doc.on.clipboard'),
    'location': ('Location', 'location.fill'), 'camera': ('Camera', 'camera.fill'),
    'mic': ('Microphone', 'mic.fill'), 'tracking': ('Identifiers', 'person.crop.square'),
}
RULES = [
    ('clipboard_reads', 'Clipboard reads', 'doc.on.clipboard', 'clipboard', ('get_string',)),
    ('capture_starts', 'Capture starts', 'camera.fill', None, ('capture_start',)),
    ('location_starts', 'Location starts', 'location.fill', 'location', ('start_updating', 'start_significant')),
    ('ad_identifiers', 'Ad ID requests', 'person.crop.square', 'tracking', ('advertisingIdentifier',)),
]

def summarize(db, hours=24, app_id=None, now=None):
    if hours not in (1, 24, 168):
        raise ValueError('Choose 1, 24, or 168 hours')
    now = time.time() if now is None else now
    start = now - hours * 3600
    where = "timestamp >= ? AND timestamp <= ? AND app_id != 'com.appmon.native'"
    params = [start, now]
    if app_id:
        if not isinstance(app_id, str) or len(app_id) > 255:
            raise ValueError('Invalid app')
        where += ' AND app_id = ?'
        params.append(app_id)
    rows = db.execute('SELECT app_id,category,action,COUNT(*),MAX(timestamp) FROM events WHERE '+where+' GROUP BY app_id,category,action', params).fetchall()
    apps = {}; categories = {}; rule_counts = {r[0]: 0 for r in RULES}; total = 0; latest = None
    for app, cat, action, count, last in rows:
        total += count; latest = max(latest or last, last)
        categories[cat] = categories.get(cat, 0) + count
        entry = apps.setdefault(app, dict(app_id=app, count=0, latest_event=last, categories={}, signals={r[0]:0 for r in RULES}))
        entry['count'] += count; entry['latest_event'] = max(entry['latest_event'], last)
        entry['categories'][cat] = entry['categories'].get(cat, 0) + count
        for key, title, symbol, category, actions in RULES:
            if action in actions and (cat == category if category else cat in ('camera','mic')):
                rule_counts[key] += count; entry['signals'][key] += count
    # Latest nonempty name within the selected window, without returning raw event details.
    for app, entry in apps.items():
        named = db.execute("SELECT display_name,exe_name FROM events WHERE "+where+" AND app_id = ? ORDER BY (display_name IS NOT NULL AND display_name != '') DESC, timestamp DESC,id DESC LIMIT 1", params+[app]).fetchone()
        entry['name'] = (named[0] or named[1] or app) if named else app
    def cats(values):
        return [dict(id=k, title=CATEGORIES.get(k, ('Other','circle.grid.2x2'))[0], symbol=CATEGORIES.get(k, ('Other','circle.grid.2x2'))[1], count=v) for k,v in sorted(values.items(), key=lambda x:(-x[1],x[0]))]
    app_list = sorted(apps.values(), key=lambda a:(-a['count'],a['app_id']))
    for entry in app_list:
        entry['categories'] = cats(entry['categories'])
    # Fixed UTC-duration buckets; client formats the timestamps in its local timezone.
    step = 3600 if hours in (1,24) else 86400
    buckets = 1 if hours == 1 else 24 if hours == 24 else 7
    history = [dict(start=start+i*step, end=start+(i+1)*step, count=0) for i in range(buckets)]
    for bucket, count in db.execute('SELECT CAST((timestamp - ?) / ? AS INTEGER),COUNT(*) FROM events WHERE '+where+' GROUP BY 1', [start,step]+params):
        history[min(buckets-1,max(0,bucket))]['count'] += count
    all_where = "app_id != 'com.appmon.native'" + (' AND app_id = ?' if app_id else '')
    last = db.execute('SELECT MAX(timestamp) FROM events WHERE '+all_where, [app_id] if app_id else []).fetchone()[0]
    return dict(generated_at=now, period_start=start, period_end=now, hours=hours,
                total=total, app_count=len(app_list), latest_event=last, categories=cats(categories),
                apps=app_list, history=history,
                signals=[dict(id=k,title=t,symbol=s,count=rule_counts[k]) for k,t,s,_,_ in RULES],
                rules_version=1, excludes_monitor=True)
