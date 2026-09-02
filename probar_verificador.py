"""Pruebas de las reglas de PLATA del Verificador, en un Chrome sin ventana.

POR QUE EXISTE ESTE ARCHIVO. El Verificador decide, mirando la pantalla, si un auto puede
irse. Una vez se equivoco: todo pase diario se pintaba verde "PAGADO" por el solo hecho de
ser pase diario, asi que un pase INGRESADO PENDIENTE se veia igual que uno pagado y el auto
salia sin pagar. La regla que arregla eso no puede volver a romperse en silencio.

COMO PRUEBA CODIGO QUE VIVE DENTRO DE UN index.html. La logica esta en un <script> junto a
la app entera, que necesita Firebase y una sesion para arrancar. En vez de levantar todo
eso, se RECORTA la funcion del archivo real y se evalua sola en una pagina vacia: se prueba
el codigo que de verdad se publica, sin depender de la red.

Uso:  python probar_verificador.py
"""
import html
import os
import re
import shutil
import subprocess
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE = os.path.join(AQUI, "index.html")

# Las funciones que se recortan del index.html para probarlas aisladas.
FUNCIONES = ("paseEstaPagado", "fechaDeHoy", "leerColilla")

CASOS = """
// ---- paseEstaPagado: la regla que decide si el auto puede irse ----
// Las tres formas en que la caja escribe un pase en la nube, tal cual.
iguala('ingreso normal: entro y NO ha pagado',
       paseEstaPagado({ metodo_pago: 'Pendiente', pago: 'NO', status: 'Activo', total_pagado: 0 }), false);
iguala('pase cobrado en caja',
       paseEstaPagado({ metodo_pago: 'Efectivo', pago: 'SI', status: 'PAGADO', total_pagado: 6000 }), true);
iguala('reserva pagada por la web',
       paseEstaPagado({ metodo_pago: 'Reserva Web', pago: 'SI', status: 'PAGADO' }), true);

// ANTE LA DUDA, PENDIENTE. De los dos errores posibles, un pendiente falso se aclara
// preguntando en caja; un pagado falso es un auto que se va sin pagar.
iguala('un documento sin ningun campo de pago NO se da por pagado', paseEstaPagado({}), false);
iguala('un documento nulo tampoco', paseEstaPagado(null), false);
iguala('metodo de pago vacio no es pagado', paseEstaPagado({ metodo_pago: '' }), false);
iguala('metodo de pago en blancos no es pagado', paseEstaPagado({ metodo_pago: '   ' }), false);

// Cada campo por si solo alcanza para declararlo pagado.
iguala('solo con el metodo de pago', paseEstaPagado({ metodo_pago: 'Tarjeta' }), true);
iguala('solo con pago=SI', paseEstaPagado({ pago: 'SI' }), true);
iguala('solo con status=PAGADO', paseEstaPagado({ status: 'PAGADO' }), true);

// La caja no siempre escribe con las mismas mayusculas.
iguala('no le importan las mayusculas', paseEstaPagado({ pago: 'si' }), true);
iguala('PENDIENTE en mayusculas sigue siendo pendiente',
       paseEstaPagado({ metodo_pago: 'PENDIENTE' }), false);
iguala('pendiente con espacios sigue siendo pendiente',
       paseEstaPagado({ metodo_pago: ' Pendiente ' }), false);

// ---- leerColilla: EL CONTRATO CON LA CAJA ----
// El texto del codigo de barras lo escribe Python (`payload_salida` en vqspa_core) y lo
// lee esto. Son dos programas, en dos repos, que no comparten una linea de codigo — y los
// tickets ya impresos y en el bolsillo de un cliente no se pueden corregir. Estas pruebas
// son el espejo exacto de las de test_colilla_salida.py.
iguala('lee una colilla', leerColilla('VQS-AABB05'), 'AABB05');
iguala('no le importan las mayusculas', leerColilla('vqs-aabb05'), 'AABB05');
iguala('aguanta espacios alrededor', leerColilla('  VQS-AABB05  '), 'AABB05');

// El 99,5% de las patentes tiene 6 caracteres, pero en 18 meses hay 65 con 5, 7, 8 y 13.
iguala('acepta patentes que NO miden seis', leerColilla('VQS-ABC1234'), 'ABC1234');
iguala('y las cortas tambien', leerColilla('VQS-XY12'), 'XY12');

// Lo que NO es una colilla. La patente pelada es justo lo que lleva el QR de COBRO del
// pase pendiente: si pasara por colilla, un pase impago se daria por salido.
iguala('una patente pelada NO es colilla', leerColilla('AABB05'), null);
iguala('otra marca no pasa', leerColilla('XXX-AABB05'), null);
iguala('basura no revienta', leerColilla('hola'), null);
iguala('vacio no revienta', leerColilla(''), null);
iguala('nulo no revienta', leerColilla(null), null);
iguala('sin patente no pasa', leerColilla('VQS-'), null);
iguala('patente muy corta no pasa', leerColilla('VQS-AB'), null);
iguala('tres partes no pasan', leerColilla('VQS-AABB05-310826'), null);

// ---- fechaDeHoy: tiene que hablar el idioma de la caja ----
// La caja escribe con strftime('%d-%m-%Y'). Si aca saliera '2026-08-30' o '30/08/2026',
// el filtro de "ultimas salidas" no encontraria NADA y el listado quedaria siempre vacio.
iguala('formato DD-MM-AAAA, igual que la caja', /^\\d{2}-\\d{2}-\\d{4}$/.test(fechaDeHoy()), true);
(() => {
    const d = new Date();
    const esperado = String(d.getDate()).padStart(2, '0') + '-' +
                     String(d.getMonth() + 1).padStart(2, '0') + '-' + d.getFullYear();
    iguala('es la fecha de hoy', fechaDeHoy(), esperado);
})();
"""

