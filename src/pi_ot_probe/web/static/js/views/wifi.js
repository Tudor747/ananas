// Render observations as text; action callbacks are supplied by app.js.
import {
  appendPair,
  byId,
  createText,
  emptyState,
  tableEmptyState,
  valueOrUnknown,
} from "../dom.js";

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
