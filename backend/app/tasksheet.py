"""Task sheet: la ficha del servicio.

Debe ser digerible, precisa y lo mas comprimida posible. La ve el equipo
de seguridad en su app y se comparte con el solicitante y el ejecutivo
una vez cerrada la planeacion. Si hay modificaciones, se les manda la
version mas reciente.
"""
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import correo_html
from app import models as m
from app import senal as senal_motor
from app import textos_aviso as ta
from app.experiencia import horas_acumuladas
from app.operacion import distancia_metros
from app.presentacion import llegada_del_equipo
from app.telefonos import poner_lada

HOSPITALES_A_MOSTRAR = 3

# Que tan lejos puede llegar un hospital. Un primer nivel estabiliza y
# refiere; un tercer nivel opera. En una emergencia real esa diferencia
# pesa mas que un par de kilometros, y por eso la lista siempre lleva uno.
NIVELES = {m.NivelHospital.PRIMERO: 1,
           m.NivelHospital.SEGUNDO: 2,
           m.NivelHospital.TERCERO: 3}
NIVEL_ALTO = 3


def _rango(nivel) -> int:
    return NIVELES.get(nivel, 0)


def hospitales_cercanos(db: Session, plaza_id: int | None, lat, lon,
                        cuantos: int = HOSPITALES_A_MOSTRAR) -> list[dict]:
    """Los mas cercanos al punto de referencia, dentro de su ciudad.

    Por ciudad y no por pais: un servicio en Monterrey no se atiende con
    un hospital de Ciudad de Mexico, y ofrecerlo a setecientos
    kilometros es peor que no ofrecer nada, porque parece una respuesta.
    Si la ciudad no tiene hospitales cargados, la lista sale vacia y la
    hoja lo dice; eso se ve y se corrige.

    De los que hay, los mas cercanos. Pero la lista nunca se queda sin un
    hospital de tercer nivel: si los tres de al lado son clinicas, el
    ultimo lugar se lo cede al tercer nivel mas cercano. Una clinica a
    ochocientos metros no sustituye a un quirofano.
    """
    if lat is None or lon is None or not plaza_id:
        return []

    catalogo = (db.query(m.Hospital)
                .filter_by(plaza_id=plaza_id, activo=True).all())
    con_distancia = []
    for h in catalogo:
        metros = distancia_metros(lat, lon, h.lat, h.lon)
        con_distancia.append({
            "nombre": h.nombre,
            "direccion": h.direccion,
            "telefono": h.telefono,
            "nivel": h.nivel_atencion.value if h.nivel_atencion else None,
            "km": round(metros / 1000, 1),
            "_rango": _rango(h.nivel_atencion),
        })
    con_distancia.sort(key=lambda x: x["km"])

    elegidos = con_distancia[:cuantos]
    if elegidos and not any(x["_rango"] >= NIVEL_ALTO for x in elegidos):
        alto = next((x for x in con_distancia if x["_rango"] >= NIVEL_ALTO),
                    None)
        if alto:
            elegidos = elegidos[:cuantos - 1] + [alto]
            elegidos.sort(key=lambda x: x["km"])

    for x in elegidos:
        x.pop("_rango", None)
    return elegidos


def hospedaje_de(db: Session, equipo: m.Equipo) -> list[dict]:
    """Donde se hospeda el ejecutivo principal de ESTE equipo.

    Uno por equipo. Sigue devolviendo una lista porque la hoja la
    imprime como bloque y porque los servicios viejos traen sus estancias
    colgadas del servicio, sin equipo; esas se siguen viendo hasta que
    alguien las vuelva a capturar."""
    estancias = (db.query(m.Hospedaje)
                 .filter(m.Hospedaje.equipo_id == equipo.id)
                 .all())
    if not estancias:
        estancias = (db.query(m.Hospedaje)
                     .filter(m.Hospedaje.servicio_id == equipo.servicio_id,
                             m.Hospedaje.equipo_id.is_(None))
                     .order_by(m.Hospedaje.desde.nulls_first(),
                               m.Hospedaje.id).all())
    return [{
        "hotel": h.nombre,
        "direccion": h.direccion,
        "telefono": h.telefono,
        # El pin del hotel: de ahi salen los hospitales cercanos. Es
        # donde el ejecutivo pasa la noche, que es cuando una emergencia
        # encuentra al equipo mas lejos de todo.
        #
        # Como float y no como Decimal: la hoja publicada se guarda en
        # JSON y el Decimal no se puede serializar. Aqui la precision de
        # un flotante sobra —son metros sobre kilometros—.
        "lat": float(h.hotel.lat) if h.hotel and h.hotel.lat is not None else None,
        "lon": float(h.hotel.lon) if h.hotel and h.hotel.lon is not None else None,
        # Solo salen cuando alguien las capturo: en un servicio de tres
        # dias con un solo hotel no dicen nada que no este ya en la hoja.
        "desde": h.desde.isoformat() if h.desde else None,
        "hasta": h.hasta.isoformat() if h.hasta else None,
        "notas": h.notas,
    } for h in estancias]


