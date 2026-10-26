"""El Verificador SIN SENAL, de punta a punta, en un Chrome sin ventana.

POR QUE EXISTE ESTE ARCHIVO. Hasta octubre de 2026 el Verificador no abria sin senal (el
sw.js no estaba registrado desde enero) y un ingreso anotado sin senal se quedaba
esperando al servidor para siempre y se perdia al cerrar la app. Esas dos cosas no se ven
en el PC con internet: hay que cortar la red para verlas. Esto la corta.

QUE HACE, EN ORDEN:
  1. Abre el Verificador CON red, como el primer dia: el sw.js se instala y guarda la app.
  2. APAGA EL SERVIDOR y la red, y lo vuelve a abrir. Tiene que abrir.
  3. Busca una patente que el telefono nunca vio: tiene que decir NO REGISTRADO con el
     aviso SIN SENAL, no "Error de conexion".
  4. La registra: tiene que terminar en segundos y quedar EN COLA.
  4b. Marca la SALIDA y el REINGRESO de un pase pagado: EN COLA, y en ese orden.
  5. Cierra Chrome entero y lo vuelve a abrir, sin red: el registro tiene que seguir ahi.
  5b. SENAL DEBIL, el caso del cerro: el telefono cree que tiene red y no llega nada.
     Buscar y registrar tienen que terminar en segundos igual.
  6. En un perfil limpio y CON red: lo publicado se tiene que ver al abrir, sin esperar.

NUNCA LLEGA A LA NUBE DE VERDAD. Tres seguros, cualquiera alcanza: (a) solo se deja pasar
al propio Verificador y a sus librerias, Firestore y el inicio de sesion quedan
bloqueados; (b) no hay sesion iniciada, y sin sesion las reglas rechazan todo; (c) lo que
se registra se registra con la red cortada y el perfil se borra al terminar.

Uso:  python probar_sin_senal.py            (la copia de trabajo)
      python probar_sin_senal.py b3caadb    (una version del historial, para ver que falla)

Necesita Playwright (pip install playwright) y usa el Chrome instalado: no descarga nada.
"""
import functools
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright, Error as PWError

AQUI = os.path.dirname(os.path.abspath(__file__))
GIT = r"C:\Program Files\Git\cmd\git.exe"
ARCHIVOS = ["index.html", "sw.js", "manifest.json", "logo.png",
            "icon-192.png", "icon-512.png", "icon-maskable-192.png",
            "icon-maskable-512.png", "icon-splash-192.png", "icon-splash-512.png"]

# Lo unico que puede salir a internet: las librerias que el Verificador carga.
PERMITIDOS = ("www.gstatic.com", "cdnjs.cloudflare.com",
              "fonts.googleapis.com", "fonts.gstatic.com")

PATENTE = "ZZ9999"   # no existe en Chile: no puede chocar con nada real
PASE = "ZZ9997"      # un pase diario pagado, creado solo dentro del perfil de prueba

resultados = []
bloqueados = {}   # host -> cuantas veces se le corto el paso


def anota(nombre, ok, detalle=""):
    resultados.append(ok)
    print(("  OK    " if ok else "  FALLA ") + nombre + (f"  ({detalle})" if detalle else ""))


def preparar(destino, version):
    """Copia el Verificador a destino/Verificador/, como en GitHub Pages."""
    carpeta = os.path.join(destino, "Verificador")
    os.makedirs(carpeta)
    for a in ARCHIVOS:
        salida = os.path.join(carpeta, a)
        if version is None:
            if os.path.exists(os.path.join(AQUI, a)):
                shutil.copy(os.path.join(AQUI, a), salida)
        else:
            r = subprocess.run([GIT, "-C", AQUI, "show", f"{version}:{a}"], capture_output=True)
            if r.returncode == 0:
                with open(salida, "wb") as f:
                    f.write(r.stdout)
    return carpeta


class Servidor:
    def __init__(self, raiz):
        manejador = functools.partial(Silencioso, directory=raiz)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
        self.puerto = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def apagar(self):
        self.srv.shutdown()
        self.srv.server_close()


