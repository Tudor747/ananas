const byId = (id) => document.getElementById(id);
let operationBusy = false;
let operationCancellable = false;
let lastState = null;

function empty(message) { const node = document.createElement("div"); node.className = "empty"; node.textContent = message; return node; }
function text(tag, value, className = "") { const node = document.createElement(tag); node.textContent = value ?? ""; if (className) node.className = className; return node; }
function valueOrUnknown(value, label = "Not observed") { return value === null || value === undefined || value === "" ? label : String(value); }
function setStatus(message, kind = "") { const status = byId("status"); status.className = `status ${kind}`.trim(); status.textContent = message; }
function isAuthorized() { return byId("authorized").checked; }

function updateControls() {
  const unavailable = operationBusy || byId("network").disabled;
  byId("run-button").disabled = unavailable || !isAuthorized();
  byId("cancel-button").disabled = !operationBusy || !operationCancellable;
  byId("wifi-button").disabled = operationBusy || !isAuthorized() || !lastState?.current_site;
  byId("baseline-button").disabled = operationBusy || !lastState?.assets?.length;
  document.querySelectorAll(".verify-button").forEach((button) => { button.disabled = operationBusy || !isAuthorized(); });
}

function appendPair(root, label, value) {
  const row = text("div", "", "raw-pair");
  row.append(text("dt", label), text("dd", valueOrUnknown(value)));
  root.append(row);
}

function assetDetails(asset) {
  const details = document.createElement("details");
  details.className = "raw-details";
  details.append(text("summary", "Raw details"));
  const list = document.createElement("dl");
  appendPair(list, "Status", asset.status);
  appendPair(list, "Discovery reason", asset.discovery_reason);
  appendPair(list, "All hostnames", asset.hostnames?.map((item) => `${item.name} (${item.type})`).join(", "));
  appendPair(list, "Collection source", asset.source);
  appendPair(list, "First seen", asset.first_seen);
  appendPair(list, "Last seen", asset.last_seen);
  details.append(list);
  if (asset.services?.length) {
    details.append(text("h3", "Service observations"));
    asset.services.forEach((service) => {
      const block = text("div", "", "raw-service");
      block.append(text("strong", `${service.transport.toUpperCase()}/${service.port} — ${valueOrUnknown(service.name)}`));
      const serviceList = document.createElement("dl");
      appendPair(serviceList, "State / reason", `${valueOrUnknown(service.state)} / ${valueOrUnknown(service.reason)}`);
      appendPair(serviceList, "Product", service.product);
      appendPair(serviceList, "Version", service.version);
      appendPair(serviceList, "Extra information", service.extra_info);
      appendPair(serviceList, "Detection method", service.method);
      appendPair(serviceList, "Nmap confidence", service.confidence);
      appendPair(serviceList, "TLS tunnel", service.tunnel);
      appendPair(serviceList, "CPE identifiers", service.cpes?.join(", "));
      appendPair(serviceList, "Evidence", service.evidence);
      appendPair(serviceList, "Observed at", service.observed_at);
      block.append(serviceList); details.append(block);
    });
  }
  if (asset.web_observations?.length) {
    details.append(text("h3", "Website observations"));
    asset.web_observations.forEach((observation) => {
      const block = text("div", "", "raw-service");
      block.append(text("strong", `${observation.scheme.toUpperCase()} ${observation.status_code} ${observation.status_reason}`));
      const webList = document.createElement("dl");
      appendPair(webList, "URL", `${observation.scheme}://${observation.host}:${observation.port}${observation.path}`);
      appendPair(webList, "HTTP version", observation.http_version);
      appendPair(webList, "Response headers", observation.headers?.map((header) => `${header.name}: ${header.value}`).join(" | "));
      appendPair(webList, "TLS protocol", observation.tls?.protocol);
      appendPair(webList, "TLS cipher", observation.tls?.cipher);
      appendPair(webList, "Certificate SHA-256", observation.tls?.certificate_sha256);
      appendPair(webList, "Certificate validation", observation.tls?.certificate_validation);
      appendPair(webList, "Observed at", observation.observed_at);
      block.append(webList); details.append(block);
    });
  }
  return details;
}

