// Render observations as text; action callbacks are supplied by app.js.
import {
  appendPair,
  byId,
  createText,
  emptyState,
  tableEmptyState,
  valueOrUnknown,
} from "../dom.js";

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
