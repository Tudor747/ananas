async function parseResponse(response) {
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || `Request failed (${response.status})`);
  }
  return result;
}

export async function getJson(url) {
  return parseResponse(await fetch(url));
}

export async function postJson(url, payload = {}) {
  return parseResponse(await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  }));
}
