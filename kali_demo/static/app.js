import {getJson, postJson} from "./api.js";
import {byId} from "./dom.js";
import {
  renderAssets,
  renderBaseline,
  renderChanges,
  renderScans,
  renderScenarios,
  renderValidationTargets,
  renderWifi,
} from "./renderers.js";

const REFRESH_INTERVAL_MS = 1000;
let operationBusy = false;
let operationCancellable = false;
let lastState = null;

function setStatus(message, kind = "") {
  const status = byId("status");
  status.className = `status ${kind}`.trim();
  status.textContent = message;
}

function isAuthorized() {
  return byId("authorized").checked;
}

function openTab(name) {
  for (const button of document.querySelectorAll(".tab-button")) {
    const selected = button.dataset.tab === name;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  }
  for (const panel of document.querySelectorAll(".tab-panel")) {
    const selected = panel.id === `tab-${name}`;
    panel.hidden = !selected;
    panel.classList.toggle("active", selected);
  }
}

function updateControls() {
  const networkUnavailable = operationBusy || byId("network").disabled;
  byId("run-button").disabled = networkUnavailable || !isAuthorized();
  byId("cancel-button").disabled = !operationBusy || !operationCancellable;
  byId("wifi-button").disabled = operationBusy || !isAuthorized() || !lastState?.current_site;
  byId("baseline-button").disabled = operationBusy || !lastState?.assets?.length;
  byId("red-verify-button").disabled = operationBusy || !isAuthorized() || byId("red-target").disabled;
  for (const button of document.querySelectorAll(".verify-button, .web-button")) {
    button.disabled = operationBusy || !isAuthorized();
  }
}

async function refresh() {
  const state = await getJson("/api/state");
  lastState = state;
  const openPorts = state.assets.reduce(
    (total, asset) => total + (asset.ports?.length || 0),
    0,
  );
  byId("metric-assets").textContent = state.assets.length;
  byId("metric-services").textContent = openPorts;
  byId("metric-wifi").textContent = state.access_points.length;
  byId("asset-count").textContent = state.assets.length;
  byId("current-site").textContent = state.current_site || "No discovery yet";
  byId("current-mode").textContent = state.current_site
    ? `${state.mode.replaceAll("_", " ")} / ${state.assets.length} current devices`
    : "Ready for local inventory";

  renderAssets(state.assets, {verifyHost, inspectWeb});
  renderValidationTargets(state.assets);
  renderChanges(state.changes, triageChange);
  renderWifi(state.access_points);
  renderScans(state.scans);
  renderBaseline(state.baseline);
  updateControls();
}

async function withOperation(message, operation, {cancellable = true} = {}) {
  operationBusy = true;
  operationCancellable = cancellable;
  updateControls();
  setStatus(message, "running");
  const poll = setInterval(() => refresh().catch(() => {}), REFRESH_INTERVAL_MS);
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
    const result = await withOperation(
      "Running rate-limited host discovery...",
      () => postJson("/api/real/run", {
        target: byId("network").value,
        authorized: isAuthorized(),
      }),
    );
    setStatus(result.cancelled
      ? `Scan ${result.scan_id.slice(0, 8)} was cancelled; no baseline comparison was made.`
      : `Discovery complete: ${result.assets} current devices; ${result.changes} baseline differences.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function verifyHost(host) {
  try {
    const result = await withOperation(
      `Checking 20 common TCP ports on ${host}...`,
      () => postJson("/api/real/verify", {host, authorized: isAuthorized()}),
    );
    setStatus(result.cancelled
      ? `Check ${result.scan_id.slice(0, 8)} was cancelled.`
      : `Verification complete for ${host}: ${result.open_ports.length} open port(s), ${result.changes} baseline difference(s).`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function inspectWeb(host, port, scheme) {
  try {
    const result = await withOperation(
      `Reading response metadata from ${scheme}://${host}:${port}/...`,
      () => postJson("/api/real/web", {
        host,
        port,
        scheme,
        authorized: isAuthorized(),
      }),
      {cancellable: false},
    );
    setStatus(
      `Website inspection complete: ${result.http_version} ${result.status_code} ${result.status_reason}. No redirect was followed.`,
    );
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function refreshWifi() {
  try {
    const result = await withOperation(
      "Reading Wi-Fi data exposed by this operating system...",
      () => postJson("/api/wifi/refresh", {authorized: isAuthorized()}),
      {cancellable: false},
    );
    setStatus(`Wi-Fi inventory updated: ${result.access_points} radios; ${result.changes} baseline differences.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function createBaseline() {
  try {
    const result = await postJson("/api/baseline", {name: byId("baseline-name").value});
    await refresh();
    setStatus(`Baseline created with ${result.assets} devices and ${result.access_points} Wi-Fi radios.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function triageChange(changeId, status, note) {
  try {
    await postJson(`/api/changes/${changeId}/triage`, {status, note});
    await refresh();
    setStatus(`Change ${changeId} updated to ${status.replaceAll("_", " ")}.`);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function cancelOperation() {
  const result = await postJson("/api/cancel");
  setStatus(result.cancel_requested
    ? "Cancellation requested. Waiting for the collector to stop..."
    : "No cancellable scan is running.");
}

async function loadNetworks() {
  const selector = byId("network");
  const result = await getJson("/api/networks");
  selector.replaceChildren();
  if (!result.nmap_available) {
    throw new Error("Nmap was not found. Install it or add its folder to PATH, then restart the app.");
  }
  if (!result.networks.length) {
    throw new Error("No active private IPv4 interface was found.");
  }
  for (const network of result.networks) {
    selector.append(new Option(
      `${network.interface} - ${network.safe_target} - this computer ${network.address}`,
      network.safe_target,
    ));
  }
  selector.disabled = false;
  setStatus("Ready. Select a local network and confirm authorization.");
  updateControls();
}

async function loadScenarios() {
  const result = await getJson("/api/validation/scenarios");
  renderScenarios(result.scenarios);
}

function registerEventHandlers() {
  for (const button of document.querySelectorAll(".tab-button")) {
    button.addEventListener("click", () => openTab(button.dataset.tab));
  }
  for (const button of document.querySelectorAll("[data-open-tab]")) {
    button.addEventListener("click", () => openTab(button.dataset.openTab));
  }
  byId("run-button").addEventListener("click", runAudit);
  byId("cancel-button").addEventListener("click", cancelOperation);
  byId("baseline-button").addEventListener("click", createBaseline);
  byId("wifi-button").addEventListener("click", refreshWifi);
  byId("red-verify-button").addEventListener(
    "click",
    () => verifyHost(byId("red-target").value),
  );
  byId("authorized").addEventListener("change", updateControls);
  byId("change-filter").addEventListener(
    "change",
    () => renderChanges(lastState?.changes || [], triageChange),
  );
}

async function initialize() {
  registerEventHandlers();
  const results = await Promise.allSettled([refresh(), loadNetworks(), loadScenarios()]);
  const failed = results.find((result) => result.status === "rejected");
  if (failed) {
    setStatus(failed.reason.message, "error");
  }
}

initialize();
