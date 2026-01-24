const CACHE_NAME = 'quintay-v1';

// Instalación: No forzamos rutas para evitar errores de carga
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

// Estrategia: Ir a la red primero, si falla, buscar en caché
self.addEventListener('fetch', (event) => {
    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request);
        })
    );
});
