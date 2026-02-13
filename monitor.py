import socket
import time
import os
import statistics
import sqlite3
import datetime

# Configuration from Docker environment
TARGET_IP = os.getenv("TARGET_IP", "127.0.0.1")
# We use the Container ID or Hostname as a unique ID for the scaling test
NODE_ID = os.getenv("HOSTNAME", "unknown_node") 
PORT = 12345
SAMPLES_PER_BATCH = 10
DB_PATH = "/app/research_data.db"

def init_db():
    """Ensures the database and table exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ntp_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT,
            offset_sec REAL,
            jitter_ms REAL,
            packet_loss REAL,
            recorded_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_to_db(offset, jitter, loss):
    """Saves results to the shared database file."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ntp_metrics (node_id, offset_sec, jitter_ms, packet_loss, recorded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (NODE_ID, offset, jitter, loss, datetime.datetime.now()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Log Error: {e}")

def measure_network():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    
    results = []
    success_count = 0

    for _ in range(SAMPLES_PER_BATCH):
        t1 = time.time()
        try:
            sock.sendto(b"ping", (TARGET_IP, PORT))
            data, _ = sock.recvfrom(1024)
            t4 = time.time()
            
            t2_t3 = float(data.decode())
            
            # NTP Offset Formula
            offset = ((t2_t3 - t1) + (t2_t3 - t4)) / 2
            rtt = (t4 - t1) * 1000 
            
            results.append({'offset': offset, 'rtt': rtt})
            success_count += 1
        except socket.timeout:
            pass
        time.sleep(0.05) # High-frequency sampling

    if results:
        rtts = [r['rtt'] for r in results]
        offsets = [r['offset'] for r in results]
        
        jitter = statistics.stdev(rtts) if len(rtts) > 1 else 0
        loss = ((SAMPLES_PER_BATCH - success_count) / SAMPLES_PER_BATCH) * 100
        avg_offset = statistics.mean(offsets)
        
        print(f"[{NODE_ID}] Offset: {avg_offset:.6f}s | Jitter: {jitter:.3f}ms | Loss: {loss}%")
        log_to_db(avg_offset, jitter, loss)

if __name__ == "__main__":
    init_db()
    print(f"Node {NODE_ID} starting continuous monitor...")
    while True:
        measure_network()
        time.sleep(5) # Wait 5 seconds between batches