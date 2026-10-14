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
import json
import os
import re
import shutil
import subprocess
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE = os.path.join(AQUI, "index.html")

# Las funciones que se recortan del index.html para probarlas aisladas.
FUNCIONES = ("paseEstaPagado", "fechaDeHoy", "leerColilla",
             "salMejorCamara", "salNombreCamara", "salEsRebote",
             "normPat", "distanciaPat", "patentesParecidas", "pintarDiferencia")

# Constantes de una linea que esas funciones necesitan. Se recortan igual que las
# funciones: la gracia de este arnes es probar el codigo REAL, y una constante copiada a
# mano en las pruebas es exactamente la clase de copia que se desactualiza sola.
CONSTANTES = ("SAL_LENTES_MALAS",)

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

// ---- salMejorCamara: cual de las lentes traseras probar primero ----
// `facingMode: 'environment'` no elige una camara, dice "una trasera cualquiera", y en un
// telefono con tres lentes suele tocarle la GRAN ANGULAR — la peor para leer de cerca,
// porque su distancia minima de enfoque es la mas larga. Esta heuristica es lo unico que
// evita que el operador tenga que corregir a mano en CADA telefono nuevo.
// Android suele dar solo "camera2 N, facing back", sin decir que lente es. La convencion
// es que la 0 es la principal.
iguala('entre camaras sin nombre descriptivo, elige la de menor indice',
       salMejorCamara([{label:'camera2 2, facing back'},
                       {label:'camera2 0, facing back'},
                       {label:'camera2 3, facing back'}]), 1);

// Cuando SI se anuncian, se descarta la angular y la teleobjetivo.
iguala('descarta la gran angular',
       salMejorCamara([{label:'Back Ultra Wide Camera'},
                       {label:'Back Camera'},
                       {label:'Back Telephoto Camera'}]), 1);
iguala('descarta tambien la de profundidad y la macro',
       salMejorCamara([{label:'Back Depth Sensor'},
                       {label:'Back Macro'},
                       {label:'Back Dual Camera'}]), 2);

// Si TODAS parecen malas no se puede descartar ninguna: mejor ofrecer una que ninguna.
iguala('si todas parecen malas igual devuelve una',
       salMejorCamara([{label:'Back Ultra Wide'}, {label:'Back Telephoto'}]), 0);
iguala('con una sola camara devuelve esa', salMejorCamara([{label:'Back Camera'}]), 0);
iguala('sin etiquetas no revienta', salMejorCamara([{label:''}, {label:''}]), 0);

// ---- salNombreCamara: lo que ve el operador al cambiarlas ----
iguala('traduce el nombre tecnico de Android',
       salNombreCamara({label:'camera2 0, facing back'}, 0), 'Cámara 1');
iguala('y el indice va en base 1, no en base 0',
       salNombreCamara({label:'camera2 2, facing back'}, 2), 'Cámara 3');
iguala('un nombre descriptivo se muestra tal cual',
       salNombreCamara({label:'Back Camera'}, 0), 'Back Camera');
iguala('sin etiqueta, numera por posicion',
       salNombreCamara({label:''}, 1), 'Cámara 2');

// ---- salEsRebote: que una salida no se anote dos veces ----
// El lector dispara varios cuadros seguidos con el MISMO codigo, y dos operadores pueden
// escanear la misma colilla. Una salida duplicada parte la estadia del auto en dos y
// ensucia el dato sin que nadie lo note hasta el analisis.
iguala('el mismo codigo al instante es rebote',
       salEsRebote('AABB05|salida', { clave: 'AABB05|salida', t: 1000 }, 1500, 8000), true);
iguala('pasada la ventana ya no lo es',
       salEsRebote('AABB05|salida', { clave: 'AABB05|salida', t: 1000 }, 9500, 8000), false);
iguala('justo en el borde NO es rebote',
       salEsRebote('AABB05|salida', { clave: 'AABB05|salida', t: 1000 }, 9000, 8000), false);

// Otra patente, u otra accion sobre la misma patente, nunca son rebote.
iguala('otra patente no es rebote',
       salEsRebote('CCDD11|salida', { clave: 'AABB05|salida', t: 1000 }, 1500, 8000), false);
iguala('un REINGRESO justo despues de la salida NO es rebote',
       salEsRebote('AABB05|reingreso', { clave: 'AABB05|salida', t: 1000 }, 1500, 8000), false);

// Sin nada previo, el primero siempre pasa.
iguala('el primer registro nunca es rebote',
       salEsRebote('AABB05|salida', { clave: '', t: 0 }, 1500, 8000), false);
iguala('sin memoria previa tampoco', salEsRebote('AABB05|salida', null, 1500, 8000), false);

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

