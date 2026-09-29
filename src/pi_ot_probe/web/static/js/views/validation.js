// Render observations as text; action callbacks are supplied by app.js.
import {
  appendPair,
  byId,
  createText,
  emptyState,
  tableEmptyState,
  valueOrUnknown,
} from "../dom.js";

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
