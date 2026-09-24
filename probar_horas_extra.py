#!/usr/bin/env python3
"""Las horas extra (seccion 65), probadas contra el sistema de desarrollo.

    python3 probar_horas_extra.py          arma un servicio de prueba y
                                           revisa como cuenta las horas
    python3 probar_horas_extra.py 123      revisa ese servicio despues de
                                           corregir y dar el visto bueno

La primera corrida arma un eventual de cuatro dias full day ya pasados,
del Cliente Demo AAA, con el personal y las unidades de la siembra (nunca
el personal real). La central hace lo que hace cuando el telefono no marca:
asienta a mano la llegada y el meet and greet, y cierra el dia a mano con
su hora de termino. La corrida revisa que las horas extra salgan como se
decidio el 24 de septiembre:

  dia 1  termina 5 min antes de que corran             0 h
  dia 2  llega 5 min tarde, termina 1 h 50 despues     2 h  corren desde la
                                                            presentacion
  dia 3  meet and greet 30 min antes de la             1 h  corren desde el
         presentacion, termina 10 min antes del fin         meet and greet
  dia 4  termina 1 min despues de que corran           1 h  un minuto ya
                                                            cuenta

Despues tu, en la consola y como consultora, corriges una hora y das el
visto bueno. La segunda corrida revisa lo que quedo: la correccion con su
hora original, el candado del visto bueno y lo que ve finanzas.

Cada corrida crea un servicio nuevo y no toca los que ya estan. No lleva
marcas de la calle ni direcciones, asi que no sale a Google ni a Pegasus.
No imprime nombres.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal

try:
    from zoneinfo import ZoneInfo
    HOY = datetime.now(ZoneInfo("America/Mexico_City")).date()
except Exception:  # sin base de zonas: la fecha de esta maquina
    HOY = datetime.now().date()

BASE = os.environ.get("CENTAURO_API", "http://localhost:8000")
CUENTAS = {"consultora": "ana.solis@centauro.lat",
           "central": "central@centauro.lat",
           "finanzas": "finanzas@centauro.lat"}
CONSULTORA = "Ana Solis"
CLIENTE = "Cliente Demo AAA"
PERSONAL = ("Juan Ramirez", "Luis Mendoza", "Miguel Torres", "Hector Palacios")
UNIDADES = ("ABC-1234", "ABC-5678")
PRESENTACION = "07:00:00"
MOTIVO = ("Prueba de horas extra (seccion 65): el telefono no marco y la "
          "central asienta las horas que confirmo el equipo")

# Que pasa ese dia, minutos contra la presentacion, minutos contra el fin
# programado y las horas extra que tienen que salir.
CASOS = [
    ("termina 5 min antes de que corran", 0, -5, 0),
    ("llega 5 min tarde, termina 1 h 50 despues", 5, 110, 2),
    ("meet and greet 30 min antes, termina 10 min antes del fin", -30, -10, 1),
    ("termina 1 min despues de que corran", 0, 1, 1),
]

fallas = []


def alto(mensaje):
    print("\nALTO: " + mensaje)
    sys.exit(1)


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers=cab)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        bruto = e.read()
        try:
            return e.code, json.loads(bruto or b"null")
        except ValueError:
            return e.code, bruto.decode(errors="replace")[:300]
    except urllib.error.URLError:
        alto(f"No contesta el sistema en {BASE}. Esta arriba docker compose?")


def entrar(quien):
    datos = urllib.parse.urlencode({"username": CUENTAS[quien],
                                    "password": "centauro2026"}).encode()
    req = urllib.request.Request(
        BASE + "/auth/token", data=datos, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        alto(f"La cuenta de prueba de {quien} no entra ({e.code}).")
    except urllib.error.URLError:
        alto(f"No contesta el sistema en {BASE}. Esta arriba docker compose?")


def detalle(cuerpo):
    """Solo el mensaje: las alertas traen nombres y aqui no se imprimen."""
    if isinstance(cuerpo, dict) and "detail" in cuerpo:
        d = cuerpo["detail"]
        if isinstance(d, dict):
            return str(d.get("mensaje") or "")[:200]
        if isinstance(d, list):
            return "datos que no pasan la validacion"
        return str(d)[:200]
    return str(cuerpo)[:200]


def exigir(respuesta, que):
    codigo, cuerpo = respuesta
    if codigo not in (200, 201):
        alto(f"{que}: {codigo} {detalle(cuerpo)}")
    return cuerpo


def revisar(ok, texto, nota=None):
    print(("  OK     " if ok else "  FALLA  ") + texto)
    if nota:
        print("         " + nota)
    if not ok:
        fallas.append(texto)


def aviso(texto):
    print("  AVISO  " + texto)


def hhmm(iso):
    return iso[11:16] if iso else "--:--"


def dia(fecha):
    return fecha[8:10] + "/" + fecha[5:7]


def pesos(x):
    return "${:,.2f}".format(Decimal(str(x)))


def uno(filas, que, **igual):
    for f in filas:
        if all(f.get(k) == v for k, v in igual.items()):
            return f
    alto(f"No encontre {que} en los catalogos de desarrollo.")


def horas_del_dia(jornada_id, token):
    return exigir(pedir("GET", f"/operacion/jornadas/{jornada_id}/dia",
                        token=token), "leer el dia")["horas"]


def estatus_del_cierre(servicio_id, token):
    e = exigir(pedir("GET", f"/cierre/servicio/{servicio_id}/estado",
                     token=token), "leer el cierre")
    return e.get("estatus") or "sin cierre"


# --------------------------------------------------------------- primera corrida

def armar():
    print(f"Sistema {BASE} · hoy en Mexico {HOY:%d/%m/%Y}\n")
    ana, central = entrar("consultora"), entrar("central")

    def catalogo(nombre):
        return exigir(pedir("GET", "/catalogos/" + nombre, token=ana),
                      "leer el catalogo " + nombre.split("?")[0])

    mx = next((p for p in catalogo("paises") if p["codigo"] in ("MX", "MEX")),
              None) or alto("No encontre Mexico en los catalogos.")
    cdmx = uno(catalogo("plazas?todas=true"), "la plaza Ciudad de Mexico",
               nombre="Ciudad de Mexico", pais_id=mx["id"])
    full_day = uno(catalogo("modalidades"), "el full day de Mexico",
                   codigo="full_day", pais_id=mx["id"])
    if not full_day.get("aplica_horas_extra"):
        alto("En esta base el full day no lleva horas extra.")
    rol = uno(catalogo("perfiles"), "el rol conductor de seguridad",
              codigo="conductor_seguridad")
    suv = uno(catalogo("categorias-vehiculo"), "la categoria SUV blindada",
              codigo="suv_blindada")
    vehiculos = catalogo("vehiculos")
    unidades = [v for placa in UNIDADES for v in vehiculos
                if v["placa"] == placa and v["categoria_id"] == suv["id"]]
    personal = catalogo("personal")
    gente = [p for nombre in PERSONAL for p in personal
             if p["nombre"] == nombre]
    if not gente:
        alto("No encontre al personal de la siembra.")
    consultora = uno(personal, "a la consultora de prueba", nombre=CONSULTORA)
    cliente = uno(catalogo("clientes"), "al cliente de prueba", nombre=CLIENTE)

    # ---- el servicio: cuatro dias ya pasados, del mas viejo a ayer
    fechas = [HOY - timedelta(days=len(CASOS) - i) for i in range(len(CASOS))]
    servicio = exigir(pedir("POST", "/servicios", {
        "cliente_id": cliente["id"], "pais_id": mx["id"],
        "plaza_id": cdmx["id"], "tipo": "eventual",
        "consultor_id": consultora["id"],
        "solicitante_nombre": "Prueba", "solicitante_apellidos": "Horas Extra",
        "solicitante_correo": "solicitante@example.com",
        "ejecutivo_nombre": "Prueba", "ejecutivo_apellidos": "Seccion 65",
        "ejecutivo_correo": "ejecutivo@example.com",
        "equipos": [{"clave": "EQ-1", "jornadas": [
            {"fecha": str(f), "modalidad_id": full_day["id"],
             "hora_presentacion": PRESENTACION} for f in fechas]}],
    }, ana), "crear el servicio")
    sid = servicio["id"]
    jornadas = sorted(servicio["equipos"][0]["jornadas"],
                      key=lambda j: j["fecha"])

    # ---- cada dia con quien este libre: al calculo no le importa quien.
    # Si ninguna unidad de la siembra esta libre ese dia, va sin unidad.
    quien, con_unidad = {}, set()
    for j in jornadas:
        for p in gente:
            if pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-personal",
                     {"persona_id": p["id"], "rol_id": rol["id"],
                      "forzar": True}, ana)[0] in (200, 201):
                quien[j["id"]] = p["id"]
                break
        else:
            alto(f"Nadie del personal de la siembra esta libre el "
                 f"{dia(j['fecha'])}. El servicio {servicio['folio']} quedo "
                 "a medias; no afecta nada.")
        for v in unidades:
            if pedir("POST", f"/servicios/jornadas/{j['id']}/asignar-vehiculo",
                     {"vehiculo_id": v["id"], "forzar": True},
                     ana)[0] in (200, 201):
                con_unidad.add(j["id"])
                break

    # ---- se cotiza lo que va, y el cliente lo autoriza
    lineas = []
    for j in jornadas:
        lineas.append({"fecha": j["fecha"], "tipo": "recurso",
                       "perfil_id": rol["id"]})
        if j["id"] in con_unidad:
            lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                           "categoria_id": suv["id"]})
    cotizacion = exigir(pedir("POST", "/cotizaciones", {
        "servicio_id": sid, "lineas": lineas}, ana), "cotizar")
    exigir(pedir("POST", f"/cotizaciones/{cotizacion['cotizacion_id']}"
                         "/autorizar",
                 {"autorizada_por": "Prueba de horas extra"}, ana),
           "autorizar la cotizacion")

    # ---- la central asienta cada dia: llegada, meet and greet y termino
    for j, (_, desde, hasta, _) in zip(jornadas, CASOS):
        inicio = (datetime.fromisoformat(j["inicio_programado"])
                  + timedelta(minutes=desde))
        fin = (datetime.fromisoformat(j["fin_programado"])
               + timedelta(minutes=hasta))
        for tipo, momento in (("llegada_origen", inicio - timedelta(minutes=10)),
                              ("contacto_ejecutivo", inicio)):
            exigir(pedir("POST", f"/operacion/jornadas/{j['id']}/marca-a-mano",
                         {"tipo": tipo, "persona_id": quien[j["id"]],
                          "momento": momento.isoformat(),
                          "justificacion": MOTIVO}, central),
                   f"asentar a mano el {tipo.replace('_', ' ')} del "
                   f"{dia(j['fecha'])}")
        exigir(pedir("POST", f"/operacion/jornadas/{j['id']}/cerrar-a-mano",
                     {"justificacion": MOTIVO, "fin_real": fin.isoformat()},
                     central),
               "cerrar a mano el " + dia(j["fecha"]))
    exigir(pedir("POST", f"/cierre/servicio/{sid}/abrir", token=ana),
           "abrir el visto bueno")

    print(f"Servicio de prueba {servicio['folio']} (id {sid}): "
          f"{len(jornadas)} dias full day, presentacion "
          f"{PRESENTACION[:5]}, {len(con_unidad)} de ellos con unidad\n")

    # ---- 1. el panel de cada dia
    print("1. Lo que dice el panel de cada dia (Horas del dia)")
    total = 0
    for n, (j, (que, _, _, esperado)) in enumerate(zip(jornadas, CASOS), 1):
        h = horas_del_dia(j["id"], ana)
        total += esperado
        revisar(h["horas_extra"] == esperado,
                f"dia {n} ({dia(j['fecha'])}) {que}: {h['horas_extra']} h "
                f"extra" + ("" if h["horas_extra"] == esperado
                            else f", tenian que ser {esperado}"),
                f"presentacion {hhmm(h['presentacion'])} · con el ejecutivo "
                f"{hhmm(h['con_el_ejecutivo'])} · corren hasta "
                f"{hhmm(h['corren_hasta'])} · termino {hhmm(h['termino'])}")
    revisar(h["puedo_corregir"],
            "la consultora del servicio puede corregir las horas (aun no da "
            "su visto bueno)")

    # ---- 2. lo que llega al visto bueno
    print("\n2. Lo que llega al visto bueno")
    comparativo = exigir(pedir("GET", f"/cierre/servicio/{sid}/comparativo",
                               token=ana), "leer el comparativo")
    ejecutado = comparativo["ejecutado"]
    revisar(ejecutado["horas_extra"] == total,
            f"{ejecutado['horas_extra']} h extra en el servicio (tenian que "
            f"ser {total})")
    importe = Decimal(str(ejecutado["importe_horas_extra"]))
    if ejecutado["horas_extra_sin_precio"]:
        aviso("el tarifario del cliente no tiene precio de hora extra para "
              "el rol: el visto bueno lo va a decir y no se cobrarian")
    elif ejecutado["horas_extra"]:
        revisar(importe > 0,
                f"se cobran {pesos(importe)} de horas extra: "
                f"{ejecutado['horas_extra']} h x "
                f"{pesos(importe / ejecutado['horas_extra'])}")
    if con_unidad:
        diferencia = Decimal(str(comparativo["diferencia"]))
        revisar(diferencia == importe,
                f"contra lo cotizado solo sube lo de las horas extra "
                f"({pesos(diferencia)}): la unidad no las cobra")
    else:
        aviso("ninguna unidad de la siembra estaba libre esos dias: no se "
              "revisa que la unidad no cobre horas extra")
    revision = exigir(pedir("GET", f"/cierre/servicio/{sid}/revision",
                            token=ana), "leer la revision")
    renglones = [o for o in revision.get("observaciones", [])
                 if o.get("clave") == "horas_extra"]
    con_extra = sum(1 for c in CASOS if c[3])
    revisar(len(renglones) == con_extra,
            f"el visto bueno las dice dia por dia ({len(renglones)} "
            f"renglones, uno por dia con horas extra)")
    for o in renglones:
        print("         " + o["mensaje"])
    estatus = estatus_del_cierre(sid, ana)
    print(f"         el cierre esta en: {estatus}" + (
        " (corre la comprobacion de viaticos; sin viaticos que esperar, el "
        "reloj del sistema lo pasa al visto bueno en menos de cinco minutos)"
        if estatus == "abierto" else ""))

    dos = jornadas[1]
    fin_dos = datetime.fromisoformat(dos["fin_programado"])
    corregido = (fin_dos + timedelta(minutes=40)).strftime("%H:%M")
    print(f"""
