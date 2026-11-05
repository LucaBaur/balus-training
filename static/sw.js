// Cache-first Service Worker fuer eine OFFLINE-App: die App-Huelle wird sofort
// aus dem Cache geliefert (auch offline / bei schlechtem Netz kein Warten), und
// im Hintergrund frisch nachgeladen. Neue Versionen kommen ueber CACHE-Bump +
// controllerchange-Reload (siehe app.js) trotzdem zuverlaessig an.
const CACHE = "elo-v88";
const HUELLE = ["/", "/index.html", "/style.css?v=56", "/theme.js?v=1", "/local-db.js?v=3", "/sync.js?v=11", "/teams-local.js?v=2", "/nav.js?v=2", "/home-logik.js?v=3", "/app.js?v=85", "/tvg-logo.png?v=1", "/manifest.webmanifest", "/portraits/index.json"];

// Die Portraits gehoeren zur Huelle, stehen aber nicht fest in der Liste:
// welche es gibt, sagt /portraits/index.json. So muss hier nichts nachgepflegt
// werden, wenn ein Foto dazukommt - und offline sind alle Gesichter sofort da.
function portraitsCachen(c) {
  return fetch("/portraits/index.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => c.addAll(Object.values((d && d.spieler) || {}).map((f) => "/portraits/" + f)))
    .catch(() => {});
}

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(HUELLE).catch(() => {}).then(() => portraitsCachen(c)))
    .catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Cache-first mit Hintergrund-Update ("stale-while-revalidate").
function cacheFirst(request, cacheKey) {
  const key = cacheKey || request;
  return caches.match(key).then((cached) => {
    const netz = fetch(request)
      .then((resp) => {
        caches.open(CACHE).then((c) => c.put(key, resp.clone())).catch(() => {});
        return resp;
      })
      .catch(() => cached); // offline -> nimm den Cache
    return cached || netz;    // Cache sofort; nur ohne Cache aufs Netz warten
  });
}

// Selbst hochgeladene Portraits: die URL traegt ?v=<Version>, ein neues Foto ist
// also eine neue URL - der Inhalt ist unveraenderlich, Cache zuerst genuegt.
// Nur Erfolge werden gemerkt (ein 401/404 darf nie als "Foto" im Cache landen).
function portraitHolen(request) {
  return caches.match(request).then((cached) => cached || fetch(request).then((resp) => {
    if (resp.ok) caches.open(CACHE).then((c) => c.put(request, resp.clone())).catch(() => {});
    return resp;
  }));
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method === "GET" && url.pathname.startsWith("/api/portrait/")) {
    e.respondWith(portraitHolen(e.request));
    return;
  }
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;

  // App-Start (Navigation): immer die gecachte Shell (/index.html) zuerst.
  if (e.request.mode === "navigate") {
    e.respondWith(cacheFirst(e.request, "/index.html"));
    return;
  }

  // Shell-Assets (js/css/manifest/icons): ebenfalls cache-first.
  e.respondWith(cacheFirst(e.request));
});

// ------------------------------------------------------------- Web-Push ----
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) {}
  const titel = d.title || "Balu's Training";
  e.waitUntil(self.registration.showNotification(titel, {
    body: d.body || "",
    icon: "/icon-192.png",
    badge: "/badge-96.png",
    data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const ziel = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((liste) => {
    for (const c of liste) { if ("focus" in c) return c.focus(); }
    if (clients.openWindow) return clients.openWindow(ziel);
  }));
});
