# -*- coding: utf-8 -*-
"""El zoológico: la base de desarrollo llena de servicios de verdad.

Una prueba automática verifica que el campo `hospedaje` traiga tres
hoteles. Lo que **no puede** es juzgar si al abrir la pantalla falta el
teléfono del hotel, si sobra una columna que nadie usa, o si un renglón
dice "—" donde debería decir algo. Eso lo juzga una persona mirando, y
para mirarlo hacen falta pantallas llenas de datos creíbles.

Esto las llena: un servicio por escenario, en todos los estados en los
que el sistema los puede tener.

    docker compose exec -T api python sembrar_360.py
    docker compose exec -T api python sembrar_360.py --borrar
    docker compose exec -T api python sembrar_360.py --solo en_curso

**Se siembra por la puerta de la calle.** Todo entra por la misma API y
con los mismos permisos que usa la operación: si un escenario no se
puede armar por ahí, eso ya es un hallazgo y no algo que se resuelva
metiendo filas a mano. Las ayudas son las mismas de las pruebas
(`tests/ayudas.py`), para que el día que cambie un candado esto cambie
con él en vez de seguir mintiendo.

**No corre contra la base de pruebas**, y lo verifica antes de escribir
nada. Es dato de demostración: se reconoce por el correo de quien
solicita y se borra completo con `--borrar`.
"""
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, "tests")

from fastapi.testclient import TestClient          # noqa: E402

from app import models as m                        # noqa: E402
from app.db import SessionLocal, engine            # noqa: E402
from app.main import app                           # noqa: E402

from ayudas import (asignar, cotizar_y_autorizar,  # noqa: E402
                    crear_servicio, depositar, ejecutar_jornada, jornada,
                    marcar, revisar_unidad)

