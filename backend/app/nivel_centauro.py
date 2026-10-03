"""El Nivel Centauro: el riesgo de fondo de cada estado y municipio, de 0
a 100, cada mes (seccion 138).

La formula la propuso Connect y la decidio Salvador el 2 de octubre de
2026 (documento de la Central de Inteligencia, «El Nivel Centauro»):

    Nivel = suma de peso_i x P_i, con seis componentes de 0 a 100

    1 violencia letal          18   Secretariado: homicidio doloso y feminicidio
    2 delitos con violencia    12   Secretariado: robo con violencia, lesiones con arma de fuego
    3 delincuencia organizada  10   Secretariado: secuestro, extorsion, narcomenudeo
    4 miedo                    12   ENSU por ciudad; fuera de ellas, ENVIPE del estado
    5 lo que no se denuncia     8   ENVIPE: victimas por 100 mil del estado
    6 cifra negra de redes     40   los hechos publicados en el mapa, 90 dias

Cada componente: la tasa por 100 mil habitantes de los ultimos 12 meses
(los meses que haya de la metodologia 2026, llevados a 12), la tasa del
municipio mezclada con la de su estado segun su tamano, y su percentil
contra todos los municipios del pais (o contra los 32 estados). Un
componente sin datos --la ENVIPE que nadie ha subido-- no cuenta como
cero: se deja fuera y los demas se reparten su peso, y el borrador lo
dice.

El calculo hace un borrador; lo revisa el analista, lo ajusta con motivo
si hace falta y lo publica el jefe de turno. Nada llega al cliente sin
publicarse.
"""
import json
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models as m
from app import nivel_catalogo as nc
from app import reloj
from app.fuentes_riesgo import FUENTE_SESNSP, normalizar

POR_CIEN_MIL = 100_000
CAMBIO_GRANDE = 10          # puntos contra el mes publicado anterior


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _mes(d: date) -> date:
    return date(d.year, d.month, 1)


def _mes_menos(d: date, n: int) -> date:
    y, mo = d.year, d.month - n
    while mo < 1:
        mo += 12
        y -= 1
    return date(y, mo, 1)


def _fin_de_mes(d: date) -> date:
    return _mes_menos(d, -1) - timedelta(days=1)


# ================================================================ parametros

def parametros(db: Session, pais: m.Pais) -> dict:
    fila = db.query(m.ParametrosNivel).filter_by(pais_id=pais.id).first()
    if not fila:
        return {"pesos": dict(nc.PESOS_INICIALES),
                "cortes": list(nc.CORTES_INICIALES), "suavizado": 50000,
                "referencia_id": None}
    return {"pesos": json.loads(fila.pesos), "cortes": json.loads(fila.cortes),
            "suavizado": fila.suavizado, "referencia_id": fila.referencia_id}


def guardar_parametros(db: Session, pais: m.Pais, pesos: dict | None,
                       cortes: list | None, referencia_id: int | None = None,
                       quitar_referencia: bool = False) -> dict:
    fila = db.query(m.ParametrosNivel).filter_by(pais_id=pais.id).first()
    if not fila:
        fila = m.ParametrosNivel(pais_id=pais.id,
                                 pesos=json.dumps(nc.PESOS_INICIALES),
                                 cortes=json.dumps(nc.CORTES_INICIALES))
        db.add(fila)
    if pesos is not None:
        if set(pesos) != set(nc.COMPONENTES) or \
                any(float(v) < 0 for v in pesos.values()):
            raise HTTPException(400, "Van los seis componentes, sin pesos "
                                     "negativos")
        if round(sum(float(v) for v in pesos.values()), 2) != 100:
            raise HTTPException(400, "Los pesos tienen que sumar 100")
        fila.pesos = json.dumps({k: float(pesos[k]) for k in nc.COMPONENTES})
    if cortes is not None:
        c = [float(x) for x in cortes]
        if len(c) != 4 or c != sorted(c) or c[0] <= 0 or c[-1] >= 100 or \
                len(set(c)) != 4:
            raise HTTPException(400, "Van cuatro cortes, de menor a mayor, "
                                     "entre 0 y 100")
        fila.cortes = json.dumps(c)
    if quitar_referencia:
        fila.referencia_id = None
    elif referencia_id is not None:
        ref = db.get(m.NivelMes, referencia_id)
        if not ref or ref.pais_id != pais.id or ref.estado != "publicado":
            raise HTTPException(400, "La referencia tiene que ser un mes "
                                     "publicado")
        fila.referencia_id = ref.id
    db.flush()
    return parametros(db, pais)