Ahora tu, en la consola ({BASE}), con la cuenta de la consultora
({CUENTAS['consultora']}):

  a. Abre el servicio {servicio['folio']}. En «Dias de servicio», el dia 2
     ({dia(dos['fecha'])}) -> «Punto de origen y agenda». Abajo, en «Horas
     del dia»: 2 h extra.
  b. «Corregir horas»: termino a las {corregido} y un motivo. Antes de
     guardar, la vista previa dice 1 h. Guarda: queda la hora original.
  c. Mas abajo, «Visto bueno y facturacion» (se abre sola en menos de
     cinco minutos; si aun no, recarga): las horas por dia y tu
     correccion. Da el visto bueno.
  d. Vuelve al dia 2: el boton de corregir ya no sale.

Y luego:

    python3 probar_horas_extra.py {sid}
""")


# --------------------------------------------------------------- segunda corrida

def despues(sid):
    ana, finanzas = entrar("consultora"), entrar("finanzas")
    servicio = exigir(pedir("GET", f"/servicios/{sid}", token=ana),
                      "leer el servicio")
    jornadas = sorted((j for e in servicio["equipos"] for j in e["jornadas"]),
                      key=lambda j: j["fecha"])
    print(f"Servicio {servicio['folio']} (id {sid}) · el cierre esta en: "
          f"{estatus_del_cierre(sid, ana)}\n")

    print("1. Los dias, como quedaron")
    correcciones, cerrado = 0, None
    for n, j in enumerate(jornadas, 1):
        h = horas_del_dia(j["id"], ana)
        print(f"         dia {n} ({dia(j['fecha'])}): termino "
              f"{hhmm(h['termino'])}, corren hasta {hhmm(h['corren_hasta'])}"
              f" -> {h['horas_extra']} h extra")
        for c in h["correcciones"]:
            correcciones += 1
            cual = "arranque" if c["campo"] == "inicio" else "termino"
            revisar(bool(c["antes"]) and bool(c["motivo"]),
                    f"corregido: el {cual} paso de {hhmm(c['antes'])} a "
                    f"{hhmm(c['despues'])}, con la hora original y el motivo")
        if h["por_que_no"] == "visto_bueno" and cerrado is None:
            cerrado = (j, h)
    revisar(correcciones > 0, f"{correcciones} correccion(es) de horas")

    print("\n2. El candado del visto bueno")
    if cerrado is None:
        aviso("todavia no hay visto bueno: dalo y corre esto otra vez")
    else:
        j, h = cerrado
        revisar(not h["puedo_corregir"],
                "la consola ya no le ofrece a la consultora corregir")
        otra = (datetime.fromisoformat(h["termino"])
                - timedelta(minutes=5)).isoformat()
        codigo, cuerpo = pedir("POST", f"/operacion/jornadas/{j['id']}/horas",
                               {"fin": otra, "justificacion":
                                "Intento de la prueba despues del visto bueno"},
                               ana)
        revisar(codigo == 409,
                f"y si lo intenta por fuera de la consola, el sistema lo "
                f"rechaza ({codigo})",
                detalle(cuerpo) if codigo != 200 else
                "OJO: la correccion entro y ese dia de prueba ya cambio")

    print("\n3. Lo que ve finanzas")
    revision = exigir(pedir("GET", f"/cierre/servicio/{sid}/revision",
                            token=finanzas), "leer la revision como finanzas")
    corregidas = [o for o in revision.get("observaciones", [])
                  if o.get("clave") == "horas_corregidas"]
    revisar(len(corregidas) == correcciones,
            f"ve {len(corregidas)} correccion(es) de horas, con quien, "
            f"cuando y el motivo")
    for o in corregidas:
        d = o["datos"]
        cual = "arranque" if d["campo"] == "inicio" else "termino"
        print(f"         {d['fecha']}: el {cual} paso de {d['antes']} a "
              f"{d['despues']}")
    comparativo = exigir(pedir("GET", f"/cierre/servicio/{sid}/comparativo",
                               token=finanzas), "leer el comparativo")
    ejecutado = comparativo["ejecutado"]
    print(f"         {ejecutado['horas_extra']} h extra por "
          f"{pesos(ejecutado['importe_horas_extra'])}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if not sys.argv[1].isdigit():
            alto("Pasa el id del servicio, el numero que imprimio la primera "
                 "corrida.")
        despues(int(sys.argv[1]))
    else:
        armar()
    print("\n" + ("Todo cuadra." if not fallas else
                  f"{len(fallas)} cosa(s) no cuadran; pegame la salida."))
    sys.exit(1 if fallas else 0)
