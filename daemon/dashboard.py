"""
AppBehaviorMonitor — Web Dashboard
Serves on 127.0.0.1:8800. Pure Python, no dependencies.
"""

import html
import json
import sqlite3
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class DashboardServer:
    def __init__(self, db: sqlite3.Connection, db_lock: threading.Lock, port: int = 8800):
        self.db = db
        self.db_lock = db_lock
        self.port = port

    def serve(self):
        import socket as _socket

        class ReuseHTTPServer(HTTPServer):
            allow_reuse_address = True
            allow_reuse_port = True

        server = ReuseHTTPServer(("127.0.0.1", self.port), self._make_handler())
        server.serve_forever()

    def _make_handler(self):
        db = self.db
        db_lock = self.db_lock

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Suppress access logs

            def _query(self, sql, params=()):
                with db_lock:
                    db.row_factory = sqlite3.Row
                    cur = db.execute(sql, params)
                    return [dict(r) for r in cur.fetchall()]

            def _html(self, title, body):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(PAGE_TEMPLATE.format(title=esc(title), body=body).encode())

            def _json_resp(self, data):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                qs = parse_qs(parsed.query)

                try:
                    if path == "/":
                        self._serve_index()
                    elif path.startswith("/app/"):
                        app_id = path[5:]
                        page = int(qs.get("page", ["1"])[0])
                        cat_filter = qs.get("cat", [None])[0]
                        self._serve_app(app_id, page, cat_filter)
                    elif path.startswith("/category/"):
                        cat = path[10:]
                        page = int(qs.get("page", ["1"])[0])
                        self._serve_category(cat, page)
                    elif path == "/live":
                        self._serve_live()
                    elif path == "/search":
                        q = qs.get("q", [""])[0]
                        self._serve_search(q)
                    elif path == "/api/events":
                        limit = int(qs.get("limit", ["100"])[0])
                        offset = int(qs.get("offset", ["0"])[0])
                        cat = qs.get("cat", [None])[0]
                        app = qs.get("app", [None])[0]
                        self._api_events(limit, offset, cat, app)
                    elif path == "/api/apps":
                        self._api_apps()
                    elif path == "/api/stats":
                        self._api_stats()
                    else:
                        self.send_error(404)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode())

            # ── Pages ──

            def _serve_index(self):
                apps = self._query(
                    "SELECT app_id, COUNT(*) as cnt, MAX(timestamp) as last_seen "
                    "FROM events GROUP BY app_id ORDER BY cnt DESC LIMIT 20"
                )
                cats = self._query(
                    "SELECT category, COUNT(*) as cnt FROM events GROUP BY category ORDER BY cnt DESC"
                )
                total = self._query("SELECT COUNT(*) as c FROM events")[0]["c"]
                recent = self._query(
                    "SELECT * FROM events ORDER BY id DESC LIMIT 10"
                )

                body = f'<h2>Overview</h2><p>Total events: <b>{total:,}</b></p>'
                body += '<div class="grid">'

                # Top apps
                body += '<div class="card"><h3>Top Apps</h3><table><tr><th>App</th><th>Events</th><th>Last Seen</th></tr>'
                for a in apps:
                    ts = time.strftime("%H:%M:%S", time.localtime(a["last_seen"]))
                    body += f'<tr><td><a href="/app/{esc(a["app_id"])}">{esc(a["app_id"])}</a></td><td>{a["cnt"]:,}</td><td>{ts}</td></tr>'
                body += '</table></div>'

                # Categories
                body += '<div class="card"><h3>Categories</h3><table><tr><th>Category</th><th>Events</th></tr>'
                for c in cats:
                    body += f'<tr><td><a href="/category/{esc(c["category"])}">{esc(c["category"])}</a></td><td>{c["cnt"]:,}</td></tr>'
                body += '</table></div>'
                body += '</div>'

                # Recent
                body += '<h3>Recent Events</h3>'
                body += events_table(recent)

                self._html("AppMon Dashboard", body)

            def _serve_app(self, app_id, page=1, cat_filter=None):
                per_page = 500
                offset = (page - 1) * per_page
                params = [app_id]
                where = "app_id = ?"
                if cat_filter:
                    where += " AND category = ?"
                    params.append(cat_filter)

                events = self._query(
                    f"SELECT * FROM events WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                    params + [per_page, offset],
                )
                total = self._query(f"SELECT COUNT(*) as c FROM events WHERE {where}", params)[0]["c"]
                cats = self._query(
                    "SELECT DISTINCT category FROM events WHERE app_id = ?", (app_id,)
                )

                body = f'<h2>{esc(app_id)}</h2><p>{total:,} events</p>'
                body += '<div class="filters">Filter: <a href="/app/' + esc(app_id) + '">all</a> '
                for c in cats:
                    cn = c["category"]
                    active = " class='active'" if cn == cat_filter else ""
                    body += f'<a href="/app/{esc(app_id)}?cat={esc(cn)}"{active}>{esc(cn)}</a> '
                body += '</div>'
                body += events_table(events)
                body += pagination(f"/app/{app_id}" + (f"?cat={cat_filter}&" if cat_filter else "?"), page, total, per_page)
                self._html(f"App: {app_id}", body)

            def _serve_category(self, cat, page=1):
                per_page = 500
                offset = (page - 1) * per_page
                events = self._query(
                    "SELECT * FROM events WHERE category = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (cat, per_page, offset),
                )
                total = self._query("SELECT COUNT(*) as c FROM events WHERE category = ?", (cat,))[0]["c"]

                body = f'<h2>Category: {esc(cat)}</h2><p>{total:,} events</p>'
                body += events_table(events)
                body += pagination(f"/category/{cat}?", page, total, per_page)
                self._html(f"Category: {cat}", body)

            def _serve_live(self):
                body = '<h2>Live Feed</h2><div id="live"></div>'
                body += '''<script>
                function refresh() {
                    fetch("/api/events?limit=50")
                        .then(r => r.json())
                        .then(data => {
                            let h = "<table><tr><th>Time</th><th>App</th><th>Cat</th><th>Action</th><th>Detail</th></tr>";
                            data.forEach(e => {
                                let t = new Date(e.timestamp * 1000).toLocaleTimeString();
                                let d = (e.detail || "").substring(0, 120);
                                h += `<tr><td>${t}</td><td><a href="/app/${e.app_id}">${e.app_id}</a></td>`;
                                h += `<td><a href="/category/${e.category}">${e.category}</a></td>`;
                                h += `<td>${e.action}</td><td class="detail">${d}</td></tr>`;
                            });
                            h += "</table>";
                            document.getElementById("live").innerHTML = h;
                        });
                }
                refresh();
                setInterval(refresh, 3000);
                </script>'''
                self._html("Live Feed", body)

            def _serve_search(self, q):
                results = []
                if q:
                    results = self._query(
                        "SELECT * FROM events WHERE detail LIKE ? ORDER BY id DESC LIMIT 200",
                        (f"%{q}%",),
                    )
                body = f'<h2>Search</h2>'
                body += f'<form method="get" action="/search"><input name="q" value="{esc(q)}" placeholder="Search details..." style="width:300px;padding:8px;background:#333;color:#eee;border:1px solid #555;border-radius:4px"> '
                body += '<button type="submit" style="padding:8px 16px;background:#4a9eff;color:#fff;border:none;border-radius:4px;cursor:pointer">Search</button></form>'
                if q:
                    body += f'<p>{len(results)} results for "{esc(q)}"</p>'
                    body += events_table(results)
                self._html("Search", body)

            # ── JSON API ──

            def _api_events(self, limit, offset, cat, app):
                limit = min(limit, 1000)
                where_parts = []
                params = []
                if cat:
                    where_parts.append("category = ?")
                    params.append(cat)
                if app:
                    where_parts.append("app_id = ?")
                    params.append(app)
                where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
                rows = self._query(
                    f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                    params + [limit, offset],
                )
                self._json_resp(rows)

            def _api_apps(self):
                rows = self._query(
                    "SELECT app_id, COUNT(*) as event_count, MAX(timestamp) as last_seen "
                    "FROM events GROUP BY app_id ORDER BY event_count DESC"
                )
                self._json_resp(rows)

            def _api_stats(self):
                total = self._query("SELECT COUNT(*) as c FROM events")[0]["c"]
                cats = self._query("SELECT category, COUNT(*) as c FROM events GROUP BY category")
                apps = self._query("SELECT COUNT(DISTINCT app_id) as c FROM events")[0]["c"]
                self._json_resp({"total_events": total, "unique_apps": apps, "categories": cats})

        return Handler


