// Cache-first Service Worker fuer eine OFFLINE-App: die App-Huelle wird sofort
// aus dem Cache geliefert (auch offline / bei schlechtem Netz kein Warten), und
// im Hintergrund frisch nachgeladen. Neue Versionen kommen ueber CACHE-Bump +
// controllerchange-Reload (siehe app.js) trotzdem zuverlaessig an.
const CACHE = "elo-v42";
const HUELLE = ["/", "/index.html", "/style.css?v=30", "/local-db.js?v=2", "/sync.js?v=9", "/teams-local.js?v=2", "/app.js?v=41", "/tvg-logo.png?v=1", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(HUELLE)).catch(() => {}));
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

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
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
    badge: "/icon-192.png",
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
