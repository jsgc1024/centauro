"""Tablero de profesionalismo del personal de seguridad.

Junta en un solo lugar lo que ya vive disperso: estrellas del mes,
satisfaccion del ejecutivo, historial de incidencias, capacitacion y
horas acumuladas. De ahi sale una calificacion de 0 a 100 que sirve para
ordenar al personal y para que el sistema recomiende a quien conviene
mandar.

Dos cuidados que valen mas que la formula:

Una dimension sin datos NO cuenta como cero. A quien lleva dos semanas
en la empresa nadie lo ha calificado todavia, y castigarlo por eso seria
injusto ademas de falso: su peso se reparte entre las dimensiones que si
tienen con que medirse, igual que las estrellas del bono.

Solo pesan las incidencias YA AUTORIZADAS por el director de
operaciones. Una incidencia capturada y sin visto bueno todavia no es un
hecho, y no puede bajarle la calificacion a nadie.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from app import models as m
from app.experiencia import horas_por_persona

CERO = Decimal("0")
CIEN = Decimal("100")

# El manejo entra con 10 %, que sale de estrellas (30 -> 25) e
# incidencias (25 -> 20): decision de Salvador, 23 sep (seccion 60).
# Siguen siendo de ejemplo.
PESOS_POR_DEFECTO = {
    m.DimensionProfesionalismo.ESTRELLAS: Decimal("25"),
    m.DimensionProfesionalismo.SATISFACCION: Decimal("25"),
    m.DimensionProfesionalismo.INCIDENCIAS: Decimal("20"),
    m.DimensionProfesionalismo.CAPACITACION: Decimal("10"),
    m.DimensionProfesionalismo.EXPERIENCIA: Decimal("10"),
    m.DimensionProfesionalismo.MANEJO: Decimal("10"),
}


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _desde(meses: int | None, hoy: date | None = None) -> tuple[int, int]:
    """(anio, mes) del inicio de la ventana."""
    hoy = hoy or date.today()
    meses = meses or POR_DEFECTO["meses_ventana"]
    total = hoy.year * 12 + (hoy.month - 1) - (meses - 1)
    return total // 12, total % 12 + 1


POR_DEFECTO = {
    "meses_ventana": 6,
    "horas_referencia": 2000,
    "castigo_error_menor": Decimal("0"),
    "castigo_leve": Decimal("25"),
    "castigo_grave": Decimal("60"),
    "puntos_por_evento_manejo": Decimal("3"),
}


class _Parametros:
    """Los parametros con valores reales, vengan de la base o no.

    Ojo con el objeto de SQLAlchemy a secas: sus valores por omision se
    aplican al guardar, no al construirlo, asi que un objeto sin guardar
    trae todo en nulo. Eso hacia que los castigos por incidencia valieran
    cero sin que nadie se enterara.
    """

    def __init__(self, fila=None):
        for campo, valor in POR_DEFECTO.items():
            de_la_base = getattr(fila, campo, None) if fila else None
            setattr(self, campo, de_la_base if de_la_base is not None else valor)


def parametros(db: Session, pais_id: int) -> _Parametros:
    """El tablero se puede ver antes de configurarlo: si no hay catalogo,
    se usan los valores por defecto sin guardarlos."""
    fila = (db.query(m.ParametroProfesionalismo)
            .filter_by(pais_id=pais_id).first())
    return _Parametros(fila)


def pesos(db: Session, pais_id: int) -> dict:
    filas = (db.query(m.PesoProfesionalismo)
             .filter_by(pais_id=pais_id, activo=True).all())
    if not filas:
        return dict(PESOS_POR_DEFECTO)
    return {f.dimension: _d(f.peso) for f in filas}


# ---------------------------------------------------------------- dimensiones
#
# Cada dimension se calcula para VARIAS personas de un golpe (seccion
# 101): una consulta por dimension, no una por persona. "Asignar
# recursos" pedia la ficha de cada persona del pais por cada dia del
# equipo --930 consultas con 16 personas y tres dias en la base de
# pruebas-- y con 200 personas y el historial de un mes eran decenas de
# segundos por clic, creciendo cada mes. Las cifras son las mismas que
# antes: solo cambia cuantas veces se le pregunta a la base.

def _en_ventana(anio: int, mes: int, desde: tuple[int, int]) -> bool:
    return (anio, mes) >= desde


def _evaluaciones_de(db: Session, ids: list[int],
                     ventana: dict[int, tuple[int, int]]) -> dict[int, list]:
    """persona -> sus evaluaciones mensuales dentro de su ventana."""
    piso = min(ventana.values())
    filas = (db.query(m.EvaluacionMensual)
             .filter(m.EvaluacionMensual.persona_id.in_(ids),
                     or_(m.EvaluacionMensual.anio > piso[0],
                         and_(m.EvaluacionMensual.anio == piso[0],
                              m.EvaluacionMensual.mes >= piso[1])))
             .all())
    salida: dict[int, list] = {}
    for e in filas:
        if _en_ventana(e.anio, e.mes, ventana[e.persona_id]):
            salida.setdefault(e.persona_id, []).append(e)
    return salida


def _criterios_de(db: Session, evaluaciones: dict[int, list]) -> dict:
    """evaluacion -> (criterios que le aplicaron, cumplidos)."""
    ids = [e.id for lista in evaluaciones.values() for e in lista]
    if not ids:
        return {}
    RC = m.ResultadoCriterio
    filas = (db.query(RC.evaluacion_id, func.count(RC.id),
                      func.coalesce(func.sum(case((RC.cumplido.is_(True), 1),
                                                  else_=0)), 0))
             .filter(RC.evaluacion_id.in_(ids), RC.aplica.is_(True))
             .group_by(RC.evaluacion_id).all())
    return {evaluacion_id: (int(aplicables), int(obtenidas))
            for evaluacion_id, aplicables, obtenidas in filas}


def _frase(clave: str, **datos) -> dict:
    """La frase que explica una dimension, en piezas: la consola la arma
    en el idioma de quien mira (seccion 101). Antes viajaba solo en
    espanol y salia asi en la consola en ingles o portugues."""
    return {"clave": clave, "datos": datos}


def _estrellas(evaluaciones: list, criterios: dict) -> dict:
    if not evaluaciones:
        return {"aplica": False, "detalle": "Sin evaluaciones en la ventana",
                "frase": _frase("sin_evaluaciones")}

    obtenidas = aplicables = 0
    for e in evaluaciones:
        cuantos, cumplidos = criterios.get(e.id, (0, 0))
        aplicables += cuantos
        obtenidas += cumplidos

    if not aplicables:
        return {"aplica": False, "detalle": "Ningun criterio le aplico",
                "frase": _frase("sin_criterios")}
    valor = _d(obtenidas) / _d(aplicables) * CIEN
    return {"aplica": True, "valor": valor,
            "detalle": f"{obtenidas} de {aplicables} estrellas posibles en "
                       f"{len(evaluaciones)} meses",
            "frase": _frase("estrellas", n=obtenidas, t=aplicables,
                            m=len(evaluaciones))}


def _satisfaccion_de(db: Session, ids: list[int]) -> dict[int, tuple]:
    """persona -> (servicios atendidos, calificaciones, suma).

    Las calificaciones del ejecutivo de los servicios en que ha ido, de
    siempre --como estaba--, sumadas en la base en vez de cargar cada
    asignacion con su jornada y su equipo.
    """
    pares = (db.query(m.AsignacionPersonal.persona_id.label("persona_id"),
                      m.Equipo.servicio_id.label("servicio_id"))
             .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
             .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
             .filter(m.AsignacionPersonal.persona_id.in_(ids))
             .distinct().subquery())
    filas = (db.query(pares.c.persona_id,
                      func.count(pares.c.servicio_id.distinct()),
                      func.count(m.Encuesta.id),
                      func.coalesce(func.sum(m.Encuesta.calificacion), 0))
             .outerjoin(m.Encuesta, and_(
                 m.Encuesta.servicio_id == pares.c.servicio_id,
                 m.Encuesta.tipo == m.TipoEncuesta.EJECUTIVO,
                 m.Encuesta.calificacion.isnot(None)))
             .group_by(pares.c.persona_id).all())
    return {persona_id: (int(servicios), int(notas), int(suma))
            for persona_id, servicios, notas, suma in filas}


def _satisfaccion(cuenta: tuple | None) -> dict:
    servicios, notas, suma = cuenta or (0, 0, 0)
    if not servicios:
        return {"aplica": False, "detalle": "Sin servicios atendidos",
                "frase": _frase("sin_servicios")}
    if not notas:
        return {"aplica": False, "detalle": "Ningun ejecutivo lo ha calificado",
                "frase": _frase("sin_calificacion")}

    promedio = _d(suma) / _d(notas)
    # Del 1 al 5 a una escala de 0 a 100: un 1 es cero, un 5 es cien.
    valor = (promedio - 1) / 4 * CIEN
    return {"aplica": True, "valor": valor,
            "promedio_1_a_5": round(float(promedio), 2),
            "detalle": f"{notas} calificaciones, promedio "
                       f"{round(float(promedio), 2)} de 5",
            "frase": _frase("calificaciones", n=notas,
                            p=round(float(promedio), 2))}


def _incidencias_de(db: Session, ids: list[int],
                    ventana: dict[int, tuple[int, int]]) -> dict[int, list]:
    """persona -> sus incidencias autorizadas dentro de su ventana."""
    piso = min(ventana.values())
    filas = (db.query(m.Incidencia)
             .filter(m.Incidencia.persona_id.in_(ids),
                     m.Incidencia.autorizada.is_(True),
                     m.Incidencia.fecha >= date(piso[0], piso[1], 1))
             .all())
    salida: dict[int, list] = {}
    for i in filas:
        if _en_ventana(i.fecha.year, i.fecha.month, ventana[i.persona_id]):
            salida.setdefault(i.persona_id, []).append(i)
    return salida


def _incidencias(filas: list, p: "_Parametros") -> dict:
    """Arranca en 100 y baja con cada incidencia ya autorizada."""
    castigo = {
        m.GravedadIncidencia.ERROR_MENOR: _d(p.castigo_error_menor),
        m.GravedadIncidencia.LEVE: _d(p.castigo_leve),
        m.GravedadIncidencia.GRAVE: _d(p.castigo_grave),
    }
    total = sum((castigo.get(i.gravedad, CERO) for i in filas), CERO)
    valor = max(CERO, CIEN - total)
    if not filas:
        detalle = "Sin incidencias autorizadas en la ventana"
        frase = _frase("sin_incidencias")
    else:
        por_gravedad = {}
        for i in filas:
            por_gravedad[i.gravedad.value] = por_gravedad.get(i.gravedad.value, 0) + 1
        detalle = ", ".join(f"{n} {g}" for g, n in sorted(por_gravedad.items()))
        frase = _frase("incidencias", por_gravedad=[
            {"n": n, "g": g} for g, n in sorted(por_gravedad.items())])
    # Esta dimension siempre aplica: no tener incidencias es informacion,
    # no ausencia de informacion.
    return {"aplica": True, "valor": valor, "detalle": detalle, "frase": frase,
            "incidencias": len(filas)}


def _capacitacion(evaluaciones: list) -> dict:
    if not evaluaciones:
        return {"aplica": False, "detalle": "Sin evaluaciones en la ventana",
                "frase": _frase("sin_evaluaciones")}
    cumplidos = len([e for e in evaluaciones if e.capacitacion_cumplida])
    valor = _d(cumplidos) / _d(len(evaluaciones)) * CIEN
    return {"aplica": True, "valor": valor,
            "detalle": f"{cumplidos} de {len(evaluaciones)} meses al corriente",
            "frase": _frase("capacitacion", n=cumplidos, t=len(evaluaciones))}


def _manejo_de(db: Session, ventana: dict[int, tuple[int, int]],
               puntos: dict[int, Decimal]) -> dict[int, dict]:
    """Los excesos y los arrancones o frenadas bruscas que conto el GPS,
    por cada mil km al volante en servicio (seccion 60). Solo los dias en
    que esa persona iba al volante: al escolta no le aplica, y su peso se
    reparte entre lo demas, como con cualquier dimension sin datos."""
    from app import gps
    return gps.manejo_de_varios(db, ventana, puntos)


def _experiencia(horas: int, p: "_Parametros") -> dict:
    referencia = p.horas_referencia or 2000
    valor = min(CIEN, _d(horas) / _d(referencia) * CIEN)
    return {"aplica": True, "valor": valor, "horas": horas,
            "detalle": f"{horas:,} h acumuladas en Centauro",
            "frase": _frase("experiencia", h=horas)}


# ---------------------------------------------------------------- ficha

def _usuarios_de(db: Session, ids: list[int]) -> dict[int, dict]:
    """Con que correo entra al sistema cada quien, o nada si no tiene
    cuenta.

    Va pegado a la ficha porque la pregunta se hace mirando esta
    pantalla --"y este, ya puede abrir la app?"--: sin esto hay que
    salir a Accesos y volver a buscar a la misma persona.

    La contrasena no se puede ensenar aqui ni en ningun lado: se guarda
    un hash, no la contrasena. Lo unico que se puede decir es si ya puso
    una; quien no, entra con el codigo que le dicta su consultor.
    """
    filas = (db.query(m.Usuario)
             .filter(m.Usuario.persona_id.in_(ids)).all())
    return {u.persona_id: {"correo": u.correo, "activo": u.activo,
                           "ya_puso_contrasena": u.hash_contrasena is not None}
            for u in filas}


def ficha(db: Session, persona_id: int, hoy: date | None = None) -> dict:
    """La ficha de una persona: la de `fichas`, de una."""
    return fichas(db, [persona_id], hoy).get(persona_id, {})


def fichas(db: Session, persona_ids, hoy: date | None = None) -> dict[int, dict]:
    """Las fichas de varias personas, por lote: persona -> ficha.

    Quien no existe no sale. Los parametros y los pesos se leen una vez
    por pais; cada dimension se trae con una sola consulta para todas.
    """
    ids = sorted({int(i) for i in persona_ids if i})
    if not ids:
        return {}
    personas = (db.query(m.Persona)
                .options(joinedload(m.Persona.plaza))
                .filter(m.Persona.id.in_(ids)).all())
    if not personas:
        return {}
    ids = [persona.id for persona in personas]

    por_pais: dict[int, tuple] = {}
    for persona in personas:
        pais_id = persona.plaza.pais_id
        if pais_id not in por_pais:
            p = parametros(db, pais_id)
            por_pais[pais_id] = (p, pesos(db, pais_id), _desde(p.meses_ventana, hoy))
    ventana = {persona.id: por_pais[persona.plaza.pais_id][2]
               for persona in personas}
    puntos = {persona.id: por_pais[persona.plaza.pais_id][0].puntos_por_evento_manejo
              for persona in personas}

    evaluaciones = _evaluaciones_de(db, ids, ventana)
    criterios = _criterios_de(db, evaluaciones)
    satisfaccion = _satisfaccion_de(db, ids)
    incidencias = _incidencias_de(db, ids, ventana)
    horas = horas_por_persona(db, ids)
    manejo = _manejo_de(db, ventana, puntos)
    usuarios = _usuarios_de(db, ids)

    D = m.DimensionProfesionalismo
    salida = {}
    for persona in personas:
        p, tabla_pesos, _ = por_pais[persona.plaza.pais_id]
        suyas = evaluaciones.get(persona.id, [])
        medidas = {
            D.ESTRELLAS: _estrellas(suyas, criterios),
            D.SATISFACCION: _satisfaccion(satisfaccion.get(persona.id)),
            D.INCIDENCIAS: _incidencias(incidencias.get(persona.id, []), p),
            D.CAPACITACION: _capacitacion(suyas),
            D.EXPERIENCIA: _experiencia(horas.get(persona.id, 0), p),
            D.MANEJO: manejo[persona.id],
        }
        salida[persona.id] = _armar(persona, p, tabla_pesos, medidas,
                                    usuarios.get(persona.id),
                                    horas.get(persona.id, 0))
    return salida


def _armar(persona: m.Persona, p: "_Parametros", tabla_pesos: dict,
           medidas: dict, usuario: dict | None, horas: int) -> dict:
    """La ficha a partir de sus seis medidas: la calificacion de 0 a 100
    con el peso de lo que no se puede medir repartido entre lo que si."""
    peso_util = sum((tabla_pesos.get(d, CERO) for d, v in medidas.items()
                     if v["aplica"]), CERO)

    dimensiones = []
    calificacion = CERO
    for dimension, medida in medidas.items():
        peso = tabla_pesos.get(dimension, CERO)
        fila = {"dimension": dimension.value, "peso_base": float(peso),
                "aplica": medida["aplica"], "detalle": medida["detalle"],
                # La misma frase, en piezas, para que la consola la diga
                # en su idioma (seccion 101): `detalle` es el espanol.
                "frase": medida.get("frase")}
        if medida["aplica"] and peso_util > 0:
            peso_real = peso / peso_util * CIEN
            aporte = medida["valor"] * peso_real / CIEN
            calificacion += aporte
            fila.update({"valor": round(float(medida["valor"]), 1),
                         "peso_aplicado": round(float(peso_real), 1),
                         "aporte": round(float(aporte), 1)})
        else:
            fila.update({"valor": None, "peso_aplicado": 0, "aporte": 0})
        if "promedio_1_a_5" in medida:
            fila["promedio_1_a_5"] = medida["promedio_1_a_5"]
        if "horas" in medida:
            fila["horas"] = medida["horas"]
        dimensiones.append(fila)

    sin_medir = [f["dimension"] for f in dimensiones if not f["aplica"]]
    return {
        "persona_id": persona.id,
        "persona": persona.nombre,
        "usuario": usuario,
        # Sin puesto: el rol es de la tarea, no de la persona.
        "plaza": persona.plaza.nombre,
        "es_freelance": persona.es_freelance,
        # Si hay a donde depositarle (decision 7, seccion 105). La cuenta
        # viene de Odoo; aqui solo se dice si esta o falta, nunca el
        # numero: eso es de finanzas, en su bandeja.
        "cuenta": "tiene" if persona.clabe else "falta",
        "calificacion": round(float(calificacion), 1),
        "ventana_meses": p.meses_ventana,
        "horas_en_centauro": horas,
        "dimensiones": dimensiones,
        "sin_datos_para_medir": sin_medir,
        "confianza": ("alta" if not sin_medir else
                      "media" if len(sin_medir) == 1 else "baja"),
    }


def tabla(db: Session, pais_id: int, plaza_id: int | None = None,
          hoy: date | None = None) -> list[dict]:
    """Todo el personal de seguridad, de mejor a peor calificado."""
    consulta = (db.query(m.Persona)
                .join(m.Plaza, m.Persona.plaza_id == m.Plaza.id)
                .filter(m.Plaza.pais_id == pais_id,
                        m.Persona.activo.is_(True),
                        # La oficina que llega de Odoo (seccion 74) no es
                        # personal de seguridad.
                        m.Persona.oficina.is_(False)))
    if plaza_id:
        consulta = consulta.filter(m.Persona.plaza_id == plaza_id)
    # El filtro por puesto se fue con el puesto: una persona ya no es de
    # un rol, va con el rol que le toco ese dia.

    # Las fichas de todos de un golpe (seccion 101): una por una eran
    # una docena de consultas por persona.
    todas = fichas(db, [persona.id for persona in consulta.all()], hoy)
    renglones = [_renglon(db, f, hoy) for f in todas.values()]
    return sorted(renglones, key=lambda x: x["calificacion"], reverse=True)


def _dimension(f: dict, cual) -> dict:
    return next((d for d in f["dimensiones"]
                 if d["dimension"] == cual.value), {})


def _renglon(db: Session, f: dict, hoy: date | None) -> dict:
    """El renglon de la lista, con lo que ya se calculo.

    `ficha` calcula las cinco dimensiones --cada una con su valor, su
    peso y una frase que la explica-- y esta tabla se quedaba con cuatro
    campos y tiraba el resto. El calculo caro ya se hizo: lo que faltaba
    no era motor, era enseñarlo.

    Se le agregan dos cosas que no estaban en ninguna de las dos: el
    semaforo del padron de certificados y el bono del mes vencido.
    """
    from app import bonos, capacitaciones

    D = m.DimensionProfesionalismo
    satisfaccion = _dimension(f, D.SATISFACCION)
    incidencias = _dimension(f, D.INCIDENCIAS)

    anio, mes = bonos.mes_anterior(hoy or date.today())
    evaluacion = (db.query(m.EvaluacionMensual)
                  .filter_by(persona_id=f["persona_id"], anio=anio, mes=mes)
                  .first())

    return {
        "persona_id": f["persona_id"], "persona": f["persona"],
        "usuario": f["usuario"],
        "plaza": f["plaza"],
        "es_freelance": f["es_freelance"],
        "calificacion": f["calificacion"],
        "horas_en_centauro": f["horas_en_centauro"],
        "confianza": f["confianza"],
        # "Confianza baja" se leia como desconfianza de la persona.
        # Lo que dice es que al sistema le faltan datos sobre ella
        # --justo lo que le pasa a quien lleva dos semanas--, asi que se
        # dice como lo que es.
        "medido_con": len(f["dimensiones"]) - len(f["sin_datos_para_medir"]),
        "dimensiones_totales": len(f["dimensiones"]),
        "sin_datos_para_medir": f["sin_datos_para_medir"],
        "satisfaccion": ({"promedio": satisfaccion.get("promedio_1_a_5"),
                          "detalle": satisfaccion.get("detalle")}
                         if satisfaccion.get("aplica") else None),
        "incidencias": incidencias.get("detalle"),
        "incidencias_frase": incidencias.get("frase"),
        "capacitacion": capacitaciones.por_vencer(db, f["persona_id"], hoy),
        "bono": ({"periodo": f"{mes:02d}/{anio}",
                  "estrellas": evaluacion.estrellas,
                  "posibles": sum(1 for r in evaluacion.detalle if r.aplica),
                  "monto": evaluacion.monto_bono,
                  "moneda": evaluacion.moneda.value,
                  "estatus": evaluacion.estatus.value,
                  "anulado": evaluacion.anulado_por_incidencia}
                 if evaluacion else None),
    }


def expediente(db: Session, persona_id: int, meses: int = 6) -> dict:
    """Lo que la ficha de la persona enseña debajo de las dimensiones.

    Tres bloques que viven en tres tablas distintas y que hasta hoy no se
    podian ver juntos: el bono de los ultimos meses, lo que dijeron los
    clientes --con el texto, no solo el promedio-- y el padron de
    certificados con sus fechas.
    """
    from app import bonos

    persona = db.get(m.Persona, persona_id)
    if not persona:
        return {}

    anio, mes = bonos.mes_anterior(date.today())
    total = anio * 12 + (mes - 1)
    periodos = [((total - i) // 12, (total - i) % 12 + 1) for i in range(meses)]
    evaluaciones = [e for e in db.query(m.EvaluacionMensual)
                    .filter_by(persona_id=persona_id).all()
                    if (e.anio, e.mes) in periodos]
    evaluaciones.sort(key=lambda e: (e.anio, e.mes), reverse=True)

    servicios = {a.jornada.equipo.servicio_id
                 for a in db.query(m.AsignacionPersonal)
                 .filter_by(persona_id=persona_id).all()}
    encuestas = []
    if servicios:
        encuestas = (db.query(m.Encuesta)
                     .filter(m.Encuesta.servicio_id.in_(servicios),
                             m.Encuesta.tipo == m.TipoEncuesta.EJECUTIVO,
                             m.Encuesta.calificacion.isnot(None))
                     .order_by(m.Encuesta.respondida_en.desc()).limit(8).all())

    cursos = (db.query(m.Capacitacion)
              .filter_by(persona_id=persona_id, activo=True)
              .order_by(m.Capacitacion.nombre).all())
    hoy = date.today()

    # Sus incidencias, todas (seccion 105): la pendiente, la autorizada y
    # la descartada con su resolucion. La descartada no toca bono ni
    # comision, pero queda en el expediente: es lo que explica, meses
    # despues, que alguien la levanto y por que no procedio.
    incidencias = (db.query(m.Incidencia)
                   .filter_by(persona_id=persona_id)
                   .order_by(m.Incidencia.fecha.desc(), m.Incidencia.id.desc())
                   .limit(12).all())

    return {
        "persona_id": persona.id,
        "persona": persona.nombre,
        "incidencias": [bonos.renglon_incidencia(db, i) for i in incidencias],
        "bonos": [{"periodo": f"{e.mes:02d}/{e.anio}",
                   "estrellas": e.estrellas,
                   "posibles": sum(1 for r in e.detalle if r.aplica),
                   "monto": e.monto_bono, "moneda": e.moneda.value,
                   "estatus": e.estatus.value,
                   "anulado": e.anulado_por_incidencia}
                  for e in evaluaciones],
        # Con el texto que escribieron. El promedio dice que tan bien
        # salio; la frase dice que arreglar.
        "clientes": [{"folio": e.servicio.folio if e.servicio else None,
                      "servicio_id": e.servicio_id,
                      "cliente": (e.servicio.cliente.nombre
                                  if e.servicio and e.servicio.cliente
                                  else None),
                      "calificacion": e.calificacion,
                      "cuando": (e.respondida_en.isoformat()
                                 if e.respondida_en else None),
                      "dijo": next((r.texto for r in e.respuestas if r.texto),
                                   None)}
                     for e in encuestas],
        "certificados": [{"nombre": c.nombre,
                          "institucion": c.institucion,
                          "obtenida_en": (c.obtenida_en.isoformat()
                                          if c.obtenida_en else None),
                          "vigencia_hasta": (c.vigencia_hasta.isoformat()
                                             if c.vigencia_hasta else None),
                          "dias": ((c.vigencia_hasta - hoy).days
                                   if c.vigencia_hasta else None)}
                         for c in cursos],
    }