def rango(valor: float, cortes: list) -> str:
    for corte, nombre in zip(cortes, nc.RANGOS):
        if valor < corte:
            return nombre
    return nc.RANGOS[-1]


# ================================================================ el calculo

def _poblacion(db: Session, anio: int) -> dict[int, int]:
    """municipio_id -> habitantes del ano, o del ano mas cercano."""
    anios = [a for (a,) in db.query(m.PoblacionMunicipio.anio).distinct()]
    if not anios:
        return {}
    cerca = min(anios, key=lambda a: abs(a - anio))
    return dict(db.query(m.PoblacionMunicipio.municipio_id,
                         m.PoblacionMunicipio.habitantes)
                .filter_by(anio=cerca))


def _percentil(valor: float, referencia: list[float]) -> float:
    """Que tanto de la referencia queda abajo de este valor, de 0 a 100.
    Solo cuenta lo que queda estrictamente abajo: mil municipios sin un
    solo homicidio salen en 0, no a la mitad de la tabla."""
    if not referencia:
        return 0.0
    return round(100 * bisect_left(referencia, valor) / len(referencia), 1)


def _meses_con_datos(db: Session, hasta: date) -> list[date]:
    desde = _mes_menos(hasta, 11)
    return sorted(p for (p,) in db.query(m.CifraOficial.periodo)
                  .filter(m.CifraOficial.fuente == FUENTE_SESNSP,
                          m.CifraOficial.periodo >= desde,
                          m.CifraOficial.periodo <= hasta).distinct())


def _ultima_encuesta(db: Session, fuente: str, hasta: date) -> date | None:
    return db.query(func.max(m.EncuestaValor.periodo)).filter(
        m.EncuestaValor.fuente == fuente,
        m.EncuestaValor.periodo <= _fin_de_mes(hasta)).scalar()


def _cifra_negra(db: Session, pais: m.Pais, hasta: date,
                 municipios: list[m.Municipio]) -> tuple[dict, dict, int]:
    """Los hechos publicados en los 90 dias que cierran el mes, pesados
    por nivel. Al municipio por su nombre; el que no se reconoce cuenta
    solo para el estado."""
    fin = datetime.combine(_fin_de_mes(hasta) + timedelta(days=1),
                           datetime.min.time(), tzinfo=timezone.utc)
    inicio = fin - timedelta(days=nc.DIAS_DE_CIFRA_NEGRA)
    eventos = (db.query(m.EventoRiesgo)
               .filter(m.EventoRiesgo.pais_id == pais.id,
                       m.EventoRiesgo.publicado_en.isnot(None),
                       m.EventoRiesgo.estado.in_([m.EstadoEvento.PUBLICADO,
                                                  m.EstadoEvento.CERRADO]),
                       m.EventoRiesgo.ocurrio_en >= inicio,
                       m.EventoRiesgo.ocurrio_en < fin).all())
    por_nombre = defaultdict(dict)
    for mun in municipios:
        por_nombre[mun.region_id][normalizar(mun.nombre)] = mun.id
    por_municipio, por_region = defaultdict(float), defaultdict(float)
    for e in eventos:
        peso = nc.PESO_DEL_HECHO.get(e.nivel, 1)
        por_region[e.region_id] += peso
        mid = por_nombre[e.region_id].get(normalizar(e.municipio or ""))
        if mid:
            por_municipio[mid] += peso
    return por_municipio, por_region, len(eventos)


