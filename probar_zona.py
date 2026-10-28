"""SOLO DENTRO DEL PARKING: la capa FUERA DE RANGO, de punta a punta, en un Chrome sin ventana.

Pedido suyo (28-10-2026): el operador que no esta fisicamente en el parking no puede usar
la app. Circulo de 400 m alrededor del punto que el marco en Google Maps, SIN margen: salir
del circulo bloquea al tiro. El administrador queda fuera del bloqueo.

Se le cambia la ubicacion a Chrome como si el telefono caminara (la misma via por la que un
telefono de verdad le da el GPS a la pagina). La sesion es simulada y Firestore queda
bloqueado como en `probar_sin_senal.py`: nada llega a la nube.

    <python con playwright> probar_zona.py [carpeta para capturas y video]

Con una carpeta deja ahi las capturas en tamano de telefono (412 x 915) y un video corto
del operador caminando hacia afuera y volviendo.
"""
import math
import os
import shutil
import sys
import tempfile
import time

import probar_sin_senal as base
from playwright.sync_api import sync_playwright

TELEFONO = {"width": 412, "height": 915}
CAPTURAS = sys.argv[1] if len(sys.argv) > 1 else None
anota = base.anota

CENTRO = (-33.194690, -71.699389)   # el que marco el en Google Maps
RADIO = 400
R_TIERRA = 6371008.8

# Envuelve la ubicacion del navegador para contar las veces que la pagina la pide y para
# simular lo que Chrome no deja simular: la ubicacion del telefono APAGADA (codigo 2).
ESPIA_UBICACION = """(() => {
    const g = navigator.geolocation;
    const get = g.getCurrentPosition.bind(g), watch = g.watchPosition.bind(g);
    window.__geo = { llamadas: 0, apagada: false };
    const fallar = (err) => setTimeout(() => err && err({ code: 2, message: 'apagada' }), 50);
    g.getCurrentPosition = (ok, err, op) => {
        __geo.llamadas++;
        return __geo.apagada ? fallar(err) : get(ok, err, op);
    };
    g.watchPosition = (ok, err, op) => {
        __geo.llamadas++;
        if (__geo.apagada) { fallar(err); return -1; }
        return watch(ok, err, op);
    };
})();"""

# Sesion simulada: un usuario con el rol que se le diga. `modo`: 'ya' (el servidor contesta
# el rol al tiro), 'demora' (no contesta hasta __soltarRol()), 'sin_senal' (no contesta).
SESION = """(() => {
    window.__entrar = (uid, rol, modo) => {
        let soltar = () => {};
        const espera = modo === 'sin_senal' ? Promise.reject(new Error('sin senal'))
                     : modo === 'demora' ? new Promise((r) => { soltar = r; })
                     : Promise.resolve();
        espera.catch(() => {});
        window.__soltarRol = () => soltar();
        alCambiarSesion({ uid, displayName: uid, email: uid + '@verificador.vivequintay.cl',
                          getIdTokenResult: () => espera.then(() => ({ claims: { rol } })) });
    };
})();"""


def destino(d, rumbo):
    """El punto a `d` metros del centro hacia `rumbo` (0 = norte, 90 = este)."""
    f1, l1, t = math.radians(CENTRO[0]), math.radians(CENTRO[1]), math.radians(rumbo)
    s = d / R_TIERRA
    f2 = math.asin(math.sin(f1) * math.cos(s) + math.cos(f1) * math.sin(s) * math.cos(t))
    l2 = l1 + math.atan2(math.sin(t) * math.sin(s) * math.cos(f1), math.cos(s) - math.sin(f1) * math.sin(f2))
    return math.degrees(f2), math.degrees(l2)


def ir(ctx, d=0, rumbo=0, precision=10):
    lat, lon = destino(d, rumbo)
    ctx.set_geolocation({"latitude": lat, "longitude": lon, "accuracy": precision})


def estado(page):
    return page.evaluate("""() => ({
        estado: zonaEstado,
        tapa: getComputedStyle(document.getElementById('zona-capa')).display !== 'none',
        texto: document.getElementById('zona-texto').textContent,
        login: getComputedStyle(document.getElementById('login-overlay')).display !== 'none' })""")


