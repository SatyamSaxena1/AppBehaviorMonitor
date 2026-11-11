"""
AppBehaviorMonitor — Web Dashboard
Serves on 127.0.0.1:8800. Pure Python, no dependencies.
Human-friendly privacy monitor UI.
"""

import html
from insight_store import list_insights
from pathlib import Path
import json
import re
import sqlite3
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

# ─── Human-Friendly Mappings ─────────────────────────────

APP_PACKAGE = Path(__file__).resolve().parent / "static" / "PrivacyMonitor-App.deb"

CATEGORY_INFO = {
    "network":   {"icon": "↗", "label": "Internet Access",   "color": "#4a9eff", "desc": "Connections to servers and websites"},
    "file":      {"icon": "▤", "label": "File Access",       "color": "#f5a623", "desc": "Reading, writing, or deleting your files"},
    "keychain":  {"icon": "⚿", "label": "Saved Passwords",   "color": "#e74c3c", "desc": "Access to saved passwords and keys"},
    "clipboard": {"icon": "▣", "label": "Clipboard",         "color": "#9b59b6", "desc": "Reading or writing copied text"},
    "location":  {"icon": "⌖", "label": "Location",          "color": "#2ecc71", "desc": "Access to your GPS location"},
    "camera":    {"icon": "◉", "label": "Camera",            "color": "#e67e22", "desc": "Using the camera"},
    "mic":       {"icon": "♪", "label": "Microphone",        "color": "#e74c3c", "desc": "Using the microphone"},
    "tracking":  {"icon": "◎", "label": "Tracking",          "color": "#c0392b", "desc": "Identifying you for ads or analytics"},
}

ACTION_LABELS = {
    # Network
    "data_task":      "Sent a request",
    "upload_task":    "Uploaded data",
    "download_task":  "Downloaded data",
    # File
    "read":           "Read a file",
    "write":          "Saved a file",
    "delete":         "Deleted a file",
    "copy":           "Copied a file",
    # Keychain
    "copy_matching":  "Read saved password",
    "add":            "Saved new password",
    "update":         "Updated saved password",
    # Clipboard
    "set_string":     "Copied text to clipboard",
    "get_string":     "Read from clipboard",
    "set_strings":    "Copied multiple items",
    "set_image":      "Copied an image",
    # Location
    "start_updating":    "Started tracking location",
    "start_significant": "Tracking significant location changes",
    "req_when_in_use":   "Asked for location (while using app)",
    "req_always":        "Asked for location (always)",
    # Camera / Mic
    "capture_start":  "Started recording",
    "request_access": "Asked for permission",
    # Tracking
    "identifierForVendor":    "Read device ID",
    "advertisingIdentifier":  "Read advertising ID",
    "req_att_authorization":  "Asked to track you",
    "check_att_status":       "Checked tracking permission",
}


def friendly_app_name(app_id, exe_name="", display_name=""):
    """Use real display name from the app bundle, fall back to exe or bundle ID."""
    if display_name and display_name != "" and display_name != "unknown":
        return display_name
    if exe_name and exe_name != "unknown" and exe_name != app_id:
        return exe_name
    # Strip common prefixes and use last component
    parts = app_id.split(".")
    if len(parts) >= 2:
        name = parts[-1]
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        return name.title().replace("Ios", "iOS").replace("Mobilesafari", "Safari")
    return app_id


