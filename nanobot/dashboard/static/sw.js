const CACHE_NAME = 'nanobot-pwa-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(ASSETS_TO_CACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // Network First for API
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => new Response(JSON.stringify({ error: "App is offline cache fallback", success: false }), {
        headers: { 'Content-Type': 'application/json' }
      }))
    );
  } else {
    // Static assets: Cache First. HTML routing: Network First, fallback to cached '/'
    event.respondWith(
      caches.match(event.request).then(cachedResponse => {
        if (cachedResponse && url.pathname.startsWith('/static/')) {
            return cachedResponse;
        }
        return fetch(event.request).catch(() => {
            return cachedResponse || caches.match('/');
        });
      })
    );
  }
});
