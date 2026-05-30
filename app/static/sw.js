/* Aero Vip Academy service worker.
 * Prefix-aware (the app is served under /aerovip/): all paths are resolved
 * relative to the worker's own location. Navigations are ALWAYS network-first
 * (never stale HTML); only same-origin static assets are cached.
 */
const CACHE = 'aerovip-v3';
const SCOPE_URL = new URL('./', self.location);                 // e.g. https://host/aerovip/
const STATIC_PREFIX = new URL('static/', SCOPE_URL).pathname;   // e.g. /aerovip/static/
const OFFLINE = new URL('static/offline.html', SCOPE_URL).href;
const PRECACHE = [
  'static/css/style.css',
  'static/img/logo.png',
  'static/img/icon-192.png',
  'static/img/icon-512.png',
  'static/offline.html',
].map((p) => new URL(p, SCOPE_URL).href);

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).catch(() => {}));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  ]));
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;             // skip CDNs, Maps, weather API

  if (req.mode === 'navigate') {                               // pages: network-first
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)));
    return;
  }

  if (url.pathname.startsWith(STATIC_PREFIX)) {                // static: cache-first
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return resp;
      }).catch(() => cached))
    );
  }
});