def friendly_detail(category, action, detail, extra_json):
    """Make raw detail human-readable."""
    if not detail:
        return ""

    extra = {}
    if extra_json:
        try:
            extra = json.loads(extra_json)
        except (json.JSONDecodeError, TypeError):
            pass

    if category == "network":
        # "POST https://long-url..." → "apple.com" or "google.com"
        host = extra.get("host", "")
        if host:
            # Shorten host: strip "www.", keep last 2-3 parts
            host = re.sub(r"^www\.", "", host)
            parts = host.split(".")
            if len(parts) > 2 and parts[-2] in ("co", "com"):
                host = ".".join(parts[-3:])
            elif len(parts) > 2:
                host = ".".join(parts[-2:])
        method = detail.split(" ")[0] if " " in detail else ""
        url = detail.split(" ", 1)[1] if " " in detail else detail
        # Extract path (just first component)
        try:
            parsed = urlparse(url)
            path = parsed.path.split("/")[1] if parsed.path and len(parsed.path.split("/")) > 1 else ""
            if path and len(path) < 40:
                return f"{host}/{path}" if host else detail[:80]
            return host or detail[:80]
        except Exception:
            return host or detail[:80]

    elif category == "file":
        # Turn "/var/mobile/Library/Saved Application State/com.foo.bar.savedState/UUID/data.data"
        # into something like "App State Data" or "Preferences"
        path = detail
        if "Saved Application State" in path:
            return "App saved state"
        elif "/Preferences/" in path:
            fname = path.rsplit("/", 1)[-1]
            return f"Preference: {fname}"
        elif "/Caches/" in path:
            return "Cache data"
        elif "/Cookies/" in path:
            return "Cookies"
        elif "/WebKit/" in path:
            return "Browser data"
        elif "/tmp/" in path or "/Caches/" in path:
            return "Temporary data"
        elif "/Documents/" in path:
            fname = path.rsplit("/", 1)[-1]
            return f"Document: {fname}"
        else:
            # Show just the filename
            fname = path.rsplit("/", 1)[-1]
            if len(fname) > 40 or re.match(r"^[A-F0-9-]{36}", fname):
                return "Internal data"
            return fname

    elif category == "keychain":
        if detail:
            # "com.matchstic.ReProvision" → "ReProvision credentials"
            parts = detail.split(".")
            name = parts[-1] if parts else detail
            return f"{name} credentials"
        return ""

    elif category == "clipboard":
        if extra.get("length"):
            length = extra["length"]
            if length > 500:
                return f"Large text ({length} chars)"
            elif detail:
                return detail[:60]
        return detail[:60] if detail else ""

    elif category == "location":
        return ""

    elif category in ("camera", "mic"):
        if detail and detail not in ("video", "audio"):
            return detail
        return ""

    elif category == "tracking":
        return ""

    return detail[:80] if detail else ""


def time_ago(ts):
    """Convert timestamp to '2m ago' style."""
    diff = time.time() - ts
    if diff < 60:
        return f"{int(diff)}s ago"
    elif diff < 3600:
        return f"{int(diff / 60)}m ago"
    elif diff < 86400:
        return f"{int(diff / 3600)}h ago"
    else:
        return f"{int(diff / 86400)}d ago"


def cat_badge(category):
    """Render a colored category badge."""
    info = CATEGORY_INFO.get(category, {"icon": "", "label": category, "color": "#666"})
    return (
        f'<a href="/category/{esc(category)}" class="cat-badge" '
        f'style="--cat-color:{info["color"]}">'
        f'<span class="mi">{info["icon"]}</span>{info["label"]}</a>'
    )


def esc(s):
    return html.escape(str(s)) if s else ""


def events_table(events, show_app=True):
    if not events:
        return '<p class="empty">No activity recorded yet.</p>'
    h = '<div class="events-list">'
    for e in events:
        ts = e["timestamp"]
        cat = e["category"]
        info = CATEGORY_INFO.get(cat, {"icon": "", "label": cat, "color": "#666"})
        action_label = ACTION_LABELS.get(e["action"], e["action"].replace("_", " ").title())
        detail = friendly_detail(cat, e["action"], e.get("detail"), e.get("extra_json"))
        app_name = friendly_app_name(e["app_id"], e.get("exe_name", ""), e.get("display_name", ""))
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))

        h += f'<div class="event-row" style="--cat-color:{info["color"]}">'
        h += f'<div class="event-icon"><span class="mi">{info["icon"]}</span></div>'
        h += '<div class="event-body">'
        if show_app:
            h += f'<span class="event-app"><a href="/app/{esc(e["app_id"])}">{esc(app_name)}</a></span> '
        h += f'<span class="event-action">{esc(action_label)}</span>'
        if detail:
            h += f' <span class="event-detail">{esc(detail)}</span>'
        raw = json.dumps({"app": e["app_id"], "action": e["action"], "detail": e.get("detail"), "extra": e.get("extra_json")}, ensure_ascii=False, indent=2)
        h += f'<details><summary>Technical details</summary><pre>{esc(raw)}</pre></details>'
        h += f'</div>'
        h += f'<div class="event-time">{time_str}</div>'
        h += '</div>'
    h += '</div>'
    return h


