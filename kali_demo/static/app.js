const byId = (id) => document.getElementById(id);

function empty(message) {
  const node = document.createElement("div");
  node.className = "empty";
  node.textContent = message;
  return node;
}

function text(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value ?? "";
  if (className) node.className = className;
  return node;
}

function riskClass(score) {
  if (score >= 85) return "critical";
  if (score >= 65) return "high";
  if (score >= 40) return "medium";
  return "low";
}

function renderAssets(assets) {
  const body = byId("assets-body");
  body.replaceChildren();
  if (!assets.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.append(empty("No assets stored yet."));
    row.append(cell);
    body.append(row);
    return;
  }
  assets.forEach((asset) => {
    const row = document.createElement("tr");
    row.append(text("td", asset.ip));

    const identity = document.createElement("td");
    identity.append(text("strong", asset.hostname || "Unknown"));
    identity.append(text("span", `${asset.vendor || "Unknown vendor"} · ${asset.mac || "No MAC"}`, "subtext"));
    row.append(identity);
    row.append(text("td", asset.device_type));

    const exposure = document.createElement("td");
    exposure.append(text("span", asset.ports || "No ports"));
    exposure.append(text("span", asset.protocols || "No OT protocol", "subtext"));
    row.append(exposure);

    const risk = document.createElement("td");
    risk.append(text("span", String(asset.risk_score), `risk ${riskClass(asset.risk_score)}`));
    row.append(risk);
    body.append(row);
  });
}

function renderFindings(findings) {
  const root = byId("findings");
  root.replaceChildren();
  if (!findings.length) return root.append(empty("No findings recorded."));
  findings.slice(0, 6).forEach((finding) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    head.append(text("span", finding.title));
    head.append(text("span", String(finding.risk_score), `risk ${riskClass(finding.risk_score)}`));
    item.append(head);
    item.append(text("p", `${finding.asset} · ${finding.human_explanation}`));
    root.append(item);
  });
}

function renderChanges(changes) {
  const root = byId("changes");
  root.replaceChildren();
  if (!changes.length) return root.append(empty("Baseline scenario has no synthetic changes."));
  changes.slice(0, 8).forEach((change) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    head.append(text("span", change.change_type.replaceAll("_", " ").toUpperCase()));
    head.append(text("code", change.asset_identity));
    item.append(head, text("p", change.summary));
    root.append(item);
  });
}

function renderWifi(accessPoints) {
  const root = byId("wifi");
  root.replaceChildren();
  if (!accessPoints.length) return root.append(empty("No access points recorded."));
  accessPoints.forEach((ap) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    head.append(text("span", ap.ssid));
    head.append(text("span", ap.encryption, `risk ${ap.encryption === "OPEN" ? "high" : "low"}`));
    item.append(head, text("p", `${ap.bssid} · channel ${ap.channel} · ${ap.signal_dbm} dBm`));
    root.append(item);
  });
}

function renderScans(scans) {
  const root = byId("scans");
  root.replaceChildren();
  if (!scans.length) return root.append(empty("No audits run yet."));
  scans.slice(0, 6).forEach((scan) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    head.append(text("span", scan.status.toUpperCase()));
    head.append(text("code", scan.id.slice(0, 8)));
    item.append(head, text("p", `${scan.assets_found} assets · ${scan.findings_found} findings · ${scan.profile} profile`));
    root.append(item);
  });
}

async function refresh() {
  const response = await fetch("/api/state");
  if (!response.ok) throw new Error(`State request failed (${response.status})`);
  const state = await response.json();
  const otDevices = state.assets.filter((asset) => ["PLC", "HMI", "industrial gateway"].includes(asset.device_type)).length;
  byId("metric-assets").textContent = state.assets.length;
  byId("metric-ot").textContent = otDevices;
  byId("metric-findings").textContent = state.counts.findings;
  byId("metric-changes").textContent = state.changes.length;
  byId("asset-count").textContent = state.assets.length;
  renderAssets(state.assets);
  renderFindings(state.findings);
  renderChanges(state.changes);
  renderWifi(state.access_points);
  renderScans(state.scans);
}

async function runAudit() {
  const button = byId("run-button");
  const status = byId("status");
  button.disabled = true;
  status.className = "status running";
  status.textContent = "Running offline simulation… no packets are being transmitted.";
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({scenario: byId("scenario").value}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Audit failed (${response.status})`);
    await refresh();
    status.className = "status";
    status.textContent = `Completed ${result.scenario} simulation: ${result.assets} assets and ${result.findings} findings. Scan ${result.scan_id.slice(0, 8)}.`;
  } catch (error) {
    status.className = "status error";
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

byId("run-button").addEventListener("click", runAudit);
refresh().catch((error) => {
  const status = byId("status");
  status.className = "status error";
  status.textContent = error.message;
});