# La marca de la casa: por aquí se reconoce lo sembrado y por aquí se
# borra. Va en el correo de quien solicita porque es un campo que el
# alta siempre escribe y que ninguna regla usa para decidir nada.
CORREO = "demo360@centauro.lat"
CLAVE = "centauro2026"
def sesion_de(c, s, persona_id) -> dict:
    """Las cabeceras de quien quedo asignado, sea de la casa o del
    reparto del zoologico. Un dia se ejecuta con la sesion de quien lo
    trabaja: cualquier otra cosa la rechaza el servidor, con razon."""
    with SessionLocal() as db:
        persona = db.get(m.Persona, persona_id)
        correo = persona.correo if persona else None
    if not correo:
        raise RuntimeError(f"la persona {persona_id} no tiene correo")
    r = c.post("/auth/token", data={"username": correo, "password": CLAVE})
    if r.status_code != 200:
        raise RuntimeError(f"no se pudo entrar como {correo}: {r.text[:120]}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


CUENTAS = {
    "admin": "admin@centauro.lat",
    "consultor": "ana.solis@centauro.lat",
    "central": "central@centauro.lat",
    "finanzas": "finanzas@centauro.lat",
    "juan": "juan.ramirez@centauro.lat",
    "luis": "luis.mendoza@centauro.lat",
    "carlos": "carlos.vega@centauro.lat",
}


# ==================================================================
# Candados
# ==================================================================

def revisar_donde_estamos() -> None:
    """Lo primero, antes de escribir una sola fila.

    El conftest de las pruebas apunta a `centauro_test` y vacía tablas.
    Esto es su espejo: si por lo que sea acabara apuntando ahí, se
    detiene. Sembrar sobre la base de pruebas no rompe nada, pero deja
    la siguiente corrida contando servicios que no son suyos.
    """
    if engine.url.database == "centauro_test":
        raise SystemExit(
            "Esto siembra la base de DESARROLLO y estás apuntando a "
            "centauro_test. No se sembró nada.")
    with SessionLocal() as db:
        if not db.query(m.Persona).count():
            raise SystemExit(
                "La base no tiene catálogos ni personal. Corre primero la "
                "semilla: docker compose exec api python -m app.seed")


# ==================================================================
# Entrar y catálogos
# ==================================================================

def entrar(c: TestClient):
    cache = {}

    def quien(nombre: str) -> dict:
        if nombre not in cache:
            r = c.post("/auth/token",
                       data={"username": CUENTAS[nombre], "password": CLAVE})
            if r.status_code != 200:
                raise SystemExit(f"No se pudo entrar como {nombre}: {r.text}")
            cache[nombre] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[nombre]

    return quien


def catalogos(c: TestClient, s) -> dict:
    """Las mismas referencias que usan las pruebas."""
    h = s("admin")

    def traer(ruta):
        r = c.get(ruta, headers=h)
        if r.status_code != 200:
            raise SystemExit(f"{ruta}: {r.text}")
        return r.json()

    paises = traer("/catalogos/paises")
    mx = next(p for p in paises if p["codigo"] == "MX")
    categorias = {x["codigo"]: x for x in traer("/catalogos/categorias-vehiculo")}
    plazas = {p["nombre"]: p for p in traer("/catalogos/plazas")}
    vehiculos = traer("/catalogos/vehiculos")
    return {
        "mx": mx,
        "cdmx": plazas["Ciudad de Mexico"],
        "gdl": plazas["Guadalajara"],
        "modalidades": {x["codigo"]: x for x in traer("/catalogos/modalidades")
                        if x["pais_id"] == mx["id"]},
        "perfiles": {p["codigo"]: p for p in traer("/catalogos/perfiles")},
        "categorias": categorias,
        "personal": {p["nombre"]: p for p in traer("/catalogos/personal")},
        "vehiculos": vehiculos,
        "cliente_id": traer("/catalogos/clientes")[0]["id"],
        "suburban": next(v for v in vehiculos
                         if v["categoria_id"]
                         == categorias["suv_blindada"]["id"]),
        "hoteles": traer("/catalogos/hoteles?todos=true"),
    }


# ==================================================================
# Ladrillos comunes
# ==================================================================

PUNTO = {"origen_direccion": "Aeropuerto Internacional Benito Juárez, T2 "
                             "— Sala de llegadas internacionales",
         "origen_lat": "19.4270", "origen_lon": "-99.1677",
         "origen_aeropuerto": True, "geocerca_metros": 250}


# Los datos del cliente que el alta de las pruebas no captura y una
# operación real sí: el teléfono del principal --que sale en el task
# sheet y en los correos-- y el de quien solicita.
CLIENTE = {
    "solicitante_correo": CORREO,
    "solicitante_telefono": "5544332211",
    "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
    "ejecutivo_correo": "ingrid.halvorsen@cliente.com",
    "ejecutivo_telefono": "5566778899",
}

# Un vuelo de verdad. La mitad de los servicios arrancan contra uno y
# es lo que amarra la hora de presentación; sin esto, media hoja del
# task sheet no se veía nunca.
def vuelo(dia, hora="06:40:00"):
    return {"vuelo_aerolinea": "Aeroméxico", "vuelo_numero": "AM 7",
            "vuelo_hora": f"{dia}T{hora}", "vuelo_origen": "Madrid (MAD)",
            "vuelo_tipo": "llegada"}


def alta(c, s, cat, dias, hora="07:00:00", desde=1, modalidad="full_day",
         del_dia=None, **extra):
    """Un servicio con sus días, ya con punto y pin en cada uno.

    El punto va en el alta y no después: es lo que el consultor captura
    cuando el cliente le dicta el vuelo, y sin él la hoja no se libera.

    `del_dia` es para lo que vive en la jornada y no en el servicio
    --`es_foraneo`, el vuelo--: mandarlo arriba lo rechaza el esquema,
    que es justo lo que uno quiere de un esquema.
    """
    h = s("consultor")
    jornadas = [
        jornada(date.today() + timedelta(days=desde + i),
                cat["modalidades"][modalidad]["id"], hora=hora,
                **PUNTO, **(del_dia or {}))
        for i in range(dias)]
    return crear_servicio(
        c, h, cat, jornadas,
        consultor_id=cat["personal"]["Ana Solis"]["id"],
        **{**CLIENTE, **extra})


def equipar(c, s, cat, servicio, quien=None, vehiculo=None,
            con_cuenta=False):
    """Gente y unidad para todos los días del equipo.

    **Pregunta quién está libre**, como hace un consultor de verdad, en
    vez de nombrar a alguien y cruzar los dedos. La base de desarrollo
    no está vacía: trae los servicios de las semanas anteriores, y el
    sistema bloquea de verdad el empalme --nadie puede estar en dos
    servicios el mismo día, ni una camioneta--. Un sembrador que nombra
    a Juan y a la Suburban para trece escenarios está peleándose con una
    regla que tiene razón.

    `quien` fuerza a una persona cuando el escenario la necesita --la
    app de campo se mira con la sesión de Juan-- y entonces sí truena si
    está ocupada, que es lo correcto: ese escenario no se puede armar.
    """
    equipo = servicio["equipos"][0]
    persona_id, vehiculo_id = equipar_equipo(c, s, cat, equipo, quien,
                                             vehiculo,
                                             con_cuenta=con_cuenta)
    servicio["_persona_id"] = persona_id
    servicio["_vehiculo_id"] = vehiculo_id
    return servicio


def equipar_equipo(c, s, cat, equipo, quien=None, vehiculo=None,
                   excluir=(), con_cuenta=False):
    """El equipo de un solo equipo. `excluir` es para el servicio de dos:
    el segundo no puede llevarse a quien ya se llevó el primero."""
    h = s("consultor")
    equipo_id = equipo["id"]
    categoria = cat["categorias"]["suv_blindada"]["id"]
    rol = cat["perfiles"]["conductor_seguridad"]["id"]
    r = c.get(f"/servicios/equipos/{equipo_id}/recomendaciones"
              f"?perfil_id={rol}&categoria_id={categoria}", headers=h)
    if r.status_code != 200:
        raise RuntimeError(f"no se pudo consultar disponibilidad: {r.text[:160]}")
    libres = r.json()

    def elegir(bloque, llave, nombre=None):
        gente = [x for x in ((libres[bloque].get("disponibles") or [])
                             + (libres[bloque].get("con_alerta") or []))
                 if x[llave] not in excluir]
        if nombre:
            suyo = next((x for x in gente if x.get("nombre") == nombre
                         or x.get("placa") == nombre), None)
            if not suyo:
                raise RuntimeError(f"{nombre} no está libre esos días")
            return suyo[llave]
        if con_cuenta and bloque == "personal":
            gente = [x for x in gente if x.get("nombre") in CON_CUENTA]
        if not gente:
            raise RuntimeError(
                f"sin {bloque}{' con cuenta' if con_cuenta else ''} libre "
                f"esos días")
        return gente[0][llave]

    persona_id = elegir("personal", "persona_id", quien)
    vehiculo_id = elegir("vehiculos", "vehiculo_id", vehiculo)

    for j in equipo["jornadas"]:
        for respuesta in asignar(c, h, j["id"], persona_id=persona_id,
                                 vehiculo_id=vehiculo_id):
            if respuesta.status_code != 200:
                raise RuntimeError(
                    f"no se pudo asignar el {j['fecha']}: "
                    f"{respuesta.text[:160]}")
    return persona_id, vehiculo_id


def viaticar(c, s, cat, servicio, monto="900", solicitar=True,
             quien=None):
    """Viáticos de todos los días, y opcionalmente pedidos a finanzas.

    De quien va, no siempre de Juan: un viático para alguien que no está
    asignado a ese día lo rechaza el servidor, con razón.
    """
    h = s("consultor")
    juan = (cat["personal"][quien]["id"] if quien
            else servicio["_persona_id"])
    for j in servicio["equipos"][0]["jornadas"]:
        r = c.post("/viaticos/asignar", headers=h, json={
            "jornada_id": j["id"], "persona_id": juan,
            "conceptos": [
                {"concepto": "alimentos", "monto": monto,
                 "origen": "tabulador"},
                {"concepto": "combustible", "monto": "350",
                 "origen": "estimado", "descripcion": "180 km estimados"}],
        })
        if r.status_code not in (200, 201):
            raise RuntimeError(f"no se pudo asignar viáticos: {r.text[:160]}")
        if solicitar:
            c.post(f"/viaticos/{r.json()['id']}/solicitar-transferencia",
                   headers=h)
    return servicio


def hospedar(c, s, cat, servicio, desde, hasta):
    """Dónde duerme el ejecutivo. Del catálogo si lo hay, y si no,
    capturado a mano —que es lo que hace el consultor la primera vez que
    va a ese hotel—.

    Se revisa la respuesta: el hotel que no se guarda deja la hoja sin
    hospedaje y sin hospitales medidos desde ahí, y eso aparecía después
    en el revisor como si la pantalla estuviera mal.
    """
    hotel = (cat["hoteles"] or [None])[0]
    cuerpo = {"equipo_id": servicio["equipos"][0]["id"],
              "desde": desde, "hasta": hasta}
    if hotel:
        cuerpo["hotel_id"] = hotel["id"]
    else:
        cuerpo.update({
            "nombre_libre": "Las Alcobas",
            "direccion_libre": "Av. Presidente Masaryk 390, Polanco",
            "telefono_libre": "+52 55 3300 3900",
            "hotel_lat": "19.4325", "hotel_lon": "-99.1935"})
    # Sin prefijo: el router del task sheet monta sus rutas en la raíz.
    r = c.post("/hospedajes", headers=s("consultor"), json=cuerpo)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"no se pudo guardar el hotel: {r.text[:160]}")
    return r


