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

from sqlalchemy.orm import Session

from app import models as m
from app.experiencia import horas_acumuladas

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

def _en_ventana(anio: int, mes: int, desde: tuple[int, int]) -> bool:
    return (anio, mes) >= desde


def _estrellas(db: Session, persona_id: int, desde: tuple[int, int]) -> dict:
    evaluaciones = [e for e in db.query(m.EvaluacionMensual)
                    .filter_by(persona_id=persona_id).all()
                    if _en_ventana(e.anio, e.mes, desde)]
    if not evaluaciones:
        return {"aplica": False, "detalle": "Sin evaluaciones en la ventana"}

    obtenidas = aplicables = 0
    for e in evaluaciones:
        criterios = db.query(m.ResultadoCriterio).filter_by(
            evaluacion_id=e.id, aplica=True).all()
        aplicables += len(criterios)
        obtenidas += len([c for c in criterios if c.cumplido])

    if not aplicables:
        return {"aplica": False, "detalle": "Ningun criterio le aplico"}
    valor = _d(obtenidas) / _d(aplicables) * CIEN
    return {"aplica": True, "valor": valor,
            "detalle": f"{obtenidas} de {aplicables} estrellas posibles en "
                       f"{len(evaluaciones)} meses"}


def _satisfaccion(db: Session, persona_id: int) -> dict:
    servicios = {a.jornada.equipo.servicio_id
                 for a in db.query(m.AsignacionPersonal)
                 .filter_by(persona_id=persona_id).all()}
    if not servicios:
        return {"aplica": False, "detalle": "Sin servicios atendidos"}

    notas = [e.calificacion for e in db.query(m.Encuesta)
             .filter(m.Encuesta.servicio_id.in_(servicios),
                     m.Encuesta.tipo == m.TipoEncuesta.EJECUTIVO,
                     m.Encuesta.calificacion.isnot(None)).all()]
    if not notas:
        return {"aplica": False, "detalle": "Ningun ejecutivo lo ha calificado"}

    promedio = _d(sum(notas)) / _d(len(notas))
    # Del 1 al 5 a una escala de 0 a 100: un 1 es cero, un 5 es cien.
    valor = (promedio - 1) / 4 * CIEN
    return {"aplica": True, "valor": valor,
            "promedio_1_a_5": round(float(promedio), 2),
            "detalle": f"{len(notas)} calificaciones, promedio "
                       f"{round(float(promedio), 2)} de 5"}


def _incidencias(db: Session, persona_id: int, desde: tuple[int, int],
                 p: "_Parametros") -> dict:
    """Arranca en 100 y baja con cada incidencia ya autorizada."""
    castigo = {
        m.GravedadIncidencia.ERROR_MENOR: _d(p.castigo_error_menor),
        m.GravedadIncidencia.LEVE: _d(p.castigo_leve),
        m.GravedadIncidencia.GRAVE: _d(p.castigo_grave),
    }
    filas = [i for i in db.query(m.Incidencia)
             .filter_by(persona_id=persona_id, autorizada=True).all()
             if _en_ventana(i.fecha.year, i.fecha.month, desde)]

    total = sum((castigo.get(i.gravedad, CERO) for i in filas), CERO)
    valor = max(CERO, CIEN - total)
    if not filas:
        detalle = "Sin incidencias autorizadas en la ventana"
    else:
        por_gravedad = {}
        for i in filas:
            por_gravedad[i.gravedad.value] = por_gravedad.get(i.gravedad.value, 0) + 1
        detalle = ", ".join(f"{n} {g}" for g, n in sorted(por_gravedad.items()))
    # Esta dimension siempre aplica: no tener incidencias es informacion,
    # no ausencia de informacion.
    return {"aplica": True, "valor": valor, "detalle": detalle,
            "incidencias": len(filas)}


def _capacitacion(db: Session, persona_id: int, desde: tuple[int, int]) -> dict:
    evaluaciones = [e for e in db.query(m.EvaluacionMensual)
                    .filter_by(persona_id=persona_id).all()
                    if _en_ventana(e.anio, e.mes, desde)]
    if not evaluaciones:
        return {"aplica": False, "detalle": "Sin evaluaciones en la ventana"}
    cumplidos = len([e for e in evaluaciones if e.capacitacion_cumplida])
    valor = _d(cumplidos) / _d(len(evaluaciones)) * CIEN
    return {"aplica": True, "valor": valor,
            "detalle": f"{cumplidos} de {len(evaluaciones)} meses al corriente"}