def esperar(page, esperado, plazo=5):
    """Segundos hasta que zonaEstado sea `esperado`, o None si no llega."""
    t0 = time.time()
    try:
        page.wait_for_function("(e) => zonaEstado === e", arg=esperado, timeout=plazo * 1000)
    except Exception:
        return None
    return round(time.time() - t0, 2)


def quieto(page, ms=1500):
    """Deja pasar un rato para ver que NO cambia nada."""
    page.wait_for_timeout(ms)
    return estado(page)


def volver_a_la_app(page, hace_cuanto_ms):
    """Como si el operador volviera de RawBT o de la camara: la ultima lectura que decidio
    algo fue hace `hace_cuanto_ms`."""
    page.evaluate("(ms) => { zonaUltima = Date.now() - ms; "
                  "document.dispatchEvent(new Event('visibilitychange')); }", hace_cuanto_ms)


def llamadas(page):
    return page.evaluate("() => __geo.llamadas")


def foto(page, nombre):
    """Sin el splash: al volver a la app tras 5 min se muestra 3 s encima de todo, tambien de
    la capa (asi es en el telefono), y la foto saldria de el."""
    if CAPTURAS:
        page.evaluate("() => { document.getElementById('splash-screen').style.display = 'none'; }")
        page.wait_for_timeout(250)
        page.screenshot(path=os.path.join(CAPTURAS, nombre + ".png"))


def abrir(pw, url, video=None):
    """Chrome con el Verificador servido en localhost. Solo salen el propio Verificador y
    sus librerias; Firestore y el inicio de sesion quedan cortados."""
    nav = pw.chromium.launch(channel="chrome", headless=True)
    opciones = {"viewport": TELEFONO}
    if video:
        opciones.update(record_video_dir=video, record_video_size=TELEFONO)
    ctx = nav.new_context(**opciones)

    def filtro(route):
        host = route.request.url.split("/")[2].split(":")[0]
        if host in ("127.0.0.1", "localhost") or host in base.PERMITIDOS:
            route.continue_()
        else:
            route.abort()
    ctx.route("**/*", filtro)
    ctx.add_init_script(ESPIA_UBICACION)
    page = ctx.new_page()
    errores = []
    base.vigilar(page, errores)
    page.goto(url)
    page.add_script_tag(content=SESION)
    # Firebase dice primero que no hay nadie; recien despues se entra con la sesion simulada.
    page.evaluate("""() => new Promise((listo) => {
        const soltar = auth.onAuthStateChanged(() => { soltar(); listo(); }); })""")
    page.evaluate("() => { const s = document.getElementById('splash-screen'); if (s) s.style.display = 'none'; }")
    return nav, ctx, page, errores