def liberar(c, s, servicio, motivo="alta del servicio"):
    """Publicar el TS y firmar la asignación: lo que la central espera
    para poder trabajar sobre el servicio."""
    h = s("consultor")
    c.post(f"/task-sheets/servicio/{servicio['id']}/publicar",
           json={"motivo": motivo}, headers=h)
    return c.post(f"/servicios/{servicio['id']}/confirmar-asignacion",
                  headers=h)


# ==================================================================
# Los escenarios
#
# Cada uno deja el sistema en un estado que de verdad ocurre, y devuelve
# una linea que dice que mirar. Se agregan aqui: la lista de abajo es lo
# unico que hay que tocar para sumar uno nuevo.
# ==================================================================

def borrador(c, s, cat):
    """Lo que el cliente pidió por teléfono y todavía no tiene nada.

    Mirar: que la pantalla diga qué falta, sin inventar lo que no hay.
    """
    servicio = alta(c, s, cat, dias=1, desde=9, modalidad="transfer",
                    hora="06:15:00")
    return servicio, "Sin gente, sin unidad, sin cotizar"


def planeado(c, s, cat):
    """Ya tiene equipo, unidad y cotización autorizada; falta firmar."""
    servicio = alta(c, s, cat, dias=3, desde=6, vestimenta="semiformal")
    equipar(c, s, cat, servicio)
    viaticar(c, s, cat, servicio, solicitar=False)
    # Sin cotización autorizada, media pantalla de cierre contesta 409.
    cotizar_y_autorizar(c, s("consultor"), servicio,
                        cat["perfiles"]["conductor_seguridad"]["id"],
                        cat["categorias"]["suv_blindada"]["id"])
    return servicio, "Asignado y cotizado, TS sin publicar"


