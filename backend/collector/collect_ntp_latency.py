#!/usr/bin/env python3
# Kubernetes/Docker NTP + network measurements.

# High-level approach:
# Run ONE collector pod/container.
# Provide a list of NTP targets (chronyd endpoints) via env var TARGETS.
# Probe each target using ntplib (UDP/123) multiple times to compute:
#     * time offset (ms)  -> "how far off each clock is" (relative to collector's view)
#     * NTP delay (ms)    -> network+processing delay estimate in NTP exchange
#     * jitter (ms)       -> stddev of offsets across samples (a practical jitter proxy)
#     * loss (%)          -> timeouts/total requests
# Optionally, ping each target from the collector (ICMP RTT/loss).

# Note on interpretation:
# NTP "offset" returned by ntplib is the estimated difference between the
#   collector and the target's clock (from the collector's perspective).
# If you want "node A vs node B clock difference", you can compare their offsets
#   measured close in time by the same collector (approx), or run per-node agents.

import csv
import json
import os
import statistics
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ntplib

def sh(cmd: str) -> Tuple[int, str]:
    # Runs a local shell command from inside the container returns: return code and combined stdout+stderr
    
    # In a Docker/Kubernetes, you usually *do not* ssh/srun into other nodes. Instead, the collector runs commands 
    # locally (like ping) and uses network protocols (like NTP) to query remote targets. This helper provides consistent
    # command execution and output capture.

    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    out = (p.stdout + "\n" + p.stderr).strip()
    return p.returncode, out

def get_targets_from_env() -> List[str]:
    # Determines which hosts/services to probe. In Kubernetes, "discovering nodes" is not trivial/portable without using the Kubernetes API 
    # The simplest robust method is: pass targets explicitly via env var.
    
    # TARGETS="chrony-server.default.svc.cluster.local,chrony-client,10.0.0.42"

    # If TARGETS is not set, defaults to ["localhost"] (useful for local testing). Returns a clean list of targets with whitespace stripped.

    # Returns List[str] of hostnames/IPs.
    raw = os.environ.get("TARGETS", "").strip()
    if not raw:
        return ["localhost"]
    return [t.strip() for t in raw.split(",") if t.strip()]

def parse_ping_summary(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    # Extract summary metrics from Linux ping output: 
    # avg RTT (ms), mdev (ms) (a measure of RTT variability; often used as "jitter" for ICMP), packet loss (%)
 
    # We want structured CSV/JSON metrics rather than raw ping logs.

    # Typical ping -q output includes lines like:
    # "5 packets transmitted, 5 received, 0% packet loss, time 4006ms"
    # "rtt min/avg/max/mdev = 0.120/0.250/0.400/0.050 ms"

    # If ping fails (DNS, blocked ICMP), those lines may not exist.
    # In that case we return (None, None, None).

    # RETURNS (avg, mdev, loss) strings or None if not found.

    avg = None
    mdev = None
    loss = None

    for line in text.splitlines():
        if "packet loss" in line:
            parts = [p.strip() for p in line.split(",")]
            for p in parts:
                if "packet loss" in p:
                    loss = p.split()[0].replace("%", "")
                    break

        if line.startswith("rtt ") or "round-trip" in line:
            rhs = line.split("=")[-1].strip()
            nums = rhs.split()[0].split("/")
            if len(nums) >= 4:
                avg = nums[1]
                mdev = nums[3]

    return avg, mdev, loss


def ping_target(dst: str, count: int = 5, timeout_sec: int = 1) -> Dict[str, object]:
    # Pings a target from the collector container/pod.
    
    # This gives you a simple network health baseline: RTT and variation and packet loss

    # This is NOT a full node-to-node ping matrix. It is:
    # collector -> each target

    # Kubernetes requirements: 
    # ping needs raw sockets; in many clusters you need NET_RAW capability or privileged container to run ping.

    # Dict with avg_ms/mdev_ms/loss_pct plus raw output.

    cmd = f"ping -c {count} -q -W {timeout_sec} {dst} || true"
    rc, out = sh(cmd)
    avg, mdev, loss = parse_ping_summary(out)

    return {
        "src": "collector",
        "dst": dst,
        "avg_ms": avg if avg else "NA",
        "mdev_ms": mdev if mdev else "NA",
        "loss_pct": loss if loss else "NA",
        "rc": rc,
        "raw": out,
    }

# NTP probing via ntplib (UDP/123)
def ntp_probe(host: str, samples: int = 10, timeout_sec: float = 1.0) -> Dict[str, object]:
    # Query an NTP endpoint (chronyd or other NTP server) multiple times and compute:
    #  mean offset (ms)  -> "time difference" estimate
    #  mean delay  (ms)  -> NTP round-trip delay estimate
    #  jitter (ms)       -> stddev of offset over samples (practical jitter proxy)
    #  loss (%)          -> timeouts / total samples

    # WHY ntplib
    # chronyc is great locally, but in Kubernetes you usually want remote probing.
    # ntplib speaks NTP directly to UDP/123, which chrony supports.

    # METRIC NOTES
    # offset: estimate of (server_time - client_time) using NTP timestamps.
    #   This is what you typically mean by "how far off the clock is".
    # delay: estimated RTT component of the NTP exchange.
    # jitter: chrony has its own jitter metric internally; here we compute jitter
    #   as variability across repeated offset samples from the collector.

    # LOSS DEFINITION
    # loss_pct = (timeouts / total_requests) * 100

    # EDGE CASES
    # If UDP/123 is blocked, you’ll get 100% loss.
    # If you only have 0 or 1 successful sample, stddev is None or 0.0.

    # RETURNS
    # Dict with computed stats + raw sample arrays for deeper analysis.

    client = ntplib.NTPClient()
    offsets_ms: List[float] = []
    delays_ms: List[float] = []
    timeouts = 0

    for _ in range(samples):
        try:
            r = client.request(host, version=3, timeout=timeout_sec)
            offsets_ms.append(r.offset * 1000.0)
            delays_ms.append(r.delay * 1000.0)
        except Exception:
            timeouts += 1

    ok = samples - timeouts
    loss_pct = (timeouts / samples) * 100.0

    def safe_mean(xs: List[float]) -> Optional[float]:
        # Mean if xs non-empty else None.
        return statistics.mean(xs) if xs else None

    def safe_std(xs: List[float]) -> Optional[float]:
        # Population stddev if >=2 samples.
        # If 1 sample, stddev is 0.0 (no variability observed).
        # If 0 samples, None.
        if len(xs) >= 2:
            return statistics.pstdev(xs)
        if len(xs) == 1:
            return 0.0
        return None

    return {
        "target": host,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "samples": samples,
        "ok": ok,
        "timeouts": timeouts,
        "loss_pct": loss_pct,
        "offset_ms_mean": safe_mean(offsets_ms),
        "offset_ms_jitter": safe_std(offsets_ms),
        "delay_ms_mean": safe_mean(delays_ms),
        "delay_ms_jitter": safe_std(delays_ms),
        "raw_offsets_ms": offsets_ms,
        "raw_delays_ms": delays_ms,
    }

# Output writing helpers
def write_json(path: Path, obj: object) -> None:
    # PURPOSE
    # Write JSON to disk with consistent formatting.

    # WHY THIS EXISTS
    # Keeps main() clean and ensures consistent indentation/newlines for tooling.

    # RETURNS
    # None (writes file as side effect).

    path.write_text(json.dumps(obj, indent=2) + "\n")


def write_ntp_csv(path: Path, ntp_records: List[Dict[str, object]]) -> None:
    # PURPOSE
    # Write a compact CSV summary of NTP results for spreadsheet use.

    # WHY THIS EXISTS
    # JSON is great for detail; CSV is great for quick scans, sorting, charts.

    # RETURNS
    # None (writes file).

    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "target", "loss_pct",
            "offset_ms_mean", "offset_ms_jitter",
            "delay_ms_mean", "delay_ms_jitter",
            "ok", "samples"
        ])
        for r in ntp_records:
            w.writerow([
                r["target"],
                f'{r["loss_pct"]:.1f}',
                "" if r["offset_ms_mean"] is None else f'{r["offset_ms_mean"]:.3f}',
                "" if r["offset_ms_jitter"] is None else f'{r["offset_ms_jitter"]:.3f}',
                "" if r["delay_ms_mean"] is None else f'{r["delay_ms_mean"]:.3f}',
                "" if r["delay_ms_jitter"] is None else f'{r["delay_ms_jitter"]:.3f}',
                r["ok"],
                r["samples"],
            ])


