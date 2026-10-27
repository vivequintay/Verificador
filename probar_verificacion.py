"""El VERIFICADO EN TERRENO, de punta a punta, en un Chrome sin ventana y SIN tocar la nube.

Pedido suyo (26-10-2026): bajo la tarjeta de un auto registrado, un gran boton verde para
dejar constancia de que el operador lo vio en el patio, con una observacion opcional. El
siguiente operador ve "VERIFICADO" con el nombre de quien fue y la observacion.

Usa la misma maquinaria que `probar_sin_senal.py`: el Verificador servido en localhost,
Firestore y el inicio de sesion bloqueados, la sesion simulada. Los autos se crean en la
memoria local del telefono de prueba, que se borra al terminar: nada llega a la nube.

    <python con playwright> probar_verificacion.py [carpeta para las capturas]

Con una carpeta, deja ahi las capturas en tamano de telefono (412 x 915).
"""
import os
import shutil
import sys
import tempfile

import probar_sin_senal as base
from playwright.sync_api import sync_playwright

TELEFONO = {"width": 412, "height": 915}
CAPTURAS = sys.argv[1] if len(sys.argv) > 1 else None
anota = base.anota


def foto(page, nombre):
    """Espera a que se apague el destello de color (1,7 s: `lanzarFlash`), que tapa toda
    la pantalla al mostrar un resultado; si no, la foto sale de un solo color."""
    if CAPTURAS:
        page.wait_for_function("""() => [...document.querySelectorAll('[id^="flash-"]')]
            .every((f) => getComputedStyle(f).display === 'none')""", timeout=5000)
        page.screenshot(path=os.path.join(CAPTURAS, nombre + ".png"))


def como(page, nombre):
    """Cambia el operador de la sesion simulada."""
    page.evaluate("(n) => { usuarioActual = n; }", nombre)


def crear(page, patente, **campos):
    """Un auto en la memoria local del telefono, como lo dejaria la caja."""
    doc = {"patente": patente, "fecha": "__HOY__", "hora": "10:00:00", **campos}
    page.evaluate("""(d) => {
        if (d.fecha === '__HOY__') d.fecha = fechaDeHoy();
        if (d.verificacion && d.verificacion.ingreso === '__OTRA__')
            d.verificacion.ingreso = fechaDeHoy() + ' 08:00:00';
        db.collection('activos').doc(d.patente).set(d);
    }""", doc)


def consultar(page, patente):
    page.evaluate("() => { cerrarObservaciones(); cerrarPanelResultado(); }")
    page.wait_for_timeout(150)
    page.fill("#inputPatente", patente)
    base.con_plazo(page, "verificarPatente", 20)
    page.wait_for_timeout(150)


def hay(page, selector):
    return page.evaluate("(s) => !!document.querySelector('#display-resultado ' + s)", selector)


def texto_de(page, selector):
    return page.evaluate("(s) => { const e = document.querySelector('#display-resultado ' + s); "
                         "return e ? e.innerText.replace(/\\s+/g, ' ').trim() : ''; }", selector)


