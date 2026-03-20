import socket
import time
import os
import sqlite3
import datetime
import ntplib
import sys
import threading

# Force unbuffered output so we see logs immediately
sys.stdout.reconfigure(line_buffering=True)

TARGET_IP = os.getenv("TARGET_IP", "time-server")
NODE_ID = os.getenv("HOSTNAME", "unknown_node")
DB_PATH = "/app/research_data.db"
EXTERNAL_TARGETS = os.getenv("TARGETS", "pool.ntp.org").split(",")

def init_db():
    print(f"Initializing database at {DB_PATH}...", flush=True)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ntp_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT, target_host TEXT, protocol_type TEXT,
            offset_sec REAL, delay_ms REAL, jitter_ms REAL,
            packet_loss REAL, recorded_at TIMESTAMP
        )
    ''')
    conn.close()
    print("Database initialized successfully.", flush=True)

def measure_custom_udp(num_probes=10):
    print(f"DEBUG: Attempting UDP probe to {TARGET_IP}...", flush=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    delays = []
    offsets = []
    lost = 0

    for _ in range(num_probes):
        try:
            t1 = time.time()
            sock.sendto(b"get_time", (TARGET_IP, 12345))
            data, _ = sock.recvfrom(1024)
            t4 = time.time()
            server_time = float(data.decode())
            delays.append((t4 - t1) * 1000)
            offsets.append(((server_time - t1) + (server_time - t4)) / 2)
            time.sleep(0.1)
        except Exception:
            lost += 1

    sock.close()

    if not delays:
        print(f"UDP ERROR: all {num_probes} probes lost", flush=True)
        log_to_db(TARGET_IP, "CUSTOM_UDP", 0, 0, 0, 1.0)
        return

    avg_delay = sum(delays) / len(delays)
    avg_offset = sum(offsets) / len(offsets)
    packet_loss = lost / num_probes
    jitter = sum(abs(d - avg_delay) for d in delays) / len(delays)

    log_to_db(TARGET_IP, "CUSTOM_UDP", avg_offset, avg_delay, jitter, packet_loss)
    print(f"SUCCESS: Custom UDP Offset {avg_offset:.6f}s Delay {avg_delay:.2f}ms Jitter {jitter:.2f}ms Loss {packet_loss:.0%}", flush=True)

def log_to_db(target, proto, offset, delay, jitter, loss):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        INSERT INTO ntp_metrics
            (node_id, target_host, protocol_type, offset_sec, delay_ms, jitter_ms, packet_loss, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (NODE_ID, target, proto, offset, delay, jitter, loss, datetime.datetime.now()))
    conn.commit()
    conn.close()

def run_external_ntp(host):
    client = ntplib.NTPClient()
    rtt_samples = []
    offset_samples = []
    lost = 0
    num_probes = 5

    for _ in range(num_probes):
        try:
            response = client.request(host, version=3, timeout=5)
            rtt_samples.append(response.delay * 1000)
            offset_samples.append(response.offset)
            time.sleep(0.2)
        except Exception:
            lost += 1

    if not rtt_samples:
        print(f"NTP ERROR {host}: all probes failed", flush=True)
        log_to_db(host, "STANDARD_NTP", 0, 0, 0, 1.0)
        return

    avg_offset = sum(offset_samples) / len(offset_samples)
    avg_delay = sum(rtt_samples) / len(rtt_samples)
    avg_delay_mean = avg_delay
    jitter = sum(abs(r - avg_delay_mean) for r in rtt_samples) / len(rtt_samples)
    packet_loss = lost / num_probes

    log_to_db(host, "STANDARD_NTP", avg_offset, avg_delay, jitter, packet_loss)
    print(f"NTP: {host} Offset {avg_offset:.6f}s Delay {avg_delay:.2f}ms Jitter {jitter:.2f}ms", flush=True)

if __name__ == "__main__":
    print("--- MONITOR STARTING ---", flush=True)
    init_db()

    # Start the collector API so the aggregator can poll our data
    import collector_api
    api_thread = threading.Thread(target=collector_api.run, daemon=True)
    api_thread.start()

    while True:
        print(f"--- Starting Measurement Cycle at {datetime.datetime.now()} ---", flush=True)
        measure_custom_udp()
        for target in EXTERNAL_TARGETS:
            if target.strip():
                run_external_ntp(target.strip())
        print("Cycle complete. Sleeping 10s...", flush=True)
        time.sleep(10)