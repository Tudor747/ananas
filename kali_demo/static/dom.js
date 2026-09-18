export const byId = (id) => document.getElementById(id);

export function createText(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value ?? "";
  if (className) {
    node.className = className;
  }
  return node;
}

export function emptyState(message) {
  return createText("div", message, "empty");
}

export function valueOrUnknown(value, fallback = "Not observed") {
  return value === null || value === undefined || value === ""
    ? fallback
    : String(value);
}

export function appendPair(root, label, value) {
  const row = createText("div", "", "raw-pair");
  row.append(
    createText("dt", label),
    createText("dd", valueOrUnknown(value)),
  );
  root.append(row);
}

export function tableEmptyState(body, columnCount, message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = columnCount;
  cell.append(emptyState(message));
  row.append(cell);
  body.append(row);
}