def manana(c, s, cat):
    """El servicio de mañana: el completo, el que hay que mirar.

    Es el único con TODO lo que un servicio puede traer --vuelo,
    vestimenta, señal de identificación, hotel--, a propósito: es el
    que dice si a una pantalla llena le falta algo.
    """
    dia = (date.today() + timedelta(days=1)).isoformat()
    servicio = alta(c, s, cat, dias=2, desde=1, hora="06:30:00",
                    del_dia=vuelo(dia), vestimenta="formal")
    equipar(c, s, cat, servicio)
    viaticar(c, s, cat, servicio)
    # La señal que el equipo levanta en el filtro.
    c.put(f"/servicios/{servicio['id']}/senal", headers=s("consultor"),
          json={"texto": "HALVORSEN",
                "nota": "El ejecutivo sale por la puerta 3"})
    hospedar(c, s, cat, servicio, dia,
             (date.today() + timedelta(days=2)).isoformat())
    liberar(c, s, servicio)
    return servicio, "El completo: vuelo, vestimenta, señal, hotel y TS"


def en_camino_en_riesgo(c, s, cat):
    """Alguien dijo que iba y no se está acercando.

    Mirar: la banda "Camino al punto" de la central, con su teléfono a
    un clic.
    """
    from app import trayecto
    servicio = alta(c, s, cat, dias=1, desde=0, hora="22:00:00")
    equipar(c, s, cat, servicio)
    liberar(c, s, servicio)
    j = servicio["equipos"][0]["jornadas"][0]
    juan = servicio["_persona_id"]
    with SessionLocal() as db:
        estar = trayecto.hora_de_estar(db, db.get(m.Jornada, j["id"]))
        # A 45 km y sin moverse entre dos lecturas: eso ya no es
        # puntualidad, es que no va a estar ahí.
        for minutos, lon in ((120, -99.5977), (100, -99.5977)):
            trayecto.registrar(db, j["id"], juan, "19.4270", str(lon),
                               ahora=estar - timedelta(minutes=minutos))
    return servicio, "En la central: 'No llega'. Con alerta abierta"