def _equipo_de(db: Session, jornada: m.Jornada) -> list[dict]:
    return [{
        "nombre": a.persona.nombre,
        "puesto": a.rol.nombre if a.rol else None,
        "telefono": a.persona.telefono,
        "foto": a.persona.foto_url,
        "horas_en_centauro": horas_acumuladas(db, a.persona_id),
        # En que unidad va. La hoja solo lo imprime cuando el dia lleva
        # mas de una: con una sola, todos van en ella.
        "abordo": a.vehiculo.placa if a.vehiculo else None,
    } for a in jornada.personal]


def _unidades_de(jornada: m.Jornada) -> list[dict]:
    return [{
        "unidad": a.vehiculo.categoria.nombre,
        "placas": a.vehiculo.placa,
        # En un auto de renta la categoria no basta: el que lo espera en
        # el estacionamiento busca una Suburban negra, no una "SUV".
        "marca_modelo": a.vehiculo.marca_modelo,
        "color": a.vehiculo.color,
        "anio": a.vehiculo.modelo_anio,
        "blindada": a.vehiculo.categoria.blindado,
        "foto": a.vehiculo.foto_url,
    } for a in jornada.vehiculos]


def _vuelo_de(jornada: m.Jornada) -> dict | None:
    """El vuelo del ejecutivo ese dia, si se capturo.

    Se va llenando por partes: a veces el consultor sabe la aerolinea y el
    numero mucho antes que la hora. Se muestra lo que haya.
    """
    if not (jornada.vuelo_aerolinea or jornada.vuelo_numero
            or jornada.vuelo_hora):
        return None
    return {
        "aerolinea": jornada.vuelo_aerolinea,
        "numero": jornada.vuelo_numero,
        "hora": jornada.vuelo_hora.strftime("%H:%M") if jornada.vuelo_hora else None,
        "fecha_iso": (jornada.vuelo_hora.date().isoformat()
                      if jornada.vuelo_hora else None),
        "procedencia": jornada.vuelo_origen,
        "tipo": jornada.vuelo_tipo,
    }


def _resolver_tipo_de_vuelo(dias: list[dict]) -> None:
    """Un servicio trae a lo mas dos vuelos: la llegada y la salida.

    Si el consultor no lo dijo, el primer dia es llegada y el ultimo es
    salida. En un servicio de un solo dia los dos casos caben (un transfer
    de aeropuerto a hotel o de hotel a aeropuerto), asi que ahi no se
    adivina: se queda en llegada salvo que el consultor diga otra cosa.
    """
    ultimo = len(dias) - 1
    for i, d in enumerate(dias):
        vuelo = d.get("vuelo")
        if not vuelo:
            continue
        if vuelo.get("tipo") not in ("llegada", "salida"):
            vuelo["tipo"] = "salida" if (i == ultimo and i != 0) else "llegada"


def _calcular_llegada_del_equipo(dias: list[dict], equipo: m.Equipo,
                                 pais: m.Pais | None) -> None:
    """El equipo llega antes: 45 min antes del vuelo si es aeropuerto,
    30 min antes de la presentacion en cualquier otro lugar."""
    aeropuerto = getattr(pais, "anticipacion_aeropuerto_min", 45) or 45
    normal = getattr(pais, "anticipacion_min", 30) or 30
    jornadas = {j.fecha.isoformat(): j for j in equipo.jornadas}

    for d in dias:
        j = jornadas.get(d["fecha_iso"])
        if not j:
            continue
        vuelo = d.get("vuelo") or {}
        hora, minutos, contra_vuelo = llegada_del_equipo(
            j.inicio_programado, j.vuelo_hora, vuelo.get("tipo"),
            aeropuerto, normal)
        d["llegada_equipo"] = {"hora": hora.strftime("%H:%M"),
                               "minutos": minutos,
                               "contra_vuelo": contra_vuelo}


