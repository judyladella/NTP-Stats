import os
import time
import statistics
from typing import Dict, Any, List

import requests
from fastapi import FastAPI, Query

app = FastAPI()

# Comma-separated list of collector endpoints (each should be .../metrics)
# Example:
# DEVICE_ENDPOINTS="http://node-01.lan:8000/metrics,http://node-02.lan:8000/metrics,http://node-03.lan:8000/metrics"
DEVICE_ENDPOINTS = [x.strip() for x in os.getenv("DEVICE_ENDPOINTS", "").split(",") if x.strip()]
POLL_TIMEOUT_SEC = float(os.getenv("POLL_TIMEOUT_SEC", "1.5"))

# Status thresholds (tweak later)
SYNC_OFFSET_MS = float(os.getenv("SYNC_OFFSET_MS", "1.0"))     # abs(offset) <= 1ms is good
SYNC_JITTER_MS = float(os.getenv("SYNC_JITTER_MS", "0.5"))     # jitter <= 0.5ms is good
SYNC_DELAY_MS  = float(os.getenv("SYNC_DELAY_MS", "5.0"))      # delay <= 5ms is good
SYNC_LOSS_PCT  = float(os.getenv("SYNC_LOSS_PCT", "5.0"))      # loss <= 5% is good

app = FastAPI()

def _now_ms() -> int:
    return int(time.time() * 1000)

def classify_status(ok: int, total: int, mean_offset: float | None, jitter: float | None, mean_delay: float | None) -> str:
    if total <= 0 or ok == 0:
        return "Unreachable"

    loss_pct = 100.0 * (total - ok) / total

    # Degraded if any metric exceeds threshold
    if loss_pct > SYNC_LOSS_PCT:
        return "Degraded"
    if mean_offset is not None and abs(mean_offset) > SYNC_OFFSET_MS:
        return "Degraded"
    if jitter is not None and jitter > SYNC_JITTER_MS:
        return "Degraded"
    if mean_delay is not None and mean_delay > SYNC_DELAY_MS:
        return "Degraded"

    return "Synced"

def compute_node_aggregates(points: List[Dict[str, Any]], window_start_ms: int) -> Dict[str, Any]:
    # keep only points within the requested window
    pts = [p for p in points if isinstance(p.get("timestamp"), int) and p["timestamp"] >= window_start_ms]

    total = len(pts)
    ok_pts = [p for p in pts if p.get("packetLoss") == 0 and p.get("offset") is not None and p.get("rtt") is not None]
    ok = len(ok_pts)

    if total == 0:
        return {
            "total": 0, "ok": 0, "lossPct": 100.0,
            "meanOffset": None, "jitter": None, "meanDelay": None
        }

    loss_pct = 100.0 * (total - ok) / total

    if ok == 0:
        return {
            "total": total, "ok": 0, "lossPct": loss_pct,
            "meanOffset": None, "jitter": None, "meanDelay": None
        }

    offsets = [float(p["offset"]) for p in ok_pts]
    delays  = [float(p["rtt"]) for p in ok_pts]  # rtt in ms (used as delay)

    mean_offset = statistics.mean(offsets)
    mean_delay = statistics.mean(delays)
    jitter = statistics.pstdev(delays) if len(delays) > 1 else 0.0

    return {
        "total": total,
        "ok": ok,
        "lossPct": loss_pct,
        "meanOffset": mean_offset,
        "jitter": jitter,
        "meanDelay": mean_delay
    }

def poll_collectors() -> Dict[str, Dict[str, Any]]:
    """
    Returns: devices[node_name] = {"metrics": [...]}
    """
    devices: Dict[str, Dict[str, Any]] = {}

    for url in DEVICE_ENDPOINTS:
        try:
            r = requests.get(url, timeout=POLL_TIMEOUT_SEC)
            payload = r.json()
            devs = payload.get("devices", {})
            for node, data in devs.items():
                # merge: last write wins if duplicates
                devices[node] = data
        except Exception:
            # If a collector is down, we can't know its node name unless you supply a registry.
            # (Frontend will show fewer totalNodes in that case; see note below.)
            continue

    return devices

@app.get("/api/ntp/dashboard")
def ntp_dashboard(
    windowSec: int = Query(60, ge=5, le=3600),
    historySec: int = Query(300, ge=10, le=3600),
    sampleTarget: int = Query(10, ge=1, le=500)
):
    """
    windowSec: aggregation window for table + top cards (e.g., last 60s)
    historySec: how much time series to return for the offset history chart
    sampleTarget: used only for display; table will compute ok/total from available points.
    """
    now = _now_ms()
    window_start = now - windowSec * 1000
    history_start = now - historySec * 1000

    devices = poll_collectors()

    # Build offset history series + node metrics table
    offset_series = []
    node_metrics = []

    synced = degraded = unreachable = 0

    for node, data in sorted(devices.items(), key=lambda x: x[0]):
        metrics = data.get("metrics", [])
        if not isinstance(metrics, list):
            metrics = []

        # Offset history points
        hist_points = []
        for p in metrics:
            ts = p.get("timestamp")
            off = p.get("offset")
            if isinstance(ts, int) and ts >= history_start and off is not None:
                hist_points.append({"t": ts, "y": float(off)})

        offset_series.append({"node": node, "points": hist_points})

        # Table aggregates
        agg = compute_node_aggregates(metrics, window_start)
        status = classify_status(agg["ok"], agg["total"], agg["meanOffset"], agg["jitter"], agg["meanDelay"])

        if status == "Synced":
            synced += 1
        elif status == "Degraded":
            degraded += 1
        else:
            unreachable += 1

        node_metrics.append({
            "target": node,
            "status": status,
            "offsetMs": agg["meanOffset"],
            "jitterMs": agg["jitter"],
            "delayMs": agg["meanDelay"],
            "lossPct": agg["lossPct"],
            "ok": agg["ok"],
            "total": agg["total"] if agg["total"] > 0 else sampleTarget
        })

    total_nodes = len(devices)

    # System status panel (stubbed for now; you can wire these later)
    system_status = [
        {"name": "PTP Grandmaster", "state": os.getenv("PTP_GRANDMASTER_STATE", "Online")},
        {"name": "Chrony", "state": os.getenv("CHRONY_STATE", "Running")},
        {"name": "GNSS MAX–MIOS", "state": os.getenv("GNSS_STATE", "Locked")},
        {"name": "USB–ETH Dongle", "state": os.getenv("USB_ETH_STATE", "Active")},
        {"name": "PPS Signal", "state": os.getenv("PPS_STATE", "1 Hz")},
        {"name": "Collector", "state": os.getenv("COLLECTOR_STATE", "Polling")},
    ]

    return {
        "metadata": {
            "mode": "NTP",
            "updatedAt": now,
            "windowSec": windowSec,
            "historySec": historySec,
            "units": {"offset": "ms", "jitter": "ms", "delay": "ms", "loss": "%"}
        },
        "topCards": {
            "totalNodes": total_nodes,
            "synced": synced,
            "degraded": degraded,
            "unreachable": unreachable
        },
        "offsetHistory": {
            "series": offset_series
        },
        "systemStatus": system_status,
        "nodeMetrics": node_metrics
    }