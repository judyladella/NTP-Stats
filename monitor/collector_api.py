import os
import time
import sqlite3
import threading
import datetime
import json
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler

DB_PATH = os.getenv("DB_PATH", "/app/research_data.db")
NODE_ID = os.getenv("HOSTNAME", "unknown-node")
PORT = int(os.getenv("API_PORT", "8000"))
HISTORY_LEN = int(os.getenv("HISTORY_LEN", "300"))

_cache = deque(maxlen=HISTORY_LEN)
_by_target_cache = {}
_lock = threading.Lock()

def load_from_db():
    try:
        conn = sqlite3.connect(DB_PATH)

        # Existing metrics cache — all rows combined
        rows = conn.execute("""
            SELECT recorded_at, offset_sec, jitter_ms, delay_ms, packet_loss
            FROM ntp_metrics
            ORDER BY recorded_at DESC
            LIMIT ?
        """, (HISTORY_LEN,)).fetchall()

        # Per-target summary — avg over last 50 rows per target
        target_rows = conn.execute("""
            SELECT target_host,
                   ROUND(AVG(offset_sec) * 1000, 3)  AS avg_offset_ms,
                   ROUND(AVG(jitter_ms), 3)           AS avg_jitter_ms,
                   ROUND(AVG(delay_ms), 3)            AS avg_delay_ms,
                   ROUND(AVG(packet_loss), 3)         AS avg_loss,
                   COUNT(*)                            AS samples
            FROM (
                SELECT target_host, offset_sec, jitter_ms, delay_ms, packet_loss
                FROM ntp_metrics
                ORDER BY recorded_at DESC
                LIMIT 150
            )
            GROUP BY target_host
        """).fetchall()

        conn.close()

        points = []
        for row in rows:
            try:
                ts_ms = int(datetime.datetime.fromisoformat(row[0]).timestamp() * 1000)
                points.append({
                    "timestamp":  ts_ms,
                    "offset":     float(row[1]) * 1000,
                    "jitter":     float(row[2]),
                    "rtt":        float(row[3]),
                    "packetLoss": int(row[4])
                })
            except Exception:
                continue

        by_target = {}
        for row in target_rows:
            by_target[row[0]] = {
                "target":       row[0],
                "avgOffsetMs":  row[1],
                "avgJitterMs":  row[2],
                "avgDelayMs":   row[3],
                "avgLossPct":   round(float(row[4]) * 100, 1),
                "samples":      row[5]
            }

        with _lock:
            _cache.clear()
            _cache.extend(reversed(points))
            _by_target_cache.clear()
            _by_target_cache.update(by_target)

    except Exception as e:
        print(f"[collector_api] DB load error: {e}", flush=True)

def refresh_loop():
    while True:
        load_from_db()
        time.sleep(5)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            with _lock:
                metrics_out = list(_cache)

            body = json.dumps({
                "metadata": {
                    "mode": "NTP",
                    "units": {"offset": "ms", "jitter": "ms", "rtt": "ms"}
                },
                "devices": {
                    NODE_ID: {
                        "metrics": metrics_out
                    }
                }
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/metrics/by-target":
            with _lock:
                by_target_out = dict(_by_target_cache)

            body = json.dumps({
                "node": NODE_ID,
                "targets": by_target_out
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run():
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    print(f"[collector_api] Serving on port {PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()