def _escalacion(db: Session, servicio: m.Servicio) -> list[dict]:
    """A quien llama el ejecutivo ante cualquier anomalia."""
    niveles = []

    consultor = (db.get(m.Persona, servicio.consultor_id)
                 if servicio.consultor_id else None)
    if consultor:
        niveles.append({"nivel": 1, "cargo": "Consultor asignado",
                        "nombre": consultor.nombre,
                        "telefono": consultor.telefono,
                        "correo": consultor.correo})

    director = (db.query(m.Persona)
                .join(m.Usuario, m.Usuario.persona_id == m.Persona.id)
                .filter(m.Usuario.rol == m.Rol.DIRECTOR_OPERACIONES,
                        m.Usuario.activo.is_(True))
                .first())
    if director:
        niveles.append({"nivel": 2, "cargo": "Director de operaciones",
                        "nombre": director.nombre,
                        "telefono": director.telefono,
                        "correo": director.correo})

    return niveles


def armar(db: Session, equipo_id: int) -> dict:
    """Arma el task sheet de UN equipo. Cada equipo lleva el suyo."""
    equipo = db.get(m.Equipo, equipo_id)
    if not equipo:
        raise HTTPException(404, f"No existe el equipo {equipo_id}")
    servicio = equipo.servicio

    dias = []
    faltantes = []

    if True:
        vivos = [x for x in sorted(equipo.jornadas, key=lambda x: x.fecha)
                 if x.estatus != m.EstatusJornada.CANCELADA]
        # El primer dia del equipo: el unico que tiene que traer su punto
        # de origen si o si.
        primero = vivos[0].id if vivos else None

        for j in vivos:

            agenda = db.query(m.AgendaJornada).filter_by(jornada_id=j.id).first()
            # Las paradas del dia, en orden de reloj; las que aun no
            # tienen hora se imprimen al final, como pendientes.
            paradas = [
                {"hora": p.hora.strftime("%H:%M") if p.hora else None,
                 "lugar": p.lugar, "direccion": p.direccion, "notas": p.notas}
                for p in sorted(
                    db.query(m.ParadaAgenda).filter_by(jornada_id=j.id).all(),
                    key=lambda x: (x.hora is None, x.hora, x.id))]
            equipo_asignado = _equipo_de(db, j)
            unidades = _unidades_de(j)

            # Obligatorio: el equipo y la unidad todos los dias, y el
            # punto de origen solo el primero.
            #
            # La agenda NO, y el punto de los demas dias tampoco: hay
            # clientes que no comparten la agenda, y el conductor le
            # pregunta al ejecutivo un dia antes a que hora y donde lo
            # recoge. Exigirlo dejaba la hoja sin publicar por algo que
            # nadie sabe todavia y que se resuelve en la calle.
            #
            # El primer dia es distinto: ahi nadie le puede preguntar
            # nada al ejecutivo, porque todavia no lo conocen. Si no
            # dice donde presentarse, no hay servicio.
            if not equipo_asignado:
                faltantes.append(f"{j.fecha}: sin personal asignado")
            if not unidades:
                faltantes.append(f"{j.fecha}: sin unidad asignada")
            if j.id == primero and not j.origen_direccion:
                faltantes.append(f"{j.fecha}: falta la direccion del punto "
                                 "de origen del primer dia")
            # Sin pin no hay geocerca que el conductor pueda pisar ni
            # hospitales cercanos que calcular. Solo se pide donde ya se
            # dijo a donde ir: escribir la direccion no fija el punto.
            elif j.origen_direccion and j.origen_lat is None:
                faltantes.append(f"{j.fecha}: falta fijar el pin de "
                                 f"'{j.origen_direccion}' en el mapa "
                                 "(sin el no hay geocerca ni hospitales)")

            dias.append({
                "fecha_iso": j.fecha.isoformat(),
                "dia_semana_num": j.fecha.weekday(),
                "fecha": j.fecha.strftime("%d/%m/%Y"),
                "equipo": equipo.alias,
                "modalidad": j.modalidad.codigo.value,
                "presentacion": j.inicio_programado.strftime("%H:%M"),
                "cierre_estimado": j.fin_programado.strftime("%H:%M"),
                "origen": j.origen_direccion,
                # Cuando el dia todavia no dice donde arranca, se dice
                # que no se sabe. El silencio se lee como "es el mismo de
                # siempre" y el equipo se presenta donde no era. El
                # primer dia no entra: ese si trae su punto obligado y ya
                # sale arriba, en el meet and greet.
                "origen_por_confirmar": not j.origen_direccion and j.id != primero,
                "origen_lat": str(j.origen_lat) if j.origen_lat is not None else None,
                "origen_lon": str(j.origen_lon) if j.origen_lon is not None else None,
                "personal": equipo_asignado,
                "unidades": unidades,
                "agenda": ({"resumen": agenda.resumen if agenda else None,
                            "puntos": agenda.puntos if agenda else None,
                            "paradas": paradas,
                            "archivo": agenda.archivo_url if agenda else None}
                           if (agenda or paradas) else None),
                "agenda_abierta": agenda is None and not paradas,
                # La ciudad del equipo, no la del servicio: en un
                # proyecto que va de Mexico a Monterrey, el de Beta se
                # atiende en Monterrey.
                "hospitales_cercanos": hospitales_cercanos(
                    db, equipo.ciudad_id, j.origen_lat, j.origen_lon),
                "vuelo": _vuelo_de(j),
                "llegada_equipo": None,     # se calcula al resolver el vuelo
            })

    pais = db.get(m.Pais, servicio.pais_id)
    _resolver_tipo_de_vuelo(dias)
    _calcular_llegada_del_equipo(dias, equipo, pais)

    hospedaje = hospedaje_de(db, equipo)

    # El equipo base del servicio se muestra una sola vez arriba.
    # Cada dia solo dice lo que cambia respecto a ese base; si es igual,
    # no dice nada.
    def _huella(dia):
        return (
            tuple(sorted(p["nombre"] for p in dia["personal"])),
            tuple(sorted(u["placas"] for u in dia["unidades"])),
            dia["origen"],
        )

    constantes = None
    if dias:
        conteo = {}
        for d in dias:
            conteo[_huella(d)] = conteo.get(_huella(d), 0) + 1
        # El base es el arreglo mas repetido; en empate, el del primer dia.
        base = max(conteo, key=lambda h: (conteo[h], -[_huella(d) for d in dias].index(h)))
        dia_base = next(d for d in dias if _huella(d) == base)

        # Desglose por modalidad de todo lo que cubre este equipo:
        # no es lo mismo "5 dias" que "3 full days y 2 transfers".
        # Cuenta todos los dias del equipo, aunque alguno tenga otro
        # punto de encuentro o un refuerzo: la diferencia se marca en
        # el dia, pero el equipo si cubre ese dia.
        por_modalidad = {}
        for d in dias:
            por_modalidad[d["modalidad"]] = por_modalidad.get(d["modalidad"], 0) + 1

        # La referencia medica se mide desde el hotel: ahi duerme el
        # ejecutivo, y una emergencia de madrugada encuentra al equipo
        # justo ahi. Sin hotel se mide desde el punto de encuentro, que
        # es lo unico que siempre existe.
        #
        # Lo que no sirve es medirla desde el dia que mas se repite:
        # ahora que los dias de en medio pueden ir sin punto —el
        # conductor lo pregunta un dia antes— ese dia suele ser uno sin
        # coordenadas, y de ahi no hay nada que medir.
        hotel = next((x for x in hospedaje
                      if x["lat"] is not None and x["lon"] is not None), None)
        con_pin = next((d for d in dias if d["origen_lat"] is not None), None)

        if hotel:
            cerca = hospitales_cercanos(db, equipo.ciudad_id,
                                        hotel["lat"], hotel["lon"])
            medidos_desde = "hotel"
        elif con_pin:
            cerca = con_pin["hospitales_cercanos"]
            medidos_desde = "encuentro"
        else:
            cerca, medidos_desde = [], None

        constantes = {
            "personal": dia_base["personal"],
            "unidades": dia_base["unidades"],
            # Si el dia mas repetido no dice donde arranca, la cabeza de
            # la hoja no se queda en blanco.
            "origen": dia_base["origen"] or dias[0]["origen"],
            "hospitales_cercanos": cerca,
            # Para que la hoja diga desde donde se midieron: "a 2 km" no
            # significa lo mismo si es del hotel o del aeropuerto.
            "hospitales_desde": medidos_desde,
            "dias_con_este_equipo": len(dias),
            "dias_por_modalidad": por_modalidad,
            # El meet and greet es donde arranca el servicio: el primer
            # dia. No es el punto que mas se repite, que suele ser el
            # hotel de los dias siguientes.
            "encuentro": {
                "lugar": dias[0]["origen"],
                "lat": dias[0]["origen_lat"],
                "lon": dias[0]["origen_lon"],
                "fecha_iso": dias[0]["fecha_iso"],
                "hora": dias[0]["presentacion"],
                "vuelo": dias[0]["vuelo"],
                "llegada_equipo": dias[0]["llegada_equipo"],
            },
        }

        nombres_base = {p["nombre"] for p in dia_base["personal"]}
        placas_base = {u["placas"] for u in dia_base["unidades"]}

        for d in dias:
            igual = _huella(d) == base
            d["igual_todo_el_servicio"] = igual
            if igual:
                d["cambios"] = None
                continue

            nombres = {p["nombre"] for p in d["personal"]}
            placas = {u["placas"] for u in d["unidades"]}
            d["cambios"] = {
                "personal_se_suma": [p for p in d["personal"]
                                     if p["nombre"] not in nombres_base],
                "personal_no_va": sorted(nombres_base - nombres),
                "unidad_se_suma": [u for u in d["unidades"]
                                   if u["placas"] not in placas_base],
                "unidad_no_va": sorted(placas_base - placas),
                # El primer dia no lo repite: su punto ya va arriba,
                # en el bloque de meet and greet.
                "otro_origen": (d["origen"]
                                if d["origen"] != dia_base["origen"]
                                and d is not dias[0] else None),
            }

    contenido = {
        "servicio": servicio.folio,
        "equipo": equipo.alias,
        "equipos_del_servicio": len(servicio.equipos),
        "tipo": servicio.tipo.value,
        "hospedaje": hospedaje,
        "cliente": servicio.cliente.nombre,
        # La hoja es de un equipo: sale a nombre de SU ejecutivo
        # principal, que con un solo equipo es el del servicio.
        "ejecutivo": equipo.ejecutivo_completo,
        "ejecutivo_telefono": equipo.ejecutivo_telefono_efectivo,
        "solicitante": servicio.solicitante_completo,
        "solicitante_telefono": servicio.solicitante_telefono,
        # Como se presenta el equipo. Solo el eventual la lleva: el
        # implantado la acuerda una vez y no servicio por servicio.
        "vestimenta": (servicio.vestimenta
                       if servicio.tipo == m.TipoServicio.EVENTUAL else None),
        "senal": ({"texto": servicio.senal_texto,
                   "imagen": servicio.senal_imagen,
                   "nota": servicio.senal_nota,
                   "color": senal_motor.color(servicio.senal_color)}
                  if (servicio.senal_texto or servicio.senal_imagen
                      or servicio.senal_color) else None),
        # La paleta viaja con la vista para que la consola la dibuje sin
        # otra consulta y sin una copia propia de los colores.
        "senal_colores": senal_motor.paleta(),
        # La ciudad donde opera ESTE equipo: en un proyecto que va de
        # Mexico a Monterrey, cada hoja dice su ciudad.
        "plaza": db.get(m.Plaza, equipo.ciudad_id).nombre,
        "constantes": constantes,
        "dias": dias,
        "escalacion": _escalacion(db, servicio),
        "faltantes": faltantes,
        "listo_para_publicar": not faltantes,
        "generado_en": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    # Ningun telefono sale sin lada: el ejecutivo marca desde el extranjero.
    return poner_lada(contenido, pais.lada if pais else None)


def _ficha_del_ts(contenido: dict, equipo: m.Equipo, version: int,
                  motivo: str | None, idioma: str | None = None) -> list:
    """La ficha del correo del task sheet.

    Lo que el cliente necesita leer cuando cambia no es que hay version
    nueva: es QUE cambio. Por eso el motivo sube a la ficha en vez de
    quedarse al final del parrafo.

    Y el primer dia con su hora y su punto, que es lo que va a buscar
    el que lo abre --si el correo ya lo dice, no tiene que abrir el
    adjunto para saber a que hora bajar.
    """
    pares = [(ta.t(idioma, "version"), str(version))]
    if motivo:
        # El motivo lo escribio una persona: va como lo escribio.
        pares.append((ta.t(idioma, "que_cambio"), motivo))
    if contenido.get("equipos_del_servicio", 1) > 1:
        pares.append((ta.t(idioma, "equipo"), equipo.alias))
    dias = contenido.get("dias") or []
    if dias:
        primero = dias[0]
        pares.append((ta.t(idioma, "primer_dia"),
                      f"{primero.get('fecha')} · {primero.get('presentacion')}"))
        if primero.get("origen"):
            pares.append((ta.t(idioma, "punto"), primero["origen"]))
    for persona in (dias[0].get("personal") if dias else []) or []:
        puesto = ta.puesto_en(idioma, persona.get("puesto"))
        pares.append((ta.t(idioma, "equipo"),
                      f"{persona.get('nombre')}"
                      + (f" · {puesto}" if puesto else ""),
                      persona.get("telefono")))
    return pares


def publicar(db: Session, equipo_id: int, publicado_por_id: int,
             motivo: str | None = None, forzar: bool = False,
             avisar: bool = False) -> m.TaskSheet:
    """Congela una version del task sheet de ese equipo.

    **Publicar no avisa.** Decision de Salvador (20 sep): el task sheet
    se corrige varias veces mientras se arma --se mueve la hora, entra
    otra unidad, se cambia una nota-- y un correo por cada version le
    ensena al cliente a no abrir ninguno. Cuando el cuarto dice "task
    sheet v4" ya nadie lo mira, y el que importaba era ese.

    `avisar` lo prende quien publica, con la casilla de la pantalla,
    cuando el cambio de verdad le sirve al cliente: otra hora de
    presentacion, otro punto, otra persona. Quien sabe si el cambio
    importa es el consultor, no el sistema.
    """
    contenido = armar(db, equipo_id)
    equipo = db.get(m.Equipo, equipo_id)
    servicio_id = equipo.servicio_id

    if contenido["faltantes"] and not forzar:
        raise HTTPException(409, {
            "mensaje": "El task sheet esta incompleto",
            "faltantes": contenido["faltantes"],
        })

    anteriores = (db.query(m.TaskSheet)
                  .filter_by(equipo_id=equipo_id)
                  .order_by(m.TaskSheet.version.desc()).all())
    version = (anteriores[0].version + 1) if anteriores else 1

    ficha = m.TaskSheet(
        servicio_id=servicio_id, equipo_id=equipo_id, version=version,
        estatus=m.EstatusTaskSheet.PUBLICADO,
        contenido=json.dumps(contenido, ensure_ascii=False),
        motivo_cambio=motivo, publicado_por_id=publicado_por_id,
        publicado_en=datetime.now())
    db.add(ficha)
    db.flush()

    servicio = equipo.servicio
    varios = contenido["equipos_del_servicio"] > 1

    for destinatario in ((m.Destinatario.SOLICITANTE, m.Destinatario.EJECUTIVO)
                         if avisar else ()):
        # Cada uno en su idioma: el principal suele leer ingles y quien
        # pidio el servicio, el del pais.
        lengua = ta.idioma_de(db, servicio, destinatario)
        correo = (servicio.solicitante_correo
                  if destinatario == m.Destinatario.SOLICITANTE
                  else equipo.ejecutivo_correo_efectivo)
        cual = (ta.t(lengua, "ts_del_equipo", alias=equipo.alias) if varios
                else ta.t(lengua, "ts_del_servicio"))
        db.add(m.Notificacion(
            servicio_id=servicio_id, destinatario=destinatario,
            canal=m.Canal.CORREO, correo=correo,
            idioma=lengua,
            asunto=ta.t(lengua,
                        "ts_asunto_equipo" if varios else "ts_asunto",
                        folio=servicio.folio, equipo=equipo.alias,
                        version=version),
            cuerpo=(ta.t(lengua, "ts_cuerpo_primero", cual=cual)
                    if version == 1
                    else ta.t(lengua, "ts_cuerpo_nuevo", cual=cual,
                              version=version)),
            datos=correo_html.guardar_datos(_ficha_del_ts(
                contenido, equipo, version, motivo, lengua))))

    db.commit()
    db.refresh(ficha)
    return ficha


def vigente(db: Session, equipo_id: int) -> m.TaskSheet | None:
    return (db.query(m.TaskSheet)
            .filter_by(equipo_id=equipo_id,
                       estatus=m.EstatusTaskSheet.PUBLICADO)
            .order_by(m.TaskSheet.version.desc())
            .first())


def equipos_de(db: Session, servicio_id: int) -> list[m.Equipo]:
    servicio = db.get(m.Servicio, servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {servicio_id}")
    return servicio.equipos
