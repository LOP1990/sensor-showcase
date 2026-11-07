/* Service worker do app de demonstração — versão 2026.11.07-0806
   Estratégia: rede primeiro, cache como reserva. Assim o tablet abre o app
   mesmo sem internet (último conteúdo visto) e pega a versão nova assim que
   a rede volta. version.json nunca é cacheado. */
const VERSION = '2026.11.07-0806';
const CACHE = 'sensor-showcase-' + VERSION;
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.endsWith('version.json')) return; // sempre da rede
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = url.pathname.endsWith('/') || url.pathname.endsWith('index.html') ? './index.html' : e.request;
    try {
      const res = await fetch(e.request, { cache: 'no-cache' });
      if (res && res.ok) cache.put(key, res.clone());
      return res;
    } catch (err) {
      const hit = await cache.match(key);
      if (hit) return hit;
      throw err;
    }
  })());
});