class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def abrir_chrome(pw, perfil, colgar=False):
    """colgar=True: lo bloqueado no se corta, se deja SIN RESPUESTA. Es la senal debil de
    verdad: un corte avisa al instante, una conexion colgada hace esperar."""
    ctx = pw.chromium.launch_persistent_context(perfil, channel="chrome", headless=True)
    ctx.colgadas = []

    def filtro(route):
        host = route.request.url.split("/")[2].split(":")[0]
        if host in ("127.0.0.1", "localhost") or host in PERMITIDOS:
            route.continue_()
            return
        bloqueados[host] = bloqueados.get(host, 0) + 1
        if colgar:
            ctx.colgadas.append(route)   # sin respuesta; el pedido nunca sale del navegador
        else:
            route.abort()
    ctx.route("**/*", filtro)
    return ctx


def cerrar(ctx):
    """Corta las colgadas antes de cerrar: si no, Playwright reclama al soltarlas."""
    for r in ctx.colgadas:
        try:
            r.abort()
        except PWError:
            pass
    ctx.unroute_all(behavior="ignoreErrors")
    ctx.close()


def simular_sesion(page):
    # Sin PIN no hay sesion de verdad, y no se quiere una: se le da al codigo el uid que
    # tendria y se esconde la pantalla de ingreso. Nada de esto llega a ningun servidor.
    # PRIMERO se espera a que Firebase diga quien esta conectado: sin red se demora, y si
    # contesta "nadie" despues de esto, borra el uid simulado y el registro sale como
    # "Tu sesion expiro" (le paso a esta prueba).
    page.evaluate("""() => new Promise((listo) => {
        const soltar = auth.onAuthStateChanged(() => { soltar(); listo(); });
    })""")
    page.evaluate("""() => {
        uidActual = 'prueba-sin-senal'; usuarioActual = 'prueba';
        document.getElementById('login-overlay').style.display = 'none';
    }""")


def con_plazo(page, js, segundos):
    """Corre `js` (una funcion async) y devuelve (resultado, segundos) o (None, None) si
    no termina en el plazo. Lo que importa medir es justamente si termina."""
    t0 = time.time()
    r = page.evaluate(f"""async () => {{
        const plazo = new Promise((r) => setTimeout(() => r('__NO_TERMINO__'), {segundos * 1000}));
        return await Promise.race([({js})(), plazo]);
    }}""")
    if r == "__NO_TERMINO__":
        return None, None
    return r, round(time.time() - t0, 1)


def vigilar(page, errores):
    """Un error de JavaScript o un aviso emergente ("Error al guardar", "Tu sesion
    expiro") es una falla, aunque la pantalla termine bien."""
    page.on("pageerror", lambda e: errores.append(str(e)))
    page.on("dialog", lambda d: (errores.append("aviso: " + d.message), d.dismiss()))


def pantalla(page):
    return page.evaluate("() => document.getElementById('display-resultado').innerText")


