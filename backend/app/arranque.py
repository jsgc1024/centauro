# -*- coding: utf-8 -*-
"""El arranque (seccion 97): lo que falta para operar todo en Connect y
apagar OVH, revisandose solo.

Pieza 5 de «Para poder operar». Decision 6 de Salvador (28 sep): el
arranque vive en el sistema y se revisa solo, como el estado del
sistema --nada escrito a mano que se quede viejo--. Cada renglon dice
como esta ahora, de quien es y donde se arregla. Lo que el sistema no
alcanza --el respaldo y sus alertas viven en el servidor-- se confirma a
mano, con nombre y fecha. Se quita cuando todo este en verde.

Decision 7 (calendario): todo lo nuevo de Mexico en Connect el lunes 2
de noviembre, y OVH apagado el lunes 7 de diciembre.

Como el resto del manual, se lee en espanol y en portugues; la consola
en ingles lo lee en espanol.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import fallas, manual, reloj, tipo_cambio
from app import models as m

TODO_EN_CONNECT = date(2026, 11, 2)
OVH_APAGADO = date(2026, 12, 7)

LISTO, EN_CAMINO, FALTA = "ok", "alerta", "grave"

# Lo que el sistema no puede revisar solo: se confirma a mano.
A_MANO = ("respaldo",)

# Los catalogos de dinero y donde anotan sus cambios en la bitacora de
# administracion (seccion 86): el `objeto` de sus renglones.
OBJETO = {"tabulador": "tabulador-viaticos", "modalidades": "modalidades",
          "pago_dia": "comisiones", "bono": "criterio_estrella"}

MESES = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
           "oct", "nov", "dic"],
    "pt": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
           "out", "nov", "dez"],
}
MESES_LARGOS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
}

TEXTOS = {
    "es": {
        "grupos": {"servidor": "El servidor", "odoo": "Odoo",
                   "dinero": "El dinero", "gente": "La gente",
                   "operacion": "La operación"},
        # Que
        "reloj": "El reloj", "correo": "El correo",
        "avisos": "Avisos al teléfono", "maps": "La llave de Google Maps",
        "respaldo": "El respaldo y sus alertas",
        "personal": "El personal de seguridad", "flota": "La flota",
        "oficina": "La oficina", "clientes": "Los clientes",
        "tarifarios": "Los tarifarios",
        "tabulador": "El tabulador de viáticos",
        "modalidades": "Las horas de cada modalidad",
        "pago_dia": "Lo que se paga por día", "bono": "El bono del mes",
        "tipo_cambio": "El tipo de cambio",
        "puestos": "Los puestos", "acceso_oficina": "La oficina, con acceso",
        "acceso_campo": "El personal de campo, con acceso",
        "avisos_encendidos": "Avisos encendidos en el teléfono",
        "implantados": "Los implantados, con {mes} abierto",
        "eventuales": "Eventuales de esta semana en Connect",
        "fallas": "Fallas por revisar",
        # Quien
        "q_salvador": "Salvador", "q_rh_ari": "Recursos Humanos y Ari",
        "q_flota": "Flota", "q_rh": "Recursos Humanos",
        "q_finanzas": "Finanzas", "q_fin_comercial": "Finanzas y comercial",
        "q_dir_op": "Dirección de operaciones",
        "q_dir_op_fin": "Dirección de operaciones y finanzas",
        "q_dir_general": "Dirección general", "q_consultores": "Consultores",
        "q_consultor_gente": "Cada consultor, con su gente",
        "q_calidad": "Sistema y calidad",
        # Donde
        "d_estado": "Estado", "d_odoo": "Odoo", "d_tarifarios": "Tarifarios",
        "d_catalogos": "Catálogos", "d_nominas": "Nóminas",
        "d_desempeno": "Desempeño", "d_accesos": "Accesos",
        "d_implantado": "EP implantado", "d_eventual": "EP eventual",
        "d_casos": "Casos",
        # Como
        "maps_si": "La llave está puesta: los puntos de encuentro se buscan "
                   "en Google Maps.",
        "maps_no": "Sin la llave, el punto de encuentro se escribe a mano.",
        "confirmado": "Confirmado a mano por {p} el {f}.",
        "confirmado_sin": "Confirmado a mano el {f}.",
        "sin_confirmar": "Vive en el servidor y el sistema no lo alcanza: se "
                         "revisa allá y se confirma aquí.",
        "odoo_sin_llave": "Este servidor no tiene la llave de Odoo.",
        "sin_primera": "Todavía no se aplica la primera lectura.",
        "leidos_ok": "{n} en Connect · ninguno pendiente.",
        "leidos_pend": "{n} en Connect · pendientes en la última lectura: {p}.",
        "tar_sin": "Todavía no se aplica la primera lectura · productos sin "
                   "confirmar: {p}.",
        "tar_pend": "Productos sin confirmar: {p} · clientes sin tarifario: {c}.",
        "tar_ok": "Los productos confirmados y cada cliente con su tarifario.",
        "cambiado": "Cambiado el {f} por {p}.",
        "ya_no_ejemplo": "Ya no son los montos de ejemplo.",
        "ejemplo": "Sigue con los montos de ejemplo.",
        "ejemplo_horas": "Siguen las horas de ejemplo.",
        "tc_ok": "${t} por dólar, puesto el {f} por {p}.",
        "tc_ok_sin": "${t} por dólar, puesto el {f}.",
        "tc_no": "No hay tipo de cambio: sin él no se autoriza ni se factura "
                 "en dólares.",
        "puestos_ok": "Puestos creados: {n}.",
        "puestos_no": "Ninguno todavía: cada quien entra con lo de su rol.",
        "acceso": "{a} de {n} · {e} ya entraron.",
        "acceso_oficina_sin": "Todavía no se lee la oficina de Odoo.",
        "acceso_campo_sin": "Todavía no hay personal de campo.",
        "de": "{a} de {n}.",
        "impl_sin": "Todavía no hay implantados dados de alta.",
        "eventuales_n": "{n}.",
        "eventuales_0": "Ninguno todavía esta semana.",
        "fallas_0": "Ninguna.",
        "fallas_n": "Por revisar: {n}.",
    },
    "pt": {
        "grupos": {"servidor": "O servidor", "odoo": "Odoo",
                   "dinero": "O dinheiro", "gente": "As pessoas",
                   "operacion": "A operação"},
        "reloj": "O relógio", "correo": "O e-mail",
        "avisos": "Avisos no telefone", "maps": "A chave do Google Maps",
        "respaldo": "O backup e os seus alertas",
        "personal": "O pessoal de segurança", "flota": "A frota",
        "oficina": "O escritório", "clientes": "Os clientes",
        "tarifarios": "As tabelas de preços",
        "tabulador": "A tabela de diárias",
        "modalidades": "As horas de cada modalidade",
        "pago_dia": "O que se paga por dia", "bono": "O bônus do mês",
        "tipo_cambio": "A taxa de câmbio",
        "puestos": "Os cargos", "acceso_oficina": "O escritório, com acesso",
        "acceso_campo": "O pessoal de campo, com acesso",
        "avisos_encendidos": "Avisos ligados no telefone",
        "implantados": "Os implantados, com {mes} aberto",
        "eventuales": "Eventuais desta semana no Connect",
        "fallas": "Falhas por revisar",
        "q_salvador": "Salvador", "q_rh_ari": "Recursos Humanos e Ari",
        "q_flota": "Frota", "q_rh": "Recursos Humanos",
        "q_finanzas": "Financeiro", "q_fin_comercial": "Financeiro e comercial",
        "q_dir_op": "Direção de operações",
        "q_dir_op_fin": "Direção de operações e financeiro",
        "q_dir_general": "Direção geral", "q_consultores": "Consultores",
        "q_consultor_gente": "Cada consultor, com o seu pessoal",
        "q_calidad": "Sistema e qualidade",
        "d_estado": "Estado", "d_odoo": "Odoo", "d_tarifarios": "Tabelas",
        "d_catalogos": "Catálogos", "d_nominas": "Folhas",
        "d_desempeno": "Desempenho", "d_accesos": "Acessos",
        "d_implantado": "EP implantado", "d_eventual": "EP eventual",
        "d_casos": "Casos",
        "maps_si": "A chave está colocada: os pontos de encontro se buscam "
                   "no Google Maps.",
        "maps_no": "Sem a chave, o ponto de encontro se escreve à mão.",
        "confirmado": "Confirmado à mão por {p} em {f}.",
        "confirmado_sin": "Confirmado à mão em {f}.",
        "sin_confirmar": "Vive no servidor e o sistema não o alcança: é "
                         "revisado lá e confirmado aqui.",
        "odoo_sin_llave": "Este servidor não tem a chave do Odoo.",
        "sin_primera": "A primeira leitura ainda não foi aplicada.",
        "leidos_ok": "{n} no Connect · nenhum pendente.",
        "leidos_pend": "{n} no Connect · pendentes na última leitura: {p}.",
        "tar_sin": "A primeira leitura ainda não foi aplicada · produtos sem "
                   "confirmar: {p}.",
        "tar_pend": "Produtos sem confirmar: {p} · clientes sem tabela: {c}.",
        "tar_ok": "Os produtos confirmados e cada cliente com a sua tabela.",
        "cambiado": "Alterado em {f} por {p}.",
        "ya_no_ejemplo": "Já não são os valores de exemplo.",
        "ejemplo": "Continua com os valores de exemplo.",
        "ejemplo_horas": "Continuam as horas de exemplo.",
        "tc_ok": "${t} por dólar, colocado em {f} por {p}.",
        "tc_ok_sin": "${t} por dólar, colocado em {f}.",
        "tc_no": "Não há taxa de câmbio: sem ela não se autoriza nem se "
                 "fatura em dólares.",
        "puestos_ok": "Cargos criados: {n}.",
        "puestos_no": "Nenhum ainda: cada um entra com o do seu papel.",
        "acceso": "{a} de {n} · {e} já entraram.",
        "acceso_oficina_sin": "O escritório ainda não foi lido do Odoo.",
        "acceso_campo_sin": "Ainda não há pessoal de campo.",
        "de": "{a} de {n}.",
        "impl_sin": "Ainda não há implantados cadastrados.",
        "eventuales_n": "{n}.",
        "eventuales_0": "Nenhum ainda nesta semana.",
        "fallas_0": "Nenhuma.",
        "fallas_n": "Por revisar: {n}.",
    },
}


# ---------------------------------------------------------------- ayudas

def _renglon(clave, tono, que, como, quien=None, ir=None, donde=None,
             **extra) -> dict:
    return {"clave": clave, "tono": tono, "que": que, "como": como,
            "quien": quien, "ir": ir, "donde": donde, **extra}


def _hoy_mx(ahora: datetime) -> date:
    return ahora.astimezone(reloj.zona(reloj.ZONA_POR_OMISION)).date()


def _dia(cuando, idioma: str) -> str:
    """«5 oct»: el dia en Mexico, sin anio --todo esto pasa este otono--."""
    if isinstance(cuando, datetime):
        cuando = manual._aware(cuando).astimezone(
            reloj.zona(reloj.ZONA_POR_OMISION)).date()
    return f"{cuando.day} {MESES[idioma][cuando.month - 1]}"


def _nombre(db: Session, persona_id: int | None) -> str | None:
    persona = db.get(m.Persona, persona_id) if persona_id else None
    return persona.nombre if persona else None


def _cuantos(db: Session, consulta) -> int:
    """Cuantos renglones trae un select."""
    return db.scalar(select(func.count()).select_from(consulta.subquery())) or 0


def _tono_de_avance(listos: int, total: int) -> str:
    """Todos: listo. Algunos: en camino. Ninguno: falta."""
    if total and listos >= total:
        return LISTO
    return EN_CAMINO if listos else FALTA


# ---------------------------------------------------------------- el servidor

def _servidor(db: Session, T: dict, idioma: str, ahora: datetime) -> list:
    from app.config import settings

    E = manual.ESTADO[idioma]
    ir, donde = "#/manual/atorado", T["d_estado"]
    renglones = []

    r = manual._estado_reloj(db, E, idioma, ahora)
    renglones.append(_renglon("reloj", r["tono"], T["reloj"],
                              f"{r['etiqueta']}. {r['texto']}", None, ir, donde))

    # Para arrancar, el correo apagado es algo que falta, no un cuidado.
    c = manual._estado_correo(db, E)
    tono = FALTA if c["etiqueta"] == E["apagado"] else c["tono"]
    renglones.append(_renglon("correo", tono, T["correo"],
                              f"{c['etiqueta']}. {c['texto']}",
                              T["q_salvador"], ir, donde))

    a = manual._estado_avisos(E)
    renglones.append(_renglon("avisos", a["tono"], T["avisos"],
                              f"{a['etiqueta']}. {a['texto']}",
                              T["q_salvador"], ir, donde))

    llave = bool(settings.google_maps_key)
    renglones.append(_renglon("maps", LISTO if llave else FALTA, T["maps"],
                              T["maps_si"] if llave else T["maps_no"],
                              T["q_salvador"]))

    renglones.append(_a_mano(db, "respaldo", T, idioma, T["q_salvador"]))
    return renglones


def _a_mano(db: Session, clave: str, T: dict, idioma: str, quien: str) -> dict:
    fila = db.get(m.ConfirmacionArranque, clave)
    if not fila:
        return _renglon(clave, FALTA, T[clave], T["sin_confirmar"], quien,
                        a_mano=True, confirmado=False)
    por = _nombre(db, fila.confirmado_por_id)
    como = (T["confirmado"].format(p=por, f=_dia(fila.confirmado_en, idioma))
            if por else
            T["confirmado_sin"].format(f=_dia(fila.confirmado_en, idioma)))
    return _renglon(clave, LISTO, T[clave], como, quien, a_mano=True,
                    confirmado=True)


# ---------------------------------------------------------------- odoo

def _odoo(db: Session, T: dict) -> list:
    from app import odoo_api, odoo_tarifarios

    conectado = odoo_api.hay_conexion()
    L = m.SincronizacionOdoo
    P = m.Persona
    en_connect = {
        "personal": db.query(P).filter(P.odoo_id.isnot(None), P.activo.is_(True),
                                       P.oficina.is_(False)).count(),
        "flota": db.query(m.Vehiculo).filter(m.Vehiculo.odoo_id.isnot(None),
                                             m.Vehiculo.activo.is_(True)).count(),
        "oficina": db.query(P).filter(P.odoo_id.isnot(None), P.activo.is_(True),
                                      P.oficina.is_(True)).count(),
        "clientes": db.query(m.Cliente).filter(m.Cliente.odoo_id.isnot(None),
                                               m.Cliente.activo.is_(True)).count(),
    }
    quien = {"personal": T["q_rh_ari"], "flota": T["q_flota"],
             "oficina": T["q_rh"], "clientes": T["q_finanzas"]}
    ir, donde = "#/odoo", T["d_odoo"]

    renglones = []
    for tipo in ("personal", "flota", "oficina", "clientes"):
        if not conectado:
            tono, como = FALTA, T["odoo_sin_llave"]
        elif db.query(L.id).filter_by(tipo=tipo, automatica=False).first() is None:
            # La de cada hora espera a la primera, hecha a mano.
            tono, como = FALTA, T["sin_primera"]
        else:
            ultima = (db.query(L).filter_by(tipo=tipo)
                      .order_by(L.hecha_en.desc(), L.id.desc()).first())
            pendientes = ultima.pendientes if ultima else 0
            tono = EN_CAMINO if pendientes else LISTO
            como = (T["leidos_pend"].format(n=en_connect[tipo], p=pendientes)
                    if pendientes else T["leidos_ok"].format(n=en_connect[tipo]))
        renglones.append(_renglon(tipo, tono, T[tipo], como, quien[tipo], ir, donde))

    sin_confirmar = (db.query(m.ProductoOdoo)
                     .filter(m.ProductoOdoo.vendible.is_(True),
                             m.ProductoOdoo.confirmado.is_(False)).count())
    sin_tarifario = (db.query(m.Cliente)
                     .filter(m.Cliente.activo.is_(True),
                             m.Cliente.tarifario_id.is_(None)).count())
    if not conectado:
        tono, como = FALTA, T["odoo_sin_llave"]
    elif not odoo_tarifarios.en_marcha(db):
        tono, como = FALTA, T["tar_sin"].format(p=sin_confirmar)
    elif sin_confirmar or sin_tarifario:
        tono, como = EN_CAMINO, T["tar_pend"].format(p=sin_confirmar, c=sin_tarifario)
    else:
        tono, como = LISTO, T["tar_ok"]
    renglones.append(_renglon("tarifarios", tono, T["tarifarios"], como,
                              T["q_fin_comercial"], "#/facturacion",
                              T["d_tarifarios"]))
    return renglones


# ---------------------------------------------------------------- el dinero

def _ultimo_cambio(db: Session, objeto: str) -> m.RegistroAdmin | None:
    R = m.RegistroAdmin
    return (db.query(R).filter(R.objeto == objeto)
            .order_by(R.creado_en.desc(), R.id.desc()).first())


def _bono_de_ejemplo(db: Session) -> bool:
    """Si los criterios del bono de Mexico siguen como se sembraron. Los
    cambios de antes de la seccion 97 no quedaban en la bitacora: por eso
    tambien se comparan los montos."""
    from app import seed

    mx = db.query(m.Pais).filter_by(codigo="MX").first()
    if not mx:
        return True
    ejemplo = {codigo: (Decimal(umbral), Decimal(monto), minutos, veces)
               for codigo, _, umbral, monto, minutos, veces
               in seed.CRITERIOS_DE_EJEMPLO}
    for c in db.query(m.CriterioEstrella).filter_by(pais_id=mx.id):
        hoy = (Decimal(str(c.umbral_pct)), Decimal(str(c.monto_mensual)),
               c.tolerancia_minutos, c.tolerancia_ocasiones)
        if ejemplo.get(c.codigo) != hoy:
            return False
    return True


def _dinero(db: Session, T: dict, idioma: str) -> list:
    donde = {"tabulador": ("#/catalogos", T["d_catalogos"], T["q_dir_op"]),
             "modalidades": ("#/catalogos", T["d_catalogos"], T["q_dir_op"]),
             "pago_dia": ("#/nomina", T["d_nominas"], T["q_dir_op_fin"]),
             "bono": ("#/bonos", T["d_desempeno"], T["q_dir_op"])}
    renglones = []
    for clave in ("tabulador", "modalidades", "pago_dia", "bono"):
        ir, lugar, quien = donde[clave]
        cambio = _ultimo_cambio(db, OBJETO[clave])
        if cambio:
            por = _nombre(db, cambio.persona_id) or "—"
            tono, como = LISTO, T["cambiado"].format(
                f=_dia(cambio.creado_en, idioma), p=por)
        elif clave == "bono" and not _bono_de_ejemplo(db):
            tono, como = LISTO, T["ya_no_ejemplo"]
        else:
            tono, como = FALTA, T["ejemplo_horas" if clave == "modalidades"
                                  else "ejemplo"]
        renglones.append(_renglon(clave, tono, T[clave], como, quien, ir, lugar))

    tc = tipo_cambio.vigente(db, "USD", "MXN")
    if tc:
        dia = _dia(tc["puesto_en"], idioma) if tc["puesto_en"] else "—"
        como = (T["tc_ok"].format(t=tipo_cambio.corto(tc["tasa"]), f=dia, p=tc["por"])
                if tc["por"] else
                T["tc_ok_sin"].format(t=tipo_cambio.corto(tc["tasa"]), f=dia))
        tono = LISTO
    else:
        tono, como = FALTA, T["tc_no"]
    renglones.append(_renglon("tipo_cambio", tono, T["tipo_cambio"], como,
                              T["q_finanzas"], "#/facturacion", T["d_tarifarios"]))
    return renglones


# ---------------------------------------------------------------- la gente

def _gente(db: Session, T: dict, idioma: str) -> list:
    P, U = m.Persona, m.Usuario
    ir, donde = "#/accesos", T["d_accesos"]
    renglones = []

    puestos = (db.query(m.CategoriaAcceso)
               .filter(m.CategoriaAcceso.activa.is_(True)).count())
    renglones.append(_renglon(
        "puestos", LISTO if puestos else FALTA, T["puestos"],
        T["puestos_ok"].format(n=puestos) if puestos else T["puestos_no"],
        T["q_dir_general"], ir, donde))

    # La oficina: la que se lee de Odoo.
    oficina = select(P.id).where(P.activo.is_(True), P.oficina.is_(True))
    n = _cuantos(db, oficina)
    con_acceso = select(U.id).where(U.persona_id.in_(oficina), U.activo.is_(True))
    a = _cuantos(db, con_acceso)
    e = _cuantos(db, con_acceso.where(U.ultimo_acceso.isnot(None)))
    renglones.append(_renglon(
        "acceso_oficina", _tono_de_avance(a, n) if n else FALTA,
        T["acceso_oficina"],
        T["acceso"].format(a=a, n=n, e=e) if n else T["acceso_oficina_sin"],
        T["q_rh"], ir, donde))

    # El personal de campo: quien va a la calle. No cuenta a quien tiene
    # un acceso de oficina aunque no venga de la oficina de Odoo.
    de_oficina = select(U.persona_id).where(U.rol != m.Rol.PERSONAL_SEGURIDAD)
    campo = select(P.id).where(P.activo.is_(True), P.oficina.is_(False),
                               P.id.notin_(de_oficina))
    n = _cuantos(db, campo)
    con_acceso = select(U.id).where(U.persona_id.in_(campo), U.activo.is_(True),
                                    U.rol == m.Rol.PERSONAL_SEGURIDAD)
    a = _cuantos(db, con_acceso)
    e = _cuantos(db, con_acceso.where(U.ultimo_acceso.isnot(None)))
    renglones.append(_renglon(
        "acceso_campo", _tono_de_avance(a, n) if n else FALTA,
        T["acceso_campo"],
        T["acceso"].format(a=a, n=n, e=e) if n else T["acceso_campo_sin"],
        T["q_rh"], ir, donde))

    S = m.SuscripcionPush
    con_avisos = (db.query(func.count(func.distinct(S.persona_id)))
                  .filter(S.activa.is_(True), S.persona_id.in_(campo)).scalar() or 0)
    renglones.append(_renglon(
        "avisos_encendidos", _tono_de_avance(con_avisos, n) if n else FALTA,
        T["avisos_encendidos"],
        T["de"].format(a=con_avisos, n=n) if n else T["acceso_campo_sin"],
        T["q_consultor_gente"]))

    # Los implantados, con el mes en que todo pasa a Connect ya abierto.
    Sv = m.Servicio
    vivos = select(Sv.id).where(
        Sv.tipo == m.TipoServicio.IMPLANTADO,
        Sv.estatus.notin_((m.EstatusServicio.CANCELADO, m.EstatusServicio.CERRADO)))
    total = _cuantos(db, vivos)
    con_mes = (db.query(func.count(func.distinct(m.ContratoImplantado.servicio_id)))
               .filter(m.ContratoImplantado.servicio_id.in_(vivos),
                       m.ContratoImplantado.anio == TODO_EN_CONNECT.year,
                       m.ContratoImplantado.mes == TODO_EN_CONNECT.month)
               .scalar() or 0)
    mes = MESES_LARGOS[idioma][TODO_EN_CONNECT.month - 1]
    renglones.append(_renglon(
        "implantados", _tono_de_avance(con_mes, total) if total else FALTA,
        T["implantados"].format(mes=mes),
        T["de"].format(a=con_mes, n=total) if total else T["impl_sin"],
        T["q_consultores"], "#/implantados", T["d_implantado"]))
    return renglones


# ---------------------------------------------------------------- la operacion

def _operacion(db: Session, T: dict, ahora: datetime) -> list:
    hoy = _hoy_mx(ahora)
    lunes = hoy - timedelta(days=hoy.weekday())
    Sv, E, J = m.Servicio, m.Equipo, m.Jornada
    eventuales = (db.query(func.count(func.distinct(Sv.id)))
                  .join(E, E.servicio_id == Sv.id).join(J, J.equipo_id == E.id)
                  .filter(Sv.tipo == m.TipoServicio.EVENTUAL,
                          Sv.estatus != m.EstatusServicio.CANCELADO,
                          J.fecha >= lunes, J.fecha <= lunes + timedelta(days=6))
                  .scalar() or 0)
    abiertas = (db.query(m.CasoResuelto)
                .filter(m.CasoResuelto.estado.in_(fallas.ABIERTOS)).count())
    return [
        _renglon("eventuales", LISTO if eventuales else EN_CAMINO, T["eventuales"],
                 T["eventuales_n"].format(n=eventuales) if eventuales
                 else T["eventuales_0"], None, "#/servicios", T["d_eventual"]),
        _renglon("fallas", EN_CAMINO if abiertas else LISTO, T["fallas"],
                 T["fallas_n"].format(n=abiertas) if abiertas else T["fallas_0"],
                 T["q_calidad"], "#/manual/casos/abiertos", T["d_casos"]),
    ]


# ---------------------------------------------------------------- todo junto

def revisar(db: Session, pedido: str | None,
            ahora: datetime | None = None) -> dict:
    """El arranque completo, en el idioma de quien lo lee."""
    idioma = manual.idioma_de(pedido)
    T = TEXTOS[idioma]
    ahora = manual._aware(ahora) or datetime.now(timezone.utc)
    grupos = [
        ("servidor", _servidor(db, T, idioma, ahora)),
        ("odoo", _odoo(db, T)),
        ("dinero", _dinero(db, T, idioma)),
        ("gente", _gente(db, T, idioma)),
        ("operacion", _operacion(db, T, ahora)),
    ]
    tonos = [r["tono"] for _, renglones in grupos for r in renglones]
    return {
        "idioma": idioma,
        "en_otro_idioma": (pedido or "es")[:2].lower() not in manual.IDIOMAS,
        "ahora": ahora.isoformat(),
        "fecha": TODO_EN_CONNECT.isoformat(),
        "dias": (TODO_EN_CONNECT - _hoy_mx(ahora)).days,
        "apagar_ovh": OVH_APAGADO.isoformat(),
        "resumen": {"listos": tonos.count(LISTO),
                    "en_camino": tonos.count(EN_CAMINO),
                    "faltan": tonos.count(FALTA), "total": len(tonos)},
        "grupos": [{"clave": clave, "titulo": T["grupos"][clave],
                    "renglones": renglones} for clave, renglones in grupos],
    }


# ---------------------------------------------------------------- a mano

def _clave_a_mano(clave: str) -> str:
    if clave not in A_MANO:
        raise HTTPException(400, "Ese renglón del arranque se revisa solo: "
                                 "no se confirma a mano.")
    return clave


def confirmar(db: Session, clave: str, usuario: m.Usuario) -> None:
    """Quien lo confirma y cuando: el renglon lo dice con su nombre."""
    from app import accesos

    clave = _clave_a_mano(clave)
    fila = db.get(m.ConfirmacionArranque, clave)
    if fila is None:
        fila = m.ConfirmacionArranque(clave=clave)
        db.add(fila)
    fila.confirmado_por_id = usuario.persona_id
    fila.confirmado_en = datetime.now(timezone.utc)
    accesos.anotar(db, usuario, "arranque confirmado", "arranque",
                   detalle=TEXTOS["es"][clave])
    db.flush()


def quitar(db: Session, clave: str, usuario: m.Usuario) -> None:
    """Si algo dejo de estar bien --el respaldo fallo--, se quita y vuelve
    a faltar."""
    from app import accesos

    clave = _clave_a_mano(clave)
    fila = db.get(m.ConfirmacionArranque, clave)
    if fila is not None:
        db.delete(fila)
        accesos.anotar(db, usuario, "arranque sin confirmar", "arranque",
                       detalle=TEXTOS["es"][clave])
    db.flush()
