// Service worker : coquille installable + cache des fichiers statiques.
const CACHE = 'veille-ht-v2';
const ASSETS = ['.', 'index.html', 'style.css', 'app.js', 'engine.js', 'manifest.webmanifest', 'icons/icon.svg', 'data/cote.json', 'data/lots.json'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS.map((a) => new Request(a, { cache: 'reload' }))).catch(() => {})).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  // Données fraîches d'abord (lots + cote), repli cache.
  if (u.pathname.endsWith('lots.json') || u.pathname.endsWith('cote.json')) {
    e.respondWith(fetch(e.request).then((r) => { const c = r.clone(); caches.open(CACHE).then((k) => k.put(e.request, c)); return r; }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then((c) => c || fetch(e.request)));
});