def salida(page):
    texto = page.evaluate("() => document.getElementById('sal-resultado').innerText")
    return texto.replace("\n", " | ")


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"Verificador sin senal - {'copia de trabajo' if version is None else version}")
    tmp = tempfile.mkdtemp(prefix="verif_sin_senal_")
    perfil = os.path.join(tmp, "perfil")
    try:
        preparar(tmp, version)
        srv = Servidor(tmp)
        url = f"http://127.0.0.1:{srv.puerto}/Verificador/index.html"
        with sync_playwright() as pw:
            # 1. Con red, como el primer dia.
            ctx = abrir_chrome(pw, perfil)
            page = ctx.new_page()
            page.goto(url)
            listo = page.evaluate("""() => Promise.race([
                navigator.serviceWorker ? navigator.serviceWorker.ready.then(() => true) : false,
                new Promise((r) => setTimeout(() => r(false), 15000))])""")
            anota("con red, el sw.js se instala", listo)
            page.wait_for_timeout(1500)       # las librerias terminan de guardarse
            ctx.close()

            # 2. Sin servidor y sin red.
            srv.apagar()
            ctx = abrir_chrome(pw, perfil)
            ctx.set_offline(True)
            page = ctx.new_page()
            errores = []
            vigilar(page, errores)
            try:
                page.goto(url, timeout=15000)
                abrio = page.evaluate("() => typeof firebase !== 'undefined' && !!document.getElementById('inputPatente')")
            except PWError as e:
                abrio = False
                errores.append(str(e).splitlines()[0])
            anota("sin red, la app abre (con Firebase cargado)", abrio,
                  "" if abrio else (errores[-1] if errores else ""))
            if not abrio:
                ctx.close()
                return

            simular_sesion(page)
            persistencia = page.evaluate("""() => new Promise((r) => {
                const t0 = Date.now();
                (function mira() {
                    if (typeof persistenciaLocal !== 'undefined' && persistenciaLocal) return r(true);
                    if (Date.now() - t0 > 8000) return r(false);
                    setTimeout(mira, 100);
                })(); })""")
            anota("la persistencia de Firestore queda encendida", persistencia)

            # 3. Una patente que el telefono nunca vio.
            page.fill("#inputPatente", PATENTE)
            _, seg = con_plazo(page, "verificarPatente", 20)
            texto = pantalla(page)
            form = page.evaluate("() => getComputedStyle(document.getElementById('registro-container')).display")
            anota("buscar sin red termina", seg is not None, f"{seg} s" if seg is not None else "")
            anota("dice NO REGISTRADO y SIN SEÑAL (no 'Error de conexion')",
                  "NO REGISTRADO" in texto and "SIN SEÑAL" in texto, texto.replace("\n", " | ")[:80])
            anota("ofrece registrarla", form != "none", form)

            # 4. Registrarla.
            page.fill("#patenteNueva", PATENTE)
            _, seg = con_plazo(page, "accionRegistrar", 20)
            anota("registrar sin red termina en segundos", seg is not None and seg < 8,
                  f"{seg} s" if seg is not None else "no termino en 20 s")
            texto = pantalla(page)
            anota("queda PENDIENTE y EN COLA", "PENDIENTE" in texto and "EN COLA" in texto,
                  texto.replace("\n", " | ")[:80])

            # 4b. SALIDA de un pase pagado, sin red. El pase se crea aca mismo, solo en este
            # perfil de prueba, como lo dejaria la caja.
            page.evaluate("""() => { db.collection('activos').doc('%s').set({
                patente: '%s', tipo: 'Pase Diario', pago: 'SI', status: 'PAGADO',
                metodo_pago: 'Efectivo', fecha: fechaDeHoy(), hora: '10:00:00' }); }"""
                          % (PASE, PASE))
            _, seg = con_plazo(page, f"() => salBuscar('{PASE}', 'salida')", 20)
            texto = salida(page)
            anota("salida sin red termina y queda EN COLA",
                  seg is not None and seg < 5 and "SALIDA" in texto and "EN COLA" in texto,
                  (f"{seg} s · " if seg is not None else "no termino · ") + texto[:60])
            _, seg = con_plazo(page, f"() => salBuscar('{PASE}', 'reingreso')", 20)
            texto = salida(page)
            anota("reingreso sin red termina y queda EN COLA",
                  seg is not None and seg < 5 and "REINGRESO" in texto and "EN COLA" in texto,
                  (f"{seg} s · " if seg is not None else "no termino · ") + texto[:60])
            con_plazo(page, "() => salBuscar('ZZ9990', 'salida')", 20)
            estado = page.evaluate("() => document.getElementById('sal-estado').textContent")
            anota("salida de una patente que el telefono no conoce: no inventa 'no esta'",
                  "Sin conexión" in estado, estado)
            ctx.close()

            # 5. Chrome entero cerrado y abierto de nuevo, sin red.
            ctx = abrir_chrome(pw, perfil)
            ctx.set_offline(True)
            page = ctx.new_page()
            vigilar(page, errores)
            page.goto(url, timeout=15000)
            simular_sesion(page)
            page.fill("#inputPatente", PATENTE)
            con_plazo(page, "verificarPatente", 20)
            texto = pantalla(page)
            anota("al reabrir sin red, el registro sigue ahi y EN COLA",
                  "PENDIENTE" in texto and "EN COLA" in texto, texto.replace("\n", " | ")[:80])
            pase = page.evaluate("""async () => {
                const d = (await db.collection('activos').doc('%s').get({ source: 'cache' })).data();
                return { movs: (d.movimientos_terreno || []).map((m) => m.tipo).join(','),
                         dentro: d.dentro }; }""" % PASE)
            anota("al reabrir, salida y reingreso siguen ahi, EN ORDEN, y el auto adentro",
                  pase["movs"] == "salida,reingreso" and pase["dentro"] is True, str(pase))
            ctx.close()

            # 5b. Senal debil: hay "red", pero Firestore no contesta nunca.
            ctx = abrir_chrome(pw, perfil, colgar=True)
            page = ctx.new_page()
            vigilar(page, errores)
            page.goto(url, timeout=15000)
            simular_sesion(page)
            page.fill("#inputPatente", "ZZ9998")
            _, seg = con_plazo(page, "verificarPatente", 30)
            texto = pantalla(page)
            anota("senal debil: buscar una nueva termina en segundos", seg is not None and seg < 5,
                  f"{seg} s" if seg is not None else "no termino en 30 s")
            anota("senal debil: NO REGISTRADO y SIN SEÑAL",
                  "NO REGISTRADO" in texto and "SIN SEÑAL" in texto, texto.replace("\n", " | ")[:80])
            page.fill("#patenteNueva", "ZZ9998")
            _, seg = con_plazo(page, "accionRegistrar", 30)
            texto = pantalla(page)
            anota("senal debil: registrar termina en segundos", seg is not None and seg < 6,
                  f"{seg} s" if seg is not None else "no termino en 30 s")
            anota("senal debil: queda EN COLA", "PENDIENTE" in texto and "EN COLA" in texto,
                  texto.replace("\n", " | ")[:80])
            page.fill("#inputPatente", PATENTE)
            _, seg = con_plazo(page, "verificarPatente", 30)
            texto = pantalla(page)
            anota("senal debil: la registrada antes se encuentra en segundos",
                  seg is not None and seg < 5 and "EN COLA" in texto,
                  (f"{seg} s · " if seg is not None else "no termino · ") + texto.replace("\n", " | ")[:60])
            _, seg = con_plazo(page, "verTotalPendientes", 30)
            lista = page.evaluate("() => document.getElementById('lista-pendientes').innerText")
            anota("senal debil: la lista de PENDIENTES termina en segundos y avisa SIN SEÑAL",
                  seg is not None and seg < 5 and "TOTAL PENDIENTES" in lista and "SIN SEÑAL" in lista,
                  (f"{seg} s · " if seg is not None else "no termino · ") + lista.replace("\n", " | ")[:60])
            _, seg = con_plazo(page, f"() => salBuscar('{PASE}', 'salida')", 30)
            texto = salida(page)
            anota("senal debil: la salida termina en segundos y queda EN COLA",
                  seg is not None and seg < 7 and "EN COLA" in texto,
                  (f"{seg} s · " if seg is not None else "no termino · ") + texto[:60])
            cerrar(ctx)
            anota("sin errores de JavaScript ni avisos", not errores, "; ".join(errores)[:120])

        # 6. Perfil limpio y con red: lo publicado se ve al abrir.
        perfil2 = os.path.join(tmp, "perfil2")
        srv = Servidor(tmp)
        url = f"http://127.0.0.1:{srv.puerto}/Verificador/index.html"
        pagina = os.path.join(tmp, "Verificador", "index.html")
        with sync_playwright() as pw:
            ctx = abrir_chrome(pw, perfil2)
            page = ctx.new_page()
            page.goto(url)
            page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
            # La marca va DENTRO del body: un comentario despues de </html> el navegador lo
            # cuelga fuera del documento y no se lee.
            with open(pagina, encoding="utf-8") as f:
                html = f.read()
            with open(pagina, "w", encoding="utf-8") as f:
                f.write(html.replace("</body>", '<i id="marca-publicada"></i></body>', 1))
            marca = "() => !!document.getElementById('marca-publicada')"
            page.reload()
            anota("con red, lo recien publicado se ve al abrir", page.evaluate(marca))
            srv.apagar()
            ctx.set_offline(True)
            page.reload()
            anota("y sin red se abre esa misma version", page.evaluate(marca))
            ctx.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        ok = sum(resultados)
        if bloqueados:
            print("\n  bloqueado (nunca salio): " +
                  ", ".join(f"{h} x{n}" for h, n in sorted(bloqueados.items())))
        print(f"\n{ok} de {len(resultados)} bien")
        sys.exit(0 if resultados and all(resultados) else 1)


if __name__ == "__main__":
    main()
