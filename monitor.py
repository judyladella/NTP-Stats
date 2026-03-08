import socket
import time
import os
import sqlite3
import datetime
import ntplib
import sys

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

def measure_custom_udp():
    print(f"DEBUG: Attempting UDP probe to {TARGET_IP}...", flush=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    try:
        t1 = time.time()
        sock.sendto(b"get_time", (TARGET_IP, 12345))
        data, addr = sock.recvfrom(1024)
        t4 = time.time()
        
        server_time = float(data.decode())
        offset = ((server_time - t1) + (server_time - t4)) / 2
        delay = (t4 - t1) * 1000
        
        log_to_db(TARGET_IP, "CUSTOM_UDP", offset, delay, 0, 0)
        print(f"SUCCESS: Custom UDP Offset {offset:.6f}s", flush=True)
    except Exception as e:
        print(f"UDP ERROR: {e}", flush=True)
    finally:
        sock.close()

def log_to_db(target, proto, offset, delay, jitter, loss):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        INSERT INTO ntp_metrics (node_id, target_host, protocol_type, offset_sec, delay_ms, jitter_ms, packet_loss, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (NODE_ID, target, proto, offset, delay, jitter, loss, datetime.datetime.now()))
    conn.commit()
    conn.close()

def run_external_ntp(host):
    client = ntplib.NTPClient()
    try:
        response = client.request(host, version=3, timeout=5)
        log_to_db(host, "STANDARD_NTP", response.offset, response.delay * 1000, 0, 0)
        print(f"NTP: {host} Offset {response.offset:.6f}s", flush=True)
    except Exception as e:
        print(f"NTP ERROR {host}: {e}", flush=True)

if __name__ == "__main__":
    print("--- MONITOR STARTING ---", flush=True)
    init_db()
    
    while True:
        print(f"--- Starting Measurement Cycle at {datetime.datetime.now()} ---", flush=True)
        measure_custom_udp()
        for target in EXTERNAL_TARGETS:
            if target.strip():
                run_external_ntp(target.strip())
        
        print("Cycle complete. Sleeping 10s...", flush=True)
        time.sleep(10)