function renderAssets(assets) {
  const body = byId("assets-body"); body.replaceChildren();
  if (!assets.length) {
    const row = document.createElement("tr"); const cell = document.createElement("td"); cell.colSpan = 6;
    cell.append(empty("No devices stored yet. Run discovery on an authorized local network.")); row.append(cell); body.append(row); return;
  }
  assets.forEach((asset) => {
    const row = document.createElement("tr"); row.append(text("td", asset.ip)); row.append(text("td", valueOrUnknown(asset.hostname)));
    const identity = document.createElement("td"); identity.append(text("span", valueOrUnknown(asset.mac, "MAC not observed"))); identity.append(text("span", valueOrUnknown(asset.vendor, "Vendor not observed"), "subtext")); row.append(identity);
    const services = document.createElement("td");
    if (asset.services?.length) asset.services.forEach((service) => services.append(text("span", `${service.transport.toUpperCase()}/${service.port} ${valueOrUnknown(service.name)}`, "data-chip")));
    else services.append(text("span", "Not checked", "muted-cell"));
    row.append(services);
    const evidence = document.createElement("td"); evidence.append(text("span", valueOrUnknown(asset.status))); evidence.append(text("span", valueOrUnknown(asset.discovery_reason, "Reason not supplied"), "subtext")); evidence.append(assetDetails(asset)); row.append(evidence);
    const action = document.createElement("td"); const verify = text("button", "Check 20 TCP ports", "small-button verify-button"); verify.type = "button"; verify.addEventListener("click", () => verifyHost(asset.ip)); action.append(verify);
    asset.services?.filter((service) => String(service.name).toLowerCase().includes("http") || [80, 443, 8080, 8443].includes(service.port)).forEach((service) => {
      const secure = service.tunnel === "ssl" || String(service.name).toLowerCase().includes("https") || [443, 8443].includes(service.port);
      const button = text("button", `Inspect ${secure ? "HTTPS" : "HTTP"}/${service.port}`, "small-button subtle web-button"); button.type = "button"; button.addEventListener("click", () => inspectWeb(asset.ip, service.port, secure ? "https" : "http")); action.append(button);
    });
    row.append(action); body.append(row);
  });
}

function renderWifi(accessPoints) {
  const body = byId("wifi-body"); body.replaceChildren();
  if (!accessPoints.length) {
    const row = document.createElement("tr"); const cell = document.createElement("td"); cell.colSpan = 6;
    cell.append(empty("No Wi-Fi observations stored. Confirm authorization, then refresh Wi-Fi inventory.")); row.append(cell); body.append(row); return;
  }
  accessPoints.forEach((ap) => {
    const row = document.createElement("tr"); row.append(text("td", valueOrUnknown(ap.ssid, "Hidden / not broadcast"))); row.append(text("td", ap.bssid));
    const signal = document.createElement("td"); signal.append(text("span", ap.signal_percent === null ? "Not observed" : `${ap.signal_percent}% reported`)); signal.append(text("span", ap.signal_dbm_estimated === null ? "dBm estimate unavailable" : `about ${ap.signal_dbm_estimated} dBm (estimated)`, "subtext")); row.append(signal);
    row.append(text("td", `Channel ${valueOrUnknown(ap.channel)} / ${valueOrUnknown(ap.band)}`));
    const security = document.createElement("td"); security.append(text("span", valueOrUnknown(ap.authentication))); security.append(text("span", `Cipher: ${valueOrUnknown(ap.cipher || ap.encryption)}`, "subtext")); row.append(security);
    const radio = document.createElement("td"); radio.append(text("span", valueOrUnknown(ap.radio_type || ap.mode))); radio.append(text("span", `${valueOrUnknown(ap.frequency_mhz)} MHz / ${valueOrUnknown(ap.rate, "Rate not supplied")}`, "subtext")); radio.append(text("span", ap.source, "subtext")); row.append(radio); body.append(row);
  });
}

function renderChanges(changes) {
  const root = byId("changes"); root.replaceChildren(); if (!changes.length) return root.append(empty("No differences from the active baseline."));
  changes.slice(0, 20).forEach((change) => {
    const item = text("div", "", `item ${change.acknowledged_at ? "acknowledged" : ""}`); const head = text("div", "", "item-head"); head.append(text("span", change.change_type.replaceAll("_", " ").toUpperCase())); head.append(text("code", change.asset_identity));
    item.append(head, text("p", change.summary), text("small", new Date(change.detected_at).toLocaleString(), "subtext"));
    if (!change.acknowledged_at) { const button = text("button", "Acknowledge", "small-button subtle"); button.type = "button"; button.addEventListener("click", () => acknowledgeChange(change.id)); item.append(button); }
    root.append(item);
  });
}

function renderScans(scans) {
  const root = byId("scans"); root.replaceChildren(); if (!scans.length) return root.append(empty("No scans recorded yet."));
  scans.slice(0, 10).forEach((scan) => {
    const item = text("div", "", "item"); const head = text("div", "", "item-head"); const kind = scan.level === 2 ? "SERVICE CHECK" : "HOST DISCOVERY";
    head.append(text("span", `${kind} / ${scan.status.toUpperCase()}`)); head.append(text("code", scan.id.slice(0, 8))); item.append(head, text("p", `${scan.assets_found} device record(s) / target ${scan.target}`)); item.append(text("small", `${valueOrUnknown(scan.started_at)} — ${valueOrUnknown(scan.finished_at)}`, "subtext")); if (scan.error) item.append(text("p", scan.error, "error-text")); root.append(item);
  });
}