def en_curso(c, s, cat):
    """El servicio de hoy, con el equipo trabajando."""
    servicio = alta(c, s, cat, dias=1, desde=0, hora="08:00:00")
    # Con Juan: la app de campo se mira con su sesión.
    equipar(c, s, cat, servicio, quien="Juan Ramirez")
    viaticar(c, s, cat, servicio)
    liberar(c, s, servicio)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    revisar_unidad(c, s("juan"), servicio["id"], servicio["_vehiculo_id"],
                   "recibe", 42_000)
    marcar(c, s("juan"), j["id"], "llegada_origen",
           inicio - timedelta(minutes=12))
    marcar(c, s("juan"), j["id"], "contacto_ejecutivo", inicio)
    return servicio, "En curso: unidad recibida, ejecutivo contactado"


def con_panico(c, s, cat):
    """El botón de pánico, tomado por la central y todavía abierto."""
    servicio = alta(c, s, cat, dias=1, desde=0, hora="09:00:00")
    equipar(c, s, cat, servicio)
    liberar(c, s, servicio)
    j = servicio["equipos"][0]["jornadas"][0]
    # La captura la central: el agente llamó por radio. Es el otro
    # camino de la alerta y el que más se usa cuando el teléfono se
    # quedó en el coche.
    alerta = c.post("/contingencia/alertas", headers=s("central"), json={
        "canal": "llamada", "jornada_id": j["id"],
        "reporta_persona_id": servicio["_persona_id"],
        "lat": "19.4284", "lon": "-99.1957",
        "descripcion": "Vehículo sospechoso siguiendo a la unidad"}).json()
    if "id" in alerta:
        c.post(f"/contingencia/alertas/{alerta['id']}/tomar",
               json={"equipo_respuesta_enviado": True}, headers=s("central"))
    return servicio, "Alerta de pánico tomada, equipo de respuesta enviado"


def terminado_sin_cerrar(c, s, cat):
    """Ayer se trabajó completo y nadie ha cerrado los viáticos.

    Mirar: la banda de 'días sin cerrar' de la central.
    """
    servicio = alta(c, s, cat, dias=1, desde=-1, hora="07:00:00")
    equipar(c, s, cat, servicio, con_cuenta=True)
    viaticar(c, s, cat, servicio)
    liberar(c, s, servicio)
    equipo_id = servicio["equipos"][0]["id"]
    juan = servicio["_persona_id"]
    depositar(c, s("finanzas"), equipo_id, juan, referencia="SPEI-360-001")
    ejecutar_jornada(c, sesion_de(c, s, juan),
                     servicio["equipos"][0]["jornadas"][0])
    return servicio, "Día trabajado, dinero entregado, sin comprobar"


def con_horas_extra(c, s, cat):
    """El día que se alargó dos horas y media."""
    servicio = alta(c, s, cat, dias=1, desde=-2, hora="07:00:00")
    equipar(c, s, cat, servicio, con_cuenta=True)
    viaticar(c, s, cat, servicio)
    liberar(c, s, servicio)
    ejecutar_jornada(c, sesion_de(c, s, servicio["_persona_id"]),
                     servicio["equipos"][0]["jornadas"][0], horas_extra=2)
    return servicio, "Dos horas extra en el cierre y en la nómina"


def con_reemplazo(c, s, cat):
    """Juan se presentó y a media mañana entró Luis: el día partido."""
    servicio = alta(c, s, cat, dias=2, desde=0, hora="08:30:00")
    equipar(c, s, cat, servicio, con_cuenta=True)
    liberar(c, s, servicio)
    j = servicio["equipos"][0]["jornadas"][0]
    inicio = datetime.fromisoformat(j["inicio_programado"])
    # Marca su llegada desde su propia app antes de que lo releven:
    # eso es lo que parte el día.
    marcar(c, sesion_de(c, s, servicio["_persona_id"]), j["id"],
           "llegada_origen", inicio - timedelta(minutes=10))
    # Quien entra: alguien libre ese día que no sea el que sale.
    entra = next(
        x["persona_id"] for x in
        c.get(f"/servicios/equipos/{servicio['equipos'][0]['id']}"
              f"/recomendaciones?categoria_id="
              f"{cat['categorias']['suv_blindada']['id']}",
              headers=s("consultor")).json()["personal"]["disponibles"]
        if x["persona_id"] != servicio["_persona_id"])
    c.post("/contingencia/reemplazos/personal", headers=s("consultor"), json={
        "desde_jornada_id": j["id"],
        "sale_persona_id": servicio["_persona_id"],
        "entra_persona_id": entra,
        "motivo": "Se reportó enfermo a media mañana"})
    return servicio, "Día partido: los dos cobran, y el cliente ya lo sabe"


