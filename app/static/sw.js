/* Aero Vip Academy service worker.
 * Deliberately conservative: navigations are ALWAYS network-first (never serve
 * stale HTML), only same-origin static assets are cached. This makes the app
 * installable without the stale-page problems a careless SW would cause.
 */
const CACHE = 'aerovip-v1';
const PRECACHE = [
  '/static/css/style.css',
  '/static/img/logo.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/offline.html',
];

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
  if (req.method !== 'GET') return;                       // never touch POST/forms
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;        // skip CDNs, Google Maps, weather API

  // HTML navigations: network-first, fall back to offline page when offline.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }

  // Static assets: cache-first, then network (and cache the result).
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return resp;
      }).catch(() => cached))
    );
  }
});