def main():
    if CAPTURAS:
        os.makedirs(CAPTURAS, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="verif_zona_")
    try:
        base.preparar(tmp, None)
        srv = base.Servidor(tmp)
        url = f"http://127.0.0.1:{srv.puerto}/Verificador/index.html"
        with sync_playwright() as pw:
            nav, ctx, page, errores = abrir(pw, url)

            # 0. La regla de medir: el centro es el suyo y las distancias son las del mapa.
            centro = page.evaluate("() => [ZONA_CENTRO.lat, ZONA_CENTRO.lon, ZONA_RADIO_M]")
            anota("el centro es el que marcaste y el radio 400 m",
                  centro == [CENTRO[0], CENTRO[1], RADIO], str(centro))
            # Referencias que no salen de la misma formula: un minuto de latitud mide 1.853 m,
            # y uno de longitud, a esta latitud, eso por el coseno (1.551 m).
            minutos = page.evaluate("""() => [
                distanciaM(-33.19469, -71.699389, -33.19469 + 1/60, -71.699389),
                distanciaM(-33.19469, -71.699389, -33.19469, -71.699389 + 1/60)]""")
            esperado_lon = 1853.25 * math.cos(math.radians(CENTRO[0]))
            anota("las distancias calzan con el mapa (1' de latitud y de longitud)",
                  abs(minutos[0] - 1853.25) < 0.5 and abs(minutos[1] - esperado_lon) < 0.5,
                  f"{minutos[0]:.1f} m y {minutos[1]:.1f} m")

            # 1. Sin sesion no hay capa ni se pide la ubicacion: manda la pantalla de ingreso.
            e = estado(page)
            anota("sin sesion: ni capa ni ubicacion, se ve el ingreso",
                  not e["tapa"] and e["login"] and llamadas(page) == 0, str(e))

            # 2. Primera vez en el telefono: se tapa sin pedir la ubicacion hasta saber el rol.
            ctx.grant_permissions(["geolocation"])
            ir(ctx, 0)
            page.evaluate("() => __entrar('marcela', 'operador', 'demora')")
            page.wait_for_timeout(300)
            e = estado(page)
            anota("primera vez, rol sin llegar: tapado y SIN pedir la ubicacion",
                  e["tapa"] and e["estado"] == "buscando" and llamadas(page) == 0, str(e))
            foto(page, "1 buscando")
            page.evaluate("() => __soltarRol()")
            seg = esperar(page, "dentro")
            anota("llega el rol de operador, se mide y esta en el parking: entra",
                  seg is not None and not estado(page)["tapa"], f"{seg} s")
            anota("y se pudo tocar la app (lo que hay bajo el dedo es la caja de patente)",
                  page.evaluate("""() => { const r = document.getElementById('inputPatente').getBoundingClientRect();
                      return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).id; }""") == "inputPatente")
            foto(page, "2 en el parking")

            # 3. Camina hacia afuera. Sin margen: 401 m bloquea al tiro.
            page.click("#inputPatente")
            ir(ctx, 399, 0)
            anota("a 399 m al norte: sigue dentro", quieto(page)["estado"] == "dentro")
            ir(ctx, 401, 0)
            seg = esperar(page, "fuera", 3)
            e = estado(page)
            anota("a 401 m: FUERA DE RANGO al tiro, sin esperar nada",
                  seg is not None and seg < 1.5 and e["tapa"] and e["texto"] == "FUERA DE RANGO",
                  f"{seg} s · {e}")
            anota("la capa tapa todo: lo que hay bajo el dedo es la capa",
                  page.evaluate("""() => { const r = document.getElementById('inputPatente').getBoundingClientRect();
                      return !!document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).closest('#zona-capa'); }"""))
            anota("y el teclado se cierra (la caja de patente pierde el foco)",
                  page.evaluate("() => document.activeElement.id") != "inputPatente")
            foto(page, "3 fuera de rango")
            ir(ctx, 0)
            seg = esperar(page, "dentro", 3)
            anota("vuelve al parking: la app aparece sola", seg is not None and not estado(page)["tapa"], f"{seg} s")

            # 4. Es un circulo: igual hacia los cuatro lados.
            lados = []
            for rumbo, nombre in ((90, "este"), (180, "sur"), (270, "oeste")):
                ir(ctx, 399, rumbo)
                adentro = esperar(page, "dentro", 3) is not None and quieto(page, 600)["estado"] == "dentro"
                ir(ctx, 401, rumbo)
                afuera = esperar(page, "fuera", 3) is not None
                lados.append(f"{nombre} {'bien' if adentro and afuera else 'MAL'}")
            ir(ctx, 0)
            esperar(page, "dentro", 3)
            anota("399 m dentro y 401 m fuera hacia el este, el sur y el oeste",
                  all(l.endswith("bien") for l in lados), ", ".join(lados))

            # 5. Una lectura mala no bloquea al que esta dentro; una lejana, aunque mala, si.
            ir(ctx, 0, 0, precision=1500)
            anota("dentro, llega una lectura con 1.500 m de error: no lo bloquea",
                  quieto(page)["estado"] == "dentro")
            ir(ctx, 5000, 45, precision=1500)
            anota("a 5 km, aun con 1.500 m de error: FUERA DE RANGO", esperar(page, "fuera", 3) is not None)
            ir(ctx, 0)
            esperar(page, "dentro", 3)

            # 5b. Con el telefono quieto Chrome no avisa nada: cada minuto se vuelve a medir.
            antes = llamadas(page)
            page.evaluate("() => { zonaPedida = Date.now() - 61000; }")
            e = quieto(page, 1600)
            anota("quieto un minuto en el parking: vuelve a medir y sigue dentro, sin taparse",
                  llamadas(page) == antes + 1 and e["estado"] == "dentro", f"pedidos {llamadas(page) - antes}")
            ir(ctx, 600, 200)
            anota("y si en ese minuto se fue: FUERA DE RANGO", esperar(page, "fuera", 3) is not None)
            ir(ctx, 0)
            esperar(page, "dentro", 3)

            # 6. Volver de otra app (RawBT, la camara).
            volver_a_la_app(page, 20000)
            anota("vuelve de RawBT a los 20 s: sigue dentro, sin tapar",
                  quieto(page, 800)["estado"] == "dentro")
            ir(ctx, 2000, 0)
            volver_a_la_app(page, 5 * 60000)
            e = estado(page)
            anota("vuelve a los 5 min: se tapa hasta medir de nuevo", e["tapa"], str(e))
            anota("y si ahora esta a 2 km: FUERA DE RANGO", esperar(page, "fuera", 3) is not None)
            ir(ctx, 0)
            esperar(page, "dentro", 3)

            # 7. Sin permiso de ubicacion, y con la ubicacion del telefono apagada.
            ctx.clear_permissions()
            volver_a_la_app(page, 5 * 60000)
            seg = esperar(page, "sin_ubicacion", 5)
            e = estado(page)
            anota("sin permiso de ubicacion: ACTIVA LA UBICACION",
                  seg is not None and e["tapa"] and e["texto"] == "ACTIVA LA UBICACIÓN", str(e))
            foto(page, "4 activa la ubicacion")
            ctx.grant_permissions(["geolocation"])
            volver_a_la_app(page, 5 * 60000)
            anota("da el permiso y vuelve a la app: entra", esperar(page, "dentro", 5) is not None)
            # Chrome avisa "apagada" en cada tropiezo del GPS, con la lectura buena detras
            # (el Chrome de esta prueba lo hace en CADA cambio de ubicacion).
            page.evaluate("() => zonaError({ code: 2 })")
            anota("dentro, un aviso suelto de ubicacion apagada: no lo tapa",
                  quieto(page)["estado"] == "dentro")
            page.evaluate("() => { __geo.apagada = true; zonaError({ code: 2 }); }")
            seg = esperar(page, "sin_ubicacion", 3)
            anota("dentro, apaga la ubicacion del telefono: ACTIVA LA UBICACION",
                  seg is not None, str(estado(page)))
            page.evaluate("() => { __geo.apagada = false; }")
            seg = esperar(page, "dentro", 8)
            # Reintenta cada 5 s y lo revisa con un reloj de 1 s: a lo mas, 6 s.
            anota("la enciende sin salir de la app: se destapa sola en unos 5 s",
                  seg is not None and seg <= 6.5, f"{seg} s")
            page.evaluate("() => { __geo.apagada = true; }")
            volver_a_la_app(page, 5 * 60000)
            anota("abre la app con la ubicacion apagada: ACTIVA LA UBICACION",
                  esperar(page, "sin_ubicacion", 3) is not None)
            page.evaluate("() => { __geo.apagada = false; }")
            anota("la enciende: entra", esperar(page, "dentro", 8) is not None)

            # 8. Solo lecturas malas al abrir (la ubicacion "aproximada" de Android): no entra,
            # y a los 30 s pide la ubicacion. Este caso espera el plazo de verdad.
            ir(ctx, 0, 0, precision=2000)
            volver_a_la_app(page, 5 * 60000)
            anota("solo lecturas con 2 km de error: no deja entrar",
                  quieto(page, 3000)["estado"] == "buscando")
            seg = esperar(page, "sin_ubicacion", 35)
            anota("a los 30 s: ACTIVA LA UBICACION", seg is not None, f"{seg} s mas")
            ir(ctx, 0)
            volver_a_la_app(page, 5 * 60000)
            esperar(page, "dentro", 5)

            # 9. El boton de la capa cierra la sesion (el unico boton que tiene).
            ir(ctx, 3000, 0)
            esperar(page, "fuera", 3)
            page.evaluate("() => { window.cerrarSesion = () => alCambiarSesion(null); }")
            page.click("#zona-capa .btn-esquina")
            page.wait_for_timeout(300)
            e = estado(page)
            anota("fuera de rango, toca cerrar sesion: sale y queda el ingreso, sin capa",
                  not e["tapa"] and e["login"] and e["estado"] is None, str(e))

            # 10. EL ADMINISTRADOR, a 50 km: nunca se le tapa ni se le pide la ubicacion.
            ir(ctx, 50000, 300)
            antes = llamadas(page)
            page.evaluate("() => __entrar('mickael', 'administrador', 'demora')")
            page.wait_for_timeout(200)
            page.evaluate("() => __soltarRol()")
            e = quieto(page, 1500)
            anota("administrador a 50 km, primera vez: sin capa y sin pedir la ubicacion",
                  not e["tapa"] and llamadas(page) == antes, f"{e} · pedidos {llamadas(page) - antes}")
            foto(page, "5 administrador a 50 km")
            page.evaluate("() => alCambiarSesion(null)")
            antes = llamadas(page)
            page.evaluate("() => __entrar('mickael', 'administrador', 'sin_senal')")
            e = quieto(page, 1500)
            anota("administrador a 50 km SIN SENAL (no se puede preguntar el rol): tampoco",
                  not e["tapa"] and llamadas(page) == antes, str(e))
            page.evaluate("() => alCambiarSesion(null)")

            # 11. El operador que ya entro antes en este telefono, en su casa.
            page.evaluate("() => __entrar('marcela', 'operador', 'demora')")
            seg = esperar(page, "fuera", 3)
            anota("operador a 50 km, rol todavia sin llegar: FUERA DE RANGO igual",
                  seg is not None, f"{seg} s")
            page.evaluate("() => __soltarRol()")
            anota("y sigue asi cuando llega el rol", quieto(page)["estado"] == "fuera")
            page.evaluate("() => alCambiarSesion(null)")
            page.evaluate("() => __entrar('marcela', 'operador', 'sin_senal')")
            anota("operador a 50 km sin senal: FUERA DE RANGO (el GPS no necesita internet)",
                  esperar(page, "fuera", 3) is not None)
            page.evaluate("() => alCambiarSesion(null)")

            # 12. Si el rol cambia en la caja, manda el del servidor.
            page.evaluate("() => __entrar('marcela', 'administrador', 'ya')")
            anota("a la operadora la hacen administradora: deja de taparse",
                  quieto(page)["estado"] is None and not estado(page)["tapa"])
            page.evaluate("() => alCambiarSesion(null)")
            page.evaluate("() => __entrar('marcela', 'operador', 'ya')")
            anota("y si vuelve a operadora: FUERA DE RANGO otra vez", esperar(page, "fuera", 3) is not None)

            anota("sin errores de JavaScript ni avisos", not errores, "; ".join(errores)[:200])
            ctx.close()
            nav.close()

            if CAPTURAS:
                video(pw, url)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = sum(base.resultados)
    print(f"\n{ok} de {len(base.resultados)} bien")
    sys.exit(0 if ok == len(base.resultados) else 1)


