export async function api(pfad, methode = "GET", body = null) {
  const opt = { method: methode, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const res = await fetch(pfad, opt);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || res.statusText);
  }
  return res.status === 204 ? null : res.json();
}