def pagination(base_url, page, total, per_page):
    pages = max(1, (total + per_page - 1) // per_page)
    if pages <= 1:
        return ""
    h = '<div class="pagination">'
    if page > 1:
        h += f'<a href="{base_url}page={page - 1}">Previous</a> '
    h += f'<span class="page-info">Page {page} of {pages}</span> '
    if page < pages:
        h += f'<a href="{base_url}page={page + 1}">Next</a>'
    h += "</div>"
    return h


class DashboardServer:
    def __init__(self, db: sqlite3.Connection, db_lock: threading.Lock, port: int = 8800):
        self.db = db
        self.db_lock = db_lock
        self.port = port

    def serve(self):
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
                pass

            def _query(self, sql, params=()):
                with db_lock:
                    db.row_factory = sqlite3.Row
                    cur = db.execute(sql, params)
                    return [dict(r) for r in cur.fetchall()]

            def _app_summaries(self):
                return self._query(
                    "SELECT e.app_id, "
                    "(SELECT exe_name FROM events WHERE app_id = e.app_id ORDER BY id DESC LIMIT 1) AS exe_name, "
                    "COALESCE((SELECT display_name FROM events WHERE app_id = e.app_id "
                    "AND display_name NOT IN ('', 'unknown') ORDER BY id DESC LIMIT 1), '') AS display_name, "
                    "COUNT(*) AS event_count, MAX(timestamp) AS last_seen "
                    "FROM events e GROUP BY e.app_id ORDER BY event_count DESC"
                )

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
                        app_id = unquote(path[5:])
                        page = int(qs.get("page", ["1"])[0])
                        cat_filter = qs.get("cat", [None])[0]
                        self._serve_app(app_id, page, cat_filter)
                    elif path.startswith("/category/"):
                        cat = path[10:]
                        page = int(qs.get("page", ["1"])[0])
                        self._serve_category(cat, page)
                    elif path == "/download/app":
                        if not APP_PACKAGE.is_file():
                            self.send_error(404, "Native app package is not available on this device")
                            return
                        data = APP_PACKAGE.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/vnd.debian.binary-package")
                        self.send_header("Content-Disposition", 'attachment; filename="PrivacyMonitor-App.deb"')
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                    elif path == "/help":
                        self._serve_help()
                    elif path == "/api/insights":
                        with db_lock:
                            insights = list_insights(db)
                        self._json_resp({"insights": insights})
                    elif path == "/api/health":
                        self._json_resp(self._health())
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

            def _health(self):
                row = self._query("SELECT COUNT(*) AS total, MAX(timestamp) AS latest FROM events")[0]
                age = max(0, time.time() - row["latest"]) if row["latest"] else None
                return {"collector": "online", "total_events": row["total"],
                        "latest_event": row["latest"], "seconds_since_event": age,
                        "activity": "waiting" if age is None else "recent" if age < 120 else "idle"}

            def _serve_help(self):
                body = '''<h2>Get the native app</h2><section class="notice"><p>Download Privacy Monitor, then share the downloaded package to Sileo to install its Home Screen app. It uses the collector already running on this iPhone.</p><a class="filter-btn" href="/download/app">Download iPhone app</a></section><h2>Make yourself at home</h2>
<section class="notice"><h3>Open Privacy Monitor like an app</h3>
<p>In Safari, tap Share → Add to Home Screen. Your dashboard stays on this iPhone.</p></section>
<h2>Check your setup</h2>
<ol class="guide"><li>Install AppBehaviorMonitor in Sileo or Zebra.</li>
<li>Close and reopen the apps you want to observe after installing an update. Restart SpringBoard if your package manager asks.</li>
<li>Open Live, switch to another app, then come back to see its activity.</li></ol>
<h2>An app is missing or misbehaving?</h2>
<p>The monitor records supported actions in apps where its tweak loads. An empty feed can simply mean no supported activity occurred.</p>
<p>If you use Choicy, check the app’s tweak configuration. To stop monitoring a sensitive or unstable app, disable AppBehaviorMonitor for that app, then close and reopen it. Disabling all tweak injection also disables monitoring.</p>
<h2>What the events mean</h2>
<p>A recorded action is an observation, not proof of misuse. A network request does not tell us everything an app sent. Only supported hooks are visible; this is not a complete audit of every app action.</p>
<p>App names arrive with new events. Older entries may still show an executable name. Open Technical details on a timeline entry when you need its original values.</p>
<h2>Your history</h2>
<p>Activity is stored locally. The collector removes entries older than seven days during its hourly cleanup while running. The dashboard does not upload your activity.</p>
<p>If this page stops opening, the collector may be offline. After a reboot, reactivate your jailbreak and check the collector service. Repeated resprings are not a troubleshooting requirement.</p>'''
                self._html("Help — Privacy Monitor", body)

            def _serve_index(self):
                apps = self._app_summaries()[:20]
                cats = self._query(
                    "SELECT category, COUNT(*) as cnt FROM events GROUP BY category ORDER BY cnt DESC"
                )
                total = self._query("SELECT COUNT(*) as c FROM events")[0]["c"]
                unique_apps = self._query("SELECT COUNT(DISTINCT app_id) as c FROM events")[0]["c"]
                recent = self._query("SELECT * FROM events ORDER BY id DESC LIMIT 15")

                # Header stats
                health = self._health()
                latest = time_ago(health["latest_event"]) if health["latest_event"] else "No activity yet"
                body = '<section class="notice"><h2>On this iPhone</h2><p><span class="status-dot"></span>Collector online · Last activity: ' + esc(latest) + '</p><p>Open an app to record supported activity. <a href="/help">Setup &amp; help</a></p></section>'
                body += '<div class="stats-bar">'
                body += f'<div class="stat"><div class="stat-num">{unique_apps}</div><div class="stat-label">Apps Monitored</div></div>'
                body += f'<div class="stat"><div class="stat-num">{total:,}</div><div class="stat-label">Activities Logged</div></div>'
                cats_count = len(cats)
                body += f'<div class="stat"><div class="stat-num">{cats_count}</div><div class="stat-label">Activity Types</div></div>'
                body += '</div>'

                # Category overview cards
                body += '<h2>What apps are doing</h2>'
                body += '<div class="cat-grid">'
                for c in cats:
                    cn = c["category"]
                    info = CATEGORY_INFO.get(cn, {"icon": "", "label": cn, "color": "#666", "desc": ""})
                    body += (
                        f'<a href="/category/{esc(cn)}" class="cat-card" style="--cat-color:{info["color"]}">'
                        f'<div class="cat-card-icon"><span class="mi">{info["icon"]}</span></div>'
                        f'<div class="cat-card-body">'
                        f'<div class="cat-card-label">{info["label"]}</div>'
                        f'<div class="cat-card-count">{c["cnt"]:,} events</div>'
                        f'<div class="cat-card-desc">{info["desc"]}</div>'
                        f'</div></a>'
                    )
                body += '</div>'

                # Top apps
                body += '<h2>Most Active Apps</h2>'
                body += '<div class="app-list">'
                for a in apps:
                    name = friendly_app_name(a["app_id"], a.get("exe_name", ""), a.get("display_name", ""))
                    ago = time_ago(a["last_seen"])
                    body += (
                        f'<a href="/app/{esc(a["app_id"])}" class="app-row">'
                        f'<div class="app-name">{esc(name)}</div>'
                        f'<div class="app-id">{esc(a["app_id"])}</div>'
                        f'<div class="app-stats">{a["event_count"]:,} activities &middot; {ago}</div>'
                        f'</a>'
                    )
                body += '</div>'

                # Recent
                body += '<h2>Recent Activity</h2>'
                body += events_table(recent) if recent else '<section class="notice"><h3>Ready when you are</h3><p>Close and reopen an app, use it for a moment, then visit <a href="/live">Live activity</a>.</p><a href="/help">Check your setup</a></section>'

                self._html("Privacy Monitor", body)

            def _serve_app(self, app_id, page=1, cat_filter=None):
                per_page = 100
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
                    "SELECT category, COUNT(*) as cnt FROM events WHERE app_id = ? GROUP BY category ORDER BY cnt DESC",
                    (app_id,),
                )
                exe = self._query("SELECT exe_name FROM events WHERE app_id = ? ORDER BY id DESC LIMIT 1", (app_id,))
                exe_name = exe[0]["exe_name"] if exe else ""
                display = self._query("SELECT display_name FROM events WHERE app_id = ? AND display_name NOT IN ('', 'unknown') ORDER BY id DESC LIMIT 1", (app_id,))
                dname = display[0]["display_name"] if display else ""
                name = friendly_app_name(app_id, exe_name, dname)

                body = f'<h2>{esc(name)}</h2>'
                body += f'<p class="subtitle">{esc(app_id)} &middot; {total:,} activities</p>'

                # Category breakdown for this app
                body += '<div class="filters">'
                all_active = " active" if not cat_filter else ""
                body += f'<a href="/app/{esc(app_id)}" class="filter-btn{all_active}">All</a> '
                for c in cats:
                    cn = c["category"]
                    info = CATEGORY_INFO.get(cn, {"label": cn, "color": "#666"})
                    active = " active" if cn == cat_filter else ""
                    body += f'<a href="/app/{esc(app_id)}?cat={esc(cn)}" class="filter-btn{active}" style="--cat-color:{info["color"]}">{info["label"]} ({c["cnt"]})</a> '
                body += '</div>'

                body += events_table(events, show_app=False)
                body += pagination(f"/app/{app_id}" + (f"?cat={cat_filter}&" if cat_filter else "?"), page, total, per_page)
                self._html(f"{name} — Privacy Monitor", body)

            def _serve_category(self, cat, page=1):
                per_page = 100
                offset = (page - 1) * per_page
                info = CATEGORY_INFO.get(cat, {"icon": "", "label": cat, "color": "#666", "desc": ""})
                events = self._query(
                    "SELECT * FROM events WHERE category = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (cat, per_page, offset),
                )
                total = self._query("SELECT COUNT(*) as c FROM events WHERE category = ?", (cat,))[0]["c"]

                body = f'<h2>{info["label"]}</h2>'
                body += f'<p class="subtitle">{info["desc"]} &middot; {total:,} total</p>'
                body += events_table(events)
                body += pagination(f"/category/{cat}?", page, total, per_page)
                self._html(f"{info['label']} — Privacy Monitor", body)

            def _serve_live(self):
                body = '<h2>Live Activity</h2>'
                body += '<p class="subtitle">Auto-updates every 3 seconds</p>'
                body += '<p id="connection" role="status" aria-live="polite">Connecting…</p><button type="button" id="refresh-now" class="filter-btn">Refresh now</button><div id="live"><p class="empty">Loading...</p></div>'
                body += '''<script>
const CAT = ''' + json.dumps({k: {"icon": v["icon"], "label": v["label"], "color": v["color"]} for k, v in CATEGORY_INFO.items()}) + ''';
const ACT = ''' + json.dumps(ACTION_LABELS) + ''';

function escapeHTML(value) {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
}

function appName(id, exe, displayName) {
    if (displayName && displayName !== "unknown") return displayName;
    if (exe && exe !== "unknown" && exe !== id) return exe;
    let p = id.split(".");
    if (p.length >= 2) {
        let n = p[p.length-1];
        return n.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, s=>s.toUpperCase());
    }
    return id;
}

function friendlyDetail(cat, act, detail, extra) {
    if (!detail) return "";
    let ex = {};
    try { if (extra) ex = JSON.parse(extra); } catch(e) {}
    if (cat === "network") return ex.host ? ex.host.replace(/^www\\./, "") : "";
    if (cat === "file") {
        if (detail.includes("Saved Application State")) return "App saved state";
        if (detail.includes("/Preferences/")) return "Preference: " + detail.split("/").pop();
        if (detail.includes("/Caches/")) return "Cache data";
        if (detail.includes("/Cookies/")) return "Cookies";
        let fn = detail.split("/").pop();
        if (fn.length > 36 || /^[A-F0-9-]{36}/.test(fn)) return "Internal data";
        return fn;
    }
    if (cat === "keychain") {
        let p = detail.split(".");
        return p[p.length-1] + " credentials";
    }
    if (cat === "clipboard") return detail.substring(0, 60);
    return "";
}

let refreshTimer;
let refreshing = false;
async function refresh() {
    clearTimeout(refreshTimer);
    if (refreshing || document.hidden) return;
    refreshing = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    await fetch("/api/events?limit=50", {signal: controller.signal})
        .then(r => { if (!r.ok) throw new Error("Request failed"); return r.json(); })
        .then(data => {
            document.getElementById("connection").textContent = "Connected · Updated " + new Date().toLocaleTimeString();
            if (!data.length) {
                document.getElementById("live").innerHTML = '<p class="empty">No activity yet. Open some apps!</p>';
                return;
            }
            let h = '<div class="events-list">';
            data.forEach(e => {
                let c = CAT[e.category] || {icon:"", label:e.category, color:"#666"};
                let act = ACT[e.action] || e.action.replace(/_/g, " ");
                let detail = friendlyDetail(e.category, e.action, e.detail, e.extra_json);
                let name = escapeHTML(appName(e.app_id, e.exe_name, e.display_name));
                let t = new Date(e.timestamp * 1000).toLocaleTimeString();
                h += `<div class="event-row" style="--cat-color:${c.color}">`;
                h += `<div class="event-icon"><span class="mi">${c.icon}</span></div>`;
                h += `<div class="event-body">`;
                h += `<span class="event-app"><a href="/app/${encodeURIComponent(e.app_id)}">${name}</a></span> `;
                h += `<span class="event-action">${escapeHTML(act)}</span>`;
                if (detail) h += ` <span class="event-detail">${escapeHTML(detail)}</span>`;
                h += `</div><div class="event-time">${t}</div></div>`;
            });
            h += "</div>";
            document.getElementById("live").innerHTML = h;
        })
        .catch(() => {
            document.getElementById("connection").textContent = "Connection lost. Your last activity stays below. Retrying…";
        })
        .finally(() => {
            clearTimeout(timeout);
            refreshing = false;
            if (!document.hidden) refreshTimer = setTimeout(refresh, 3000);
        });
}
document.getElementById("refresh-now").addEventListener("click", refresh);
document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(refreshTimer); else refresh();
});
refresh();
</script>'''
                self._html("Live Activity — Privacy Monitor", body)

            def _serve_search(self, q):
                results = []
                if q:
                    matching_actions = [action for action, label in ACTION_LABELS.items() if q.casefold() in label.casefold()]
                    results = self._query(
                        "SELECT * FROM events WHERE detail LIKE ? OR app_id LIKE ? OR exe_name LIKE ? "
                        "OR display_name LIKE ? OR action LIKE ? OR action IN ("
                        + ",".join("?" for _ in matching_actions) + ") ORDER BY id DESC LIMIT 200",
                        [f"%{q}%"] * 5 + matching_actions,
                    )
                body = '<h2>Search</h2>'
                body += (
                    f'<form method="get" action="/search" class="search-form">'
                    f'<input name="q" value="{esc(q)}" placeholder="Search by app name, website, action...">'
                    f'<button type="submit">Search</button></form>'
                )
                if q:
                    body += f'<p class="subtitle">{len(results)} results for "{esc(q)}"</p>'
                    body += events_table(results)
                self._html("Search — Privacy Monitor", body)

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
                rows = self._app_summaries()
                self._json_resp(rows)

            def _api_stats(self):
                total = self._query("SELECT COUNT(*) as c FROM events")[0]["c"]
                cats = self._query("SELECT category, COUNT(*) as c FROM events GROUP BY category")
                apps = self._query("SELECT COUNT(DISTINCT app_id) as c FROM events")[0]["c"]
                self._json_resp({"total_events": total, "unique_apps": apps, "categories": cats})

        return Handler


PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Privacy Monitor">
<meta name="theme-color" content="#0d1117">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0d1117;--surface:#161b22;--surface2:#21262d;--border:#30363d;--text:#e6edf3;--text2:#8b949e;--text3:#6e7681;--accent:#58a6ff}}
body{{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:15px;-webkit-text-size-adjust:100%;padding-bottom:40px}}
a{{color:var(--accent);text-decoration:none}}
a:active{{opacity:0.7}}

/* Nav */
nav{{background:var(--surface);padding:14px 16px;display:flex;gap:14px;align-items:center;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);background:rgba(22,27,34,0.85)}}
nav .brand{{font-weight:700;font-size:17px;color:#fff;margin-right:auto}}
nav a{{color:var(--text2);font-size:14px;font-weight:500;padding:6px 10px;border-radius:8px}}
nav a:hover,nav a:active{{color:#fff;background:var(--surface2)}}

/* Offline, accessible device dashboard */
.notice{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:16px;margin:20px 0}}
.notice h2{{margin:0 0 8px}}
.notice p,p{{line-height:1.6;margin:8px 0 14px}}
.status-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3fb950;margin-right:6px}}
.guide{{padding-left:24px;line-height:1.7}}
.guide li{{padding:6px 0}}
summary{{color:var(--text2);font-size:12px;cursor:pointer;padding:8px 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;color:var(--text2)}}
a:focus-visible,button:focus-visible,input:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
button{{font:inherit;cursor:pointer}}
nav{{flex-wrap:wrap;gap:4px;padding-top:max(12px,env(safe-area-inset-top))}}
nav a{{min-height:44px;display:flex;align-items:center}}
body{{padding-bottom:max(40px,env(safe-area-inset-bottom))}}
.search-form input{{min-width:0;font-size:16px}}
/* Content */
.content{{max-width:800px;margin:0 auto;padding:0 16px}}
h2{{color:#fff;font-size:20px;font-weight:700;margin:24px 0 8px;letter-spacing:-0.3px}}
.subtitle{{color:var(--text2);font-size:13px;margin-bottom:12px}}
.empty{{color:var(--text3);text-align:center;padding:40px 16px;font-size:15px}}

/* Stats bar */
.stats-bar{{display:flex;gap:1px;margin:16px 0;background:var(--border);border-radius:12px;overflow:hidden}}
.stat{{flex:1;background:var(--surface);padding:16px 12px;text-align:center}}
.stat:first-child{{border-radius:12px 0 0 12px}}
.stat:last-child{{border-radius:0 12px 12px 0}}
.stat-num{{font-size:24px;font-weight:700;color:#fff}}
.stat-label{{font-size:11px;color:var(--text2);margin-top:2px;text-transform:uppercase;letter-spacing:0.5px}}

/* Category grid */
.cat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0 20px}}
.cat-card{{display:flex;align-items:center;gap:12px;padding:14px;background:var(--surface);border-radius:12px;border:1px solid var(--border);transition:border-color 0.15s}}
.cat-card:active{{border-color:var(--cat-color)}}
.cat-card-icon{{width:40px;height:40px;border-radius:10px;background:var(--surface2);background:color-mix(in srgb,var(--cat-color) 15%,transparent);display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.cat-card-icon .mi{{color:var(--cat-color);font-size:20px}}
.cat-card-label{{font-weight:600;font-size:14px;color:#fff}}
.cat-card-count{{font-size:12px;color:var(--text2)}}
.cat-card-desc{{font-size:11px;color:var(--text3);margin-top:1px}}

/* App list */
.app-list{{margin:8px 0 20px}}
.app-row{{display:block;padding:12px 14px;background:var(--surface);border-radius:10px;margin-bottom:6px;border:1px solid var(--border)}}
.app-row:active{{border-color:var(--accent)}}
.app-name{{font-weight:600;font-size:15px;color:#fff}}
.app-id{{font-size:11px;color:var(--text3);font-family:"SF Mono",Menlo,monospace;margin-top:1px}}
.app-stats{{font-size:12px;color:var(--text2);margin-top:3px}}

/* Events list */
.events-list{{margin:8px 0}}
.event-row{{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-bottom:1px solid var(--border)}}
.event-icon{{width:32px;height:32px;border-radius:8px;background:var(--surface2);background:color-mix(in srgb,var(--cat-color) 12%,transparent);display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.event-icon .mi{{color:var(--cat-color);font-size:16px}}
.event-body{{flex:1;min-width:0}}
.event-app a{{font-weight:600;font-size:14px;color:#fff}}
.event-action{{font-size:13px;color:var(--text)}}
.event-detail{{font-size:12px;color:var(--text2);display:block;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.event-time{{font-size:11px;color:var(--text3);flex-shrink:0;padding-top:2px;min-width:58px;text-align:right}}

/* Filters */
.filters{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 14px}}
.filter-btn{{display:inline-block;padding:6px 14px;background:var(--surface2);border:1px solid var(--border);border-radius:20px;font-size:13px;color:var(--text2);font-weight:500}}
.filter-btn.active{{background:var(--surface2);background:color-mix(in srgb,var(--cat-color,var(--accent)) 20%,transparent);border-color:var(--cat-color,var(--accent));color:#fff}}

/* Category badges */
.cat-badge{{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:500;background:var(--surface2);background:color-mix(in srgb,var(--cat-color) 15%,transparent);color:var(--cat-color)}}

/* Search */
.search-form{{display:flex;gap:8px;margin:12px 0}}
.search-form input{{flex:1;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:16px;outline:none}}
.search-form input:focus{{border-color:var(--accent)}}
.search-form button{{padding:10px 20px;background:var(--accent);color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer}}

/* Pagination */
.pagination{{display:flex;justify-content:center;align-items:center;gap:12px;margin:20px 0;padding:12px}}
.pagination a{{padding:8px 16px;background:var(--surface2);border:1px solid var(--border);border-radius:8px;font-size:13px;color:var(--text);font-weight:500}}
.page-info{{font-size:13px;color:var(--text2)}}

/* Material icons via codepoints */
.mi{{font-family:-apple-system,system-ui,sans-serif;font-weight:normal;font-style:normal;font-size:20px;display:inline-block;line-height:1;text-transform:none;letter-spacing:normal;word-wrap:normal;white-space:nowrap;direction:ltr;-webkit-font-smoothing:antialiased;font-variation-settings:'FILL' 1,'wght' 500,'GRAD' 0,'opsz' 24}}

@media(max-width:500px){{
    .cat-grid{{grid-template-columns:1fr}}
    .stats-bar{{flex-direction:column}}
    .stat:first-child,.stat:last-child{{border-radius:0}}
    .stat:first-child{{border-radius:12px 12px 0 0}}
    .stat:last-child{{border-radius:0 0 12px 12px}}
}}
</style></head><body>
<nav>
<span class="brand">Privacy Monitor</span>
<a href="/">Home</a>
<a href="/live">Live</a>
<a href="/search">Search</a>
<a href="/help">Help</a>
</nav>
<div class="content">
{body}
</div>
</body></html>"""
