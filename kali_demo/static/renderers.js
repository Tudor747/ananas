import {
  appendPair,
  byId,
  createText,
  emptyState,
  tableEmptyState,
  valueOrUnknown,
} from "./dom.js";

const TRIAGE_OPTIONS = [
  ["new", "New"],
  ["investigating", "Investigating"],
  ["confirmed", "Confirmed observation"],
  ["benign_change", "Expected change"],
  ["remediated", "Resolved"],
];

function renderServiceDetails(details, services) {
  if (!services?.length) {
    return;
  }
  details.append(createText("h3", "Service observations"));
  for (const service of services) {
    const block = createText("div", "", "raw-service");
    const transport = String(service.transport || "tcp").toUpperCase();
    block.append(createText(
      "strong",
      `${transport}/${service.port} - ${valueOrUnknown(service.name)}`,
    ));
    const fields = document.createElement("dl");
    appendPair(fields, "State / reason", `${valueOrUnknown(service.state)} / ${valueOrUnknown(service.reason)}`);
    appendPair(fields, "Product", service.product);
    appendPair(fields, "Version", service.version);
    appendPair(fields, "Extra information", service.extra_info);
    appendPair(fields, "Detection method", service.method);
    appendPair(fields, "Nmap confidence", service.confidence);
    appendPair(fields, "TLS tunnel", service.tunnel);
    appendPair(fields, "CPE identifiers", service.cpes?.join(", "));
    appendPair(fields, "Evidence", service.evidence);
    appendPair(fields, "Observed at", service.observed_at);
    block.append(fields);
    details.append(block);
  }
}

function renderWebsiteDetails(details, observations) {
  if (!observations?.length) {
    return;
  }
  details.append(createText("h3", "Website observation history"));
  for (const observation of observations) {
    const block = createText("div", "", "raw-service");
    block.append(createText(
      "strong",
      `${observation.scheme.toUpperCase()} ${observation.status_code} ${observation.status_reason}`,
    ));
    const fields = document.createElement("dl");
    appendPair(fields, "URL", `${observation.scheme}://${observation.host}:${observation.port}${observation.path}`);
    appendPair(fields, "HTTP version", observation.http_version);
    appendPair(fields, "Response headers", observation.headers?.map(
      (header) => `${header.name}: ${header.value}`,
    ).join(" | "));
    appendPair(fields, "TLS protocol", observation.tls?.protocol);
    appendPair(fields, "TLS cipher", observation.tls?.cipher);
    appendPair(fields, "Certificate SHA-256", observation.tls?.certificate_sha256);
    appendPair(fields, "Certificate validation", observation.tls?.certificate_validation);
    appendPair(fields, "Observed at", observation.observed_at);
    block.append(fields);
    details.append(block);
  }
}

function assetDetails(asset) {
  const details = document.createElement("details");
  details.className = "raw-details";
  details.append(createText("summary", "Raw evidence"));

  const fields = document.createElement("dl");
  appendPair(fields, "Status", asset.status);
  appendPair(fields, "Discovery reason", asset.discovery_reason);
  appendPair(fields, "All hostnames", asset.hostnames?.map(
    (hostname) => `${hostname.name} (${hostname.type})`,
  ).join(", "));
  appendPair(fields, "Collection source", asset.source);
  appendPair(fields, "First seen", asset.first_seen);
  appendPair(fields, "Last seen", asset.last_seen);
  details.append(fields);

  renderServiceDetails(details, asset.services);
  renderWebsiteDetails(details, asset.web_observations);
  return details;
}

function isWebService(service) {
  const name = String(service.name || "").toLowerCase();
  return name.includes("http") || [80, 443, 8080, 8443].includes(service.port);
}

function webScheme(service) {
  const name = String(service.name || "").toLowerCase();
  return service.tunnel === "ssl" || name.includes("https") || [443, 8443].includes(service.port)
    ? "https"
    : "http";
}

