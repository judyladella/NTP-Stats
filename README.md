# NTP-Stats

## Overview

This project implements a system for measuring and visualizing clock synchronization performance across multiple devices using Network Time Protocol (NTP).

The system collects metrics from multiple nodes and clusters them into an API that feeds a real-time monitoring dashboard. The goal is to evaluate synchronization quality in our research environment involving Raspberry Pi clusters.

## Research Motivation

This project aims to:

1. Collect synchronization statistics from multiple devices
2. Aggregate these metrics in real time
3. Visualize synchronization behavior over time

## System Architecture

### 1. Backend: Aggregation and Monitoring API

Built with:

- `FastAPI`
- `Uvicorn`
- `HTTPX`
- `asyncio`
- `Python 3`

Backend responsibilities:

- Poll collector nodes asynchronously
- Aggregate synchronization metrics across devices
- Provide a unified dataset for visualization through REST endpoints

The backend collects and aggregates the following metrics:

- clock offset
- network jitter
- round-trip delay
- packet loss

Collectors are queried concurrently using `httpx.AsyncClient` to allow the system to scale efficiently across many nodes.

### 2. Collector Nodes — NTP Measurement Service

Built with:

- `Python`
- `socket`
- `statistics`
- `FastAPI`

Collector responsibilities:

- Send NTP requests to a reference time server
- Measure network timing characteristics
- Compute synchronization metrics
- Expose results through a `/metrics` API endpoint

Each collector acts as an independent monitoring node.

This architecture allows the system to be deployed across:

- Raspberry Pi clusters
- distributed servers
- Docker containers

### 3. Frontend — Real-Time Monitoring Dashboard

Built with:

- `React`
- `Vite`
- `Recharts`

Frontend responsibilities:

- Display synchronization metrics in real time
- Provide an overview of clock synchronization performance
- Displays system health classifications (Synced / Degraded / Unreachable)

The dashboard queries the collects the API periodically and updates the interface with the latest metrics.

## Running the Project
### 1. Start the Backend (Docker)

Open a terminal in the the backend directory

From the root directory of the repository, run:

```bash
docker compose up --build

```
### 2. Start the Frontend

Open a new terminal in the the frontend directory

From the root directory of the repository, run:

```bash
npm run dev

```
