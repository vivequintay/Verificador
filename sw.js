// EL VERIFICADOR TIENE QUE ABRIR SIN SEÑAL.
//
// Android cierra la PWA cuando el teléfono pasa un rato en el bolsillo. Si el operador la
// vuelve a abrir en un punto del cerro sin señal, sin este archivo el teléfono muestra la
// página de error del navegador: no hay nada guardado de dónde sacar la app.
//
// HISTORIA, PARA QUE NO VUELVA. La primera versión (enero 2026) guardaba '/index.html' con
// barra adelante. En GitHub Pages eso es vivequintay.github.io/index.html, que no es el
// Verificador: la precarga fallaba, se sacó, y en la misma reescritura se perdió el
// registro en index.html. Desde entonces este archivo no corría en ningún teléfono. Por
// eso acá TODA ruta propia es relativa a la carpeta del Verificador.
//
// LA PÁGINA SIGUE SALIENDO FRESCA. Con señal se pide a la red saltando el caché HTTP de
// GitHub Pages (max-age=600), así lo publicado se ve al abrir, como hasta ahora. Lo
// guardado sólo entra si la red falla o se demora más de ESPERA_RED_MS.

const CACHE_NAME = 'verificador-v5';

// Más que esto, mirando una pantalla quieta, el operador cree que el teléfono se colgó.
const ESPERA_RED_MS = 4000;

// logo_ticket.png va aunque no se vea en pantalla: es el que imprime el ticket, y sin él
// guardado el ticket sale sin logo cuando no hay señal.
const PROPIOS = [
    'index.html', 'manifest.json', 'logo.png', 'logo_ticket.png',
    'icon-192.png', 'icon-512.png',
    'icon-maskable-192.png', 'icon-maskable-512.png',
    'icon-splash-192.png', 'icon-splash-512.png',
];

// Firebase y el lector de QR. Traen la versión en la dirección, así que una vez
// guardados no cambian nunca: se sirven desde el teléfono sin gastar datos.
const LIBRERIAS = [
    'https://www.gstatic.com/firebasejs/8.10.0/firebase-app.js',
    'https://www.gstatic.com/firebasejs/8.10.0/firebase-firestore.js',
    'https://www.gstatic.com/firebasejs/8.10.0/firebase-auth.js',
    'https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js',
];

const LA_PAGINA = new URL('index.html', self.registration.scope).href;

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        // Lo propio TIENE que quedar: si falla, este archivo no se instala y sigue el
        // anterior. `reload` salta el caché HTTP para no guardar una versión vieja.
        await cache.addAll(PROPIOS.map((p) => new Request(p, { cache: 'reload' })));
        // Las librerías, a lo que salga: si una no baja ahora, se guarda la primera vez
        // que la página la pida. No pueden impedir que lo demás quede instalado.
        await Promise.all(LIBRERIAS.map((url) =>
            fetch(url, { mode: 'no-cors' })
                .then((res) => cache.put(url, res))
                .catch(() => {})));
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const nombres = await caches.keys();
        await Promise.all(nombres.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)));
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);

    if (req.mode === 'navigate') {
        event.respondWith(laPagina(event, req));
    } else if (LIBRERIAS.includes(req.url) || url.hostname === 'fonts.gstatic.com') {
        event.respondWith(guardadoPrimero(req));
    } else if (url.origin === self.location.origin || url.hostname === 'fonts.googleapis.com') {
        event.respondWith(guardadoYRefrescar(event, req));
    }
    // Todo lo demás (Firestore, el inicio de sesión) pasa directo, sin tocarlo: esas
    // conexiones son vivas y tienen su propia forma de funcionar sin señal.
});

// La red si contesta a tiempo; si no, lo guardado. Cada respuesta buena de la red
// reemplaza a la guardada, así lo guardado es siempre lo último que se publicó.
async function laPagina(event, req) {
    const cache = await caches.open(CACHE_NAME);
    const red = fetch(req, { cache: 'no-store' });
    // Se guarda aunque la respuesta llegue tarde y la página ya haya salido de lo
    // guardado: así la próxima apertura sin señal trae lo último publicado.
    event.waitUntil(red
        .then((res) => (res.ok ? cache.put(LA_PAGINA, res.clone()) : null))
        .catch(() => {}));
    const guardada = () => cache.match(LA_PAGINA);
    const aTiempo = red.then(
        (res) => (res.ok ? res : guardada().then((g) => g || res)),
        () => guardada().then((g) => g || Response.error()));
    const tarde = new Promise((r) => setTimeout(r, ESPERA_RED_MS))
        .then(guardada)
        .then((g) => g || aTiempo);
    return Promise.race([aTiempo, tarde]);
}

async function guardadoPrimero(req) {
    const cache = await caches.open(CACHE_NAME);
    const guardado = await cache.match(req);
    if (guardado) return guardado;
    const res = await fetch(req);
    if (res.ok || res.type === 'opaque') cache.put(req, res.clone());
    return res;
}

// Lo guardado al tiro, y por detrás se trae lo nuevo para la próxima vez. Para el logo,
// los íconos y el manifiesto: un logo cambiado se ve en la apertura siguiente.
async function guardadoYRefrescar(event, req) {
    const cache = await caches.open(CACHE_NAME);
    const guardado = await cache.match(req, { ignoreSearch: true });
    const red = fetch(req).then(async (res) => {
        if (res.ok) await cache.put(req, res.clone());
        return res;
    });
    if (guardado) {
        event.waitUntil(red.catch(() => {}));
        return guardado;
    }
    return red;
}
