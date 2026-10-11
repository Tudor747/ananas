// Keep HTTP and error handling here so views do not depend on fetch().
async function parseResponse(response) {
  const result = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(result.detail)
      ? result.detail.map(item => `${item.loc?.at(-1) || "Request"}: ${item.msg}`).join("; ")
      : result.detail;
    throw new Error(detail || `Request failed (${response.status})`);
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
