import { useState, useEffect } from "react";
const API_BASE = import.meta?.env?.VITE_API_BASE || "http://localhost:8001";
const DASHBOARD_URL = `${API_BASE}/api/ntp/dashboard?windowSec=60&historySec=300`;

// ─────────────────────────────────────────────
// NODE LOCATION MAP
// ─────────────────────────────────────────────
const NODE_LOCATIONS = {
  "ntp-collector-0": "Georgia Tech, Atlanta GA",
  "ntp-collector-1": "San Diego State University, CA",
  "ntp-collector-2": "SDSC, San Diego CA",
  "time-monitor-east": "Spelman College, Atlanta GA",
  "time-monitor-west": "San Diego State University, CA",
};

// ─────────────────────────────────────────────
// DUMMY DATA
// ─────────────────────────────────────────────
const DUMMY_NTP = [
  { target: "node-01.lan", timestamp: "2026-02-08T23:24:16Z", samples: 10, ok: 9,  timeouts: 1,  loss_pct: 10.0,  offset_ms_mean: 0.42,  offset_ms_jitter: 0.07, delay_ms_mean: 1.23, delay_ms_jitter: 0.05 },
  { target: "node-02.lan", timestamp: "2026-02-08T23:24:17Z", samples: 10, ok: 10, timeouts: 0,  loss_pct: 0.0,   offset_ms_mean: -0.18, offset_ms_jitter: 0.03, delay_ms_mean: 0.98, delay_ms_jitter: 0.02 },
  { target: "node-03.lan", timestamp: "2026-02-08T23:24:17Z", samples: 10, ok: 7,  timeouts: 3,  loss_pct: 30.0,  offset_ms_mean: 1.87,  offset_ms_jitter: 0.44, delay_ms_mean: 3.11, delay_ms_jitter: 0.21 },
  { target: "localhost",   timestamp: "2026-02-08T23:24:16Z", samples: 10, ok: 0,  timeouts: 10, loss_pct: 100.0, offset_ms_mean: null,  offset_ms_jitter: null, delay_ms_mean: null, delay_ms_jitter: null },
];

const OFFSET_HISTORY = [
  { t: "23:20", "node-01.lan": 0.38, "node-02.lan": -0.21, "node-03.lan": 1.92 },
  { t: "23:21", "node-01.lan": 0.41, "node-02.lan": -0.19, "node-03.lan": 1.75 },
  { t: "23:22", "node-01.lan": 0.39, "node-02.lan": -0.20, "node-03.lan": 2.10 },
  { t: "23:23", "node-01.lan": 0.44, "node-02.lan": -0.17, "node-03.lan": 1.88 },
  { t: "23:24", "node-01.lan": 0.42, "node-02.lan": -0.18, "node-03.lan": 1.87 },
];

const CLUSTERS = [
  { id: "cls-01", name: "Cluster Alpha", nodes: 8,  cores: 128, ram: "512 GB" },
  { id: "cls-02", name: "Cluster Beta",  nodes: 4,  cores: 64,  ram: "256 GB" },
  { id: "cls-03", name: "Cluster Gamma", nodes: 16, cores: 256, ram: "1 TB"   },
];

const DUMMY_RESERVATIONS = [
  { id: 1, email: "alice@lab.edu", cluster: "Cluster Alpha", start: "2026-03-04T09:00", end: "2026-03-04T12:00", status: "Active"   },
  { id: 2, email: "bob@lab.edu",   cluster: "Cluster Beta",  start: "2026-03-04T13:00", end: "2026-03-04T15:00", status: "Active"   },
  { id: 3, email: "carol@lab.edu", cluster: "Cluster Gamma", start: "2026-03-05T08:00", end: "2026-03-05T10:00", status: "Upcoming" },
];

const CHART_COLORS = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#e11d48"];