def deposito_tras_cancelar(c, s, cat):
    """El depósito que llegó cuando la solicitud ya estaba cancelada."""
    servicio = alta(c, s, cat, dias=1, desde=4)
    equipar(c, s, cat, servicio)
    viaticar(c, s, cat, servicio)
    equipo_id = servicio["equipos"][0]["id"]
    juan = servicio["_persona_id"]
    c.post(f"/viaticos/equipos/{equipo_id}/cancelar-solicitud",
           json={}, headers=s("consultor"))
    depositar(c, s("finanzas"), equipo_id, juan, referencia="SPEI-360-TARDE")
    return servicio, "Dinero depositado tras cancelar: por aplicar o devolver"


def cancelado(c, s, cat):
    """El que el cliente echó para atrás con el dinero ya afuera."""
    servicio = alta(c, s, cat, dias=2, desde=3)
    equipar(c, s, cat, servicio)
    viaticar(c, s, cat, servicio)
    equipo_id = servicio["equipos"][0]["id"]
    depositar(c, s("finanzas"), equipo_id, servicio["_persona_id"],
              referencia="SPEI-360-002")
    c.post(f"/servicios/{servicio['id']}/cancelar", headers=s("consultor"),
           json={"motivo": "El ejecutivo canceló el viaje"})
    return servicio, "Cancelado con depósito hecho: hay que recuperarlo"


def foraneo_con_hotel(c, s, cat):
    """Tres días fuera, con hospedaje y hospitales medidos desde el hotel."""
    servicio = alta(c, s, cat, dias=3, desde=7,
                    del_dia={"es_foraneo": True, "km_estimados": 320})
    equipar(c, s, cat, servicio)
    viaticar(c, s, cat, servicio, monto="1500")
    hospedar(c, s, cat, servicio, str(date.today() + timedelta(days=7)),
             str(date.today() + timedelta(days=10)))
    liberar(c, s, servicio)
    return servicio, "Foráneo con hotel: viáticos altos y hospitales del hotel"


def dos_equipos(c, s, cat):
    """Un proyecto con dos equipos: dos hojas, dos ejecutivos."""
    h = s("consultor")
    fecha = date.today() + timedelta(days=5)
    cuerpo = {
        "cliente_id": cat["cliente_id"], "pais_id": cat["mx"]["id"],
        "plaza_id": cat["cdmx"]["id"], "tipo": "eventual",
        "consultor_id": cat["personal"]["Ana Solis"]["id"],
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": CORREO, "solicitante_telefono": "5544332211",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "ejecutivo_correo": "ingrid@cliente.com",
        "equipos": [
            {"clave": "EQ-1", "jornadas": [
                jornada(fecha, cat["modalidades"]["full_day"]["id"], **PUNTO)]},
            {"clave": "EQ-2", "plaza_id": cat["gdl"]["id"],
             "ejecutivo_nombre": "Hans", "ejecutivo_apellidos": "Brenner",
             "ejecutivo_correo": "hans@cliente.com",
             "jornadas": [
                 jornada(fecha, cat["modalidades"]["full_day"]["id"],
                         **PUNTO)]},
        ],
    }
    r = c.post("/servicios", json=cuerpo, headers=h)
    if r.status_code != 201:
        raise SystemExit(f"dos_equipos: {r.text}")
    servicio = r.json()
    tomados = set()
    for equipo in servicio["equipos"]:
        persona_id, vehiculo_id = equipar_equipo(c, s, cat, equipo,
                                                 excluir=tomados)
        tomados |= {persona_id, vehiculo_id}
    return servicio, "Dos equipos y dos ciudades: dos TS a nombre de cada uno"


