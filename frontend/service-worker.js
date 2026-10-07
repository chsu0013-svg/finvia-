const CACHE='finvia-v4-shell';
const SHELL=['/','/index.html','/app.css','/app.js','/manifest.webmanifest','/icon-512.png','/icon-192.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  const req=e.request,url=new URL(req.url);
  // Never cache API calls (they contain the visitor's financial data) or cross-origin requests.
  if(req.method!=='GET'||url.origin!==location.origin||url.pathname.startsWith('/api/')||url.pathname==='/health')return;
  e.respondWith(fetch(req).then(r=>{if(r.ok){const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy))}return r}).catch(()=>caches.match(req)));
});