def calcular(db: Session, pais: m.Pais, periodo: date) -> m.NivelMes:
    """El borrador del mes. Si ya habia borrador de ese mes se rehace; un
    mes publicado no se toca."""
    periodo = _mes(periodo)
    previo = db.query(m.NivelMes).filter_by(pais_id=pais.id,
                                            periodo=periodo).first()
    if previo and previo.estado == "publicado":
        raise HTTPException(409, "Ese mes ya se publicó")
    par = parametros(db, pais)
    regiones = {r.id: r for r in db.query(m.Region).filter_by(pais_id=pais.id)}
    municipios = (db.query(m.Municipio)
                  .filter(m.Municipio.region_id.in_(regiones)).all())
    pob = _poblacion(db, periodo.year)
    municipios = [x for x in municipios if pob.get(x.id)]
    pob_region = defaultdict(int)
    for x in municipios:
        pob_region[x.region_id] += pob[x.id]

    # 1-3: el Secretariado, llevado a 12 meses.
    meses = _meses_con_datos(db, periodo)
    factor = 12 / len(meses) if meses else 0
    cuenta_mun = defaultdict(lambda: defaultdict(int))
    cuenta_reg = defaultdict(lambda: defaultdict(int))
    reporto = set()
    if meses:
        for comp, rid, mid, per, v in (
                db.query(m.CifraOficial.componente, m.CifraOficial.region_id,
                         m.CifraOficial.municipio_id, m.CifraOficial.periodo,
                         m.CifraOficial.valor)
                .filter(m.CifraOficial.fuente == FUENTE_SESNSP,
                        m.CifraOficial.periodo.in_(meses))):
            cuenta_reg[rid][comp] += v
            if mid:
                cuenta_mun[mid][comp] += v
                if per == meses[-1]:
                    reporto.add(mid)

    # 4-5: las encuestas, la ultima que haya.
    ensu = _ultima_encuesta(db, "ensu", periodo)
    env_per = _ultima_encuesta(db, "envipe_percepcion", periodo)
    env_pre = _ultima_encuesta(db, "envipe_prevalencia", periodo)

    def valores(fuente, cuando):
        if not cuando:
            return {}, {}
        filas = (db.query(m.EncuestaValor)
                 .filter_by(fuente=fuente, periodo=cuando).all())
        return ({f.municipio_id: float(f.valor) for f in filas if f.municipio_id},
                {f.region_id: float(f.valor) for f in filas
                 if not f.municipio_id})
    ensu_mun, _ = valores("ensu", ensu)
    _, percepcion_reg = valores("envipe_percepcion", env_per)
    _, prevalencia_reg = valores("envipe_prevalencia", env_pre)

    # 6: la cifra negra de la Central.
    cn_mun, cn_reg, hechos = _cifra_negra(db, pais, periodo, municipios)

    # Las tasas de cada estado y de cada municipio, componente por
    # componente. None = sin dato (no es cero).
    def tasa(n, poblacion):
        return n * POR_CIEN_MIL / poblacion if poblacion else None

    tasas_reg, tasas_mun = {}, {}
    for rid in regiones:
        p = pob_region.get(rid)
        if not p:
            continue
        t = {}
        for comp in nc.OFICIALES:
            t[comp] = tasa(cuenta_reg[rid][comp] * factor, p) if meses else None
        t["miedo"] = percepcion_reg.get(rid)
        t["no_denuncia"] = prevalencia_reg.get(rid)
        t["cifra_negra"] = tasa(cn_reg.get(rid, 0), p)
        tasas_reg[rid] = t
    s = par["suavizado"]
    for x in municipios:
        p, est = pob[x.id], tasas_reg.get(x.region_id, {})
        a = p / (p + s)
        t = {}
        for comp in nc.OFICIALES + ("cifra_negra",):
            if comp in nc.OFICIALES and not meses:
                t[comp] = None
                continue
            n = (cuenta_mun[x.id][comp] * factor if comp in nc.OFICIALES
                 else cn_mun.get(x.id, 0))
            propia = tasa(n, p)
            t[comp] = (a * propia + (1 - a) * est[comp]
                       if est.get(comp) is not None else propia)
        t["miedo"] = ensu_mun.get(x.id, est.get("miedo"))
        t["no_denuncia"] = est.get("no_denuncia")
        tasas_mun[x.id] = t

    # Contra que se comparan: el mes de referencia si hay, si no este.
    ref_reg, ref_mun = _referencias(db, par.get("referencia_id"),
                                    tasas_reg, tasas_mun)

    pesos = par["pesos"]
    # Un componente cuenta si dice algo: con datos y no todos iguales (sin
    # un solo hecho de cifra negra en el pais, ese 40% no distingue a
    # nadie y solo empujaria a todos hacia arriba o hacia abajo).
    # Y con un mes de referencia fijo, tiene que haber estado tambien en
    # ese mes: contra una lista vacia todos saldrian en cero.
    disponibles = [c for c in nc.COMPONENTES
                   if len({round(t[c], 6) for t in tasas_reg.values()
                           if t.get(c) is not None}) > 1
                   and ref_reg[c]]

    def nivel(t, ref):
        comps, total, peso_usado = {}, 0.0, 0.0
        for c in nc.COMPONENTES:
            v = t.get(c)
            if v is None or c not in disponibles or not ref[c]:
                comps[c] = {"tasa": None, "p": None}
                continue
            p_ = _percentil(v, ref[c])
            comps[c] = {"tasa": round(v, 2), "p": p_}
            total += pesos[c] * p_
            peso_usado += pesos[c]
        valor = round(total / peso_usado, 2) if peso_usado else 0.0
        return valor, comps

    # Rehacer el borrador no borra lo que la Central ajusto con su motivo:
    # se recalcula el numero de Connect y el ajuste se queda.
    ajustes = {}
    if previo:
        ajustes = {(x.region_id, x.municipio_id): x for x in
                   db.query(m.NivelLugar).filter_by(nivel_mes_id=previo.id)
                   .filter(m.NivelLugar.ajuste_motivo.isnot(None))}
        ajustes = {k: (x.valor, x.ajuste_motivo, x.ajustado_por_id,
                       x.ajustado_en) for k, x in ajustes.items()}
        db.query(m.NivelLugar).filter_by(nivel_mes_id=previo.id).delete()
        mes = previo
    else:
        mes = m.NivelMes(pais_id=pais.id, periodo=periodo,
                         calculado_en=_ahora(), resumen="{}")
        db.add(mes)
        db.flush()
    mes.estado = "borrador"
    mes.calculado_en = _ahora()
    mes.resumen = json.dumps({
        "pesos": pesos, "cortes": par["cortes"],
        "referencia_id": par.get("referencia_id"),
        "faltan": [c for c in nc.COMPONENTES if c not in disponibles],
        "fuentes": {
            "sesnsp": {"meses": [x.isoformat() for x in meses]},
            "ensu": ensu.isoformat() if ensu else None,
            "envipe_percepcion": env_per.isoformat() if env_per else None,
            "envipe_prevalencia": env_pre.isoformat() if env_pre else None,
            "cifra_negra": {"hechos": hechos,
                            "dias": nc.DIAS_DE_CIFRA_NEGRA},
        }})
    filas = []
    for rid, t in tasas_reg.items():
        v, comps = nivel(t, ref_reg)
        filas.append(m.NivelLugar(nivel_mes_id=mes.id, region_id=rid,
                                  municipio_id=None, calculado=v, valor=v,
                                  componentes=json.dumps(comps)))
    for x in municipios:
        v, comps = nivel(tasas_mun[x.id], ref_mun)
        filas.append(m.NivelLugar(
            nivel_mes_id=mes.id, region_id=x.region_id, municipio_id=x.id,
            calculado=v, valor=v, componentes=json.dumps(comps),
            sin_reporte=bool(meses) and x.id not in reporto))
    for fila in filas:
        ajuste = ajustes.get((fila.region_id, fila.municipio_id))
        if ajuste:
            (fila.valor, fila.ajuste_motivo, fila.ajustado_por_id,
             fila.ajustado_en) = ajuste
    db.add_all(filas)
    db.flush()
    return mes