# El orden importa poco, salvo que los de hoy conviene sembrarlos juntos
# para que la central se vea llena de un golpe.
ESCENARIOS = [
    ("borrador", borrador),
    ("planeado", planeado),
    ("manana", manana),
    ("en_camino_en_riesgo", en_camino_en_riesgo),
    ("en_curso", en_curso),
    ("con_panico", con_panico),
    ("con_reemplazo", con_reemplazo),
    ("terminado_sin_cerrar", terminado_sin_cerrar),
    ("con_horas_extra", con_horas_extra),
    ("deposito_tras_cancelar", deposito_tras_cancelar),
    ("cancelado", cancelado),
    ("foraneo_con_hotel", foraneo_con_hotel),
    ("dos_equipos", dos_equipos),
]


# ==================================================================
# Sembrar y borrar
# ==================================================================

def sembrados(db) -> list:
    return (db.query(m.Servicio)
            .filter(m.Servicio.solicitante_correo == CORREO)
            .order_by(m.Servicio.id).all())


def borrar() -> int:
    """Se lleva todo lo sembrado, esté en el estado que esté.

    Por la API no se puede: un servicio cerrado o en curso no se borra
    —con razón—, y esto tiene que poder limpiarse siempre. Usa la
    MISMA función que el borrado de verdad, `desarmar_servicio`, para
    que no exista una segunda lista de tablas que se quede corta el día
    que aparezca una tabla nueva.
    """
    from app.routers.servicios import desarmar_servicio

    with SessionLocal() as db:
        servicios = sembrados(db)
        for servicio in servicios:
            jornada_ids = [j.id for e in servicio.equipos for j in e.jornadas]
            desarmar_servicio(db, servicio, jornada_ids, servicio.folio)
            db.delete(servicio)
        db.commit()
    quitar_reparto()
    return len(servicios)


# El reparto de la casa. La base de desarrollo tiene cuatro camionetas
# en Ciudad de Mexico y una agenda de semanas llena: el zoologico se
# quedaba sin unidad a media siembra. Trae la suya y deja de pelearse
# con los servicios de verdad, que son los que importan.
# La ultima de cada lista es de Guadalajara: el servicio de dos equipos
# manda uno a otra ciudad, y un equipo sin unidad en su plaza no se
# puede armar.
PLACAS = (("DEMO-001", "Ciudad de Mexico"), ("DEMO-002", "Ciudad de Mexico"),
          ("DEMO-003", "Ciudad de Mexico"), ("DEMO-004", "Ciudad de Mexico"),
          ("DEMO-005", "Guadalajara"))
GENTE = (("Demo Ricardo Nava", "demo360.rnava@centauro.lat",
          "Ciudad de Mexico"),
         ("Demo Alonso Prieto", "demo360.aprieto@centauro.lat",
          "Ciudad de Mexico"),
         ("Demo Emilio Bustos", "demo360.ebustos@centauro.lat",
          "Ciudad de Mexico"),
         ("Demo Ivan Cordero", "demo360.icordero@centauro.lat",
          "Ciudad de Mexico"),
         ("Demo Sandra Peralta", "demo360.speralta@centauro.lat",
          "Guadalajara"))

# Quien puede entrar a la app. Los escenarios que marcan hitos necesitan
# la sesion de quien los marca, y la base de desarrollo tiene gente sin
# cuenta: elegir a alguien de esos dejaba el escenario a medias.
CON_CUENTA = ({"Juan Ramirez", "Luis Mendoza", "Carlos Vega"}
              | {nombre for nombre, _c, _p in GENTE})


