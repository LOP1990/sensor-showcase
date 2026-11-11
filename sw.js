/* Service worker do app de demonstração — versão 2026.11.10-2116
   - App (index.html, fontes, ícones): rede primeiro, cache como reserva → abre offline.
   - Vídeos e áudio (/videos/, /audio/): cache primeiro, baixados uma única vez, com suporte a
     pedidos parciais (Range) para o <video> conseguir buscar/avançar a partir do cache.
   - version.json e config.json: sempre da rede (nunca cacheados). */
const VERSION = '2026.11.10-2116';
const CACHE = 'sensor-showcase-' + VERSION;
const MEDIA = 'sensor-showcase-media';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE && k !== MEDIA).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

function isMedia(url) { return /\/(videos|audio)\//.test(url.pathname) || /\.(mp4|webm|m4v|mp3|m4a|ogg)$/i.test(url.pathname); }

const warming = new Set();
function rangeFrom(full, request, blob) {
  const range = request.headers.get('range');
  if (!range) return full;
  return blob.then((b) => {
    const size = b.size;
    const m = /bytes=(\d*)-(\d*)/.exec(range);
    let start = m && m[1] ? parseInt(m[1], 10) : 0;
    let end = m && m[2] ? parseInt(m[2], 10) : size - 1;
    if (isNaN(start) || start >= size) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
    end = Math.min(end, size - 1);
    return new Response(b.slice(start, end + 1), {
      status: 206,
      headers: {
        'Content-Type': full.headers.get('Content-Type') || 'application/octet-stream',
        'Content-Range': `bytes ${start}-${end}/${size}`,
        'Content-Length': String(end - start + 1),
        'Accept-Ranges': 'bytes',
      },
    });
  });
}
async function mediaResponse(e) {
  const request = e.request;
  const url = new URL(request.url); url.search = '';
  const cache = await caches.open(MEDIA);
  const full = await cache.match(url.href);
  if (full) return rangeFrom(full, request, full.blob());
  // Ainda não está em cache: a primeira reprodução vem direto da rede (começa a tocar na hora) e,
  // ao mesmo tempo, o mesmo fluxo é gravado no cache para as próximas vezes.
  const range = request.headers.get('range');
  const fromStart = !range || /^bytes=0-\s*$/.test(range);
  if (fromStart && !warming.has(url.href)) {
    const res = await fetch(url.href, { cache: 'no-store' });
    if (!res.ok || res.status !== 200 || !res.body) return res;
    warming.add(url.href);
    const [toClient, toCache] = res.body.tee();
    const headers = new Headers(res.headers);
    const put = cache.put(url.href, new Response(toCache, { status: 200, headers })).catch(() => {}).finally(() => warming.delete(url.href));
    e.waitUntil(put);
    return new Response(toClient, { status: 200, headers });
  }
  return fetch(request); // buscas/avanços antes de o cache completar: direto da rede, com Range
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (/version\.json$|config\.json$/.test(url.pathname)) return; // sempre da rede
  if (isMedia(url)) { e.respondWith(mediaResponse(e)); return; }
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