def _referencias(db: Session, referencia_id: int | None, tasas_reg: dict,
                 tasas_mun: dict) -> tuple[dict, dict]:
    """Las tasas ordenadas de cada componente contra las que se saca el
    percentil: las del mes de referencia (escala fija) o las de este."""
    fuente_reg, fuente_mun = list(tasas_reg.values()), list(tasas_mun.values())
    if referencia_id:
        fuente_reg, fuente_mun = [], []
        for mid, comps in (db.query(m.NivelLugar.municipio_id,
                                    m.NivelLugar.componentes)
                           .filter_by(nivel_mes_id=referencia_id)):
            t = {c: d.get("tasa") for c, d in json.loads(comps).items()}
            (fuente_mun if mid else fuente_reg).append(t)
    ordenar = lambda filas: {c: sorted(t[c] for t in filas  # noqa: E731
                                       if t.get(c) is not None)
                             for c in nc.COMPONENTES}
    return ordenar(fuente_reg), ordenar(fuente_mun)


# ================================================================ revisar y publicar

def _publicado_antes(db: Session, mes: m.NivelMes, meses_antes: int
                     ) -> m.NivelMes | None:
    objetivo = _mes_menos(mes.periodo, meses_antes)
    return db.query(m.NivelMes).filter_by(pais_id=mes.pais_id,
                                          periodo=objetivo,
                                          estado="publicado").first()