// ─────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────
function statusOf(node) {
  if (node.loss_pct === 100) return "Unreachable";
  if (node.loss_pct > 20 || Math.abs(node.offset_ms_mean ?? 0) > 15) return "Degraded";
  return "Synced";
}
function fmt(v, unit = "") {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(2)}${unit}`;
}

const BADGE = {
  Synced:      { bg: "#f0fdf4", color: "#15803d", border: "#bbf7d0" },
  Degraded:    { bg: "#fff7ed", color: "#c2410c", border: "#fed7aa" },
  Unreachable: { bg: "#fef2f2", color: "#b91c1c", border: "#fecaca" },
  Active:      { bg: "#eff6ff", color: "#1d4ed8", border: "#bfdbfe" },
  Upcoming:    { bg: "#f5f3ff", color: "#6d28d9", border: "#ddd6fe" },
  Available:   { bg: "#f0fdf4", color: "#15803d", border: "#bbf7d0" },
  "In Use":    { bg: "#fff7ed", color: "#c2410c", border: "#fed7aa" },
};

function Badge({ label }) {
  const s = BADGE[label] ?? { bg: "#f3f4f6", color: "#374151", border: "#e5e7eb" };
  return (
    <span style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}`, borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 500, whiteSpace: "nowrap" }}>
      {label}
    </span>
  );
}

function Card({ children, style = {} }) {
  return <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 10, ...style }}>{children}</div>;
}

function SectionTitle({ children }) {
  return <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 14 }}>{children}</div>;
}

