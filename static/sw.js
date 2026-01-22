const VERSION = 'v8';
const STATIC_CACHE = `manganegus-static-${VERSION}`;
const DATA_CACHE = `manganegus-data-${VERSION}`;
const IMAGE_CACHE = `manganegus-images-${VERSION}`;

const STATIC_ASSETS = [
  '/',
  '/reader',
  '/static/manifest.json',
  '/static/css/styles.css',
  '/static/css/reader.css',
  '/static/js/main.js',
  '/static/js/reader.js',
  '/static/images/sharingan.png',
  '/static/images/placeholder.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => ![STATIC_CACHE, DATA_CACHE, IMAGE_CACHE].includes(key))
        .map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

async function cacheFirst(request, cacheName = STATIC_CACHE) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(cacheName);
  cache.put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    // Only cache successful responses (2xx status codes)
    // Don't cache errors like 429 rate limit, 403 forbidden, etc.
    if (response.ok) {
      const cache = await caches.open(DATA_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.pathname.startsWith('/api/download/direct')) {
    return;
  }
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  if (url.pathname.startsWith('/api/proxy/image') || url.pathname.startsWith('/downloads/') || url.pathname.startsWith('/static/downloads/')) {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }

  if (request.mode === 'navigate') {
    const path = url.pathname === '/reader' ? '/reader' : '/';
    event.respondWith(
      cacheFirst(path).catch(() => caches.match(path) || caches.match('/'))
    );
    return;
  }

  event.respondWith(cacheFirst(request));
});