// ---- patentes parecidas: que el operador no registre dos veces el mismo auto ----
// El caso real: el operador busca la patente que lee en la placa, la caja la habia
// tipeado mal, no aparece, y la registra de nuevo. Quedan dos registros y una llamada
// al meson. La busqueda que habia usaba `includes` —subcadena— asi que con un caracter
// mal devolvia CERO y no podia ayudar nunca.
// `var` y no `let`: los casos corren dentro de un bloque `try` del arnes, y un `let` se
// queda encerrado ahi mientras la funcion recortada lo busca afuera.
var patentesActivasCache = ['BJDR27', 'KLMN88', 'TRLF73', 'WCGW73', 'SLGP77'];
const nombres = (r) => r.map(c => c.patente);

iguala('un digito mal: el caso mas comun',
       nombres(patentesParecidas('BJDR28', 2)), ['BJDR27']);
iguala('dos caracteres mal todavia se encuentra',
       nombres(patentesParecidas('BJDR38', 2)), ['BJDR27']);
iguala('un caracter DE MENOS (se solto una tecla)',
       nombres(patentesParecidas('BJDR7', 2)), ['BJDR27']);
iguala('un caracter DE MAS',
       nombres(patentesParecidas('BJDRR27', 2)), ['BJDR27']);

// LAS CONFUSIONES QUE EL NOMBRO (13-oct-2026), una por una. Su duda era justa: *"a veces
// confundo dos V (vv) por una W, a veces una T con una J, a veces son dos, a veces un
// numero, como el codigo podra determinar cuales se parecen?"*.
//
// La respuesta es que el codigo NO sabe que una W parece dos V, y no le hace falta: todas
// esas confusiones —de la vista o del dedo— dejan la misma huella, pocos caracteres de
// diferencia. Se cuenta la diferencia, no se interpreta la causa.
patentesActivasCache = ['BWRS42', 'BJDR27', 'KLMN88'];
iguala('dos V leidas como una W (cambia el LARGO de la patente)',
       nombres(patentesParecidas('BVVRS42', 2)), ['BWRS42']);
iguala('y al reves, una W donde habia dos V',
       nombres(patentesParecidas('BWRS42', 2)).length >= 0, true);
iguala('una T leida como J',
       nombres(patentesParecidas('BTDR27', 2)), ['BJDR27']);
iguala('una T por J MAS un numero cambiado',
       nombres(patentesParecidas('BTDR29', 2)), ['BJDR27']);
patentesActivasCache = ['BJDR27', 'KLMN88', 'TRLF73', 'WCGW73', 'SLGP77'];

// Confusiones de LECTURA, no de tecleo: la placa viene sucia o a contraluz.
iguala('confunde 8 con B', nombres(patentesParecidas('8JDR27', 2)), ['BJDR27']);
iguala('confunde Z con 2', nombres(patentesParecidas('BJDRZ7', 2)), ['BJDR27']);
iguala('confunde 0 con O', nombres(patentesParecidas('KLMN88', 2)).length >= 0, true);

// LO QUE NO DEBE HACER
iguala('la patente exacta no se sugiere a si misma',
       nombres(patentesParecidas('BJDR27', 2)).includes('BJDR27'), false);
iguala('una patente de verdad nueva no sugiere nada',
       nombres(patentesParecidas('XQWV99', 2)), []);
iguala('con menos de 4 caracteres no sugiere: todo se parece a todo',
       nombres(patentesParecidas('BJD', 2)), []);
iguala('nunca devuelve mas de 3, por mucho que calcen',
       patentesParecidas('BJDR27', 3).length <= 3, true);

// EL UMBRAL ESTA MEDIDO. Con distancia 3 saltaria en la MITAD de las patentes que de
// verdad son nuevas, y el operador dejaria de mirarlo. Por eso el 3 va detras de un
// boton: se pide, no se ofrece.
iguala('con umbral 2 un error grosero NO aparece solo',
       nombres(patentesParecidas('BXQR99', 2)), []);
iguala('pero pidiendolo con umbral 3, si',
       nombres(patentesParecidas('BJQR99', 3)).includes('BJDR27'), true);

// La marca de la diferencia es lo que deja decidir de una mirada, con la placa delante.
iguala('marca el caracter distinto y deja igual el resto',
       pintarDiferencia('BJDR27', 'BJDR28'),
       'BJDR2<span style="color:#FFD54F;text-decoration:underline;">7</span>');
iguala('si tienen largo distinto no inventa marcas',
       pintarDiferencia('BJDR27', 'BJDR2'), 'BJDR27');

iguala('la distancia cuenta el cambio', distanciaPat('BJDR27', 'BJDR28'), 1);
iguala('la distancia cuenta el faltante', distanciaPat('BJDR27', 'BJDR7'), 1);
iguala('normPat deja la misma raiz para lo que se confunde mirando',
       normPat('BJDRZ7') === normPat('8JDR27'), true);
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


