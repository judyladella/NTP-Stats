import os
import time
import threading
import statistics
from collections import deque

import ntplib
from fastapi import FastAPI
import uvicorn

# Identity
NODE_ID = os.getenv("NODE_ID", os.getenv("HOSTNAME", "node-unknown"))
TARGET_HOST = os.getenv("TARGET_HOST", os.getenv("TARGET_IP", "127.0.0.1"))

# NTP
NTP_TIMEOUT_SEC = float(os.getenv("NTP_TIMEOUT_SEC", "1.0"))
NTP_VERSION = int(os.getenv("NTP_VERSION", "3"))

# Sampling
SAMPLE_PERIOD_SEC = float(os.getenv("SAMPLE_PERIOD_SEC", "1.0"))
HISTORY_LEN = int(os.getenv("HISTORY_LEN", "300"))  # points stored in memory

# (Optional) per-point jitter shown in the raw metrics stream (rolling over recent RTTs)
JITTER_WINDOW = int(os.getenv("JITTER_WINDOW", "10"))

app = FastAPI()
history = deque(maxlen=HISTORY_LEN)
rtt_window = deque(maxlen=JITTER_WINDOW)
lock = threading.Lock()

def probe_loop():
    client = ntplib.NTPClient()

    while True:
        ts_ms = int(time.time() * 1000)
        packet_loss = 0

        try:
            r = client.request(TARGET_HOST, version=NTP_VERSION, timeout=NTP_TIMEOUT_SEC)
            offset_ms = float(r.offset) * 1000.0
            rtt_ms = float(r.delay) * 1000.0  # NTP delay estimate (RTT-like)

            rtt_window.append(rtt_ms)
            jitter_ms = statistics.pstdev(rtt_window) if len(rtt_window) > 1 else 0.0

        except Exception:
            packet_loss = 1
            offset_ms = None
            rtt_ms = None
            jitter_ms = statistics.pstdev(rtt_window) if len(rtt_window) > 1 else 0.0

        point = {
            "timestamp": ts_ms,
            "offset": offset_ms,       # ms
            "jitter": jitter_ms,       # ms (rolling, optional)
            "rtt": rtt_ms,             # ms
            "packetLoss": packet_loss  # 0 or 1
        }

        with lock:
            history.append(point)

        time.sleep(SAMPLE_PERIOD_SEC)

@app.get("/metrics")
def metrics():
    with lock:
        metrics_out = list(history)

    return {
        "metadata": {
            "mode": "NTP",
            "units": {"offset": "ms", "jitter": "ms", "rtt": "ms"}
        },
        "devices": {
            NODE_ID: {
                "metrics": metrics_out
            }
        }
    }

@app.get("/health")
def health():
    return {"ok": True, "node": NODE_ID, "target": TARGET_HOST}

if __name__ == "__main__":
    t = threading.Thread(target=probe_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))