export function renderAssets(assets, handlers) {
  const body = byId("assets-body");
  body.replaceChildren();
  if (!assets.length) {
    tableEmptyState(body, 6, "No current devices. Run an authorized discovery.");
    return;
  }

  for (const asset of assets) {
    const row = document.createElement("tr");
    row.append(
      createText("td", asset.ip),
      createText("td", valueOrUnknown(asset.hostname)),
    );

    const identity = document.createElement("td");
    identity.append(
      createText("span", valueOrUnknown(asset.mac, "MAC not observed")),
      createText("span", valueOrUnknown(asset.vendor, "Vendor not observed"), "subtext"),
    );
    row.append(identity);

    const services = document.createElement("td");
    if (asset.services?.length) {
      for (const service of asset.services) {
        const transport = String(service.transport || "tcp").toUpperCase();
        services.append(createText(
          "span",
          `${transport}/${service.port} ${valueOrUnknown(service.name)}`,
          "data-chip",
        ));
      }
    } else {
      services.append(createText("span", "Not checked since latest discovery", "muted-cell"));
    }
    row.append(services);

    const evidence = document.createElement("td");
    evidence.append(
      createText("span", valueOrUnknown(asset.status)),
      createText("span", valueOrUnknown(asset.discovery_reason, "Reason not supplied"), "subtext"),
      assetDetails(asset),
    );
    row.append(evidence);

    const actions = document.createElement("td");
    const verify = createText("button", "Verify 20 TCP ports", "small-button verify-button");
    verify.type = "button";
    verify.addEventListener("click", () => handlers.verifyHost(asset.ip));
    actions.append(verify);
    for (const service of asset.services?.filter(isWebService) || []) {
      const scheme = webScheme(service);
      const inspect = createText(
        "button",
        `Inspect ${scheme.toUpperCase()}/${service.port}`,
        "small-button subtle web-button",
      );
      inspect.type = "button";
      inspect.addEventListener("click", () => handlers.inspectWeb(asset.ip, service.port, scheme));
      actions.append(inspect);
    }
    row.append(actions);
    body.append(row);
  }
}

export function renderValidationTargets(assets) {
  const selector = byId("red-target");
  const previous = selector.value;
  selector.replaceChildren();
  if (!assets.length) {
    selector.append(new Option("No discovered devices", ""));
    selector.disabled = true;
    return;
  }
  for (const asset of assets) {
    selector.append(new Option(
      `${asset.ip} - ${valueOrUnknown(asset.hostname, "hostname not observed")}`,
      asset.ip,
    ));
  }
  if (assets.some((asset) => asset.ip === previous)) {
    selector.value = previous;
  }
  selector.disabled = false;
}

export function renderWifi(accessPoints) {
  const body = byId("wifi-body");
  body.replaceChildren();
  if (!accessPoints.length) {
    tableEmptyState(body, 6, "No Wi-Fi observations stored.");
    return;
  }
  for (const accessPoint of accessPoints) {
    const row = document.createElement("tr");
    row.append(
      createText("td", valueOrUnknown(accessPoint.ssid, "Hidden / not broadcast")),
      createText("td", accessPoint.bssid),
    );
    const signal = document.createElement("td");
    signal.append(
      createText("span", accessPoint.signal_percent === null ? "Not observed" : `${accessPoint.signal_percent}% reported`),
      createText("span", accessPoint.signal_dbm_estimated === null ? "dBm estimate unavailable" : `about ${accessPoint.signal_dbm_estimated} dBm (estimated)`, "subtext"),
    );
    row.append(signal);
    row.append(createText("td", `Channel ${valueOrUnknown(accessPoint.channel)} / ${valueOrUnknown(accessPoint.band)}`));
    const security = document.createElement("td");
    security.append(
      createText("span", valueOrUnknown(accessPoint.authentication)),
      createText("span", `Cipher: ${valueOrUnknown(accessPoint.cipher || accessPoint.encryption)}`, "subtext"),
    );
    row.append(security);
    const radio = document.createElement("td");
    radio.append(
      createText("span", valueOrUnknown(accessPoint.radio_type || accessPoint.mode)),
      createText("span", `${valueOrUnknown(accessPoint.frequency_mhz)} MHz / ${valueOrUnknown(accessPoint.rate, "Rate not supplied")}`, "subtext"),
      createText("span", accessPoint.source, "subtext"),
    );
    row.append(radio);
    body.append(row);
  }
}