def esc(s):
    return html.escape(str(s)) if s else ""


def events_table(events):
    if not events:
        return "<p>No events.</p>"
    h = '<table><tr><th>Time</th><th>PID</th><th>App</th><th>Cat</th><th>Action</th><th>Detail</th></tr>'
    for e in events:
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime(e["timestamp"]))
        detail = esc((e.get("detail") or "")[:120])
        h += (
            f'<tr><td>{ts}</td><td>{e["pid"]}</td>'
            f'<td><a href="/app/{esc(e["app_id"])}">{esc(e["app_id"])}</a></td>'
            f'<td><a href="/category/{esc(e["category"])}">{esc(e["category"])}</a></td>'
            f'<td>{esc(e["action"])}</td><td class="detail">{detail}</td></tr>'
        )
    h += "</table>"
    return h


def pagination(base_url, page, total, per_page):
    pages = max(1, (total + per_page - 1) // per_page)
    if pages <= 1:
        return ""
    h = '<div class="pagination">'
    if page > 1:
        h += f'<a href="{base_url}page={page - 1}">&laquo; Prev</a> '
    h += f'Page {page}/{pages} '
    if page < pages:
        h += f'<a href="{base_url}page={page + 1}">Next &raquo;</a>'
    h += "</div>"
    return h


PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:12px;font-size:14px}}
a{{color:#4a9eff;text-decoration:none}}
a:hover{{text-decoration:underline}}
h2{{color:#fff;margin:12px 0 8px}}
h3{{color:#ccc;margin:10px 0 6px}}
p{{margin:4px 0 8px}}
nav{{background:#16213e;padding:10px 16px;margin:-12px -12px 12px;display:flex;gap:16px;flex-wrap:wrap;align-items:center}}
nav a{{color:#8ab4f8;font-weight:500}}
nav .brand{{color:#fff;font-weight:700;font-size:16px}}
table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}}
th,td{{padding:6px 8px;text-align:left;border-bottom:1px solid #2a2a4a}}
th{{background:#16213e;color:#8ab4f8;position:sticky;top:0}}
tr:hover{{background:#16213e44}}
.detail{{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;font-family:monospace;font-size:12px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:600px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:#16213e;border-radius:8px;padding:12px}}
.filters a{{display:inline-block;padding:4px 10px;margin:2px;background:#2a2a4a;border-radius:12px;font-size:12px}}
.filters a.active{{background:#4a9eff;color:#fff}}
.pagination{{margin:12px 0;text-align:center}}
.pagination a{{padding:6px 12px;background:#2a2a4a;border-radius:4px;margin:0 4px}}
</style></head><body>
<nav>
<span class="brand">AppMon</span>
<a href="/">Overview</a>
<a href="/live">Live</a>
<a href="/search">Search</a>
<a href="/api/stats">API</a>
</nav>
{body}
</body></html>"""
