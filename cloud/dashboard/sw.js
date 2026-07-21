/* forsyth live — service worker.
   Philosophy: never serve stale weather. The network is always asked first
   for anything that changes (HTML navigations, /api/); the cache exists so
   the app SHELL opens instantly and something sensible appears when the
   phone is on a mountain with one bar.
   Static assets are cache-busted by ?v=N query strings, so
   stale-while-revalidate is safe for them: a new version is a new URL.      */
'use strict';

const CACHE = 'forsyth-v2';   /* v2: "/" now serves the board, not the old index */

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/'])));
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function networkFirst(req, fallbackUrl) {
  const c = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    if (res.ok) c.put(req, res.clone());
    return res;
  } catch {
    return (await c.match(req)) ||
           (fallbackUrl && await c.match(fallbackUrl)) ||
           Response.error();
  }
}

async function staleWhileRevalidate(req) {
  const c = await caches.open(CACHE);
  const hit = await c.match(req);
  const refresh = fetch(req).then(res => {
    if (res.ok) c.put(req, res.clone());
    return res;
  }).catch(() => hit);
  return hit || refresh;
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/media/')) return;        /* big, streamy — no cache */
  if (e.request.mode === 'navigate') {
    e.respondWith(networkFirst(e.request, '/'));
  } else if (url.pathname.startsWith('/api/')) {
    e.respondWith(networkFirst(e.request));              /* offline = last-known */
  } else {
    e.respondWith(staleWhileRevalidate(e.request));      /* versioned statics    */
  }
});