// ─────────────────────────────────────────────
// OFFSET CHART — supports selectable metric
// ─────────────────────────────────────────────
function MetricChart({ history }) {
  // history is now { nodeName: [{t, y}, ...], ... }
  const nodeNames = Object.keys(history);
  if (nodeNames.length === 0) return (
    <div style={{ color: "#9ca3af", fontSize: 12, padding: 20 }}>Waiting for data...</div>
  );

  const w = 600, h = 140, pad = { l: 44, r: 16, t: 12, b: 28 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;

  const allVals = nodeNames.flatMap(n => history[n].map(p => p.y));
  if (allVals.length === 0) return null;

  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const range = maxV - minV || 1;
  const yOf = v => pad.t + ih - ((v - minV) / range) * ih;

  // Each node has its own x scale based on its own point count
  const xOf = (i, total) => pad.l + (i / Math.max(total - 1, 1)) * iw;

  // X axis labels: use the node with most points
  const longestNode = nodeNames.reduce((a, b) => history[a].length >= history[b].length ? a : b);
  const xLabels = history[longestNode];

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ overflow: "visible" }}>
        {[0, 0.5, 1].map(f => {
          const y = pad.t + ih * (1 - f);
          return <g key={f}>
            <line x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="#e5e7eb" strokeWidth="1" />
            <text x={pad.l - 6} y={y + 4} textAnchor="end" fill="#9ca3af" fontSize="10" fontFamily="'DM Mono',monospace">
              {(minV + range * f).toFixed(1)}
            </text>
          </g>;
        })}
        {xLabels.map((p, i) => (
          <text key={i} x={xOf(i, xLabels.length)} y={h - 6} textAnchor="middle" fill="#9ca3af" fontSize="9" fontFamily="'DM Mono',monospace">
            {p.t}
          </text>
        ))}
        {nodeNames.map((n, ni) => {
          const pts = history[n];
          if (!pts || pts.length === 0) return null;
          const polyPts = pts.map((p, i) => `${xOf(i, pts.length)},${yOf(p.y)}`).join(" ");
          return <g key={n}>
            <polyline points={polyPts} fill="none" stroke={CHART_COLORS[ni % CHART_COLORS.length]} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {pts.map((p, i) => (
              <circle key={i} cx={xOf(i, pts.length)} cy={yOf(p.y)} r="3" fill="white" stroke={CHART_COLORS[ni % CHART_COLORS.length]} strokeWidth="1.5" />
            ))}
          </g>;
        })}
      </svg>
      <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
        {nodeNames.map((n, i) => (
          <div key={n} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#6b7280" }}>
            <div style={{ width: 12, height: 2, background: CHART_COLORS[i % CHART_COLORS.length], borderRadius: 1 }} />{n}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// GEOGRAPHIC COMPARISON
// ─────────────────────────────────────────────
function GeoComparisonSection({ eastNode, westNode }) {
  if (!eastNode || !westNode) return null;

  const diff = ((eastNode.delayMs ?? 0) - (westNode.delayMs ?? 0)).toFixed(1);
  const eastFaster = parseFloat(diff) < 0;

  const metrics = [
    { label: "Avg Delay",  east: eastNode.delayMs,               west: westNode.delayMs,               unit: "ms", max: Math.max(eastNode.delayMs ?? 0, westNode.delayMs ?? 0, 1) },
    { label: "Jitter",     east: eastNode.jitterMs,              west: westNode.jitterMs,              unit: "ms", max: Math.max(eastNode.jitterMs ?? 0, westNode.jitterMs ?? 0, 1) },
    { label: "Offset",     east: Math.abs(eastNode.offsetMs ?? 0), west: Math.abs(westNode.offsetMs ?? 0), unit: "ms", max: Math.max(Math.abs(eastNode.offsetMs ?? 0), Math.abs(westNode.offsetMs ?? 0), 1) },
  ];

  return (
    <Card style={{ padding: "20px 24px", marginBottom: 20 }}>
      <SectionTitle>Geographic Latency Comparison — East vs West</SectionTitle>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 20 }}>
        {[
          { label: "East Coast Delay", value: `${(eastNode.delayMs ?? 0).toFixed(1)} ms`, color: "#2563eb" },
          { label: "West Coast Delay", value: `${(westNode.delayMs ?? 0).toFixed(1)} ms`, color: "#16a34a" },
          { label: "East−West Diff",   value: `${Math.abs(parseFloat(diff)).toFixed(1)} ms ${eastFaster ? "faster East" : "faster West"}`, color: eastFaster ? "#2563eb" : "#16a34a" },
        ].map(c => (
          <div key={c.label} style={{ background: "#f9fafb", borderRadius: 8, padding: "14px 16px", border: "1px solid #e5e7eb" }}>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: c.color, fontFamily: "'DM Mono', monospace" }}>{c.value}</div>
          </div>
        ))}
      </div>

      {metrics.map(m => (
        <div key={m.label} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: "#374151", marginBottom: 8 }}>{m.label}</div>
          {[{ label: "East", value: m.east, color: "#2563eb" }, { label: "West", value: m.west, color: "#16a34a" }].map(side => (
            <div key={side.label} style={{ marginBottom: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: side.color, flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: "#6b7280", width: 40 }}>{side.label}</span>
                <div style={{ flex: 1, background: "#f3f4f6", borderRadius: 4, height: 10, overflow: "hidden" }}>
                  <div style={{ width: `${((side.value ?? 0) / m.max) * 100}%`, background: side.color, height: "100%", borderRadius: 4, transition: "width 0.5s ease" }} />
                </div>
                <span style={{ fontSize: 11, fontFamily: "'DM Mono', monospace", color: "#374151", width: 65, textAlign: "right" }}>
                  {side.value != null ? `${side.value.toFixed(1)} ${m.unit}` : "—"}
                </span>
              </div>
            </div>
          ))}
          <div style={{ height: 1, background: "#f3f4f6", marginTop: 10 }} />
        </div>
      ))}

      <div style={{ display: "flex", gap: 24, marginTop: 4 }}>
        {[
          { region: "East", location: "Spelman College, Atlanta GA",       color: "#2563eb" },
          { region: "West", location: "San Diego State University, CA",    color: "#16a34a" },
        ].map(n => (
          <div key={n.region} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "#9ca3af" }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: n.color }} />
            <span style={{ color: n.color, fontWeight: 500 }}>{n.region}</span>
            <span>{n.location}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────