def _manejo(db: Session, persona_id: int, desde: tuple[int, int],
            p: "_Parametros") -> dict:
    """Los excesos y los arrancones o frenadas bruscas que conto el GPS,
    por cada mil km al volante en servicio (seccion 60). Solo los dias en
    que esa persona iba al volante: al escolta no le aplica, y su peso se
    reparte entre lo demas, como con cualquier dimension sin datos."""
    from app import gps
    return gps.manejo_de(db, persona_id, desde, p.puntos_por_evento_manejo)


def _experiencia(db: Session, persona_id: int,
                 p: "_Parametros") -> dict:
    horas = horas_acumuladas(db, persona_id)
    referencia = p.horas_referencia or 2000
    valor = min(CIEN, _d(horas) / _d(referencia) * CIEN)
    return {"aplica": True, "valor": valor, "horas": horas,
            "detalle": f"{horas:,} h acumuladas en Centauro"}


# ---------------------------------------------------------------- ficha

def _usuario(db: Session, persona_id: int) -> dict | None:
    """Con que correo entra al sistema, o nada si no tiene cuenta.

    Va pegado a la ficha porque la pregunta se hace mirando esta
    pantalla --"y este, ya puede abrir la app?"--: sin esto hay que
    salir a Accesos y volver a buscar a la misma persona.

    La contrasena no se puede enseñar aqui ni en ningun lado: se guarda
    un hash, no la contrasena. Lo unico que se puede decir es si ya puso
    una; quien no, entra con el codigo que le dicta su consultor.
    """
    u = (db.query(m.Usuario)
         .filter(m.Usuario.persona_id == persona_id).first())
    if not u:
        return None
    return {"correo": u.correo, "activo": u.activo,
            "ya_puso_contrasena": u.hash_contrasena is not None}


def ficha(db: Session, persona_id: int, hoy: date | None = None) -> dict:
    persona = db.get(m.Persona, persona_id)
    if not persona:
        return {}
    pais_id = persona.plaza.pais_id
    p = parametros(db, pais_id)
    tabla_pesos = pesos(db, pais_id)
    desde = _desde(p.meses_ventana, hoy)

    D = m.DimensionProfesionalismo
    medidas = {
        D.ESTRELLAS: _estrellas(db, persona_id, desde),
        D.SATISFACCION: _satisfaccion(db, persona_id),
        D.INCIDENCIAS: _incidencias(db, persona_id, desde, p),
        D.CAPACITACION: _capacitacion(db, persona_id, desde),
        D.EXPERIENCIA: _experiencia(db, persona_id, p),
        D.MANEJO: _manejo(db, persona_id, desde, p),
    }

    # El peso de lo que no se puede medir se reparte entre lo que si.
    peso_util = sum((tabla_pesos.get(d, CERO) for d, v in medidas.items()
                     if v["aplica"]), CERO)

    dimensiones = []
    calificacion = CERO
    for dimension, medida in medidas.items():
        peso = tabla_pesos.get(dimension, CERO)
        fila = {"dimension": dimension.value, "peso_base": float(peso),
                "aplica": medida["aplica"], "detalle": medida["detalle"]}
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
        "usuario": _usuario(db, persona.id),
        # Sin puesto: el rol es de la tarea, no de la persona.
        "plaza": persona.plaza.nombre,
        "es_freelance": persona.es_freelance,
        "calificacion": round(float(calificacion), 1),
        "ventana_meses": p.meses_ventana,
        "horas_en_centauro": horas_acumuladas(db, persona_id),
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
                        m.Persona.activo.is_(True)))
    if plaza_id:
        consulta = consulta.filter(m.Persona.plaza_id == plaza_id)
    # El filtro por puesto se fue con el puesto: una persona ya no es de
    # un rol, va con el rol que le toco ese dia.

    fichas = []
    for persona in consulta.all():
        f = ficha(db, persona.id, hoy)
        if not f:
            continue
        fichas.append(_renglon(db, f, hoy))
    return sorted(fichas, key=lambda x: x["calificacion"], reverse=True)


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

    return {
        "persona_id": persona.id,
        "persona": persona.nombre,
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