def _valores(db: Session, mes: m.NivelMes | None,
             region_id: int | None = None,
             con_municipios: bool | None = None) -> dict:
    if not mes:
        return {}
    q = (db.query(m.NivelLugar.region_id, m.NivelLugar.municipio_id,
                  m.NivelLugar.valor).filter_by(nivel_mes_id=mes.id))
    if region_id:
        q = q.filter(m.NivelLugar.region_id == region_id)
    if con_municipios is not None:
        q = q.filter(m.NivelLugar.municipio_id.isnot(None) if con_municipios
                     else m.NivelLugar.municipio_id.is_(None))
    return {(r, mu): float(v) for r, mu, v in q}


def para_revisar(db: Session, mes: m.NivelMes) -> list[dict]:
    """Lo que el analista tiene que ver antes de publicar: lo que se
    movio mas de 10 puntos, lo que cambio de rango y lo que no reporto."""
    cortes = json.loads(mes.resumen).get("cortes", nc.CORTES_INICIALES)
    antes = _valores(db, _publicado_antes(db, mes, 1))
    salida = []
    for lugar in (db.query(m.NivelLugar).filter_by(nivel_mes_id=mes.id)
                  .options(joinedload(m.NivelLugar.region),
                           joinedload(m.NivelLugar.municipio))):
        v = float(lugar.valor)
        previo = antes.get((lugar.region_id, lugar.municipio_id))
        motivos = []
        if lugar.sin_reporte:
            motivos.append({"tipo": "sin_reporte"})
        if previo is not None:
            if abs(v - previo) > CAMBIO_GRANDE:
                motivos.append({"tipo": "cambio", "puntos": round(v - previo)})
            # El rango del numero que se ve: un 19.6 se ve 20 y es Medio bajo.
            de, a = rango(round(previo), cortes), rango(round(v), cortes)
            if de != a:
                motivos.append({"tipo": "rango", "de": de, "a": a})
        if motivos:
            salida.append({**vista_lugar(lugar, cortes), "antes": previo,
                           "motivos": motivos})
    salida.sort(key=lambda x: (x["municipio_id"] is not None, -x["valor"]))
    return salida


def ajustar(db: Session, usuario: m.Usuario, lugar_id: int, valor: float,
            motivo: str) -> m.NivelLugar:
    lugar = db.get(m.NivelLugar, lugar_id)
    if not lugar:
        raise HTTPException(404, "No existe ese lugar en el nivel")
    mes = db.get(m.NivelMes, lugar.nivel_mes_id)
    if mes.estado == "publicado":
        raise HTTPException(409, "Ese mes ya se publicó: no se ajusta")
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise HTTPException(400, "Di por qué cambia: qué sabe la Central que "
                                 "las cifras no dicen todavía")
    if not 0 <= float(valor) <= 100:
        raise HTTPException(400, "El nivel va de 0 a 100")
    lugar.valor = round(float(valor), 2)
    lugar.ajuste_motivo = motivo[:400]
    lugar.ajustado_por_id = usuario.id
    lugar.ajustado_en = _ahora()
    db.flush()
    return lugar


def publicar(db: Session, usuario: m.Usuario, mes_id: int) -> m.NivelMes:
    mes = db.get(m.NivelMes, mes_id)
    if not mes:
        raise HTTPException(404, "No existe ese mes")
    if mes.estado == "publicado":
        raise HTTPException(409, "Ese mes ya se publicó")
    mes.estado = "publicado"
    mes.publicado_en = _ahora()
    mes.publicado_por_id = usuario.id
    db.flush()
    return mes


# ================================================================ lo que se ve

def vigente(db: Session, pais: m.Pais) -> m.NivelMes | None:
    """El ultimo mes publicado: el que ve el cliente."""
    return (db.query(m.NivelMes)
            .filter_by(pais_id=pais.id, estado="publicado")
            .order_by(m.NivelMes.periodo.desc()).first())


