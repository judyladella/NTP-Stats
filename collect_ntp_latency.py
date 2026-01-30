#!/usr/bin/env python3
"""
Collect NTP synchronization status and network latency
between nodes inside a Slurm allocation.

Design:
- Run ONE controller process (this script)
- Use `srun -w <node>` to execute commands on specific nodes
- Collect:
    * NTP status per node (chronyc / timedatectl)
    * ICMP ping RTT between node pairs
- Save structured outputs (JSON + CSV)
"""

import csv
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ---------------------------------------------------------------------
# Helper: run a shell command and capture output
# ---------------------------------------------------------------------
# def sh(cmd: str) -> Tuple[int, str]:
#     """
#     Run a shell command.
#     Returns:
#         (return_code, combined_stdout_stderr)
#     """
#     p = subprocess.run(
#         cmd,
#         shell=True,
#         text=True,
#         capture_output=True
#     )
#     out = (p.stdout + "\n" + p.stderr).strip()
#     return p.returncode, out

def sh(cmd: str) -> Tuple[int, str]:
    """
    Run a shell command.
    Automatically strips srun if running locally.
    """
    if "srun" in cmd and not os.environ.get("SLURM_NODELIST"):
        # Remove srun wrapper for local testing
        cmd = cmd.replace(
            'srun -N 1 -n 1 -w "localhost" bash -lc ',
            ''
        ).strip('"')

    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    out = (p.stdout + "\n" + p.stderr).strip()
    return p.returncode, out


# ---------------------------------------------------------------------
# Slurm node discovery
# ---------------------------------------------------------------------
# def get_nodes_from_slurm() -> List[str]:
#     """
#     Expand SLURM_NODELIST into individual hostnames.
#     This only works if the script is run inside a Slurm job/allocation.
#     """
#     nodelist = os.environ.get("SLURM_NODELIST")
#     if not nodelist:
#         raise SystemExit(
#             "SLURM_NODELIST not set. "
#             "Run inside salloc or sbatch."
#         )

#     rc, out = sh(f'scontrol show hostnames "{nodelist}"')
#     if rc != 0 or not out.strip():
#         raise SystemExit(f"Failed to expand SLURM_NODELIST: {out}")

#     return [line.strip() for line in out.splitlines() if line.strip()]

def get_nodes() -> List[str]:
    """
    Get node list from Slurm if available.
    Otherwise fall back to localhost (test mode).
    """
    nodelist = os.environ.get("SLURM_NODELIST")

    # ---- Local test mode ----
    if not nodelist:
        print("[INFO] SLURM not detected — running in local test mode")
        return ["localhost"]

    rc, out = sh(f'scontrol show hostnames "{nodelist}"')
    if rc != 0 or not out.strip():
        raise SystemExit(f"Failed to expand SLURM_NODELIST: {out}")

    return [line.strip() for line in out.splitlines() if line.strip()]



# ---------------------------------------------------------------------
# NTP parsing (chronyc output)
# ---------------------------------------------------------------------

# Regular expressions to extract useful fields from `chronyc tracking`
_TRACKING_RE = {
    "stratum": re.compile(r"^\s*Stratum\s*:\s*(\d+)\s*$", re.M),
    "last_offset": re.compile(
        r"^\s*Last offset\s*:\s*([-\d\.]+)\s*(\w+)\s*$", re.M
    ),
    "system_time": re.compile(
        r"^\s*System time\s*:\s*([-\d\.]+)\s*(\w+)\s*(fast|slow)?\s*$", re.M
    ),
    "ref_id": re.compile(r"^\s*Reference ID\s*:\s*(.+)\s*$", re.M),
}


def parse_chronyc_tracking(text: str) -> Dict[str, str]:
    """
    Parse chronyc tracking output into a dictionary.
    """
    parsed: Dict[str, str] = {}

    for key, regex in _TRACKING_RE.items():
        match = regex.search(text)
        if match:
            # Offsets have a number + unit (e.g. ms, us)
            if key in ("last_offset", "system_time"):
                parsed[key] = f"{match.group(1)} {match.group(2)}"
            else:
                parsed[key] = match.group(1).strip()

    return parsed


