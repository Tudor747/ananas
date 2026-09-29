// Render observations as text; action callbacks are supplied by app.js.
import {
  appendPair,
  byId,
  createText,
  emptyState,
  tableEmptyState,
  valueOrUnknown,
} from "../dom.js";

const TRIAGE_OPTIONS = [
  ["new", "New"],
  ["investigating", "Investigating"],
  ["confirmed", "Confirmed observation"],
  ["benign_change", "Expected change"],
  ["remediated", "Resolved"],
];

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
