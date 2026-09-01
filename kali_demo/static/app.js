const byId = (id) => document.getElementById(id);
let operationBusy = false;
let operationCancellable = false;
let lastState = null;

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

function setStatus(message, kind = "") {
  const status = byId("status");
  status.className = `status ${kind}`.trim();
  status.textContent = message;
}

function isAuthorized() {
  return byId("authorized").checked;
}

function updateControls() {
  const unavailable = operationBusy || byId("network").disabled;
  byId("run-button").disabled = unavailable || !isAuthorized();
  byId("cancel-button").disabled = !operationBusy || !operationCancellable;
  byId("wifi-button").disabled = operationBusy || !isAuthorized() || !lastState?.current_site;
  byId("baseline-button").disabled = operationBusy || !lastState?.assets?.length;
  document.querySelectorAll(".verify-button").forEach((button) => {
    button.disabled = operationBusy || !isAuthorized();
  });
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
    cell.colSpan = 6;
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
    identity.append(text("span", `${asset.vendor || "Unknown vendor"} / ${asset.mac || "No MAC"}`, "subtext"));
    row.append(identity);
    row.append(text("td", asset.device_type));
    const exposure = document.createElement("td");
    exposure.append(text("span", asset.ports || "Not verified"));
    exposure.append(text("span", asset.services || asset.protocols || "No service evidence", "subtext"));
    row.append(exposure);
    const risk = document.createElement("td");
    risk.append(text("span", String(asset.risk_score), `risk ${riskClass(asset.risk_score)}`));
    row.append(risk);
    const action = document.createElement("td");
    const verify = text("button", "Verify services", "small-button verify-button");
    verify.type = "button";
    verify.addEventListener("click", () => verifyHost(asset.ip));
    action.append(verify);
    row.append(action);
    body.append(row);
  });
}

function renderFindings(findings) {
  const root = byId("findings");
  root.replaceChildren();
  if (!findings.length) return root.append(empty("No evidence-based findings recorded."));
  findings.slice(0, 8).forEach((finding) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    head.append(text("span", finding.title));
    head.append(text("span", String(finding.risk_score), `risk ${riskClass(finding.risk_score)}`));
    item.append(head, text("p", `${finding.asset} / ${finding.human_explanation}`));
    root.append(item);
  });
}

function renderChanges(changes) {
  const root = byId("changes");
  root.replaceChildren();
  if (!changes.length) return root.append(empty("No baseline changes recorded."));
  changes.slice(0, 10).forEach((change) => {
    const item = text("div", "", `item ${change.acknowledged_at ? "acknowledged" : ""}`);
    const head = text("div", "", "item-head");
    head.append(text("span", change.change_type.replaceAll("_", " ").toUpperCase()));
    head.append(text("code", change.asset_identity));
    item.append(head, text("p", change.summary));
    if (!change.acknowledged_at) {
      const acknowledge = text("button", "Acknowledge", "small-button subtle");
      acknowledge.type = "button";
      acknowledge.addEventListener("click", () => acknowledgeChange(change.id));
      item.append(acknowledge);
    }
    root.append(item);
  });
}

function renderWifi(accessPoints) {
  const root = byId("wifi");
  root.replaceChildren();
  if (!accessPoints.length) return root.append(empty("No access points recorded. Use Refresh Wi-Fi inventory."));
  accessPoints.forEach((ap) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    head.append(text("span", ap.ssid));
    const open = ["OPEN", "NONE"].includes(String(ap.encryption).toUpperCase());
    head.append(text("span", ap.encryption, `risk ${open ? "high" : "low"}`));
    item.append(head, text("p", `${ap.bssid} / channel ${ap.channel} / ${ap.signal_dbm} dBm`));
    root.append(item);
  });
}

function renderScans(scans) {
  const root = byId("scans");
  root.replaceChildren();
  if (!scans.length) return root.append(empty("No audits run yet."));
  scans.slice(0, 8).forEach((scan) => {
    const item = text("div", "", "item");
    const head = text("div", "", "item-head");
    const kind = scan.level === 2 ? "SERVICE VERIFY" : "HOST DISCOVERY";
    head.append(text("span", `${kind} / ${scan.status.toUpperCase()}`));
    head.append(text("code", scan.id.slice(0, 8)));
    item.append(head, text("p", `${scan.assets_found} assets / ${scan.findings_found} findings / ${scan.profile} profile`));
    root.append(item);
  });
}

