#!/usr/bin/env python3
"""
AppBehaviorMonitor — Collector Daemon
Listens on Unix datagram socket, writes to SQLite, runs cleanup.
"""

import json
import logging
import os
import signal
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path

SOCK_PATH = "/var/jb/var/mobile/Documents/appmon/appmon.sock"
DB_PATH = "/var/jb/var/mobile/Documents/appmon/appmon.db"
LOG_PATH = "/var/jb/var/mobile/Documents/appmon/collector.log"
MAX_MSG = 4096
RETENTION_DAYS = 7
CLEANUP_INTERVAL = 3600  # 1 hour

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("collector")


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            pid INTEGER NOT NULL,
            app_id TEXT NOT NULL,
            exe_name TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            category TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            extra_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_app ON events(app_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_cat ON events(category, timestamp);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);

        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);

        CREATE TABLE IF NOT EXISTS app_summary (
            app_id TEXT,
            category TEXT,
            hour TEXT,
            event_count INTEGER DEFAULT 0,
            PRIMARY KEY (app_id, category, hour)
        );
    """)
    conn.commit()
    # Migrate: add display_name column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "display_name" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN display_name TEXT DEFAULT ''")
        conn.commit()
    return conn


class Collector:
    def __init__(self):
        self.running = True
        self.db = init_db(DB_PATH)
        self.db_lock = threading.Lock()
        self.sock = None
        self._batch = []
        self._batch_lock = threading.Lock()

    def setup_socket(self):
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(SOCK_PATH)
        os.chmod(SOCK_PATH, 0o777)  # All processes need to write
        self.sock.settimeout(1.0)
        log.info("Listening on %s", SOCK_PATH)

    def receive_loop(self):
        while self.running:
            try:
                data = self.sock.recv(MAX_MSG)
                evt = json.loads(data)
                with self._batch_lock:
                    self._batch.append(evt)
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self.running:
                    log.error("recv error: %s", e)

    def flush_loop(self):
        """Flush batched events to SQLite every 0.5s."""
        while self.running:
            time.sleep(0.5)
            self._flush()

    def _flush(self):
        with self._batch_lock:
            if not self._batch:
                return
            batch = self._batch
            self._batch = []

        rows = []
        summary_updates = {}
        for evt in batch:
            ts = evt.get("ts", time.time())
            pid = evt.get("pid", 0)
            app = evt.get("app", "unknown")
            exe = evt.get("exe", "unknown")
            name = evt.get("name", "")
            cat = evt.get("cat", "unknown")
            act = evt.get("act", "unknown")
            detail = evt.get("detail")
            extra = evt.get("extra")
            rows.append((ts, pid, app, exe, name, cat, act, detail, extra))

            hour = time.strftime("%Y-%m-%d-%H", time.gmtime(ts))
            key = (app, cat, hour)
            summary_updates[key] = summary_updates.get(key, 0) + 1

        with self.db_lock:
            try:
                self.db.executemany(
                    "INSERT INTO events (timestamp, pid, app_id, exe_name, display_name, category, action, detail, extra_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                for (app, cat, hour), count in summary_updates.items():
                    self.db.execute(
                        "INSERT INTO app_summary (app_id, category, hour, event_count) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(app_id, category, hour) DO UPDATE SET event_count = event_count + ?",
                        (app, cat, hour, count, count),
                    )
                self.db.commit()
            except Exception as e:
                log.error("DB write error: %s", e)

    def cleanup_loop(self):
        while self.running:
            time.sleep(CLEANUP_INTERVAL)
            self._cleanup()

    def _cleanup(self):
        cutoff = time.time() - RETENTION_DAYS * 86400
        with self.db_lock:
            try:
                cur = self.db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
                deleted = cur.rowcount
                cutoff_hour = time.strftime("%Y-%m-%d-%H", time.gmtime(cutoff))
                self.db.execute("DELETE FROM app_summary WHERE hour < ?", (cutoff_hour,))
                self.db.commit()
                if deleted > 0:
                    log.info("Cleaned up %d old events", deleted)
                # Vacuum on Sundays
                if time.gmtime().tm_wday == 6:
                    self.db.execute("VACUUM")
            except Exception as e:
                log.error("Cleanup error: %s", e)

    def stop(self, *_):
        log.info("Shutting down...")
        self.running = False
        self._flush()
        if self.sock:
            self.sock.close()
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        self.db.close()

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        self.setup_socket()

        threads = [
            threading.Thread(target=self.receive_loop, daemon=True),
            threading.Thread(target=self.flush_loop, daemon=True),
            threading.Thread(target=self.cleanup_loop, daemon=True),
        ]
        for t in threads:
            t.start()

        # Import and start dashboard
        from dashboard import DashboardServer
        dash = DashboardServer(self.db, self.db_lock)
        dash_thread = threading.Thread(target=dash.serve, daemon=True)
        dash_thread.start()
        log.info("Dashboard at http://127.0.0.1:8800/")

        # Main thread waits
        while self.running:
            time.sleep(1)


if __name__ == "__main__":
    Collector().run()