def vista_lugar(lugar: m.NivelLugar, cortes: list) -> dict:
    v = float(lugar.valor)
    return {"id": lugar.id, "region_id": lugar.region_id,
            "region": lugar.region.nombre, "clave_region": lugar.region.clave,
            "municipio_id": lugar.municipio_id,
            "municipio": lugar.municipio.nombre if lugar.municipio else None,
            "clave_municipio": (lugar.municipio.clave
                                if lugar.municipio else None),
            "valor": round(v), "calculado": round(float(lugar.calculado)),
            "rango": rango(round(v), cortes),
            "componentes": json.loads(lugar.componentes),
            "sin_reporte": lugar.sin_reporte,
            "ajuste_motivo": lugar.ajuste_motivo}


def vista_mes(db: Session, mes: m.NivelMes, region_id: int | None = None,
              con_municipios: bool = False) -> dict:
    """Un mes: los estados (o los municipios de un estado), con su
    comparacion contra el mes anterior y el mismo mes del ano pasado."""
    resumen = json.loads(mes.resumen)
    cortes = resumen.get("cortes", nc.CORTES_INICIALES)
    antes = _valores(db, _publicado_antes(db, mes, 1), region_id,
                     con_municipios)
    hace_un_ano = _valores(db, _publicado_antes(db, mes, 12), region_id,
                           con_municipios)
    q = (db.query(m.NivelLugar).filter_by(nivel_mes_id=mes.id)
         .options(joinedload(m.NivelLugar.region),
                  joinedload(m.NivelLugar.municipio)))
    if region_id:
        q = q.filter_by(region_id=region_id)
    q = q.filter(m.NivelLugar.municipio_id.isnot(None) if con_municipios
                 else m.NivelLugar.municipio_id.is_(None))
    lugares = []
    for lugar in q:
        datos = vista_lugar(lugar, cortes)
        llave = (lugar.region_id, lugar.municipio_id)
        datos["vs_mes"] = (round(float(lugar.valor) - antes[llave])
                           if llave in antes else None)
        datos["vs_ano"] = (round(float(lugar.valor) - hace_un_ano[llave])
                           if llave in hace_un_ano else None)
        lugares.append(datos)
    lugares.sort(key=lambda x: -x["valor"])
    publicado_por = (db.get(m.Usuario, mes.publicado_por_id)
                     if mes.publicado_por_id else None)
    return {"id": mes.id, "periodo": mes.periodo.isoformat(),
            "estado": mes.estado,
            "calculado_en": mes.calculado_en.isoformat(),
            "publicado_en": (mes.publicado_en.isoformat()
                             if mes.publicado_en else None),
            "publicado_por": (publicado_por.persona.nombre
                              if publicado_por and publicado_por.persona
                              else None),
            "cortes": cortes, "pesos": resumen.get("pesos"),
            "faltan": resumen.get("faltan", []),
            "fuentes": resumen.get("fuentes", {}), "lugares": lugares}


def meses(db: Session, pais: m.Pais) -> list[dict]:
    return [{"id": x.id, "periodo": x.periodo.isoformat(), "estado": x.estado}
            for x in db.query(m.NivelMes).filter_by(pais_id=pais.id)
            .order_by(m.NivelMes.periodo.desc()).limit(36)]


def cargas(db: Session) -> dict:
    """La ultima carga de cada fuente, para «De dónde salió»."""
    salida = {}
    for fuente in (FUENTE_SESNSP, "ensu", "envipe_percepcion",
                   "envipe_prevalencia"):
        c = (db.query(m.CargaFuente).filter_by(fuente=fuente)
             .order_by(m.CargaFuente.id.desc()).first())
        if c:
            quien = db.get(m.Usuario, c.usuario_id) if c.usuario_id else None
            salida[fuente] = {
                "periodo": c.periodo.isoformat(), "origen": c.origen,
                "en": c.en.isoformat(), "archivo": c.archivo,
                "quien": (quien.persona.nombre if quien and quien.persona
                          else None),
                "nota": json.loads(c.nota) if c.nota else None}
    return salida


def hoy_en(pais: m.Pais, ahora: datetime | None = None) -> date:
    return (ahora or _ahora()).astimezone(reloj.zona(pais.zona_horaria)).date()


def mes_a_calcular(pais: m.Pais, ahora: datetime | None = None) -> date:
    """El mes que toca: el anterior al de hoy en el pais (el Secretariado
    publica a mediados de mes lo del mes pasado)."""
    hoy = (ahora or _ahora()).astimezone(reloj.zona(pais.zona_horaria)).date()
    return _mes_menos(hoy, 1)