function renderBaseline(baseline) { byId("baseline-status").textContent = baseline ? `${baseline.name}: ${baseline.assets} devices and ${baseline.access_points} Wi-Fi radios, created ${new Date(baseline.created_at).toLocaleString()}` : "No active baseline. Run discovery, optionally refresh Wi-Fi, then create one."; }

async function refresh() {
  const response = await fetch("/api/state"); if (!response.ok) throw new Error(`State request failed (${response.status})`); const state = await response.json(); lastState = state;
  const openPorts = state.assets.reduce((total, asset) => total + (asset.ports?.length || 0), 0);
  byId("metric-assets").textContent = state.assets.length; byId("metric-services").textContent = openPorts; byId("metric-wifi").textContent = state.access_points.length; byId("metric-changes").textContent = state.counts.changes; byId("asset-count").textContent = state.assets.length;
  renderAssets(state.assets); renderChanges(state.changes); renderWifi(state.access_points); renderScans(state.scans); renderBaseline(state.baseline); updateControls();
}

async function postJson(url, payload) { const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}); const result = await response.json(); if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`); return result; }
async function withOperation(message, operation, cancellable = true) { operationBusy = true; operationCancellable = cancellable; updateControls(); setStatus(message, "running"); const poll = setInterval(() => refresh().catch(() => {}), 1000); try { return await operation(); } finally { clearInterval(poll); operationBusy = false; operationCancellable = false; await refresh(); updateControls(); } }
async function runAudit() { try { const result = await withOperation("Running rate-limited host discovery...", () => postJson("/api/real/run", {target: byId("network").value, authorized: isAuthorized()})); setStatus(result.cancelled ? `Scan ${result.scan_id.slice(0, 8)} was cancelled.` : `Discovery complete: ${result.assets} responding devices; ${result.changes} baseline differences.`); } catch (error) { setStatus(error.message, "error"); } }
async function verifyHost(host) { try { const result = await withOperation(`Checking 20 common TCP ports on ${host}...`, () => postJson("/api/real/verify", {host, authorized: isAuthorized()})); setStatus(result.cancelled ? `Check ${result.scan_id.slice(0, 8)} was cancelled.` : `Service check complete for ${host}: ${result.open_ports.length} open port(s) observed.`); } catch (error) { setStatus(error.message, "error"); } }
async function createBaseline() { try { const result = await postJson("/api/baseline", {name: byId("baseline-name").value}); await refresh(); setStatus(`Baseline created with ${result.assets} devices and ${result.access_points} Wi-Fi radios.`); } catch (error) { setStatus(error.message, "error"); } }
async function refreshWifi() { try { const result = await withOperation("Reading Wi-Fi data exposed by this operating system...", () => postJson("/api/wifi/refresh", {authorized: isAuthorized()}), false); setStatus(`Wi-Fi inventory updated: ${result.access_points} radios; ${result.changes} baseline differences.`); } catch (error) { setStatus(error.message, "error"); } }
async function inspectWeb(host, port, scheme) { try { const result = await withOperation(`Reading response metadata from ${scheme}://${host}:${port}/...`, () => postJson("/api/real/web", {host, port, scheme, authorized: isAuthorized()}), false); setStatus(`Website inspection complete: ${result.http_version} ${result.status_code} ${result.status_reason}. No redirect was followed.`); } catch (error) { setStatus(error.message, "error"); } }
async function acknowledgeChange(changeId) { try { await postJson(`/api/changes/${changeId}/acknowledge`, {}); await refresh(); setStatus("Baseline difference acknowledged."); } catch (error) { setStatus(error.message, "error"); } }
async function loadNetworks() {
  const selector = byId("network"); const response = await fetch("/api/networks"); const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Could not inspect local interfaces."); selector.replaceChildren();
  if (!result.nmap_available) throw new Error("Nmap was not found. Install it or add its folder to PATH, then restart the app."); if (!result.networks.length) throw new Error("No active private IPv4 interface was found.");
  result.networks.forEach((network) => { const option = document.createElement("option"); option.value = network.safe_target; option.textContent = `${network.interface} — ${network.safe_target} — this computer ${network.address}`; selector.append(option); }); selector.disabled = false; setStatus("Ready. Select your local network and confirm authorization."); updateControls();
}
async function cancelOperation() { const result = await postJson("/api/cancel", {}); setStatus(result.cancel_requested ? "Cancellation requested. Waiting for Nmap to stop..." : "No scan is running."); }

byId("run-button").addEventListener("click", runAudit); byId("cancel-button").addEventListener("click", cancelOperation); byId("baseline-button").addEventListener("click", createBaseline); byId("wifi-button").addEventListener("click", refreshWifi); byId("authorized").addEventListener("change", updateControls);
refresh().catch((error) => setStatus(error.message, "error")); loadNetworks().catch((error) => setStatus(error.message, "error"));