PAGINA = """<!doctype html><meta charset="utf-8"><pre id="salida">corriendo…</pre>
<script>
const res = []; let malas = 0;
function iguala(nombre, obtenido, esperado) {
    const ok = JSON.stringify(obtenido) === JSON.stringify(esperado);
    if (!ok) malas++;
    res.push((ok ? '  ok   ' : ' MAL   ') + nombre +
             (ok ? '' : '\\n         esperaba ' + JSON.stringify(esperado) +
                        '\\n         obtuvo   ' + JSON.stringify(obtenido)));
}
__FUNCIONES__
try {
__CASOS__
} catch (e) { malas++; res.push(' MAL   reventó: ' + e.message); }
document.getElementById('salida').textContent =
    res.join('\\n') + '\\n\\nRESULTADO_PRUEBAS:' +
    (malas === 0 ? 'TODAS OK (' + res.length + ')' : malas + ' FALLARON');
</script>"""


def recortar(fuente, nombre):
    """Saca `function nombre(...) { ... }` del index.html contando llaves."""
    i = fuente.find("function %s(" % nombre)
    if i < 0:
        raise SystemExit("*** no encontre la funcion %s en index.html" % nombre)
    j = fuente.index("{", i)
    prof = 0
    for k in range(j, len(fuente)):
        if fuente[k] == "{":
            prof += 1
        elif fuente[k] == "}":
            prof -= 1
            if prof == 0:
                return fuente[i:k + 1]
    raise SystemExit("*** la funcion %s no cierra" % nombre)


def main():
    with open(FUENTE, encoding="utf-8") as f:
        fuente = f.read()

    # Que la rama del pase diario SIGA consultando la regla. Si alguien la borra, las
    # pruebas de arriba pasarian igual —la funcion seguiria siendo correcta— mientras la
    # pantalla vuelve a mentir. Esto es lo que de verdad protege contra la recaida.
    if "paseEstaPagado(data)" not in fuente:
        raise SystemExit("*** el index.html ya no consulta paseEstaPagado() al mostrar el pase")
    # Lo mismo para la salida: que el escaner SIGA pasando por el lector de colillas. Sin
    # esto, alguien podria borrar la llamada y las pruebas de arriba seguirian verdes
    # mientras el escaner interpreta cualquier cosa como patente.
    if "leerColilla(txt)" not in fuente:
        raise SystemExit("*** el escaner de SALIDA ya no usa leerColilla()")
    if "paseEstaPagado(d)" not in fuente:
        raise SystemExit("*** la pantalla de SALIDA ya no comprueba si el pase esta pagado")

    pagina = (PAGINA
              .replace("__FUNCIONES__", "\n".join(recortar(fuente, n) for n in FUNCIONES))
              .replace("__CASOS__", CASOS))

    tmp = tempfile.mkdtemp(prefix="verif_")
    perfil = tempfile.mkdtemp(prefix="perfil_verif_")
    try:
        ruta = os.path.join(tmp, "p.html")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(pagina)
        r = subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
            "--disable-extensions", "--user-data-dir=" + perfil,
            "--virtual-time-budget=4000", "--dump-dom", "file:///" + ruta.replace("\\", "/"),
        ], capture_output=True, text=True, timeout=180, errors="replace")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(perfil, ignore_errors=True)

    m = re.search(r'<pre id="salida">(.*?)</pre>', r.stdout or "", re.S)
    if not m:
        print("Las pruebas no llegaron a correr.")
        print((r.stdout or "")[:600])
        raise SystemExit(1)
    salida = html.unescape(m.group(1))
    print(salida)
    raise SystemExit(0 if "TODAS OK" in salida else 1)


if __name__ == "__main__":
    main()