def reparto() -> None:
    """Cuatro unidades y cuatro personas propias del zoologico.

    Se reconocen por el nombre --todas empiezan con Demo-- y se van con
    `--borrar`. Son de la ciudad de Mexico porque ahi viven casi todos
    los escenarios.
    """
    COLORES = ("Negro", "Gris", "Blanco", "Azul marino", "Negro")
    MODELOS = ("Chevrolet Suburban", "Chevrolet Tahoe", "Toyota Sequoia",
               "Ford Expedition", "Chevrolet Suburban")
    with SessionLocal() as db:
        plazas = {p.nombre: p for p in db.query(m.Plaza).all()}
        blindada = db.query(m.CategoriaVehiculo).filter_by(
            codigo="suv_blindada").first()
        if not blindada or "Ciudad de Mexico" not in plazas:
            return
        for i, (placa, ciudad) in enumerate(PLACAS):
            if (db.query(m.Vehiculo).filter_by(placa=placa).first()
                    or ciudad not in plazas):
                continue
            db.add(m.Vehiculo(
                placa=placa, categoria_id=blindada.id,
                plaza_id=plazas[ciudad].id, costo_diario=1800,
                color=COLORES[i], marca_modelo=MODELOS[i], modelo_anio=2024))
        for nombre, correo, ciudad in GENTE:
            if (db.query(m.Persona).filter_by(correo=correo).first()
                    or ciudad not in plazas):
                continue
            db.add(m.Persona(nombre=nombre, correo=correo,
                             plaza_id=plazas[ciudad].id, es_freelance=False,
                             telefono="+52 55 5000 0000"))
        db.flush()

        # Con cuenta propia: un escenario que marca hitos necesita la
        # sesion de quien los marca, y sin esto el zoologico solo podia
        # ejecutar dias con Juan --que muchas veces ya esta ocupado--.
        # Misma contrasena de demo que el resto de la semilla.
        from app.auth import cifrar
        from app.seed import CONTRASENA_DEMO

        clave = cifrar(CONTRASENA_DEMO)
        for _nombre, correo, _ciudad in GENTE:
            persona = db.query(m.Persona).filter_by(correo=correo).first()
            if persona and not db.query(m.Usuario).filter_by(
                    persona_id=persona.id).first():
                db.add(m.Usuario(persona_id=persona.id, correo=correo,
                                 rol=m.Rol.PERSONAL_SEGURIDAD,
                                 hash_contrasena=clave))
        db.commit()


def quitar_reparto() -> None:
    """Se va con lo sembrado, y solo si ya no lo usa nadie."""
    with SessionLocal() as db:
        for placa, _ciudad in PLACAS:
            v = db.query(m.Vehiculo).filter_by(placa=placa).first()
            if v and not db.query(m.AsignacionVehiculo).filter_by(
                    vehiculo_id=v.id).count():
                db.delete(v)
        for _nombre, correo, _ciudad in GENTE:
            p = db.query(m.Persona).filter_by(correo=correo).first()
            if p and not db.query(m.AsignacionPersonal).filter_by(
                    persona_id=p.id).count():
                db.query(m.Usuario).filter_by(persona_id=p.id).delete(
                    synchronize_session=False)
                db.delete(p)
        db.commit()


def datos_bancarios() -> None:
    """A dónde se deposita.

    Viene de Odoo y esa conexión todavía no existe, así que en la base
    de desarrollo está vacío y la pantalla de finanzas se ve sin lo
    único que necesita para pagar. Son cuentas inventadas, y se ponen
    solo a quien no tiene: si alguien ya capturó una de verdad, no se
    le toca.
    """
    with SessionLocal() as db:
        for i, persona in enumerate(db.query(m.Persona)
                                    .filter(m.Persona.clabe.is_(None))
                                    .limit(12).all()):
            persona.banco = ("BBVA", "Banorte", "Santander")[i % 3]
            persona.clabe = f"0121800123456789{i:02d}"
            persona.titular_cuenta = persona.nombre
        db.commit()


def sembrar(solo: str | None = None) -> None:
    reparto()
    datos_bancarios()
    with TestClient(app) as c:
        s = entrar(c)
        cat = catalogos(c, s)
        print()
        for nombre, hacer in ESCENARIOS:
            if solo and solo != nombre:
                continue
            try:
                servicio, nota = hacer(c, s, cat)
            except Exception as err:                      # noqa: BLE001
                print(f"  ✗ {nombre:24} no se pudo armar: {err}")
                continue
            print(f"  ✓ {nombre:24} {servicio['folio']:14} "
                  f"#/servicio/{servicio['id']}")
            print(f"    {'':24} {nota}")
        print()


def main() -> None:
    revisar_donde_estamos()
    if "--borrar" in sys.argv:
        print(f"\n  Borrados {borrar()} servicios de demostración.\n")
        return
    solo = None
    if "--solo" in sys.argv:
        solo = sys.argv[sys.argv.index("--solo") + 1]
    # Se limpia antes de sembrar: si no, cada corrida apila otra tanda y
    # las pantallas dejan de parecerse a un día de trabajo.
    if not solo:
        borrar()
    sembrar(solo)
    print("  Entra a la consola y recorre las pantallas. Para quitarlo "
          "todo:\n  docker compose exec -T api python sembrar_360.py "
          "--borrar\n")


if __name__ == "__main__":
    main()