def collect_ntp_for_node(node: str) -> Dict[str, object]:
    """
    Run NTP diagnostics on a single node using srun.

    Returns a dict with:
      - raw output
      - parsed key fields
      - timestamp
    """
    cmd = (
        f'srun -N 1 -n 1 -w "{node}" bash -lc '
        '"chronyc tracking 2>/dev/null || true; '
        'echo ---; '
        'timedatectl status 2>/dev/null || true"'
    )

    rc, out = sh(cmd)

    # Split at separator so chronyc output can be parsed cleanly
    tracking_part = out.split('---')[0] if '---' in out else out
    parsed = parse_chronyc_tracking(tracking_part)

    return {
        "node": node,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "parsed": parsed,
        "raw": out,
        "rc": rc,
    }


# ---------------------------------------------------------------------
# Ping parsing
# ---------------------------------------------------------------------
def parse_ping_summary(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract:
      - average RTT (ms)
      - mdev / jitter (ms)
      - packet loss (%)
    from Linux ping summary output.
    """
    avg = None
    mdev = None
    loss = None

    for line in text.splitlines():
        if "packet loss" in line:
            # Example:
            # "5 packets transmitted, 5 received, 0% packet loss, time 4006ms"
            parts = [p.strip() for p in line.split(",")]
            for p in parts:
                if "packet loss" in p:
                    loss = p.split()[0].replace("%", "")
                    break

        if line.startswith("rtt ") or "round-trip" in line:
            # Example:
            # rtt min/avg/max/mdev = 0.120/0.250/0.400/0.050 ms
            rhs = line.split("=")[-1].strip()
            nums = rhs.split()[0].split("/")
            if len(nums) >= 4:
                avg = nums[1]
                mdev = nums[3]

    return avg, mdev, loss


def ping_from_to(src: str, dst: str,
                 count: int = 5,
                 timeout_sec: int = 1) -> Dict[str, object]:
    """
    Run ping FROM src node TO dst node using srun.

    Returns structured latency metrics.
    """
    cmd = (
        f'srun -N 1 -n 1 -w "{src}" bash -lc '
        f'"ping -c {count} -q -W {timeout_sec} {dst} || true"'
    )

    rc, out = sh(cmd)
    avg, mdev, loss = parse_ping_summary(out)

    return {
        "src": src,
        "dst": dst,
        "avg_ms": avg if avg else "NA",
        "mdev_ms": mdev if mdev else "NA",
        "loss_pct": loss if loss else "NA",
        "raw": out,
        "rc": rc,
    }


# ---------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------
def main() -> None:
    """
    Orchestrates the entire measurement run.
    """
    # nodes = get_nodes_from_slurm()
    nodes = get_nodes()

    # Timestamped output directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(f"results_{run_id}")
    (outdir / "ntp").mkdir(parents=True, exist_ok=True)

    # Save node list
    (outdir / "nodes.txt").write_text("\n".join(nodes) + "\n")

    print(f"Nodes: {len(nodes)}")
    print(f"Output directory: {outdir}")

    # -------------------------------
    # Collect NTP info (per node)
    # -------------------------------
    ntp_records = []

    for node in nodes:
        print(f"[NTP] Collecting from {node}")
        rec = collect_ntp_for_node(node)
        ntp_records.append(rec)

        # Save raw + parsed NTP info as JSON
        (outdir / "ntp" / f"{node}.json").write_text(
            json.dumps(rec, indent=2) + "\n"
        )

    # Write a summarized CSV for quick inspection
    with (outdir / "ntp_summary.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "node", "stratum", "last_offset", "system_time", "ref_id"
        ])
        for rec in ntp_records:
            p = rec.get("parsed", {})
            writer.writerow([
                rec["node"],
                p.get("stratum", ""),
                p.get("last_offset", ""),
                p.get("system_time", ""),
                p.get("ref_id", ""),
            ])

    # -------------------------------
    # Collect network latency matrix
    # -------------------------------
    # WARNING: O(n²). Large node counts can generate lots of traffic.
    with (outdir / "ping_matrix.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["src", "dst", "avg_ms", "mdev_ms", "loss_pct"])

        for src in nodes:
            for dst in nodes:
                if src == dst:
                    writer.writerow([src, dst, "0", "0", "0"])
                    continue

                print(f"[PING] {src} → {dst}")
                r = ping_from_to(src, dst)
                writer.writerow([
                    r["src"],
                    r["dst"],
                    r["avg_ms"],
                    r["mdev_ms"],
                    r["loss_pct"],
                ])

    print("Collection complete.")


if __name__ == "__main__":
    main()