function filteredChanges(changes) {
  const filter = byId("change-filter").value;
  if (filter === "all") {
    return changes;
  }
  if (filter === "confirmed") {
    return changes.filter((change) => change.triage_status === "confirmed");
  }
  return changes.filter((change) => !["benign_change", "remediated"].includes(change.triage_status));
}

export function renderChanges(changes, onTriage) {
  const totals = changes.reduce((counts, change) => {
    const key = change.triage_status || "new";
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
  const closed = (totals.benign_change || 0) + (totals.remediated || 0);
  const open = changes.length - closed;
  byId("change-new-count").textContent = totals.new || 0;
  byId("change-investigating-count").textContent = totals.investigating || 0;
  byId("change-confirmed-count").textContent = totals.confirmed || 0;
  byId("change-closed-count").textContent = closed;
  byId("change-tab-count").textContent = open;
  byId("metric-changes").textContent = open;

  const root = byId("changes");
  root.replaceChildren();
  const visible = filteredChanges(changes);
  if (!visible.length) {
    root.append(emptyState("No changes match this queue."));
    return;
  }

  for (const change of visible) {
    const item = createText("div", "", `item change ${change.acknowledged_at ? "acknowledged" : ""}`.trim());
    const heading = createText("div", "", "item-head");
    heading.append(
      createText("span", change.change_type.replaceAll("_", " ").toUpperCase()),
      createText("code", change.asset_identity),
    );
    const metadata = createText("div", "", "evidence-meta");
    metadata.append(createText("span", change.triage_status || "new", "status-chip"));
    item.append(
      heading,
      metadata,
      createText("p", change.summary),
      createText("small", new Date(change.detected_at).toLocaleString(), "subtext"),
    );

    const form = createText("div", "", "triage-form");
    const status = document.createElement("select");
    status.setAttribute("aria-label", "Review status");
    for (const [value, label] of TRIAGE_OPTIONS) {
      status.append(new Option(label, value));
    }
    status.value = change.triage_status || "new";
    const note = document.createElement("input");
    note.maxLength = 2000;
    note.placeholder = "Analyst note";
    note.value = change.analyst_note || "";
    const save = createText("button", "Save review", "small-button");
    save.type = "button";
    save.addEventListener("click", () => onTriage(change.id, status.value, note.value));
    form.append(status, note, save);
    item.append(form);
    root.append(item);
  }
}

export function renderScans(scans) {
  const root = byId("scans");
  root.replaceChildren();
  if (!scans.length) {
    root.append(emptyState("No scans recorded yet."));
    return;
  }
  for (const scan of scans.slice(0, 25)) {
    const item = createText("div", "", "item");
    const heading = createText("div", "", "item-head");
    const kind = scan.level === 2 ? "SERVICE VERIFICATION" : "HOST DISCOVERY";
    heading.append(
      createText("span", `${kind} / ${scan.status.toUpperCase()}`),
      createText("code", scan.id.slice(0, 8)),
    );
    item.append(
      heading,
      createText("p", `${scan.assets_found} device record(s) / target ${scan.target}`),
      createText("small", `${valueOrUnknown(scan.started_at)} - ${valueOrUnknown(scan.finished_at)}`, "subtext"),
    );
    if (scan.error) {
      item.append(createText("p", scan.error, "error-text"));
    }
    root.append(item);
  }
}

export function renderBaseline(baseline) {
  byId("baseline-status").textContent = baseline
    ? `${baseline.name}: ${baseline.assets} devices and ${baseline.access_points} Wi-Fi radios, created ${new Date(baseline.created_at).toLocaleString()}.`
    : "No active baseline. Review the inventory, then create a known-good reference.";
}

export function renderScenarios(scenarios) {
  const root = byId("red-scenarios");
  root.replaceChildren();
  for (const scenario of scenarios) {
    const card = createText("article", "", `scenario-card ${scenario.available ? "" : "disabled"}`.trim());
    card.append(
      createText("span", `CHECK LEVEL ${scenario.level} / ${scenario.available ? "AVAILABLE" : "PLANNED"}`, "status-chip"),
      createText("h3", scenario.name),
      createText("p", scenario.purpose),
      createText("small", scenario.traffic),
    );
    root.append(card);
  }
}