function renderBaseline(baseline) {
  byId("baseline-status").textContent = baseline
    ? `${baseline.name} / ${baseline.assets} assets / ${baseline.access_points} APs / created ${new Date(baseline.created_at).toLocaleString()}`
    : "No active baseline. Run discovery, then create one.";
}

async function refresh() {
  const response = await fetch("/api/state");
  if (!response.ok) throw new Error(`State request failed (${response.status})`);
  const state = await response.json();
  lastState = state;
  const otDevices = state.assets.filter((asset) => ["PLC", "HMI", "industrial gateway"].includes(asset.device_type)).length;
  byId("metric-assets").textContent = state.assets.length;
  byId("metric-ot").textContent = otDevices;
  byId("metric-findings").textContent = state.counts.findings;
  byId("metric-changes").textContent = state.counts.changes;
  byId("asset-count").textContent = state.assets.length;
  renderAssets(state.assets);
  renderFindings(state.findings);
  renderChanges(state.changes);
  renderWifi(state.access_points);
  renderScans(state.scans);
  renderBaseline(state.baseline);
  updateControls();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
  return result;
}

async function withOperation(message, operation, cancellable = true) {
  operationBusy = true;
  operationCancellable = cancellable;
  updateControls();
  setStatus(message, "running");
  const poll = setInterval(() => refresh().catch(() => {}), 1000);
  try {
    return await operation();
  } finally {
    clearInterval(poll);
    operationBusy = false;
    operationCancellable = false;
    await refresh();
    updateControls();
  }
}

async function runAudit() {
  try {
    const result = await withOperation("Running rate-limited host discovery...", () => postJson("/api/real/run", {
      target: byId("network").value,
      authorized: isAuthorized(),
    }));
    setStatus(result.cancelled
      ? `Scan ${result.scan_id.slice(0, 8)} was cancelled.`
      : `Discovery complete: ${result.assets} devices and ${result.changes} baseline changes.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function verifyHost(host) {
  try {
    const result = await withOperation(`Checking 20 common TCP ports on ${host}...`, () => postJson("/api/real/verify", {
      host,
      authorized: isAuthorized(),
    }));
    setStatus(result.cancelled
      ? `Verification ${result.scan_id.slice(0, 8)} was cancelled.`
      : `Service verification complete for ${host}: ${result.open_ports.length} open ports recorded.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function createBaseline() {
  try {
    const result = await postJson("/api/baseline", {name: byId("baseline-name").value});
    await refresh();
    setStatus(`Baseline created with ${result.assets} assets and ${result.access_points} access points.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function refreshWifi() {
  try {
    const result = await withOperation("Reading nearby Wi-Fi inventory...", () => postJson("/api/wifi/refresh", {
      authorized: isAuthorized(),
    }), false);
    setStatus(`Wi-Fi inventory updated: ${result.access_points} access points, ${result.changes} baseline changes.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function acknowledgeChange(changeId) {
  try {
    await postJson(`/api/changes/${changeId}/acknowledge`, {});
    await refresh();
    setStatus("Baseline change acknowledged.");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function loadNetworks() {
  const selector = byId("network");
  const response = await fetch("/api/networks");
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Could not inspect local interfaces.");
  selector.replaceChildren();
  if (!result.nmap_available) throw new Error("Nmap is not installed. Install Nmap and restart the app.");
  if (!result.networks.length) throw new Error("No active RFC1918 IPv4 interface was found.");
  result.networks.forEach((network) => {
    const option = document.createElement("option");
    option.value = network.safe_target;
    option.textContent = `${network.interface} / ${network.safe_target} / this host ${network.address}`;
    selector.append(option);
  });
  selector.disabled = false;
  setStatus("Ready. Select a local network and confirm authorization.");
  updateControls();
}

async function cancelOperation() {
  const result = await postJson("/api/cancel", {});
  setStatus(result.cancel_requested ? "Cancellation requested. Waiting for Nmap to stop..." : "No scan is currently running.");
}

byId("run-button").addEventListener("click", runAudit);
byId("cancel-button").addEventListener("click", cancelOperation);
byId("baseline-button").addEventListener("click", createBaseline);
byId("wifi-button").addEventListener("click", refreshWifi);
byId("authorized").addEventListener("change", updateControls);

refresh().catch((error) => setStatus(error.message, "error"));
loadNetworks().catch((error) => setStatus(error.message, "error"));
