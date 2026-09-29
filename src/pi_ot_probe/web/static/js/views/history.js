// Render observations as text; action callbacks are supplied by app.js.
import {
  appendPair,
  byId,
  createText,
  emptyState,
  tableEmptyState,
  valueOrUnknown,
} from "../dom.js";

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