def write_ping_csv(path: Path, ping_records: List[Dict[str, object]]) -> None:
    # PURPOSE
    # Write ping measurements to CSV.

    # RETURNS
    # None (writes file).

    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "avg_ms", "mdev_ms", "loss_pct"])
        for r in ping_records:
            w.writerow([r["src"], r["dst"], r["avg_ms"], r["mdev_ms"], r["loss_pct"]])
            
def get_results_dir() -> Path:
    # Decide where results should be written.

    # Priority:
    # 1) RESULTS_DIR env var (Docker/K8s)
    # 2) ./results (local dev)

    env = os.environ.get("RESULTS_DIR")
    if env:
        return Path(env)
    return Path.cwd() / "results"

def main() -> None:
    # PURPOSE
    # End-to-end run:
    #   1) Read targets from env
    #   2) Create a timestamped results directory
    #   3) Probe each target via NTP multiple times
    #   4) Optionally ping each target
    #   5) Write JSON + CSV summaries

    # KUBERNETES PATTERN
    # Mount /results to a PVC (or use emptyDir and kubectl cp results out)
    # Run as a Job for one-shot measurements, or Deployment for periodic runs.

    targets = get_targets_from_env()

    samples = int(os.environ.get("NTP_SAMPLES", "10"))
    ntp_timeout = float(os.environ.get("NTP_TIMEOUT", "1.0"))

    do_ping = os.environ.get("DO_PING", "1") == "1"
    ping_count = int(os.environ.get("PING_COUNT", "5"))

    # Where to write outputs inside container
    base_results = get_results_dir()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = base_results / f"results_{run_id}"
    outdir.mkdir(parents=True, exist_ok=True)

    # Record targets used for reproducibility
    (outdir / "targets.txt").write_text("\n".join(targets) + "\n")

    print(f"Targets: {targets}")
    print(f"Writing results to: {outdir}")

    # NTP probe phase
    ntp_records: List[Dict[str, object]] = []
    for t in targets:
        print(f"[NTP] probing {t}")
        ntp_records.append(ntp_probe(t, samples=samples, timeout_sec=ntp_timeout))

    write_json(outdir / "ntp.json", ntp_records)
    write_ntp_csv(outdir / "ntp_summary.csv", ntp_records)

    # Ping phase (collector->targets baseline)
    ping_records: List[Dict[str, object]] = []
    if do_ping:
        for t in targets:
            if t == "localhost":
                continue
            print(f"[PING] collector -> {t}")
            ping_records.append(ping_target(t, count=ping_count))

        write_json(outdir / "ping.json", ping_records)
        write_ping_csv(outdir / "ping_summary.csv", ping_records)

    print("Collection complete.")


if __name__ == "__main__":
    main()
