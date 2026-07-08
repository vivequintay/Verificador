const CACHE_NAME = 'quintay-v2';

// Instalación: activa de inmediato (no espera a que se cierren pestañas viejas).
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

// Estrategia: RED primero.
// Para el HTML (navegaciones) forzamos { cache: 'no-store' } para SALTAR el caché HTTP
// de GitHub Pages (max-age=600). Así, al pushear cambios, la PWA los ve al instante y no
// hay que esperar 10 min ni limpiar caché. El resto de recursos: red normal, con caché
// como respaldo si no hay conexión.
self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.mode === 'navigate' || req.destination === 'document') {
        event.respondWith(
            fetch(req, { cache: 'no-store' }).catch(() => caches.match(req))
        );
    } else {
        event.respondWith(
            fetch(req).catch(() => caches.match(req))
        );
    }
});
