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
  if (!changes.length) return root.append(empty("No baseline changes recorded."));
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
  const cancelButton = byId("cancel-button");
  const status = byId("status");
  button.disabled = true;
  cancelButton.disabled = false;
  status.className = "status running";
  status.textContent = "Running rate-limited host discovery… press Cancel to abort.";
  try {
    const response = await fetch("/api/real/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        target: byId("network").value,
        authorized: byId("authorized").checked,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Audit failed (${response.status})`);
    await refresh();
    status.className = "status";
    status.textContent = result.cancelled
      ? `Scan ${result.scan_id.slice(0, 8)} was cancelled.`
      : `Discovery complete on ${result.target}: ${result.assets} devices observed. Scan ${result.scan_id.slice(0, 8)}.`;
  } catch (error) {
    status.className = "status error";
    status.textContent = error.message;
  } finally {
    button.disabled = !byId("authorized").checked || !byId("network").value;
    cancelButton.disabled = true;
  }
}

async function loadNetworks() {
  const selector = byId("network");
  const status = byId("status");
  const response = await fetch("/api/networks");
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Could not inspect local interfaces.");
  selector.replaceChildren();
  if (!result.nmap_available) {
    throw new Error("Nmap is not installed. Run: sudo apt install nmap");
  }
  if (!result.networks.length) {
    throw new Error("No active RFC1918 IPv4 interface was found.");
  }
  result.networks.forEach((network) => {
    const option = document.createElement("option");
    option.value = network.safe_target;
    option.textContent = `${network.interface} · ${network.safe_target} · this host ${network.address}`;
    selector.append(option);
  });
  selector.disabled = false;
  status.className = "status";
  status.textContent = "Ready. Select a local network and confirm authorization.";
}

async function cancelAudit() {
  const response = await fetch("/api/cancel", {method: "POST"});
  const result = await response.json();
  byId("status").textContent = result.cancel_requested
    ? "Cancellation requested. Waiting for Nmap to stop…"
    : "No scan is currently running.";
}

byId("run-button").addEventListener("click", runAudit);
byId("cancel-button").addEventListener("click", cancelAudit);
byId("authorized").addEventListener("change", () => {
  byId("run-button").disabled = !byId("authorized").checked || byId("network").disabled;
});
refresh().catch((error) => {
  const status = byId("status");
  status.className = "status error";
  status.textContent = error.message;
});
loadNetworks().catch((error) => {
  const status = byId("status");
  status.className = "status error";
  status.textContent = error.message;
});