def video(pw, url):
    """El operador camina del parking hacia el norte de a 50 m, pasa los 400 m y vuelve.
    El rotulo amarillo de los metros lo pone ESTA PRUEBA para que se entienda el video: la
    app no lo tiene."""
    carpeta = tempfile.mkdtemp(prefix="verif_zona_video_")
    nav, ctx, page, _ = abrir(pw, url, video=carpeta)
    ctx.grant_permissions(["geolocation"])
    ir(ctx, 0)
    page.evaluate("""() => { const r = document.createElement('div'); r.id = '__metros';
        r.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:100000;'
            + 'background:#FFD600;color:#000;font:800 18px sans-serif;padding:6px 14px;border-radius:8px;'
            + 'white-space:nowrap';
        document.body.appendChild(r); }""")

    def rotulo(m):
        page.evaluate("(t) => { document.getElementById('__metros').textContent = t; }", f"PRUEBA · a {m} m del centro")
    rotulo(0)
    page.evaluate("() => __entrar('marcela', 'operador', 'ya')")
    esperar(page, "dentro", 5)
    page.wait_for_timeout(1500)
    for m in list(range(50, 451, 50)) + [400, 350, 300]:
        ir(ctx, m, 0)
        rotulo(m)
        page.wait_for_timeout(900)
    page.wait_for_timeout(800)
    nombre = page.video.path()
    ctx.close()
    nav.close()
    shutil.copy(nombre, os.path.join(CAPTURAS, "6 caminando hacia afuera y de vuelta.webm"))
    shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    main()
