"""Funciones que arman escenarios, para que las pruebas digan que verifican
y no como se monta el decorado."""
from datetime import date, datetime, timedelta

ORIGEN = {"origen_lat": "19.4270", "origen_lon": "-99.1677", "geocerca_metros": 250}
DENTRO = {"lat": "19.4272", "lon": "-99.1679"}      # a unos 30 m del origen
LEJOS = {"lat": "19.4540", "lon": "-99.1677"}       # a unos 3 km


def crear_servicio(cliente, headers, datos, jornadas, tipo="eventual",
                   consultor_id=None, pais_id=None, plaza_id=None):
    """Por omision en Mexico. `pais_id` y `plaza_id` sirven para las
    pruebas de zona horaria, que necesitan un servicio de otro pais."""
    cuerpo = {
        "cliente_id": datos["cliente_id"],
        "pais_id": pais_id or datos["mx"]["id"],
        "plaza_id": plaza_id or datos["cdmx"]["id"], "tipo": tipo,
        "solicitante_nombre": "Patricia", "solicitante_apellidos": "Lundgren",
        "solicitante_correo": "solicitante@cliente.com",
        "ejecutivo_nombre": "Ingrid", "ejecutivo_apellidos": "Halvorsen",
        "ejecutivo_correo": "ejecutivo@cliente.com",
        "equipos": [{"clave": "EQ-1", "jornadas": jornadas}],
    }
    if consultor_id:
        cuerpo["consultor_id"] = consultor_id
    r = cliente.post("/servicios", json=cuerpo, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def jornada(fecha: date, modalidad_id: int, hora="07:00:00", **extra):
    return {"fecha": str(fecha), "modalidad_id": modalidad_id,
            "hora_presentacion": hora, **extra}


# El rol con el que va la gente cuando la prueba no dice otra cosa. El
# personal de seguridad es general y el rol es de la tarea, asi que una
# asignacion sin rol no se puede cobrar ni pagar: aqui se pone uno para
# que las pruebas que no hablan de dinero no tengan que decirlo.
def rol_por_omision(cliente, headers, codigo="conductor_seguridad"):
    roles = cliente.get("/catalogos/perfiles", headers=headers).json()
    suyo = next((r for r in roles if r["codigo"] == codigo), None)
    return suyo["id"] if suyo else None


def asignar(cliente, headers, jornada_id, persona_id=None, vehiculo_id=None,
            forzar=True, rol_id=None, rol="conductor_seguridad"):
    respuestas = []
    if persona_id:
        if rol_id is None and rol:
            rol_id = rol_por_omision(cliente, headers, rol)
        respuestas.append(cliente.post(
            f"/servicios/jornadas/{jornada_id}/asignar-personal",
            json={"persona_id": persona_id, "rol_id": rol_id,
                  "forzar": forzar}, headers=headers))
    if vehiculo_id:
        respuestas.append(cliente.post(
            f"/servicios/jornadas/{jornada_id}/asignar-vehiculo",
            json={"vehiculo_id": vehiculo_id, "forzar": forzar}, headers=headers))
    return respuestas


def configurar_origen(cliente, headers, jornada_id):
    return cliente.patch(f"/operacion/jornadas/{jornada_id}/origen",
                         json=ORIGEN, headers=headers)


def marcar(cliente, headers, jornada_id, tipo, cuando=None, ubicacion=None):
    cuerpo = {"tipo": tipo, **(ubicacion or DENTRO)}
    if cuando:
        cuerpo["marcado_en"] = cuando.isoformat()
    return cliente.post(f"/operacion/jornadas/{jornada_id}/hitos",
                        json=cuerpo, headers=headers)


def ejecutar_jornada(cliente, headers_personal, jornada_dict, retraso_minutos=0,
                     horas_extra=0):
    """Marca la secuencia completa: llegada, contacto y fin."""
    inicio = datetime.fromisoformat(jornada_dict["inicio_programado"])
    fin = datetime.fromisoformat(jornada_dict["fin_programado"])
    retraso = timedelta(minutes=retraso_minutos)
    marcar(cliente, headers_personal, jornada_dict["id"], "llegada_origen",
           inicio - timedelta(minutes=10) + retraso)
    marcar(cliente, headers_personal, jornada_dict["id"], "contacto_ejecutivo",
           inicio + retraso)
    marcar(cliente, headers_personal, jornada_dict["id"], "fin_servicio",
           fin + timedelta(hours=horas_extra))


def cotizar_y_autorizar(cliente, headers, servicio, perfil_id, categoria_id,
                        roles_por_dia=None):
    """Cotiza el servicio completo y lo autoriza.

    `roles_por_dia` permite cotizar un rol distinto cada dia, que es lo
    que pasa cuando la misma persona conduce un dia y coordina el otro.
    Sin eso, el cierre detecta —con razon— que se ejecuto un recurso que
    no estaba cotizado.
    """
    lineas = []
    for idx, j in enumerate(servicio["equipos"][0]["jornadas"]):
        suyo = (roles_por_dia[idx] if roles_por_dia and idx < len(roles_por_dia)
                else perfil_id)
        lineas.append({"fecha": j["fecha"], "tipo": "recurso", "perfil_id": suyo})
        lineas.append({"fecha": j["fecha"], "tipo": "vehiculo",
                       "categoria_id": categoria_id})
    r = cliente.post("/cotizaciones",
                     json={"servicio_id": servicio["id"], "lineas": lineas},
                     headers=headers)
    assert r.status_code == 201, r.text
    cotizacion = r.json()
    cliente.post(f"/cotizaciones/{cotizacion['cotizacion_id']}/autorizar",
                 json={"autorizada_por": "Cliente de prueba"}, headers=headers)
    return cotizacion


def manana(dias=1):
    return date.today() + timedelta(days=dias)