// PAGE: DASHBOARD
// ─────────────────────────────────────────────
function DashboardPage() {
  const [nodes, setNodes] = useState(DUMMY_NTP);
  const [offsetHistory, setOffsetHistory] = useState({});
  const [systemStatus, setSystemStatus] = useState([
    { label: "PTP Grandmaster", val: "Online"  },
    { label: "Chrony",          val: "Running" },
    { label: "GNSS MAX-M10S",   val: "Locked"  },
    { label: "USB-ETH Dongle",  val: "Active"  },
    { label: "PPS Signal",      val: "1 Hz"    },
    { label: "Collector",       val: "Polling" },
  ]);

  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      try {
        setErr("");
        const res = await fetch(DASHBOARD_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        const mappedNodes = (data.nodeMetrics || []).map((n) => ({
          target: n.target,
          timestamp: new Date(data.metadata?.updatedAt || Date.now()).toISOString(),
          samples: n.total ?? 0,
          ok: n.ok ?? 0,
          timeouts: (n.total ?? 0) - (n.ok ?? 0),
          loss_pct: n.lossPct ?? 100.0,
          offset_ms_mean: n.offsetMs ?? null,
          offset_ms_jitter: n.jitterMs ?? null,
          delay_ms_mean: n.delayMs ?? null,
          delay_ms_jitter: null,
        }));

        const series = data.offsetHistory?.series || [];

        const perNodeSeries = {};
        for (const s of series) {
          const pts = (s.points || [])
            .filter(p => p.t >= (Date.now() - 300 * 1000) && p.y !== null)
            .slice(-10)
            .map(p => ({
              t: new Date(p.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }),
              y: p.y
            }));
          if (pts.length > 0) perNodeSeries[s.node] = pts;
        }

        const mappedStatus = (data.systemStatus || []).map((x) => ({
          label: x.name,
          val: x.state
        }));

        if (!alive) return;
        setNodes(mappedNodes);
        if (Object.keys(perNodeSeries).length) setOffsetHistory(perNodeSeries);
        if (mappedStatus.length) setSystemStatus(mappedStatus);
        setLoading(false);

      } catch (e) {
        if (!alive) return;
        setErr(e.message || "Failed to load dashboard");
        setLoading(false);
      }
    }

    load();
    const id = setInterval(load, 2000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const counts = {
    total:       nodes.length,
    synced:      nodes.filter(n => statusOf(n) === "Synced").length,
    degraded:    nodes.filter(n => statusOf(n) === "Degraded").length,
    unreachable: nodes.filter(n => statusOf(n) === "Unreachable").length,
  };

  const eastNode = nodes.find(n => n.target === "time-monitor-east");
  const westNode = nodes.find(n => n.target === "time-monitor-west");

  // Convert nodes to aggregator shape for geo section
  const eastAgg = eastNode ? { target: eastNode.target, delayMs: eastNode.delay_ms_mean, jitterMs: eastNode.offset_ms_jitter, offsetMs: eastNode.offset_ms_mean } : null;
  const westAgg = westNode ? { target: westNode.target, delayMs: westNode.delay_ms_mean, jitterMs: westNode.offset_ms_jitter, offsetMs: westNode.offset_ms_mean } : null;

  return (
    <div style={{ animation: "fadeIn 0.25s ease" }}>
      {err && <div style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c", borderRadius: 8, padding: "10px 16px", marginBottom: 16, fontSize: 13 }}>{err}</div>}

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 22 }}>
        {[
          { label: "Total Nodes",  value: counts.total,       color: "#111827" },
          { label: "Synced",       value: counts.synced,      color: "#15803d" },
          { label: "Degraded",     value: counts.degraded,    color: "#c2410c" },
          { label: "Unreachable",  value: counts.unreachable, color: "#b91c1c" },
        ].map(c => (
          <Card key={c.label} style={{ padding: "18px 20px" }}>
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 6 }}>{c.label}</div>
            <div style={{ fontSize: 32, fontWeight: 700, color: c.color, lineHeight: 1, fontFamily: "'DM Mono',monospace" }}>{c.value}</div>
          </Card>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", gap: 16, marginBottom: 20 }}>
        {/* Chart with metric selector */}
        <Card style={{ padding: "20px 22px" }}>
          <SectionTitle>Clock Offset History (ms)</SectionTitle>
          <MetricChart history={offsetHistory} />
        </Card>

        {/* System status */}
        <Card style={{ padding: "20px 22px" }}>
          {systemStatus.map((item) => (
            <div key={item.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 0", borderBottom: "1px solid #f3f4f6" }}>
              <span style={{ fontSize: 12, color: "#374151" }}>{item.label}</span>
              <span style={{ fontSize: 11, color: "#15803d", fontWeight: 500 }}>{item.val}</span>
            </div>
          ))}
        </Card>
      </div>

      {/* Node table */}
      <Card style={{ marginBottom: 20 }}>
        <div style={{ padding: "16px 22px", borderBottom: "1px solid #f3f4f6" }}>
          <SectionTitle>Node Metrics</SectionTitle>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                {["Target", "Location", "Status", "Offset (ms)", "Jitter (ms)", "Delay (ms)", "Loss %", "OK / Total"].map(h => (
                  <th key={h} style={{ padding: "10px 22px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "#6b7280", letterSpacing: "0.04em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {nodes.map(node => {
                const st = statusOf(node);
                const isSelected = selected === node.target;
                const location = NODE_LOCATIONS[node.target] || "—";
                return (
                  <>
                    <tr key={node.target} onClick={() => setSelected(isSelected ? null : node.target)}
                      style={{ borderTop: "1px solid #f3f4f6", cursor: "pointer", background: isSelected ? "#f8faff" : "white" }}>
                      <td style={{ padding: "12px 22px", fontWeight: 500, color: "#111827", fontFamily: "'DM Mono',monospace", fontSize: 12 }}>{node.target}</td>
                      <td style={{ padding: "12px 22px", fontSize: 12, color: "#6b7280" }}>{location}</td>
                      <td style={{ padding: "12px 22px" }}><Badge label={st} /></td>
                      <td style={{ padding: "12px 22px", color: node.offset_ms_mean !== null ? (Math.abs(node.offset_ms_mean) > 1 ? "#c2410c" : "#111827") : "#9ca3af", fontFamily: "'DM Mono',monospace" }}>{fmt(node.offset_ms_mean)}</td>
                      <td style={{ padding: "12px 22px", fontFamily: "'DM Mono',monospace", color: "#374151" }}>{fmt(node.offset_ms_jitter)}</td>
                      <td style={{ padding: "12px 22px", fontFamily: "'DM Mono',monospace", color: "#374151" }}>{fmt(node.delay_ms_mean)}</td>
                      <td style={{ padding: "12px 22px", fontFamily: "'DM Mono',monospace", color: node.loss_pct > 0 ? (node.loss_pct === 100 ? "#b91c1c" : "#c2410c") : "#15803d" }}>{node.loss_pct.toFixed(1)}%</td>
                      <td style={{ padding: "12px 22px", fontFamily: "'DM Mono',monospace", color: "#6b7280" }}>{node.ok} / {node.samples}</td>
                    </tr>
                    {isSelected && (
                      <tr key={node.target + "-exp"} style={{ background: "#f8faff", borderTop: "1px solid #e0eaff" }}>
                        <td colSpan={8} style={{ padding: "12px 22px 16px" }}>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }}>
                            {[
                              ["Timestamp",    new Date(node.timestamp).toLocaleString()],
                              ["Timeouts",     node.timeouts],
                              ["Delay Jitter", fmt(node.delay_ms_jitter, " ms")],
                              ["Offset Jitter",fmt(node.offset_ms_jitter, " ms")],
                            ].map(([l, v]) => (
                              <div key={l}>
                                <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 3 }}>{l}</div>
                                <div style={{ fontSize: 12, color: "#374151", fontFamily: "'DM Mono',monospace" }}>{v}</div>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Geographic comparison */}
      <GeoComparisonSection eastNode={eastAgg} westNode={westAgg} />

    </div>
  );
}

// ─────────────────────────────────────────────
// PAGE: CLUSTER RESERVATION
// ─────────────────────────────────────────────
function ReservationPage() {
  const [reservations, setReservations] = useState(DUMMY_RESERVATIONS);
  const [form, setForm] = useState({ email: "", cluster: CLUSTERS[0].id, start: "", end: "" });
  const [error, setError]     = useState("");
  const [success, setSuccess] = useState("");

  function isOverlapping(newStart, newEnd, clusterId) {
    const name = CLUSTERS.find(c => c.id === clusterId)?.name;
    return reservations.some(r => r.cluster === name && new Date(newStart) < new Date(r.end) && new Date(newEnd) > new Date(r.start));
  }

  function handleSubmit() {
    setError(""); setSuccess("");
    if (!form.email || !form.start || !form.end) { setError("All fields are required."); return; }
    if (new Date(form.start) >= new Date(form.end)) { setError("End time must be after start time."); return; }
    if (isOverlapping(form.start, form.end, form.cluster)) { setError("This cluster is already reserved for that time slot."); return; }
    const name = CLUSTERS.find(c => c.id === form.cluster)?.name;
    setReservations(prev => [...prev, { id: Date.now(), email: form.email, cluster: name, start: form.start, end: form.end, status: "Upcoming" }]);
    setSuccess(`Reservation confirmed — ${name} for ${form.email}`);
    setForm({ email: "", cluster: CLUSTERS[0].id, start: "", end: "" });
  }

  function isAvailable(id) {
    const name = CLUSTERS.find(c => c.id === id)?.name;
    const now = new Date();
    return !reservations.some(r => r.cluster === name && new Date(r.start) <= now && new Date(r.end) >= now);
  }

  const inputStyle = { width: "100%", border: "1px solid #d1d5db", borderRadius: 7, padding: "8px 11px", fontSize: 13, fontFamily: "inherit", color: "#111827", background: "white", outline: "none" };

  return (
    <div style={{ animation: "fadeIn 0.25s ease" }}>
      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 20, marginBottom: 22 }}>
        <Card style={{ padding: "22px 24px" }}>
          <SectionTitle>New Reservation</SectionTitle>
          {error   && <div style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c", borderRadius: 7, padding: "9px 13px", fontSize: 12, marginBottom: 14 }}>{error}</div>}
          {success && <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#15803d", borderRadius: 7, padding: "9px 13px", fontSize: 12, marginBottom: 14 }}>{success}</div>}
          {[
            { label: "Email address", key: "email", type: "email",          placeholder: "you@institution.edu" },
            { label: "Start time",    key: "start", type: "datetime-local", placeholder: "" },
            { label: "End time",      key: "end",   type: "datetime-local", placeholder: "" },
          ].map(f => (
            <div key={f.key} style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#374151", marginBottom: 5 }}>{f.label}</label>
              <input type={f.type} placeholder={f.placeholder} value={form[f.key]}
                onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))} style={inputStyle} />
            </div>
          ))}
          <div style={{ marginBottom: 18 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#374151", marginBottom: 5 }}>Cluster</label>
            <select value={form.cluster} onChange={e => setForm(p => ({ ...p, cluster: e.target.value }))} style={inputStyle}>
              {CLUSTERS.map(c => <option key={c.id} value={c.id}>{c.name} — {c.cores} cores / {c.ram}</option>)}
            </select>
          </div>
          <button onClick={handleSubmit}
            style={{ width: "100%", background: "#1d4ed8", color: "white", border: "none", borderRadius: 7, padding: "10px", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>
            Reserve Cluster
          </button>
        </Card>

        <Card style={{ padding: "22px 24px" }}>
          <SectionTitle>Cluster Availability</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {CLUSTERS.map(c => (
              <div key={c.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", border: "1px solid #e5e7eb", borderRadius: 8 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#111827", marginBottom: 3 }}>{c.name}</div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>{c.nodes} nodes · {c.cores} cores · {c.ram}</div>
                </div>
                <Badge label={isAvailable(c.id) ? "Available" : "In Use"} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <div style={{ padding: "16px 22px", borderBottom: "1px solid #f3f4f6" }}>
          <SectionTitle>All Reservations</SectionTitle>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                {["Email", "Cluster", "Start", "End", "Status", ""].map(h => (
                  <th key={h} style={{ padding: "10px 22px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "#6b7280", letterSpacing: "0.04em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reservations.length === 0 && (
                <tr><td colSpan={6} style={{ padding: "28px", textAlign: "center", color: "#9ca3af" }}>No reservations yet.</td></tr>
              )}
              {reservations.map(r => (
                <tr key={r.id} style={{ borderTop: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "12px 22px", color: "#111827" }}>{r.email}</td>
                  <td style={{ padding: "12px 22px", fontWeight: 500, color: "#374151" }}>{r.cluster}</td>
                  <td style={{ padding: "12px 22px", color: "#6b7280", fontSize: 12, fontFamily: "'DM Mono',monospace" }}>{new Date(r.start).toLocaleString()}</td>
                  <td style={{ padding: "12px 22px", color: "#6b7280", fontSize: 12, fontFamily: "'DM Mono',monospace" }}>{new Date(r.end).toLocaleString()}</td>
                  <td style={{ padding: "12px 22px" }}><Badge label={r.status} /></td>
                  <td style={{ padding: "12px 22px" }}>
                    <button onClick={() => setReservations(prev => prev.filter(x => x.id !== r.id))}
                      style={{ background: "white", border: "1px solid #e5e7eb", color: "#6b7280", borderRadius: 6, padding: "4px 10px", fontSize: 11, cursor: "pointer", fontFamily: "inherit" }}>
                      Cancel
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ─────────────────────────────────────────────
// ROOT APP
// ─────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState("dashboard");

  return (
    <div style={{ minHeight: "100vh", background: "#f9fafb", fontFamily: "'DM Sans', sans-serif", color: "#111827" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #f9fafb; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        input:focus, select:focus { border-color: #93c5fd !important; box-shadow: 0 0 0 3px #eff6ff; }
        tbody tr:hover td { background: #fafafa; }
        button { transition: opacity 0.15s; }
        button:hover { opacity: 0.85; }
      `}</style>

      {/* NAVBAR */}
      <div style={{ background: "white", borderBottom: "1px solid #e5e7eb", padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between", height: 56, position: "sticky", top: 0, zIndex: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 30, height: 30, background: "#1d4ed8", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="5" stroke="white" strokeWidth="1.5"/>
              <line x1="7" y1="3" x2="7" y2="7" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
              <line x1="7" y1="7" x2="10" y2="9" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span style={{ fontSize: 15, fontWeight: 700, color: "#111827" }}>Time Sync Platform</span>
        </div>

        <div style={{ display: "flex", gap: 2, background: "#f3f4f6", borderRadius: 8, padding: 3 }}>
          {[{ key: "dashboard", label: "NTP Dashboard" }, { key: "reservation", label: "Cluster Reservation" }].map(tab => (
            <button key={tab.key} onClick={() => setPage(tab.key)}
              style={{ background: page === tab.key ? "white" : "transparent", border: "none", color: page === tab.key ? "#111827" : "#6b7280", borderRadius: 6, padding: "6px 16px", fontSize: 13, fontWeight: page === tab.key ? 600 : 400, fontFamily: "inherit", cursor: "pointer", boxShadow: page === tab.key ? "0 1px 3px rgba(0,0,0,0.08)" : "none" }}>
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ fontSize: 12, color: "#9ca3af" }}>
          Updated · {new Date().toLocaleTimeString()}
        </div>
      </div>

      {/* PAGE */}
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "28px 24px" }}>
        {page === "dashboard"   && <DashboardPage />}
        {page === "reservation" && <ReservationPage />}
      </div>

      <div style={{ textAlign: "center", padding: "16px", fontSize: 11, color: "#d1d5db" }}>
        Time Sync Platform · NRP Nautilus · Live Data
      </div>
    </div>
  );
}