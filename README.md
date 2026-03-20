# NTP-Stats

## Overview

This project implements a distributed system for measuring and visualizing clock synchronization performance across geographically distributed nodes using Network Time Protocol (NTP). It is deployed on the [Nautilus NRP](https://nautilus.optiputer.net/) research cluster (namespace: `cmpm118`).

The system collects metrics from multiple nodes across the United States, aggregates them into a unified API, and feeds a real-time monitoring dashboard. The goal is to evaluate how geographic distance affects NTP synchronization quality — measuring offset, jitter, delay, and packet loss from both East and West Coast vantage points.

## Research Motivation

Network time synchronization is critical for distributed systems. This project investigates:

1. How geographic distance affects NTP latency and jitter
2. How different NTP servers (Cloudflare, Google, NIST, pool.ntp.org) perform from different US regions
3. How clock offset varies across nodes on the Nautilus research network

Key finding: West Coast nodes show approximately 10ms lower delay than East Coast nodes when reaching the same NTP servers, consistent with the physical location of our internal time server at San Diego State University.

## System Architecture

The system has three layers deployed on Nautilus NRP:

```
Browser / Frontend
       │
       ▼
Aggregator API (port 8001)
       │
       ├── ntp-collector-0       ← Georgia Tech, Atlanta GA
       ├── ntp-collector-1       ← San Diego State University, CA
       ├── ntp-collector-2       ← SDSC, San Diego CA
       ├── time-monitor-east     ← Spelman College, Atlanta GA
       └── time-monitor-west     ← San Diego State University, CA
```

### 1. Aggregator — `backend/aggregator/`

Built with FastAPI, Uvicorn, HTTPX, asyncio, and Python 3.

Responsibilities:
- Poll all collector and monitor nodes asynchronously on every request
- Aggregate synchronization metrics across all 5 nodes
- Provide a unified REST endpoint for the frontend at `/api/ntp/dashboard`

Metrics collected: clock offset, network jitter, round-trip delay, packet loss.

### 2. Collector Nodes — `backend/collector/`

Built with Python, ntplib, FastAPI, and statistics.

Three StatefulSet replicas deployed across Nautilus nodes, each probing `pool.ntp.org` once per second and exposing results at `/metrics`.

### 3. Geographic Monitor Nodes — `monitor/`

Built with Python, ntplib, socket, and threading.

Two Deployment pods pinned to specific geographic regions via Kubernetes `nodeAffinity`:

- **time-monitor-east** — pinned to `us-east` nodes, currently running at Spelman College, Atlanta GA
- **time-monitor-west** — pinned to `us-west` nodes, currently running at San Diego State University, CA

Each monitor probes four NTP targets every 10 seconds:
- `time.cloudflare.com` — Cloudflare Anycast NTP
- `time.google.com` — Google NTP
- `time.nist.gov` — NIST Time Server
- `pool.ntp.org` — NTP Pool

Metrics are stored in a local SQLite database and served via a `/metrics` endpoint compatible with the aggregator's collector format, and a `/metrics/by-target` endpoint for per-server breakdown.

### 4. Frontend Dashboard — `frontend/`

Built with React and Vite.

Features:
- Live clock offset history chart, updating every 2 seconds
- Node metrics table with location, status, offset, jitter, delay, and packet loss per node
- Geographic latency comparison showing East vs West delay and jitter side by side
- System status panel
- All 5 nodes visible: 3 collectors and 2 geographic monitors

## Deployment on Nautilus NRP

### Prerequisites
- `kubectl` configured with access to the `cmpm118` namespace
- Docker Hub access to push images

### Deploy the monitor pods

```bash
cd monitor
docker buildx build --platform linux/amd64,linux/arm64 \
  -t paulleeisme06/ntp-monitor:v7 --push .
kubectl apply -f k8s/nautilus-monitor.yaml -n cmpm118
```

### Deploy the aggregator and collectors

```bash
cd backend
kubectl apply -f k8s/aggregator-deployment.yaml -n cmpm118
kubectl apply -f k8s/aggregator-service.yaml -n cmpm118
kubectl apply -f k8s/collector-statefulset.yaml -n cmpm118
kubectl apply -f k8s/collector-service.yaml -n cmpm118
```

### Verify all pods are running

```bash
kubectl get pods -n cmpm118
```

Expected: 7 pods running — 1 aggregator, 3 collectors, 1 ntp-server, 1 time-monitor-east, 1 time-monitor-west.

## Running Locally

### Connect Frontend to Live Cluster

In one terminal, start the port-forward to the live Nautilus cluster:

```bash
kubectl port-forward -n cmpm118 svc/aggregator-service 8001:8001
```

In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. Keep the port-forward terminal open — closing it will disconnect the frontend from the live cluster.

### Run the Full Stack Locally with Docker

```bash
cd backend
docker compose up --build

cd monitor
docker compose up --build

# Frontend
cd frontend
npm install
npm run dev
```

## Project Structure

```
NTP-Stats/
├── backend/                      # Aggregator and collector nodes
│   ├── aggregator/
│   │   ├── aggregator_api.py
│   │   └── Dockerfile
│   ├── collector/
│   │   ├── collector_service.py
│   │   ├── collect_ntp_latency.py
│   │   └── Dockerfile
│   ├── k8s/
│   │   ├── aggregator-deployment.yaml
│   │   ├── aggregator-service.yaml
│   │   ├── collector-statefulset.yaml
│   │   └── collector-service.yaml
│   └── docker-compose.yml
├── monitor/                      # East/West geographic monitors
│   ├── monitor.py
│   ├── server.py
│   ├── collector_api.py
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── README.md
│   └── k8s/
│       └── nautilus-monitor.yaml
└── frontend/                     # React monitoring dashboard
    ├── src/
    │   ├── App.jsx
    │   └── main.jsx
    └── package.json
```

---

&copy; 2026 Paul (Fan Sheng) Lee, Judyanna Ladella, Prithika Venkatesh. All rights reserved.
