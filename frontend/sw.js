// OK Media Consulting — Service Worker
const CACHE = 'okm-v1';
const STATIC = ['/static/okm.css', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Only cache GET requests for static assets
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/static/okm.css')) {
    return; // Always fetch fresh from network
  }
  // Network-first for HTML pages
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