def main():
    if CAPTURAS:
        os.makedirs(CAPTURAS, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="verif_verificacion_")
    perfil = os.path.join(tmp, "perfil")
    try:
        base.preparar(tmp, None)
        srv = base.Servidor(tmp)
        url = f"http://127.0.0.1:{srv.puerto}/Verificador/index.html"
        with sync_playwright() as pw:
            # Con red una vez, para que el telefono guarde la app y sus librerias.
            ctx = base.abrir_chrome(pw, perfil)
            page = ctx.new_page()
            page.goto(url)
            page.evaluate("""() => Promise.race([
                navigator.serviceWorker ? navigator.serviceWorker.ready : null,
                new Promise((r) => setTimeout(r, 15000))])""")
            page.wait_for_timeout(1500)
            ctx.close()

            # Desde aca, sin red: todo vive en la memoria del telefono de prueba.
            srv.apagar()
            ctx = base.abrir_chrome(pw, perfil)
            ctx.set_offline(True)
            page = ctx.new_page()
            page.set_viewport_size(TELEFONO)
            errores = []
            base.vigilar(page, errores)
            page.goto(url, timeout=15000)
            base.simular_sesion(page)
            page.wait_for_function("() => typeof persistenciaLocal !== 'undefined' && persistenciaLocal",
                                   timeout=10000)
            page.evaluate("() => { const s = document.getElementById('splash-screen'); if (s) s.style.display = 'none'; }")

            crear(page, "ZZ1001", tipo="Pase Diario", pago="SI", status="PAGADO", metodo_pago="Efectivo")
            crear(page, "ZZ1002", tipo="Ticket por Minuto", status="Activo")
            crear(page, "ZZ1003", tipo="Ticket por Minuto", status="Finalizado", hora_pago="11:20")
            crear(page, "ZZ1004", tipo="Pase Diario", pago="SI", status="PAGADO",
                  verificacion={"por": "Antiguo", "hora": "08:30", "obs": "de otra estadia",
                                "ingreso": "__OTRA__"})
            crear(page, "ZZ1005", tipo="Pase Diario", pago="SI", status="PAGADO")

            # 1. VERIFICAR sin patente: el aviso va en la caja, no en el panel.
            page.fill("#inputPatente", "")
            page.click("#verificar-manual")
            page.wait_for_timeout(250)
            panel = page.evaluate("() => document.getElementById('panel-resultado').classList.contains('visible')")
            caja = page.evaluate("""() => { const i = document.getElementById('inputPatente');
                return [i.classList.contains('vacio'), i.placeholder, getComputedStyle(i).borderTopColor]; }""")
            anota("sin patente NO se abre el panel", not panel)
            anota("el aviso va dentro de la caja, en rojo", caja[0] and caja[1] == "INGRESA UNA PATENTE"
                  and caja[2] == "rgb(229, 57, 53)", str(caja))
            foto(page, "1 sin patente")
            page.type("#inputPatente", "A")
            anota("al escribir, la caja vuelve a la normal", page.evaluate(
                "() => !document.getElementById('inputPatente').classList.contains('vacio') && "
                "document.getElementById('inputPatente').placeholder === 'BUSCAR PATENTE'"))

            # 2. Un auto registrado sin verificar: el boton verde bajo la tarjeta.
            como(page, "Marcela")
            consultar(page, "ZZ1001")
            anota("pase pagado: aparece el boton verde", hay(page, ".btn-verificado"))
            foto(page, "2 tarjeta con boton")

            # 3. El boton abre Observaciones; se guarda con una observacion.
            page.click("#display-resultado .btn-verificado")
            page.wait_for_timeout(200)
            anota("el boton abre Observaciones", page.evaluate(
                "() => getComputedStyle(document.getElementById('modal-obs')).display") == "flex")
            page.fill("#obs-texto", "Ventana trasera abierta")
            foto(page, "3 observaciones")
            page.click("#obs-guardar")
            page.wait_for_timeout(800)
            anota("guardado: la ventana se cierra", page.evaluate(
                "() => getComputedStyle(document.getElementById('modal-obs')).display") == "none")
            tag = texto_de(page, ".tag-verificado")
            anota("queda VERIFICADO con su nombre", "VERIFICADO" in tag and "Marcela" in tag, tag)
            anota("y su observacion abajo", "Ventana trasera abierta" in texto_de(page, ".obs-verificado"))
            anota("el boton ya no esta", not hay(page, ".btn-verificado"))
            foto(page, "4 verificado con observacion")

            guardado = page.evaluate("""() => db.collection('activos').doc('ZZ1001').get({source: 'cache'})
                .then((s) => s.data())""")
            v = guardado.get("verificacion") or {}
            anota("el documento guarda quien, cuando, la observacion y la estadia",
                  v.get("por") == "Marcela" and v.get("uid") == "prueba-sin-senal" and v.get("hora")
                  and v.get("obs") == "Ventana trasera abierta"
                  and v.get("ingreso") == f"{guardado['fecha']} 10:00:00", str(v))
            anota("no toca nada mas del auto", guardado.get("status") == "PAGADO"
                  and guardado.get("pago") == "SI" and guardado.get("tipo") == "Pase Diario")

            # 4. Otro operador consulta el mismo auto: ve quien lo verifico.
            como(page, "Pedro")
            consultar(page, "ZZ1001")
            tag = texto_de(page, ".tag-verificado")
            anota("otro operador ve VERIFICADO con el nombre del primero",
                  "Marcela" in tag and "Pedro" not in tag, tag)
            anota("y la observacion", "Ventana trasera abierta" in texto_de(page, ".obs-verificado"))

            # 5. Sin observacion: verificado igual, sin el aviso ambar.
            consultar(page, "ZZ1002")
            anota("ticket por minuto pendiente: tambien se verifica", hay(page, ".btn-verificado"))
            page.click("#display-resultado .btn-verificado")
            page.wait_for_timeout(150)
            page.click("#obs-guardar")
            page.wait_for_timeout(800)
            anota("sin observacion queda verificado, sin aviso ambar",
                  hay(page, ".tag-verificado") and not hay(page, ".obs-verificado"))
            foto(page, "5 verificado sin observacion")

            # 6. Lo que NO se verifica, y la verificacion de OTRA estadia.
            consultar(page, "ZZ1003")
            anota("ticket ya pagado y FINALIZADO (se fue): ni boton ni etiqueta",
                  not hay(page, ".btn-verificado") and not hay(page, ".tag-verificado"))
            consultar(page, "ZZ1004")
            anota("una verificacion de otra estadia no cuenta: vuelve el boton",
                  hay(page, ".btn-verificado") and not hay(page, ".tag-verificado"))
            consultar(page, "ZZ1999")
            anota("NO REGISTRADO: sin boton (se registra, como siempre)",
                  not hay(page, ".btn-verificado") and "NO REGISTRADO" in texto_de(page, ""))

            # 7. Lo que escribe un operador se pinta en el telefono de OTRO: no puede ser HTML.
            consultar(page, "ZZ1004")
            page.click("#display-resultado .btn-verificado")
            page.fill("#obs-texto", '<img src=x onerror="window.__xss=1">choque')
            page.click("#obs-guardar")
            page.wait_for_timeout(800)
            anota("la observacion se muestra como texto, nunca como HTML",
                  not hay(page, ".obs-verificado img") and "<img" in texto_de(page, ".obs-verificado")
                  and not page.evaluate("() => !!window.__xss"))

            # 8. Modo caseta: tocar el boton detiene el borrado automatico.
            page.evaluate("() => toggleBooth(true)")
            consultar(page, "ZZ1005")
            page.click("#display-resultado .btn-verificado")
            page.wait_for_timeout(4200)
            anota("en modo caseta, con Observaciones abierta el resultado no se borra",
                  hay(page, ".btn-verificado") and page.evaluate(
                      "() => getComputedStyle(document.getElementById('modal-obs')).display") == "flex")
            page.click("#obs-cancelar")
            page.evaluate("() => toggleBooth(false)")
            anota("CANCELAR no verifica", not page.evaluate("""() => db.collection('activos').doc('ZZ1005')
                .get({source: 'cache'}).then((s) => !!s.data().verificacion)"""))

            anota("sin errores de JavaScript ni avisos", not errores, "; ".join(errores)[:200])
            ctx.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = sum(base.resultados)
    print(f"\n{ok} de {len(base.resultados)} bien")
    sys.exit(0 if ok == len(base.resultados) else 1)


if __name__ == "__main__":
    main()
