import {byId, createText, emptyState} from "../dom.js";

let renderedAssessment = "";
let renderedInstruments = "";

export function renderAssessment(assessment, onReview) {
  const filter = byId("assessment-filter").value;
  const signature = JSON.stringify([assessment, filter]);
  const root = byId("assessment-findings");
  if (signature === renderedAssessment) return;
  // Do not erase an in-progress review when another operation refreshes evidence.
  if (root.contains(document.activeElement) && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  renderedAssessment = signature;
  byId("assessment-site").textContent = assessment.site
    ? `Network: ${assessment.site}. Priorities guide review; they are not vulnerability scores.`
    : "Start with Discover devices, then verify selected hosts and inspect their web services. ESP registration is available before discovery.";
  for (const priority of ["high", "medium", "low"]) {
    byId(`assessment-${priority}`).textContent = assessment.counts[priority] || 0;
  }
  byId("assessment-manual").textContent = assessment.counts.review || 0;
  byId("assessment-limitations").textContent = assessment.limitations;
  const coverage = byId("assessment-coverage");
  coverage.replaceChildren();
  for (const area of assessment.coverage) {
    const row = createText("div", "", "coverage-item");
    row.append(createText("strong", area.area), createText("span", area.status, "status-chip"), createText("p", area.detail, "section-help"));
    coverage.append(row);
  }
  root.replaceChildren();
  const visible = assessment.findings.filter(item => {
    if (filter === "manual") return item.basis === "manual observation";
    if (filter === "open") return ["new", "investigating"].includes(item.status);
    return true;
  });
  if (!visible.length) root.append(emptyState("No observations match this view. Check coverage before drawing conclusions."));
  for (const finding of visible) {
    const card = createText("article", "", `item assessment-item priority-${finding.priority}`);
    const metadata = createText("div", "", "evidence-meta");
    metadata.append(createText("span", `${finding.priority} priority`, "status-chip"), createText("span", finding.basis, "status-chip"));
    const action = createText("p", "", "finding-action");
    action.append(createText("strong", "Improve / verify: "), document.createTextNode(finding.recommendation));
    const details = document.createElement("details");
    details.append(createText("summary", "Evidence and provenance"), createText("pre", JSON.stringify(finding.evidence, null, 2), "finding-evidence"));
    const form = createText("form", "", "triage-form");
    const status = document.createElement("select");
    status.setAttribute("aria-label", `Review status for ${finding.title}`);
    for (const [value, label] of [["new", "New"], ["investigating", "Investigating"], ["reviewed", "Reviewed"], ["accepted_risk", "Accepted risk"], ["remediated", "Remediated (operator)"]]) {
      status.append(new Option(label, value));
    }
    status.value = finding.status;
    const note = document.createElement("input");
    note.setAttribute("aria-label", `Review note for ${finding.title}`);
    note.maxLength = 2000;
    note.placeholder = "Reason, improvement or retest evidence";
    note.value = finding.note;
    const save = createText("button", "Save review", "small-button");
    save.type = "submit";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      save.disabled = true;
      try { await onReview(assessment.site, finding.id, status.value, note.value); }
      finally { save.disabled = false; }
    });
    form.append(status, note, save);
    card.append(metadata, createText("h3", finding.title), createText("code", finding.subject), createText("p", finding.implication), action, details, form);
    root.append(card);
  }
}

export function renderInstruments(instruments, site, busy) {
  byId("field-site").textContent = site
    ? `Evidence will be saved for ${site}. Entries are preserved as manual observations.`
    : "Run discovery first to associate observations with a network.";
  byId("field-save").disabled = busy || !site || !instruments.length;
  const signature = JSON.stringify(instruments);
  if (signature === renderedInstruments) return;
  renderedInstruments = signature;
  const root = byId("instrument-list");
  const selector = byId("field-instrument");
  const previous = selector.value;
  selector.replaceChildren();
  root.replaceChildren();
  if (!instruments.length) {
    root.append(emptyState("Register your existing ESP32 below. Unknown radio modules do not block manual evidence collection."));
    selector.append(new Option("Register an instrument first", ""));
  }
  for (const instrument of instruments) {
    selector.append(new Option(instrument.name, instrument.id));
    const card = createText("article", "", "panel instrument-card");
    card.append(createText("p", "BWifiKill / FIELD INSTRUMENT", "eyebrow"), createText("h3", instrument.name), createText("p", instrument.model), createText("p", instrument.firmware, "muted"), createText("span", "Manual evidence / connection unverified", "status-chip"));
    if (instrument.notes) card.append(createText("p", instrument.notes, "instrument-notes"));
    root.append(card);
  }
  if (instruments.some(item => String(item.id) === previous)) selector.value = previous;
}
