"""Validated local AI insights. No event mutation and no arbitrary SQL surface."""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import time
from urllib.parse import urlsplit

SCHEMA = '''CREATE TABLE IF NOT EXISTS ai_insights (
 id TEXT PRIMARY KEY, created_at REAL NOT NULL, period_start REAL NOT NULL, period_end REAL NOT NULL,
 app_id TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, summary TEXT NOT NULL,
 observations_json TEXT NOT NULL, interpretation TEXT NOT NULL, recommendations_json TEXT NOT NULL,
 limitations TEXT NOT NULL, confidence TEXT NOT NULL, priority TEXT NOT NULL,
 author TEXT NOT NULL, evidence_json TEXT NOT NULL, content_hash TEXT NOT NULL
); CREATE INDEX IF NOT EXISTS idx_ai_insights_created ON ai_insights(created_at);'''

PROPERTIES = {
 'analysis_id': {'type':'string','minLength':1,'maxLength':80},
 'title': {'type':'string','minLength':1,'maxLength':120},
 'summary': {'type':'string','minLength':1,'maxLength':1200},
 'observations': {'type':'array','minItems':1,'maxItems':10,'items':{'type':'string','minLength':1,'maxLength':500}},
 'interpretation': {'type':'string','minLength':1,'maxLength':2000},
 'recommendations': {'type':'array','minItems':1,'maxItems':8,'items':{'type':'string','minLength':1,'maxLength':400}},
 'limitations': {'type':'string','minLength':1,'maxLength':1200},
 'confidence': {'type':'string','enum':['low','medium','high']},
 'priority': {'type':'string','enum':['context','review']},
 'author': {'type':'string','minLength':1,'maxLength':80},
 'evidence_ids': {'type':'array','minItems':1,'maxItems':100,'uniqueItems':True,'items':{'type':'integer','minimum':1,'maximum':2147483647}},
 'hours': {'type':'integer','minimum':1,'maximum':168,'default':24},
 'app_id': {'type':'string','maxLength':256}
}
REQUIRED = [key for key in PROPERTIES if key not in ('app_id','hours')]

def validate(value, schema, path='arguments'):
    kind=schema.get('type')
    if kind=='object':
        if not isinstance(value,dict):raise ValueError(path+' must be an object')
        if set(value)-set(schema['properties']):raise ValueError('Unsupported argument')
        for key in schema.get('required',[]):
            if key not in value:raise ValueError('Missing '+key)
        for key,item in value.items():validate(item,schema['properties'][key],key)
    elif kind=='integer':
        if type(value) is not int or value<schema.get('minimum',-2**63) or value>schema.get('maximum',2**63):raise ValueError('Invalid '+path)
    elif kind=='string':
        if not isinstance(value,str) or len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',100000):raise ValueError('Invalid '+path)
        if schema.get('minLength',0) and not value.strip():raise ValueError('Empty '+path)
        if 'enum' in schema and value not in schema['enum']:raise ValueError('Invalid '+path)
    elif kind=='array':
        if not isinstance(value,list) or not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',1000):raise ValueError('Invalid '+path)
        for item in value:validate(item,schema['items'],path)
        if schema.get('uniqueItems') and len(set(value))!=len(value):raise ValueError('Duplicate '+path)

def initialize(db):
    db.executescript(SCHEMA)

def list_insights(db, limit=50):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_insights'").fetchone():return []
    rows=db.execute('SELECT id,created_at,period_start,period_end,app_id,title,summary,observations_json,interpretation,recommendations_json,limitations,confidence,priority,author,evidence_json FROM ai_insights WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?', (time.time()-7*86400,min(100,max(1,limit)))).fetchall()
    names=['id','created_at','period_start','period_end','app_id','title','summary','observations','interpretation','recommendations','limitations','confidence','priority','author','evidence']
    result=[]
    for row in rows:
        item=dict(zip(names,row))
        for key in ['observations','recommendations','evidence']:item[key]=json.loads(item[key])
        result.append(item)
    return result

def publish(database,args):
    validate(args,{'type':'object','properties':PROPERTIES,'required':REQUIRED})
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',args['analysis_id']):raise ValueError('Invalid analysis_id')
    digest=hashlib.sha256(json.dumps(args,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=rw',uri=True,timeout=5)) as db:
        initialize(db)
        now=time.time();start=now-args.get('hours',24)*3600
        with db:
            existing=db.execute('SELECT content_hash FROM ai_insights WHERE id=?',(args['analysis_id'],)).fetchone()
            if existing:
                if existing[0]!=digest:raise ValueError('analysis_id already exists with different content')
                return {'id':args['analysis_id'],'saved':True,'already_saved':True}
            placeholders=','.join('?' for _ in args['evidence_ids'])
            rows=db.execute('SELECT id,timestamp,app_id,exe_name,display_name,category,action,extra_json FROM events WHERE id IN ('+placeholders+')',args['evidence_ids']).fetchall()
            if len(rows)!=len(args['evidence_ids']):raise ValueError('Some evidence events are missing or have expired')
            evidence=[]
            for row in rows:
                if not start<=row[1]<=now+5:raise ValueError('Evidence falls outside the analysis window')
                if args.get('app_id') and row[2]!=args['app_id']:raise ValueError('Evidence belongs to a different app')
                item=dict(zip(['id','timestamp','app_id','exe_name','display_name','category','action'],row[:7]))
                if row[5]=='network':
                    try:
                        extra=json.loads(row[7] or '{}');raw=extra.get('host','')
                        host=urlsplit('//'+raw).hostname if isinstance(raw,str) and len(raw)<512 else None
                        if host and all(c.isalnum() or c in '.-:' for c in host):item['domain']=host
                    except (ValueError,TypeError,AttributeError):pass
                evidence.append(item)
            db.execute('INSERT INTO ai_insights VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
                args['analysis_id'],now,start,now,args.get('app_id',''),args['title'],args['summary'],
                json.dumps(args['observations'],ensure_ascii=False),args['interpretation'],json.dumps(args['recommendations'],ensure_ascii=False),
                args['limitations'],args['confidence'],args['priority'],args['author'],json.dumps(evidence,ensure_ascii=False),digest))
        return {'id':args['analysis_id'],'saved':True,'already_saved':False,'evidence_count':len(evidence)}