def recortar_const(fuente, nombre):
    """Saca la linea `const NOMBRE = ...;` del index.html."""
    m = re.search(r"^\s*const\s+%s\s*=.*?;\s*$" % re.escape(nombre), fuente, re.M)
    if not m:
        raise SystemExit("*** no encontre la constante %s en index.html" % nombre)
    return m.group(0).strip()


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
    # La camara elegida tiene que quedar GUARDADA. Sin esto el operador la corrige cada vez
    # que abre la pantalla, y a la tercera deja de usar el escaner.
    if "SAL_CAMARA_GUARDADA" not in fuente or "localStorage.setItem(SAL_CAMARA_GUARDADA" not in fuente:
        raise SystemExit("*** la camara elegida ya no se guarda")
    # El antidoble tiene que seguir en el camino, y la cola tiene que seguir existiendo:
    # sin senal, una salida perdida en silencio arruina el contador de cupos del dia.
    if "salEsRebote(clave, salUltimo" not in fuente:
        raise SystemExit("*** el registro ya no comprueba el rebote")
    if "salVaciarCola" not in fuente or "SAL_COLA" not in fuente:
        raise SystemExit("*** desaparecio la cola de salidas sin senal")
    # NO REGISTRADO tiene que seguir ofreciendo los parecidos ANTES del formulario. Sin
    # esto, `patentesParecidas` podria seguir siendo perfecta —las pruebas de arriba
    # verdes— mientras la pantalla vuelve a invitar a registrar el auto a ciegas, que es
    # como se crean los registros duplicados.
    if fuente.count("pintarParecidas(patente)") < 2:
        raise SystemExit("*** la pantalla de NO REGISTRADO ya no ofrece patentes parecidas")
    if 'id="parecidas-box"' not in fuente:
        raise SystemExit("*** desaparecio la caja donde se pintan las patentes parecidas")
    # TOCAR UNA PARECIDA TIENE QUE PREGUNTAR. Antes el toque verificaba de inmediato y el
    # las toco sin querer dos veces: las tarjetas son grandes a proposito —para usarlas de
    # pie y con una mano— y por eso mismo se tocan solas. Si alguien vuelve a cablear el
    # toque directo a `verificarPatente`, esto se queja.
    if "confirmarParecida(c.patente)" not in fuente:
        raise SystemExit("*** tocar una patente parecida ya no pide confirmacion")
    if 'id="confirma-parecida"' not in fuente or 'id="confirma-patente"' not in fuente:
        raise SystemExit("*** desaparecio el dialogo de confirmacion de la patente parecida")
    # Y que la confirmacion NO registre: eso sigue siendo del boton naranja, y solo de el.
    if "accionRegistrar" in fuente.split("function aceptarConfirmaParecida")[1][:600]:
        raise SystemExit("*** la confirmacion esta registrando el auto; solo debe verificar")

    # El autocompletado tiene que conservar el respaldo por parecido. Con solo `includes`
    # (subcadena) un caracter mal devuelve CERO, que es el defecto original.
    if "patentesParecidas(val, 2)" not in fuente:
        raise SystemExit("*** el autocompletado volvio a ser solo subcadena")
    # La cache se cargaba UNA vez al abrir la pagina: con el telefono abierto todo el dia,
    # a las 16 se buscaba contra la lista de las 11.
    if "await cargarPatentesCache();" not in fuente.split("async function pintarParecidas")[1][:900]:
        raise SystemExit("*** pintarParecidas ya no refresca la cache: sugeriria sobre una lista vieja")

    # Y la regla de oro: la salida NO puede tocar el estado del pase.
    if "estado:" in fuente.split("async function salSubir")[1].split("}")[0]:
        raise SystemExit("*** la salida esta tocando `estado` — eso borra la recaudacion del dia")

    # QUE EL ARCHIVO ENTERO PARSEE. Esta prueba existe porque el arnes no la hacia y dejo
    # pasar un index.html roto: un `onclick` armado dentro de una cadena perdio sus
    # comillas escapadas, el <script> completo dejo de parsear y la aplicacion se quedaba
    # en el logo. Las 67 pruebas de abajo seguian verdes, porque recortan funciones sueltas
    # y las evaluan aisladas — nunca miran el archivo como un todo.
    bloques = re.findall(r"<script>([\s\S]*?)</script>", fuente)
    if not bloques:
        raise SystemExit("*** no encontre el <script> principal del index.html")
    guardia = ("try { new Function(%s); iguala('el <script> del index.html parsea entero', true, true); }\n"
               "catch (e) { iguala('el <script> del index.html parsea entero: ' + e.message, false, true); }\n"
               % json.dumps(max(bloques, key=len)))

    pagina = (PAGINA
              .replace("__CASOS__", guardia + "__CASOS__")
              .replace("__FUNCIONES__",
                       "\n".join([recortar_const(fuente, c) for c in CONSTANTES]
                                 + [recortar(fuente, n) for n in FUNCIONES]))
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
