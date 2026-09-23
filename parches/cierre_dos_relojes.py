# -*- coding: utf-8 -*-
"""El cierre en dos relojes: reglas, reloj y pruebas del eventual.

Decision de Salvador, 22 sep (PROPUESTA_CIERRE_24H.md, sesion 1 de 3).

  * T0 = termino general del eventual: la hora real de termino del
    ultimo dia (o la firma, si el dia se cerro tarde), o la cancelacion.
  * Al llegar T0, TODOS los viaticos del servicio reciben el mismo
    limite: T0 + 24 h. Cerrar un dia intermedio ya no abre plazo.
  * En T0 + 24 h --o antes, si todo el dinero ya cerro-- el reloj del
    sistema (Celery, cada 5 min) pone T1: el cierre y el servicio pasan
    a `sin_visto_bueno` y el consultor tiene hasta T1 + 24 h.
  * El visto bueno del consultor (enviar a finanzas) es el termino
    general: el servicio pasa a `en_facturacion` y la factura sale a
    Odoo en ese momento. Finanzas aprueba, cierra y detona la comision.
  * Cancelar con dinero afuera o dias trabajados es un termino: mismos
    relojes, mismo proceso; el servicio se queda `cancelado`.
  * Reabrir un dia antes del visto bueno deshace el termino; despues, no.
  * El implantado NO se toca: sigue dia por dia hasta su propia sesion.

Idempotente. Todas las escrituras al final.
"""
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    "models": B / "app/models.py",
    "cierre": B / "app/cierre.py",
    "operacion": B / "app/operacion.py",
    "rcierre": B / "app/routers/cierre.py",
    "facturacion": B / "app/facturacion.py",
    "servicios": B / "app/routers/servicios.py",
    "celery": B / "app/celery_app.py",
    "revisor": B / "app/revisor.py",
    "util": B / "app/web/util.js",
    "idioma": B / "app/web/idioma.js",
    "consultor": B / "app/web/consultor.js",
    "servicio": B / "app/web/servicio.js",
    "t_plazo": B / "tests/test_plazo_comprobacion.py",
    "t_cierre": B / "tests/test_cierre.py",
    "t_360": B / "tests/test_recorrido_360_cuentas.py",
    "t_factura": B / "tests/test_facturacion.py",
    "t_zona": B / "tests/test_zona_horaria.py",
    "bitacora": RAIZ / "BITACORA.md",
}
NUEVOS = {
    B / "migrations/versions/a1c4e7b9d2f6_cierre_en_dos_relojes.py": None,
    B / "tests/test_cierre_dos_relojes.py": None,
}

textos = {k: io.open(v, encoding="utf-8").read() for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(viejo) == 1, f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces"
    textos[clave] = t.replace(viejo, nuevo)


def cambiar_tramo(clave, desde, hasta, nuevo, marca):
    """Reemplaza desde la marca `desde` hasta justo antes de `hasta`."""
    t = textos[clave]
    if marca in t:
        saltados.append(f"{clave}: ya estaba")
        return
    assert t.count(desde) == 1 and t.count(hasta) == 1, clave
    i, j = t.index(desde), t.index(hasta)
    assert i < j
    textos[clave] = t[:i] + nuevo + t[j:]


# ================================================================ modelos
cambiar("models",
        '    TERMINADO = "terminado"\n'
        '    CERRADO = "cerrado"\n',
        '    TERMINADO = "terminado"\n'
        '    # El cierre en dos relojes (decision de Salvador, 22 sep). Al\n'
        '    # terminar corren las 24 h del personal para comprobar; al vencer\n'
        '    # --o antes, si todo el dinero ya cerro-- el servicio queda sin\n'
        '    # visto bueno y corren las 24 h del consultor; su visto bueno lo\n'
        '    # manda a facturar y finanzas lo cierra. Hoy solo el eventual pasa\n'
        '    # por aqui; el implantado corta a mes y llega en su propia sesion.\n'
        '    SIN_VISTO_BUENO = "sin_visto_bueno"\n'
        '    EN_FACTURACION = "en_facturacion"\n'
        '    CERRADO = "cerrado"\n',
        marca='    SIN_VISTO_BUENO = "sin_visto_bueno"\n    EN_FACTURACION')

cambiar("models",
        '    ABIERTO = "abierto"                      # corriendo las 24 h del consultor\n'
        '    EN_REVISION_IA = "en_revision_ia"\n',
        '    ABIERTO = "abierto"                      # comprobacion: las 24 h del personal\n'
        '    SIN_VISTO_BUENO = "sin_visto_bueno"      # las 24 h del consultor\n'
        '    EN_REVISION_IA = "en_revision_ia"\n',
        marca='SIN_VISTO_BUENO = "sin_visto_bueno"      # las 24 h del consultor')

cambiar("models",
        '    limite_consultor: Mapped[datetime] = mapped_column(DateTime)\n'
        '    estatus: Mapped[EstatusCierre] = mapped_column(\n',
        '    limite_consultor: Mapped[datetime] = mapped_column(DateTime)\n'
        '    # Los dos relojes. `abierto_en` es T0 --el termino general, o la\n'
        '    # cancelacion--; `comprobacion_hasta` = T0 + 24 h es el plazo del\n'
        '    # personal; `visto_bueno_desde` es T1, cuando arranco el consultor,\n'
        '    # y `limite_consultor` = T1 + 24 h. Mientras T1 no llega, el limite\n'
        '    # del consultor queda provisional en T0 + 48 h.\n'
        '    comprobacion_hasta: Mapped[datetime | None] = mapped_column(\n'
        '        DateTime, nullable=True)\n'
        '    visto_bueno_desde: Mapped[datetime | None] = mapped_column(\n'
        '        DateTime, nullable=True)\n'
        '    # "termino" o "cancelacion": la cancelacion es un termino con su\n'
        '    # propia revision.\n'
        '    motivo_apertura: Mapped[str | None] = mapped_column(\n'
        '        String(20), nullable=True)\n'
        '    estatus: Mapped[EstatusCierre] = mapped_column(\n',
        marca="    comprobacion_hasta: Mapped[datetime | None]")

# ================================================================ migracion
NUEVOS[B / "migrations/versions/a1c4e7b9d2f6_cierre_en_dos_relojes.py"] = '''"""El cierre en dos relojes.

Al terminar el eventual corren las 24 h del personal para comprobar sus
viaticos; al vencer --o antes, si todo el dinero ya cerro-- corren las
24 h del consultor para el visto bueno, que es cuando sale la factura.
Dos estatus nuevos en el servicio (sin_visto_bueno, en_facturacion),
uno en el cierre (sin_visto_bueno) y tres columnas en el cierre.

Revision ID: a1c4e7b9d2f6
Revises: f3a8c1d2e5b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e7b9d2f6"
down_revision: Union[str, None] = "f3a8c1d2e5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS "
               "'SIN_VISTO_BUENO' AFTER 'TERMINADO'")
    op.execute("ALTER TYPE estatusservicio ADD VALUE IF NOT EXISTS "
               "'EN_FACTURACION' AFTER 'SIN_VISTO_BUENO'")
    op.execute("ALTER TYPE estatuscierre ADD VALUE IF NOT EXISTS "
               "'SIN_VISTO_BUENO' AFTER 'ABIERTO'")
    op.add_column("cierre", sa.Column("comprobacion_hasta", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("visto_bueno_desde", sa.DateTime(),
                                      nullable=True))
    op.add_column("cierre", sa.Column("motivo_apertura",
                                      sa.String(length=20), nullable=True))


def downgrade() -> None:
    # Postgres no deja quitar un valor de un enum: lo que este en los
    # estatus nuevos vuelve al anterior y el valor se queda en el tipo.
    op.execute("UPDATE servicio SET estatus = 'TERMINADO' "
               "WHERE estatus IN ('SIN_VISTO_BUENO', 'EN_FACTURACION')")
    op.execute("UPDATE cierre SET estatus = 'ABIERTO' "
               "WHERE estatus = 'SIN_VISTO_BUENO'")
    op.drop_column("cierre", "motivo_apertura")
    op.drop_column("cierre", "visto_bueno_desde")
    op.drop_column("cierre", "comprobacion_hasta")
'''

# ================================================================ cierre.py
cambiar("cierre",
        "import math\n"
        "from datetime import datetime, timedelta\n",
        "import logging\n"
        "import math\n"
        "from datetime import datetime, timedelta\n")

cambiar("cierre",
        "HORAS_CONSULTOR = 24\n"
        "HORAS_MAXIMO_TOTAL = 48\n"
        'CERO = Decimal("0")\n',
        "# Los dos relojes (decision de Salvador, 22 sep). T0 es el termino\n"
        "# general del servicio: de T0 a T0 + 24 el personal comprueba sus\n"
        "# viaticos. T1 llega al vencer ese plazo --o antes, si todo el dinero\n"
        "# ya cerro--: de T1 a T1 + 24 el consultor da el visto bueno. Si nadie\n"
        "# se adelanta, los dos suman 48 horas desde el termino.\n"
        "HORAS_PERSONAL = 24\n"
        "HORAS_CONSULTOR = 24\n"
        "HORAS_MAXIMO_TOTAL = HORAS_PERSONAL + HORAS_CONSULTOR\n"
        'CERO = Decimal("0")\n'
        "registro = logging.getLogger(__name__)\n",
        marca="HORAS_PERSONAL = 24")

cambiar_tramo(
    "cierre",
    '    registro = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n'
    '    return {\n'
    '        "momento": ahora.isoformat(),\n',
    "\n\ndef abrir(db: Session, servicio_id: int, abierto_en",
    '    fila = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()\n'
    '    if not fila:\n'
    '        return {"momento": ahora.isoformat(), "existe": False,\n'
    '                "cierre_id": None, "estatus": None, "fase": None,\n'
    '                "abierto_en": None, "comprobacion_hasta": None,\n'
    '                "visto_bueno_desde": None, "limite": None,\n'
    '                "minutos_restantes": None, "viaticos_abiertos": None,\n'
    '                "motivo": None, "factura": None, "factura_error": None}\n'
    '\n'
    '    def iso(momento):\n'
    '        return momento.isoformat() if momento else None\n'
    '\n'
    '    return {\n'
    '        "momento": ahora.isoformat(),\n'
    '        "existe": True,\n'
    '        "cierre_id": fila.id,\n'
    '        "estatus": fila.estatus.value,\n'
    '        # La fase, para las pantallas: en que reloj va.\n'
    '        "fase": FASES.get(fila.estatus),\n'
    '        "abierto_en": iso(fila.abierto_en),\n'
    '        "comprobacion_hasta": iso(fila.comprobacion_hasta),\n'
    '        "visto_bueno_desde": iso(fila.visto_bueno_desde),\n'
    '        "limite": iso(fila.limite_consultor),\n'
    '        "minutos_restantes": int(\n'
    '            (fila.limite_consultor - ahora).total_seconds() / 60),\n'
    '        "viaticos_abiertos": viaticos_abiertos(db, servicio_id),\n'
    '        "motivo": fila.motivo_apertura,\n'
    '        "factura": fila.factura_odoo,\n'
    '        "factura_error": fila.factura_error,\n'
    '    }\n',
    marca='        "fase": FASES.get(fila.estatus),')

cambiar("cierre",
        "def abrir(db: Session, servicio_id: int, abierto_en: datetime | None = None) -> m.Cierre:\n"
        '    """Arranca el reloj de las 24 horas del consultor."""\n',
        "def abrir(db: Session, servicio_id: int, abierto_en: datetime | None = None,\n"
        '          motivo: str = "termino") -> m.Cierre:\n'
        '    """Arranca el primer reloj: las 24 horas del personal.\n'
        "\n"
        "    `abierto_en` es T0 --el termino general, o la cancelacion--. De ahi\n"
        "    salen `comprobacion_hasta` (T0 + 24 h) y, provisional, el limite\n"
        "    del consultor en T0 + 48 h: el de verdad lo pone `avanzar` cuando\n"
        "    llega T1.\n"
        '    """\n',
        marca='          motivo: str = "termino") -> m.Cierre:')

cambiar("cierre",
        "    cierre = m.Cierre(servicio_id=servicio_id, abierto_en=momento,\n"
        "                      limite_consultor=momento + timedelta(hours=HORAS_CONSULTOR))\n",
        "    hasta = momento + timedelta(hours=HORAS_PERSONAL)\n"
        "    cierre = m.Cierre(servicio_id=servicio_id, abierto_en=momento,\n"
        "                      comprobacion_hasta=hasta,\n"
        "                      limite_consultor=hasta + timedelta(hours=HORAS_CONSULTOR),\n"
        "                      motivo_apertura=motivo)\n",
        marca="                      comprobacion_hasta=hasta,")

SEGUNDO_RELOJ = '''

# ---------------------------------------------------------------- el segundo reloj

# La fase, para las pantallas: lo que cada estatus del cierre quiere
# decir en la cadena de dos relojes.
FASES = {
    m.EstatusCierre.ABIERTO: "comprobacion",
    m.EstatusCierre.SIN_VISTO_BUENO: "sin_visto_bueno",
    m.EstatusCierre.EN_REVISION_IA: "sin_visto_bueno",
    m.EstatusCierre.DEVUELTO_A_OPERACION: "devuelto",
    m.EstatusCierre.ENVIADO_FINANZAS: "en_facturacion",
    m.EstatusCierre.APROBADO: "aprobado",
    m.EstatusCierre.FACTURADO: "facturado",
}

# Lo que ya no cuenta como dinero afuera.
VIATICO_RESUELTO = (m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,
                    m.EstatusViatico.CANCELADO)


def viaticos_abiertos(db: Session, servicio_id: int) -> int:
    """Cuantos viaticos del servicio siguen sin cerrar."""
    return (db.query(m.AsignacionViatico)
            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .filter(m.Equipo.servicio_id == servicio_id,
                    m.AsignacionViatico.estatus.notin_(VIATICO_RESUELTO))
            .count())


def avanzar(db: Session, cierre: m.Cierre,
            ahora: datetime | None = None) -> bool:
    """De la comprobacion al visto bueno: pone T1 y el limite del consultor.

    Lo mueve el reloj del sistema, no una persona. T1 llega cuando
    vencen las 24 h del personal (T0 + 24) o antes, si todos los
    viaticos del servicio ya cerraron, se devolvieron o se cancelaron:
    no hay nada que esperar (decision 2 de la propuesta).

    Solo escribe; quien llama decide cuando guardar. Devuelve si movio.
    """
    if cierre.estatus != m.EstatusCierre.ABIERTO:
        return False
    servicio = cierre.servicio
    ahora = reloj.ahora_del_servicio(db, servicio, ahora)

    viejo = cierre.comprobacion_hasta is None
    if viejo:
        # Nacio antes de los dos relojes: su plazo era el de siempre, 24 h
        # desde que se abrio. Se respeta tal cual (regla 10 de la
        # propuesta): lo ya terminado no se toca.
        t1, limite = cierre.abierto_en, cierre.limite_consultor
    elif ahora >= cierre.comprobacion_hasta:
        t1 = cierre.comprobacion_hasta
        limite = t1 + timedelta(hours=HORAS_CONSULTOR)
    elif viaticos_abiertos(db, servicio.id) == 0:
        t1 = ahora
        limite = t1 + timedelta(hours=HORAS_CONSULTOR)
    else:
        return False

    cierre.visto_bueno_desde = t1
    cierre.limite_consultor = limite
    cierre.estatus = m.EstatusCierre.SIN_VISTO_BUENO
    # El cancelado se queda cancelado: su rastro es el cierre.
    if servicio.estatus == m.EstatusServicio.TERMINADO:
        servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO

    if servicio.consultor_id and not viejo:
        from app import push
        try:
            push.avisar(
                db, servicio.consultor_id,
                titulo=f"{servicio.folio}: tienes 24 h para el visto bueno",
                cuerpo=("La comprobacion del personal termino. Tu plazo "
                        f"vence el {limite:%d/%m a las %H:%M}."),
                url=f"/servicios/{servicio.id}",
                etiqueta=f"visto-bueno-{cierre.id}")
        except Exception:                 # noqa: BLE001
            # Un aviso que no sale no puede frenar el reloj.
            registro.exception("no se pudo avisar el visto bueno de %s",
                               servicio.folio)
    return True


def avanzar_cierres(db: Session, ahora: datetime | None = None) -> list[str]:
    """El barrido de cada cinco minutos: lo que llego a T1 pasa a sin
    visto bueno. Devuelve los folios que movio."""
    movidos = []
    for cierre in (db.query(m.Cierre)
                   .filter(m.Cierre.estatus == m.EstatusCierre.ABIERTO)
                   .all()):
        if avanzar(db, cierre, ahora):
            movidos.append(cierre.servicio.folio)
    db.commit()
    return movidos
'''
if "def avanzar_cierres(" not in textos["cierre"]:
    textos["cierre"] = textos["cierre"].rstrip("\n") + "\n" + SEGUNDO_RELOJ
else:
    saltados.append("cierre: el segundo reloj ya estaba")

# ================================================================ operacion.py
cambiar("operacion",
        "        cuantos += 1\n"
        "    return cuantos\n"
        "\n"
        "\n"
        "def _pares_del_equipo(",
        "        cuantos += 1\n"
        "    return cuantos\n"
        "\n"
        "\n"
        "def abrir_plazo_del_servicio(db: Session, servicio: m.Servicio,\n"
        "                             termino: datetime) -> int:\n"
        '    """El eventual abre el plazo una sola vez, para todos: T0 + 24 h.\n'
        "\n"
        "    Decision de Salvador, 22 sep: las 24 horas del personal corren\n"
        "    desde el termino general del servicio --el cierre del ultimo dia,\n"
        "    o la cancelacion--, no desde el cierre de cada dia. En un servicio\n"
        "    de tres dias los tres viaticos vencen a la misma hora.\n"
        "\n"
        "    Se respeta el plazo que ya tenga un viatico: el del relevado, que\n"
        "    corre desde su relevo (decision 1 de la propuesta). Y el dinero que\n"
        "    ya cerro, se devolvio o se cancelo no recibe plazo: ya no esta\n"
        "    afuera.\n"
        '    """\n'
        "    from app import viaticos as motor_viaticos\n"
        "\n"
        "    limite = motor_viaticos.limite_de_comprobacion(termino)\n"
        "    cuantos = 0\n"
        "    for viatico in _viaticos_del_servicio(db, servicio.id):\n"
        "        if viatico.limite_comprobacion or viatico.estatus in (\n"
        "                m.EstatusViatico.CERRADO, m.EstatusViatico.DEVUELTO,\n"
        "                m.EstatusViatico.CANCELADO):\n"
        "            continue\n"
        "        viatico.limite_comprobacion = limite\n"
        "        cuantos += 1\n"
        "    return cuantos\n"
        "\n"
        "\n"
        "def _viaticos_del_servicio(db: Session, servicio_id: int) -> list:\n"
        "    return (db.query(m.AsignacionViatico)\n"
        "            .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)\n"
        "            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)\n"
        "            .filter(m.Equipo.servicio_id == servicio_id)\n"
        "            .all())\n"
        "\n"
        "\n"
        "def _pares_del_equipo(",
        marca="def abrir_plazo_del_servicio(")

cambiar("operacion",
        "        jornada.fin_real = ahora\n"
        "        jornada.estatus = m.EstatusJornada.TERMINADA\n"
        "        # El dia termino: empiezan a correr las 24 horas para comprobar.\n"
        "        abrir_plazo_de_comprobacion(db, jornada, ahora)\n"
        "        terminar_si_cerro_el_ultimo_dia(db, servicio)\n",
        "        jornada.fin_real = ahora\n"
        "        jornada.estatus = m.EstatusJornada.TERMINADA\n"
        "        # El dia termino. En el implantado empiezan a correr las 24\n"
        "        # horas para comprobar ese dia; en el eventual el plazo es uno\n"
        "        # solo para todo el servicio y arranca con el termino general,\n"
        "        # abajo, al cerrar el ultimo dia (decision de Salvador, 22 sep).\n"
        "        if servicio.tipo != m.TipoServicio.EVENTUAL:\n"
        "            abrir_plazo_de_comprobacion(db, jornada, ahora)\n"
        "        terminar_si_cerro_el_ultimo_dia(db, servicio, termino=ahora,\n"
        "                                        registrado=recibido)\n",
        marca="        terminar_si_cerro_el_ultimo_dia(db, servicio, termino=ahora,")

cambiar("operacion",
        "    abrir_plazo_de_comprobacion(db, jornada, fin)\n"
        "    jornada.cerrada_a_mano_por_id = quien_id\n"
        "    jornada.cerrada_a_mano_en = ahora\n"
        "    jornada.cierre_motivo = justificacion.strip()\n"
        "    terminar_si_cerro_el_ultimo_dia(db, jornada.equipo.servicio)\n",
        "    if jornada.equipo.servicio.tipo != m.TipoServicio.EVENTUAL:\n"
        "        abrir_plazo_de_comprobacion(db, jornada, fin)\n"
        "    jornada.cerrada_a_mano_por_id = quien_id\n"
        "    jornada.cerrada_a_mano_en = ahora\n"
        "    jornada.cierre_motivo = justificacion.strip()\n"
        "    # En el eventual, un dia firmado tarde no nace vencido: el plazo\n"
        "    # corre desde la firma, no desde la hora de termino que asento la\n"
        "    # central (decision 4 de la propuesta).\n"
        "    terminar_si_cerro_el_ultimo_dia(db, jornada.equipo.servicio,\n"
        "                                    termino=fin, registrado=ahora)\n",
        marca="                                    termino=fin, registrado=ahora)")

cambiar("operacion",
        "def terminar_si_cerro_el_ultimo_dia(db: Session,\n"
        "                                    servicio: m.Servicio) -> bool:\n",
        "def terminar_si_cerro_el_ultimo_dia(db: Session, servicio: m.Servicio,\n"
        "                                    termino: datetime | None = None,\n"
        "                                    registrado: datetime | None = None,\n"
        "                                    ) -> bool:\n",
        marca="                                    registrado: datetime | None = None,\n"
              "                                    ) -> bool:")

cambiar("operacion",
        "    servicio.estatus = m.EstatusServicio.TERMINADO\n"
        "\n"
        "    # Y arranca solo el reloj del consultor.\n"
        "    #\n"
        "    # Se abria a mano, con un boton que alguien tenia que acordarse de\n"
        "    # tocar. Si nadie lo tocaba, el plazo de 24 horas no empezaba nunca\n"
        "    # --y de ese plazo depende que el consultor cobre su comision--, asi\n"
        "    # que la regla existia sin correr. Un plazo que arranca cuando\n"
        "    # alguien se acuerda no es un plazo.\n",
        "    servicio.estatus = m.EstatusServicio.TERMINADO\n"
        "\n"
        "    # T0, el termino general: la hora real de termino del ultimo dia.\n"
        "    # Si el dia se firmo tarde --la central lo cerro a mano tres dias\n"
        "    # despues, o la marca llego con retraso--, T0 es la firma: un plazo\n"
        "    # que nace vencido no es un plazo (decision 4 de la propuesta).\n"
        "    momentos = [x for x in (termino, registrado) if x]\n"
        "    t0 = max(momentos) if momentos else reloj.ahora_del_servicio(db, servicio)\n"
        "\n"
        "    # Y arrancan solos los dos relojes: las 24 horas del personal para\n"
        "    # comprobar --todos los viaticos del servicio con el mismo limite,\n"
        "    # T0 + 24 h-- y, cuando vencen o todo el dinero ya cerro, las 24\n"
        "    # horas del consultor (`cierre.avanzar`, cada cinco minutos).\n"
        "    #\n"
        "    # Se abria a mano, con un boton que alguien tenia que acordarse de\n"
        "    # tocar. Si nadie lo tocaba, el plazo de 24 horas no empezaba nunca\n"
        "    # --y de ese plazo depende que el consultor cobre su comision--, asi\n"
        "    # que la regla existia sin correr. Un plazo que arranca cuando\n"
        "    # alguien se acuerda no es un plazo.\n",
        marca="    t0 = max(momentos) if momentos else reloj.ahora_del_servicio(db, servicio)")

cambiar("operacion",
        "    motor_cierre.abrir(db, servicio.id)\n"
        "    try:\n"
        "        motor_encuestas.generar(db, servicio.id)\n",
        "    abrir_plazo_del_servicio(db, servicio, t0)\n"
        "    motor_cierre.abrir(db, servicio.id, abierto_en=t0)\n"
        "    try:\n"
        "        motor_encuestas.generar(db, servicio.id)\n",
        marca="    motor_cierre.abrir(db, servicio.id, abierto_en=t0)\n")

cambiar("operacion",
        "    # Se deshace todo lo que escribio el cierre a mano, la hora de\n",
        "    # El eventual ya terminado: reabrir un dia deshace el termino\n"
        "    # general. Si el cierre sigue en comprobacion o sin visto bueno, se\n"
        "    # borra con sus plazos y el servicio vuelve a la calle; al cerrar el\n"
        "    # dia otra vez nace un T0 nuevo. Con el visto bueno dado ya no: la\n"
        "    # factura salio, o esta por salir, con esas horas.\n"
        "    servicio = jornada.equipo.servicio\n"
        "    if servicio.tipo == m.TipoServicio.EVENTUAL:\n"
        "        if servicio.estatus == m.EstatusServicio.CANCELADO:\n"
        "            raise HTTPException(409, {\n"
        '                "mensaje": "El servicio esta cancelado: no se reabre un dia",\n'
        '                "que_hacer": "Lo que haya que corregir de ese dia se "\n'
        '                             "resuelve en la revision de la cancelacion."})\n'
        "        cierre = (db.query(m.Cierre)\n"
        "                  .filter_by(servicio_id=servicio.id).first())\n"
        "        if cierre and (cierre.facturado_en or cierre.estatus in (\n"
        "                m.EstatusCierre.EN_REVISION_IA,\n"
        "                m.EstatusCierre.ENVIADO_FINANZAS,\n"
        "                m.EstatusCierre.APROBADO, m.EstatusCierre.FACTURADO)):\n"
        "            raise HTTPException(409, {\n"
        '                "mensaje": "El servicio ya tiene visto bueno: no se puede reabrir",\n'
        '                "que_hacer": "Lo que cambie de este dia se corrige con "\n'
        '                             "finanzas, no reabriendo el dia."})\n'
        "        if cierre:\n"
        "            for viatico in _viaticos_del_servicio(db, servicio.id):\n"
        "                if viatico.limite_comprobacion == cierre.comprobacion_hasta:\n"
        "                    viatico.limite_comprobacion = None\n"
        "            db.delete(cierre)\n"
        "            db.flush()\n"
        "        if servicio.estatus in (m.EstatusServicio.TERMINADO,\n"
        "                                m.EstatusServicio.SIN_VISTO_BUENO):\n"
        "            # En curso si otro dia ya se trabajo o esta en la calle;\n"
        "            # si no, vuelve a esperar su dia, con el estatus que le\n"
        "            # toque por sus recursos.\n"
        "            otros = [j for e in servicio.equipos for j in e.jornadas\n"
        "                     if j.id != jornada.id and j.estatus in (\n"
        "                         m.EstatusJornada.TERMINADA,\n"
        "                         m.EstatusJornada.EN_CURSO,\n"
        "                         m.EstatusJornada.ARRIBADO)]\n"
        "            if otros:\n"
        "                servicio.estatus = m.EstatusServicio.EN_CURSO\n"
        "            else:\n"
        "                from app import programacion\n"
        "                servicio.estatus = m.EstatusServicio.PLANEADO\n"
        "                programacion.evaluar(servicio)\n"
        "\n"
        "    # Se deshace todo lo que escribio el cierre a mano, la hora de\n",
        marca='                "mensaje": "El servicio ya tiene visto bueno: no se puede reabrir",')

# ================================================================ routers/cierre.py
cambiar("rcierre",
        "    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)\n"
        "    revision = revisor.revisar(db, cierre.servicio_id, momento)\n"
        "\n"
        "    if not revision[\"listo_para_finanzas\"]:\n",
        "    momento = reloj.ahora_del_servicio(db, cierre.servicio, ahora)\n"
        "\n"
        "    # El reloj del sistema pudo no haber pasado todavia: si ya llego T1\n"
        "    # --o todo el dinero ya cerro--, se avanza aqui mismo y se guarda,\n"
        "    # pase lo que pase con la revision de abajo.\n"
        "    if motor.avanzar(db, cierre, momento):\n"
        "        db.commit()\n"
        "\n"
        "    # Mientras corren las 24 h del personal, el visto bueno ni se abre:\n"
        "    # no se le va a pedir al consultor que cierre con descuento un\n"
        "    # dinero que su gente todavia tiene tiempo de comprobar. Y lo que ya\n"
        "    # se envio no se envia dos veces.\n"
        "    if cierre.estatus not in (m.EstatusCierre.SIN_VISTO_BUENO,\n"
        "                              m.EstatusCierre.DEVUELTO_A_OPERACION):\n"
        "        raise HTTPException(409, {\n"
        '            "mensaje": ("Todavia corre la comprobacion de viaticos del personal"\n'
        "                        if cierre.estatus == m.EstatusCierre.ABIERTO\n"
        '                        else f"El cierre esta en {cierre.estatus.value}"),\n'
        '            "hasta": (cierre.comprobacion_hasta.isoformat()\n'
        "                      if cierre.comprobacion_hasta else None),\n"
        '            "observaciones": [],\n'
        "        })\n"
        "\n"
        "    revision = revisor.revisar(db, cierre.servicio_id, momento)\n"
        "\n"
        "    if not revision[\"listo_para_finanzas\"]:\n",
        marca="    if motor.avanzar(db, cierre, momento):\n")

cambiar("rcierre",
        "    cierre.dentro_de_plazo = momento <= cierre.limite_consultor\n"
        "\n"
        "    auditoria.registrar(db, usuario, cierre.servicio, \"enviar a finanzas\",\n",
        "    cierre.dentro_de_plazo = momento <= cierre.limite_consultor\n"
        "    # El visto bueno es el termino general: el servicio pasa a\n"
        "    # facturacion. El cancelado se queda cancelado.\n"
        "    if cierre.servicio.estatus in (m.EstatusServicio.TERMINADO,\n"
        "                                   m.EstatusServicio.SIN_VISTO_BUENO):\n"
        "        cierre.servicio.estatus = m.EstatusServicio.EN_FACTURACION\n"
        "\n"
        "    auditoria.registrar(db, usuario, cierre.servicio, \"enviar a finanzas\",\n",
        marca="        cierre.servicio.estatus = m.EstatusServicio.EN_FACTURACION\n")

cambiar("rcierre",
        "    db.commit()\n"
        "\n"
        '    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,\n'
        '            "dentro_de_plazo": cierre.dentro_de_plazo,\n',
        "    db.commit()\n"
        "\n"
        "    # Y a Odoo, en este momento: el visto bueno del consultor es el\n"
        "    # termino general (decision de Salvador, 22 sep). Va despues del\n"
        "    # commit a proposito: el envio ya quedo guardado y un Odoo caido no\n"
        "    # lo deshace; el servicio se queda en la bandeja de por facturar\n"
        "    # con el error a la vista y se reintenta desde ahi.\n"
        "    factura = facturacion.enviar(db, cierre)\n"
        "    db.commit()\n"
        "\n"
        '    return {"resultado": "enviado a finanzas", "cierre_id": cierre.id,\n'
        '            "factura": factura,\n'
        '            "dentro_de_plazo": cierre.dentro_de_plazo,\n',
        marca='            "factura": factura,\n            "dentro_de_plazo"')

cambiar("rcierre",
        "    cierre.estatus = m.EstatusCierre.DEVUELTO_A_OPERACION\n"
        "    cierre.devuelto_motivo = datos.motivo\n",
        "    cierre.estatus = m.EstatusCierre.DEVUELTO_A_OPERACION\n"
        "    cierre.devuelto_motivo = datos.motivo\n"
        "    # Vuelve al consultor: el servicio regresa a sin visto bueno.\n"
        "    if cierre.servicio.estatus == m.EstatusServicio.EN_FACTURACION:\n"
        "        cierre.servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO\n",
        marca="        cierre.servicio.estatus = m.EstatusServicio.SIN_VISTO_BUENO\n")

cambiar("rcierre",
        "    cierre.aprobado_por_id = usuario.persona_id\n"
        "    cierre.servicio.estatus = m.EstatusServicio.CERRADO\n",
        "    cierre.aprobado_por_id = usuario.persona_id\n"
        "    # El cancelado se queda cancelado: cierra su expediente, no cambia\n"
        "    # de estatus.\n"
        "    if cierre.servicio.estatus != m.EstatusServicio.CANCELADO:\n"
        "        cierre.servicio.estatus = m.EstatusServicio.CERRADO\n",
        marca="    if cierre.servicio.estatus != m.EstatusServicio.CANCELADO:\n")

cambiar("rcierre",
        "    # Y a Odoo, que es el paso que faltaba: una factura por servicio, en\n"
        "    # cuanto finanzas aprueba.\n"
        "    #\n"
        "    # Va despues del commit a proposito. El cierre ya quedo aprobado y la\n"
        "    # comision ya se genero: si Odoo no contesta, eso no se puede\n"
        "    # deshacer. El servicio se queda en la bandeja de \"por facturar\" con\n"
        "    # el error a la vista y se reintenta desde ahi.\n"
        "    factura = facturacion.enviar(db, cierre)\n",
        "    # La factura salio con el visto bueno del consultor. Aqui solo se\n"
        "    # reintenta si aquel envio fallo y, si ya esta, el cierre pasa a\n"
        "    # facturado. Va despues del commit a proposito: el cierre ya quedo\n"
        "    # aprobado y la comision ya se genero; si Odoo no contesta, eso no\n"
        "    # se deshace y el servicio sigue en la bandeja de por facturar.\n"
        "    factura = facturacion.enviar(db, cierre)\n",
        marca="    # La factura salio con el visto bueno del consultor. Aqui solo se\n")

cambiar("rcierre",
        '    return {"cierre_id": c.id, "abierto_en": c.abierto_en.isoformat(),\n'
        '            "limite_consultor": c.limite_consultor.isoformat(),\n',
        '    return {"cierre_id": c.id, "abierto_en": c.abierto_en.isoformat(),\n'
        '            "comprobacion_hasta": (c.comprobacion_hasta.isoformat()\n'
        '                                   if c.comprobacion_hasta else None),\n'
        '            "limite_consultor": c.limite_consultor.isoformat(),\n',
        marca='            "comprobacion_hasta": (c.comprobacion_hasta.isoformat()\n')

# ================================================================ facturacion.py
cambiar("facturacion",
        "Una factura por servicio, en cuanto finanzas aprueba el cierre (decision\n"
        "de Salvador, 20 sep): cada folio tiene su factura y la rentabilidad\n"
        "cuadra sola.\n",
        "Una factura por servicio (decision de Salvador, 20 sep): cada folio\n"
        "tiene su factura y la rentabilidad cuadra sola. Sale con el visto bueno\n"
        "del consultor --el termino general del servicio (decision del 22 sep)--\n"
        "y finanzas aprueba despues; `facturado` es el ultimo eslabon, cuando las\n"
        "dos cosas ya pasaron.\n",
        marca="Sale con el visto bueno\ndel consultor")

cambiar("facturacion",
        '        "fecha": (cierre.aprobado_en or datetime.now()).date().isoformat(),\n',
        '        "fecha": (cierre.enviado_en or cierre.aprobado_en\n'
        '                  or datetime.now()).date().isoformat(),\n',
        marca='        "fecha": (cierre.enviado_en or cierre.aprobado_en\n')

cambiar("facturacion",
        "    if cierre.estatus == m.EstatusCierre.FACTURADO:\n"
        '        return {"resultado": "ya estaba facturado",\n'
        '                "factura": cierre.factura_odoo}\n'
        "\n"
        "    if cierre.estatus != m.EstatusCierre.APROBADO:\n"
        '        return {"resultado": "no se factura",\n',
        "    if cierre.estatus == m.EstatusCierre.FACTURADO or cierre.facturado_en:\n"
        "        # Salio con el visto bueno del consultor. Si finanzas ya aprobo,\n"
        "        # el cierre queda facturado: es el ultimo eslabon.\n"
        "        if cierre.estatus == m.EstatusCierre.APROBADO:\n"
        "            cierre.estatus = m.EstatusCierre.FACTURADO\n"
        "            db.flush()\n"
        '        return {"resultado": "ya estaba facturado",\n'
        '                "factura": cierre.factura_odoo}\n'
        "\n"
        "    if cierre.estatus not in (m.EstatusCierre.ENVIADO_FINANZAS,\n"
        "                              m.EstatusCierre.APROBADO):\n"
        '        return {"resultado": "no se factura",\n',
        marca="    if cierre.estatus == m.EstatusCierre.FACTURADO or cierre.facturado_en:\n")

cambiar("facturacion",
        "    cierre.estatus = m.EstatusCierre.FACTURADO\n"
        "    cierre.facturado_en = datetime.now()\n",
        "    # Facturado es el ultimo eslabon: solo cuando finanzas ya aprobo. Si\n"
        "    # la factura sale con el visto bueno del consultor, el cierre sigue\n"
        "    # enviado a finanzas, con su folio ya puesto.\n"
        "    if cierre.estatus == m.EstatusCierre.APROBADO:\n"
        "        cierre.estatus = m.EstatusCierre.FACTURADO\n"
        "    cierre.facturado_en = datetime.now()\n",
        marca="    # Facturado es el ultimo eslabon: solo cuando finanzas ya aprobo. Si\n")

cambiar("facturacion",
        "    filas = (db.query(m.Cierre)\n"
        "             .filter(m.Cierre.estatus == m.EstatusCierre.APROBADO)\n"
        "             .order_by(m.Cierre.aprobado_en).all())\n"
        "    return [{\n"
        '        "cierre_id": c.id,\n',
        "    filas = (db.query(m.Cierre)\n"
        "             .filter(m.Cierre.estatus.in_((m.EstatusCierre.ENVIADO_FINANZAS,\n"
        "                                           m.EstatusCierre.APROBADO)),\n"
        "                     m.Cierre.facturado_en.is_(None))\n"
        "             .order_by(m.Cierre.enviado_en).all())\n"
        "    return [{\n"
        '        "cierre_id": c.id,\n'
        '        "estatus": c.estatus.value,\n'
        '        "enviado_en": c.enviado_en.isoformat() if c.enviado_en else None,\n',
        marca="                     m.Cierre.facturado_en.is_(None))\n")

# ================================================================ routers/servicios.py
cambiar("servicios",
        "# Lo que ya no se puede cancelar: o esta cancelado, o ya se cerro.\n"
        "YA_NO_SE_CANCELA = {m.EstatusServicio.CANCELADO, m.EstatusServicio.CERRADO}\n",
        "# Lo que ya no se puede cancelar: o esta cancelado, o ya termino --el\n"
        "# termino general ya corrio, y con el los relojes--, o ya se cerro.\n"
        "YA_NO_SE_CANCELA = {m.EstatusServicio.CANCELADO, m.EstatusServicio.CERRADO,\n"
        "                    m.EstatusServicio.TERMINADO,\n"
        "                    m.EstatusServicio.SIN_VISTO_BUENO,\n"
        "                    m.EstatusServicio.EN_FACTURACION}\n",
        marca="                    m.EstatusServicio.SIN_VISTO_BUENO,\n"
              "                    m.EstatusServicio.EN_FACTURACION}\n")

cambiar("servicios",
        "    antes = servicio.estatus.value\n"
        "    servicio.estatus = m.EstatusServicio.CANCELADO\n"
        '    auditoria.registrar(db, usuario, servicio, "cancelar servicio",\n',
        "    # La cancelacion es un termino (decision de Salvador, 22 sep). Si\n"
        "    # hay dinero que salio de la caja o dias trabajados, arranca el\n"
        "    # mismo proceso que al terminar: T0 es ahora, los viaticos que\n"
        "    # salieron reciben su plazo y a las 24 h el consultor tiene las\n"
        "    # suyas para revisar la cancelacion. Sin nada que cerrar no hay\n"
        "    # relojes (decision 8). Solo el eventual, por ahora.\n"
        "    trabajados = [j for j in jornadas\n"
        "                  if j.estatus == m.EstatusJornada.TERMINADA]\n"
        "    salieron = [v for v in viaticos\n"
        "                if v.estatus != m.EstatusViatico.CANCELADO]\n"
        "    if servicio.tipo == m.TipoServicio.EVENTUAL and (trabajados or salieron):\n"
        "        from app import cierre as motor_cierre\n"
        "        from app import reloj\n"
        "        from app.operacion import abrir_plazo_del_servicio\n"
        "\n"
        "        momento = reloj.ahora_del_servicio(db, servicio)\n"
        "        abrir_plazo_del_servicio(db, servicio, momento)\n"
        "        motor_cierre.abrir(db, servicio.id, abierto_en=momento,\n"
        "                           motivo=\"cancelacion\")\n"
        "\n"
        "    antes = servicio.estatus.value\n"
        "    servicio.estatus = m.EstatusServicio.CANCELADO\n"
        '    auditoria.registrar(db, usuario, servicio, "cancelar servicio",\n',
        marca="        motor_cierre.abrir(db, servicio.id, abierto_en=momento,\n")

# ================================================================ celery
cambiar("celery",
        '        "aviso-horas-extra": {\n'
        '            "task": "operacion.avisar_horas_extra",\n'
        '            "schedule": crontab(minute="*/5"),\n'
        "        },\n",
        '        "aviso-horas-extra": {\n'
        '            "task": "operacion.avisar_horas_extra",\n'
        '            "schedule": crontab(minute="*/5"),\n'
        "        },\n"
        "        # El segundo reloj del cierre: lo que llego a T1 --o cerro todo\n"
        "        # su dinero antes-- pasa a sin visto bueno y arrancan las 24 h\n"
        "        # del consultor. Lo mueve el reloj, no una persona.\n"
        '        "cierre-avanzar": {\n'
        '            "task": "cierre.avanzar",\n'
        '            "schedule": crontab(minute="*/5"),\n'
        "        },\n",
        marca='        "cierre-avanzar": {\n')

TAREA = '''

@celery.task(name="cierre.avanzar")
def avanzar_cierres():
    """De la comprobacion al visto bueno, cuando toca."""
    from app.db import SessionLocal
    from app import cierre

    db = SessionLocal()
    try:
        return {"movidos": cierre.avanzar_cierres(db)}
    finally:
        db.close()
'''
if '@celery.task(name="cierre.avanzar")' not in textos["celery"]:
    textos["celery"] = textos["celery"].rstrip("\n") + "\n" + TAREA
else:
    saltados.append("celery: la tarea ya estaba")

# ================================================================ revisor
cambiar("revisor",
        "    # --- reloj del consultor\n"
        "    if registro:\n"
        "        restante = (registro.limite_consultor - ahora).total_seconds() / 3600\n",
        "    # --- los dos relojes\n"
        "    if registro and registro.estatus == m.EstatusCierre.ABIERTO:\n"
        "        # Corren las 24 h del personal: el visto bueno todavia no abre.\n"
        "        hasta = registro.comprobacion_hasta\n"
        "        observaciones.append({\n"
        '            "nivel": AVISO, "asunto": "Comprobacion en curso",\n'
        '            "mensaje": (f"El personal tiene hasta el {hasta:%d/%m %H:%M} "\n'
        '                        "para comprobar sus viaticos" if hasta else\n'
        '                        "El personal esta comprobando sus viaticos"),\n'
        '            "accion": "El visto bueno se abre cuando venza ese plazo, o "\n'
        '                      "antes si todos los viaticos ya cerraron."})\n'
        "    elif registro:\n"
        "        restante = (registro.limite_consultor - ahora).total_seconds() / 3600\n",
        marca='            "nivel": AVISO, "asunto": "Comprobacion en curso",\n')

# ================================================================ web
cambiar("util",
        '  terminado: "est_terminado",\n'
        '  cerrado: "est_cerrado",\n',
        '  terminado: "est_terminado",\n'
        '  sin_visto_bueno: "est_sin_visto_bueno",\n'
        '  en_facturacion: "est_en_facturacion",\n'
        '  cerrado: "est_cerrado",\n',
        marca='  sin_visto_bueno: "est_sin_visto_bueno",\n')

cambiar("idioma",
        '    est_terminado: "Terminado",\n'
        '    est_cerrado: "Cerrado",\n',
        '    est_terminado: "Terminado",\n'
        '    est_sin_visto_bueno: "Sin visto bueno",\n'
        '    est_en_facturacion: "En facturación",\n'
        '    srv_fase_comprobacion: "Corre la comprobación de viáticos del personal. El visto bueno se abre cuando termine, o antes si todos los viáticos ya cerraron.",\n'
        '    est_cerrado: "Cerrado",\n',
        marca='    est_sin_visto_bueno: "Sin visto bueno",\n')

cambiar("idioma",
        '    est_terminado: "Finished",\n'
        '    est_cerrado: "Closed",\n',
        '    est_terminado: "Finished",\n'
        '    est_sin_visto_bueno: "Awaiting sign-off",\n'
        '    est_en_facturacion: "Invoicing",\n'
        '    srv_fase_comprobacion: "The team\'s expense window is running. Sign-off opens when it ends, or earlier once every advance is closed.",\n'
        '    est_cerrado: "Closed",\n',
        marca='    est_sin_visto_bueno: "Awaiting sign-off",\n')

cambiar("idioma",
        '    est_terminado: "Terminado",\n'
        '    est_cerrado: "Fechado",\n',
        '    est_terminado: "Terminado",\n'
        '    est_sin_visto_bueno: "Sem aval",\n'
        '    est_en_facturacion: "Em faturamento",\n'
        '    srv_fase_comprobacion: "O prazo de comprovação da equipe está correndo. O aval abre quando ele terminar, ou antes se todos os adiantamentos já fecharam.",\n'
        '    est_cerrado: "Fechado",\n',
        marca='    est_sin_visto_bueno: "Sem aval",\n')

cambiar("consultor",
        '  terminado: "cafe", cerrado: "negro", cancelado: "grave",\n',
        '  terminado: "cafe", sin_visto_bueno: "alerta", en_facturacion: "cafe",\n'
        '  cerrado: "negro", cancelado: "grave",\n',
        marca='sin_visto_bueno: "alerta"')

cambiar("servicio",
        '  if (!["terminado", "cerrado"].includes(servicio.estatus)) {\n'
        '    return h("div", {});\n'
        "  }\n",
        '  if (!["terminado", "sin_visto_bueno", "en_facturacion", "cerrado",\n'
        '        "cancelado"].includes(servicio.estatus)) {\n'
        '    return h("div", {});\n'
        "  }\n",
        marca='  if (!["terminado", "sin_visto_bueno", "en_facturacion", "cerrado",\n')

cambiar("servicio",
        "  let r = null;\n"
        "  let fallo = null;\n"
        "  try {\n"
        "    r = await api.get(`/cierre/servicio/${servicio.id}/revision`);\n",
        "  /* El cancelado solo tiene cierre si habia algo que cerrar: dinero\n"
        "     afuera o dias trabajados. Sin cierre no hay nada que pintar. */\n"
        '  if (!c.existe && servicio.estatus === "cancelado") return h("div", {});\n'
        "\n"
        "  let r = null;\n"
        "  let fallo = null;\n"
        "  try {\n"
        "    r = await api.get(`/cierre/servicio/${servicio.id}/revision`);\n",
        marca='  if (!c.existe && servicio.estatus === "cancelado") return h("div", {});\n')

cambiar("servicio",
        '  if (c.estatus && c.estatus !== "abierto") {\n'
        '    caja.append(h("p", { clase: "gris" },\n'
        '      t("srv_cierre_en").replace("{e}", estatus(c.estatus))));\n'
        "    if (c.factura_error) {\n"
        '      caja.append(aviso(c.factura_error, "alerta"));\n'
        "    }\n"
        "    return caja;\n"
        "  }\n"
        "\n"
        '  const reloj = h("div", { clase: "reloj-cierre" });\n'
        "  pintarReloj(reloj, c.limite, c.momento);\n",
        "  /* Ya con visto bueno --o devuelto por finanzas, que es lo unico que\n"
        "     regresa aqui-- no hay reloj que correr. */\n"
        '  if (c.estatus && !["abierto", "sin_visto_bueno",\n'
        '                     "devuelto_a_operacion"].includes(c.estatus)) {\n'
        '    caja.append(h("p", { clase: "gris" },\n'
        '      t("srv_cierre_en").replace("{e}", estatus(c.estatus))));\n'
        "    if (c.factura_error) {\n"
        '      caja.append(aviso(c.factura_error, "alerta"));\n'
        "    }\n"
        "    return caja;\n"
        "  }\n"
        "\n"
        "  /* El primer reloj: la comprobacion del personal. El boton no se\n"
        "     ofrece todavia; el servidor tampoco lo aceptaria. */\n"
        '  if (c.estatus === "abierto") {\n'
        '    const cuenta = h("div", { clase: "reloj-cierre" });\n'
        "    pintarReloj(cuenta, c.comprobacion_hasta, c.momento);\n"
        '    caja.append(cuenta, h("p", { clase: "gris chico" },\n'
        '      t("srv_fase_comprobacion")));\n'
        "    return caja;\n"
        "  }\n"
        "\n"
        '  const reloj = h("div", { clase: "reloj-cierre" });\n'
        "  pintarReloj(reloj, c.limite, c.momento);\n",
        marca='  if (c.estatus === "abierto") {\n')

# ================================================================ pruebas viejas
cambiar("t_plazo",
        "def _viatico(viatico_id):\n"
        "    from app import models as m\n"
        "    from app.db import SessionLocal\n"
        "    with SessionLocal() as db:\n"
        "        v = db.get(m.AsignacionViatico, viatico_id)\n"
        "        return v.limite_comprobacion, v.jornada.fin_real\n",
        "def _viatico(viatico_id):\n"
        "    from app import models as m\n"
        "    from app.db import SessionLocal\n"
        "    with SessionLocal() as db:\n"
        "        v = db.get(m.AsignacionViatico, viatico_id)\n"
        "        return v.limite_comprobacion, v.jornada.fin_real\n"
        "\n"
        "\n"
        "def _firmado(jornada_id):\n"
        "    from app import models as m\n"
        "    from app.db import SessionLocal\n"
        "    with SessionLocal() as db:\n"
        "        return db.get(m.Jornada, jornada_id).cerrada_a_mano_en\n",
        marca="def _firmado(jornada_id):\n")

cambiar("t_plazo",
        "    assert r.status_code == 200, r.text\n"
        "\n"
        '    limite, fin_real = _viatico(viatico["id"])\n'
        "    assert limite == fin_real + timedelta(hours=24)\n",
        "    assert r.status_code == 200, r.text\n"
        "\n"
        "    # Un dia firmado tres dias tarde no nace vencido: el plazo corre\n"
        "    # desde la firma de la central, no desde la hora de termino que\n"
        "    # asento (decision de Salvador, 22 sep).\n"
        '    limite, fin_real = _viatico(viatico["id"])\n'
        '    firmado = _firmado(j["id"])\n'
        "    assert limite == firmado + timedelta(hours=24)\n"
        "    assert limite > fin_real + timedelta(hours=24)\n",
        marca='    firmado = _firmado(j["id"])\n')

cambiar("t_cierre",
        "    with SessionLocal() as db:\n"
        '        fila = db.get(mo.Cierre, cierre["cierre_id"])\n'
        "        fila.abierto_en = fila.abierto_en - timedelta(days=2)\n"
        "        fila.limite_consultor = fila.limite_consultor - timedelta(days=2)\n"
        "        db.commit()\n",
        "    # Los dos relojes se atrasan: la comprobacion del personal vencio\n"
        "    # hace dos dias, asi que T1 fue entonces y las 24 h del consultor\n"
        "    # se acabaron ayer.\n"
        "    from app import reloj\n"
        "    with SessionLocal() as db:\n"
        '        fila = db.get(mo.Cierre, cierre["cierre_id"])\n'
        "        ahora = reloj.ahora_del_servicio(db, fila.servicio)\n"
        "        fila.abierto_en = ahora - timedelta(days=3)\n"
        "        fila.comprobacion_hasta = ahora - timedelta(days=2)\n"
        "        fila.limite_consultor = ahora - timedelta(days=1)\n"
        "        db.commit()\n",
        marca="        fila.comprobacion_hasta = ahora - timedelta(days=2)\n")

cambiar("t_cierre",
        '    cierre = cliente.post(f"/cierre/servicio/{servicio[\'id\']}/abrir",\n'
        "                          headers=h).json()\n"
        '    envio = cliente.post(f"/cierre/{cierre[\'cierre_id\']}/enviar-finanzas",\n'
        "                         headers=h)\n"
        "    assert envio.status_code == 409, envio.text\n"
        '    asuntos = {o["asunto"] for o in envio.json()["detail"]["observaciones"]}\n'
        '    assert "Viaticos sin cerrar" in asuntos, envio.json()\n',
        '    cierre = cliente.post(f"/cierre/servicio/{servicio[\'id\']}/abrir",\n'
        "                          headers=h).json()\n"
        "    # Mientras corren las 24 h del personal, el visto bueno ni se abre:\n"
        "    # no se le va a pedir al consultor que cierre con descuento un\n"
        "    # dinero que su gente todavia tiene tiempo de comprobar.\n"
        '    envio = cliente.post(f"/cierre/{cierre[\'cierre_id\']}/enviar-finanzas",\n'
        "                         headers=h)\n"
        "    assert envio.status_code == 409, envio.text\n"
        '    assert "comprobacion" in envio.json()["detail"]["mensaje"].lower()\n'
        "\n"
        "    # Vencido el plazo del personal, el visto bueno se abre y el candado\n"
        "    # es el de siempre: con viaticos abiertos no se manda.\n"
        "    from app import cierre as motor\n"
        "    from app import models as mo\n"
        "    from app.db import SessionLocal\n"
        "    with SessionLocal() as db:\n"
        '        fila = db.get(mo.Cierre, cierre["cierre_id"])\n'
        "        assert motor.avanzar(db, fila, fila.comprobacion_hasta)\n"
        "        db.commit()\n"
        '    envio = cliente.post(f"/cierre/{cierre[\'cierre_id\']}/enviar-finanzas",\n'
        "                         headers=h)\n"
        "    assert envio.status_code == 409, envio.text\n"
        '    asuntos = {o["asunto"] for o in envio.json()["detail"]["observaciones"]}\n'
        '    assert "Viaticos sin cerrar" in asuntos, envio.json()\n',
        marca='    assert "comprobacion" in envio.json()["detail"]["mensaje"].lower()\n')

cambiar("t_360",
        '    assert _estatus_servicio(cliente, h, sid) == "terminado", \\\n'
        '        "enviar a finanzas no cierra: cierra finanzas"\n',
        '    assert _estatus_servicio(cliente, h, sid) == "en_facturacion", \\\n'
        '        "el visto bueno manda a facturar; cerrar, cierra finanzas"\n',
        marca='    assert _estatus_servicio(cliente, h, sid) == "en_facturacion", \\\n')

cambiar("t_factura",
        '    """Lo que se factura es lo EJECUTADO, no lo cotizado: la cotizacion\n'
        '    es lo que se ofrecio y el ejecutado lo que de verdad se presto."""\n'
        "    servicio, cierre_id = _cierre_aprobado(cliente, sesion, datos)\n"
        "\n"
        '    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))\n'
        "    assert r.status_code == 200, r.text\n"
        '    assert r.json()["factura"]["resultado"] == "facturado"\n'
        "\n"
        "    assert len(odoo) == 1, odoo\n",
        '    """Lo que se factura es lo EJECUTADO, no lo cotizado: la cotizacion\n'
        "    es lo que se ofrecio y el ejecutado lo que de verdad se presto.\n"
        "\n"
        "    Desde el 22 de septiembre la factura sale con el visto bueno del\n"
        "    consultor --enviar a finanzas--; finanzas aprueba despues y el\n"
        '    cierre queda facturado. Aprobar no la manda dos veces."""\n'
        "    servicio, cierre_id = _cierre_aprobado(cliente, sesion, datos)\n"
        '    assert len(odoo) == 1, "la factura sale con el visto bueno"\n'
        "\n"
        '    r = cliente.post(f"/cierre/{cierre_id}/aprobar", headers=sesion("finanzas"))\n'
        "    assert r.status_code == 200, r.text\n"
        '    assert r.json()["factura"]["resultado"] == "ya estaba facturado"\n'
        "\n"
        '    assert len(odoo) == 1, "aprobar no factura dos veces"\n',
        marca='    assert len(odoo) == 1, "la factura sale con el visto bueno"\n')

cambiar("t_factura",
        "    # Veinticuatro horas desde que se abrio, ni una mas.\n"
        "    from datetime import datetime\n"
        '    abierto = datetime.fromisoformat(c["abierto_en"])\n'
        '    limite = datetime.fromisoformat(c["limite"])\n'
        "    assert round((limite - abierto).total_seconds() / 3600) == 24\n",
        "    # Veinticuatro horas para el personal desde el termino general, y\n"
        "    # veinticuatro para el consultor desde que arranco su reloj --T1,\n"
        "    # cuando el personal termino de comprobar--, ni una mas.\n"
        "    from datetime import datetime\n"
        '    abierto = datetime.fromisoformat(c["abierto_en"])\n'
        '    hasta = datetime.fromisoformat(c["comprobacion_hasta"])\n'
        '    desde = datetime.fromisoformat(c["visto_bueno_desde"])\n'
        '    limite = datetime.fromisoformat(c["limite"])\n'
        "    assert round((hasta - abierto).total_seconds() / 3600) == 24\n"
        "    assert round((limite - desde).total_seconds() / 3600) == 24\n",
        marca='    desde = datetime.fromisoformat(c["visto_bueno_desde"])\n')

# ================================================================ pruebas nuevas
NUEVOS[B / "tests/test_cierre_dos_relojes.py"] = '''# -*- coding: utf-8 -*-
"""El cierre en dos relojes.

Decision de Salvador, 22 de septiembre (PROPUESTA_CIERRE_24H.md). T0 es
el termino general del eventual --el cierre del ultimo dia, o la
cancelacion--. Desde ahi corren las 24 horas del personal para
comprobar, todos con el mismo limite. Al vencer --o antes, si todo el
dinero ya cerro-- llega T1 y corren las 24 horas del consultor. Su
visto bueno manda la factura a Odoo; finanzas aprueba y cierra.

Solo el eventual. El implantado corta a mes y llega en su propia sesion.
"""
from datetime import timedelta

from ayudas import (asignar, cotizar_y_autorizar, crear_servicio, depositar,
                    devolver, ejecutar_jornada, jornada, manana)

PUNTO = {"origen_direccion": "Aeropuerto Benito Juárez, T2",
         "origen_lat": "19.4270", "origen_lon": "-99.1677",
         "geocerca_metros": 250}
H24 = timedelta(hours=24)
MOTIVO = "El equipo se quedó sin batería; confirmado por teléfono"


def _armar(cliente, sesion, datos, dias=1, offset=1300, viaticos=True,
           cotizado=True):
    """Un eventual de `dias` dias con Juan, su unidad y, si se pide, un
    viatico por dia que todavia no sale de la caja."""
    h = sesion("consultor")
    servicio = crear_servicio(
        cliente, h, datos,
        [jornada(manana(offset + i), datos["modalidades"]["full_day"]["id"],
                 **PUNTO) for i in range(dias)],
        consultor_id=datos["personal"]["Ana Solis"]["id"])
    if cotizado:
        cotizar_y_autorizar(
            cliente, h, servicio,
            datos["perfiles"]["conductor_seguridad"]["id"],
            datos["categorias"]["suv_blindada"]["id"])
    juan = datos["personal"]["Juan Ramirez"]["id"]
    vids = []
    for j in servicio["equipos"][0]["jornadas"]:
        asignar(cliente, h, j["id"], persona_id=juan,
                vehiculo_id=datos["suburban"]["id"])
        if viaticos:
            v = cliente.post("/viaticos/asignar", headers=h, json={
                "jornada_id": j["id"], "persona_id": juan,
                "conceptos": [{"concepto": "alimentos", "monto": "900",
                               "origen": "tabulador"}]})
            assert v.status_code in (200, 201), v.text
            vids.append(v.json()["id"])
    return servicio, vids, juan


def _cierre(servicio_id):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        c = db.query(m.Cierre).filter_by(servicio_id=servicio_id).first()
        if not c:
            return None
        return {"id": c.id, "estatus": c.estatus.value,
                "abierto_en": c.abierto_en,
                "comprobacion_hasta": c.comprobacion_hasta,
                "visto_bueno_desde": c.visto_bueno_desde,
                "limite": c.limite_consultor, "motivo": c.motivo_apertura}


def _limites(vids):
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        return [db.get(m.AsignacionViatico, v).limite_comprobacion
                for v in vids]


def _dia(jornada_id):
    """(fin_real, cerrada_a_mano_en, estatus) del dia."""
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        j = db.get(m.Jornada, jornada_id)
        return j.fin_real, j.cerrada_a_mano_en, j.estatus.value


def _estatus(cliente, sesion, servicio_id):
    r = cliente.get(f"/servicios/{servicio_id}", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    return r.json()["estatus"]


def _avanzar(cierre_id, ahora):
    """Lo que hace la tarea de cada cinco minutos, a una hora dada."""
    from app import cierre as motor
    from app import models as m
    from app.db import SessionLocal
    with SessionLocal() as db:
        movio = motor.avanzar(db, db.get(m.Cierre, cierre_id), ahora)
        db.commit()
        return movio


def _ahora_del(servicio_id):
    from app import models as m
    from app import reloj
    from app.db import SessionLocal
    with SessionLocal() as db:
        return reloj.ahora_del_servicio(db, db.get(m.Servicio, servicio_id))


def _sacar_dinero(cliente, sesion, servicio, vids, juan):
    """El viatico sale de la caja: se pide y finanzas lo deposita."""
    for vid in vids:
        r = cliente.post(f"/viaticos/{vid}/solicitar-transferencia",
                         headers=sesion("consultor"))
        assert r.status_code in (200, 201), r.text
    r = depositar(cliente, sesion("finanzas"),
                  servicio["equipos"][0]["id"], juan,
                  referencia=f"SPEI-2R-{servicio['id']}")
    assert r.status_code in (200, 201), r.text


def _devolver_y_cerrar(cliente, sesion, vid, monto="900"):
    r = devolver(cliente, sesion("finanzas"), vid, monto,
                 referencia=f"SPEI-DEV-2R-{vid}")
    assert r.status_code in (200, 201), r.text
    r = cliente.post(f"/viaticos/{vid}/cerrar", headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["resultado"] == "cerrado", r.json()


# ------------------------------------------------------------ T0 y T0 + 24

def test_los_viaticos_vencen_juntos_al_terminar_el_servicio(cliente, sesion,
                                                            datos):
    """Tres dias, tres viaticos, un solo limite: T0 + 24 h. Cerrar los
    dias anteriores ya no abre plazo a nadie."""
    servicio, vids, _ = _armar(cliente, sesion, datos, dias=3, offset=1300)
    dias = servicio["equipos"][0]["jornadas"]
    hj = sesion("juan")

    for d in dias[:2]:
        r = ejecutar_jornada(cliente, hj, d)
        assert r.status_code == 200, r.text
    assert _limites(vids) == [None, None, None], \\
        "el plazo no corre hasta el termino general"
    assert _cierre(servicio["id"]) is None
    assert _estatus(cliente, sesion, servicio["id"]) == "en_curso"

    r = ejecutar_jornada(cliente, hj, dias[2])
    assert r.status_code == 200, r.text
    t0, _, _ = _dia(dias[2]["id"])
    assert _limites(vids) == [t0 + H24] * 3, "todos vencen a la misma hora"

    c = _cierre(servicio["id"])
    assert c["estatus"] == "abierto" and c["motivo"] == "termino"
    assert c["abierto_en"] == t0
    assert c["comprobacion_hasta"] == t0 + H24
    assert c["limite"] == t0 + 2 * H24, "provisional: T1 todavia no llega"
    assert c["visto_bueno_desde"] is None
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"

    # La pantalla lo sabe: fase de comprobacion, con el dinero afuera.
    r = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                    headers=sesion("consultor"))
    assert r.status_code == 200, r.text
    assert r.json()["fase"] == "comprobacion"
    assert r.json()["viaticos_abiertos"] == 3


def test_el_reloj_del_sistema_abre_el_visto_bueno_a_las_24_horas(cliente,
                                                                sesion, datos):
    """A las 23 h no pasa nada y el consultor no puede adelantarse; a las
    24 el cierre queda sin visto bueno, el servicio tambien, y el
    consultor tiene hasta T1 + 24 h."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=1305)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    t0, _, _ = _dia(d["id"])
    c = _cierre(servicio["id"])

    assert _avanzar(c["id"], t0 + timedelta(hours=23)) is False
    assert _cierre(servicio["id"])["estatus"] == "abierto"
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"

    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                         headers=sesion("consultor"),
                         params={"ahora": (t0 + timedelta(hours=23)).isoformat()})
    assert envio.status_code == 409, envio.text
    assert "comprobacion" in envio.json()["detail"]["mensaje"].lower()
    assert envio.json()["detail"]["hasta"] == (t0 + H24).isoformat()

    assert _avanzar(c["id"], t0 + H24) is True
    c = _cierre(servicio["id"])
    assert c["estatus"] == "sin_visto_bueno"
    assert c["visto_bueno_desde"] == t0 + H24
    assert c["limite"] == t0 + 2 * H24
    assert _estatus(cliente, sesion, servicio["id"]) == "sin_visto_bueno"
    # Y no se mueve dos veces.
    assert _avanzar(c["id"], t0 + 3 * H24) is False

    r = cliente.get(f"/cierre/servicio/{servicio['id']}/estado",
                    headers=sesion("consultor"))
    assert r.json()["fase"] == "sin_visto_bueno"


def test_el_barrido_mueve_solo_lo_que_llego_a_su_hora(cliente, sesion, datos):
    """La tarea de Celery recorre todos los cierres abiertos y mueve los
    que ya llegaron a T1; los demas siguen esperando."""
    from app import cierre as motor
    from app.db import SessionLocal

    temprano, _, _ = _armar(cliente, sesion, datos, offset=1310)
    tarde, _, _ = _armar(cliente, sesion, datos, offset=1312)
    for s in (temprano, tarde):
        d = s["equipos"][0]["jornadas"][0]
        assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    t0_temprano = _cierre(temprano["id"])["abierto_en"]

    with SessionLocal() as db:
        movidos = motor.avanzar_cierres(db, t0_temprano + H24)
    assert temprano["folio"] in movidos
    assert tarde["folio"] not in movidos
    assert _cierre(temprano["id"])["estatus"] == "sin_visto_bueno"
    assert _cierre(tarde["id"])["estatus"] == "abierto"


def test_con_todo_el_dinero_cerrado_el_consultor_arranca_antes(cliente, sesion,
                                                              datos):
    """Si todos los viaticos ya cerraron, no hay nada que esperar: T1 es
    ese momento y el consultor tiene 24 h desde ahi."""
    servicio, vids, juan = _armar(cliente, sesion, datos, offset=1315)
    _sacar_dinero(cliente, sesion, servicio, vids, juan)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    t0, _, _ = _dia(d["id"])
    c = _cierre(servicio["id"])

    # Con el dinero afuera, a las dos horas no se mueve.
    assert _avanzar(c["id"], t0 + timedelta(hours=2)) is False

    _devolver_y_cerrar(cliente, sesion, vids[0])
    assert _avanzar(c["id"], t0 + timedelta(hours=2)) is True
    c = _cierre(servicio["id"])
    assert c["visto_bueno_desde"] == t0 + timedelta(hours=2)
    assert c["limite"] == t0 + timedelta(hours=26)


# ------------------------------------------------------------ el visto bueno

def test_el_visto_bueno_manda_a_facturar_y_finanzas_cierra(cliente, sesion,
                                                          datos, monkeypatch):
    """Sin viaticos, el consultor arranca de inmediato. Su visto bueno
    pone el servicio en facturacion y manda la factura --aqui sin Odoo,
    asi que queda por facturar con el error a la vista--. Finanzas
    aprueba y el servicio queda cerrado."""
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, _, _ = _armar(cliente, sesion, datos, offset=1320, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    c = _cierre(servicio["id"])
    h = sesion("consultor")

    envio = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h)
    assert envio.status_code == 200, envio.text
    assert envio.json()["dentro_de_plazo"] is True
    assert envio.json()["factura"]["resultado"] == "sin conexion"
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"
    c = _cierre(servicio["id"])
    assert c["estatus"] == "enviado_finanzas"
    assert c["visto_bueno_desde"] is not None, "T1 llego solo: no habia dinero"
    assert c["limite"] == c["visto_bueno_desde"] + H24

    # Enviado no se envia dos veces.
    otra = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h)
    assert otra.status_code == 409, otra.text

    # En la bandeja de finanzas, esperando Odoo.
    bandeja = cliente.get("/cierre/por-facturar", headers=sesion("finanzas"))
    suyo = next(x for x in bandeja.json()["por_facturar"]
                if x["cierre_id"] == c["id"])
    assert suyo["estatus"] == "enviado_finanzas" and suyo["error"]

    r = cliente.post(f"/cierre/{c['id']}/aprobar", headers=sesion("finanzas"))
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "cerrado"
    assert _cierre(servicio["id"])["estatus"] == "aprobado"


def test_finanzas_devuelve_y_el_servicio_regresa_a_sin_visto_bueno(cliente,
                                                                  sesion, datos,
                                                                  monkeypatch):
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, _, _ = _armar(cliente, sesion, datos, offset=1322, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    c = _cierre(servicio["id"])
    h = sesion("consultor")
    assert cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                        headers=h).status_code == 200

    r = cliente.post(f"/cierre/{c['id']}/devolver", headers=sesion("finanzas"),
                     json={"motivo": "Falta el respaldo de las horas extra"})
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "sin_visto_bueno"

    # El consultor lo vuelve a mandar.
    r = cliente.post(f"/cierre/{c['id']}/enviar-finanzas", headers=h)
    assert r.status_code == 200, r.text
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"


# ------------------------------------------------------------ dias firmados tarde

def test_un_dia_firmado_tarde_no_nace_vencido(cliente, sesion, datos):
    """La central cierra a mano un dia de hace tres dias: T0 es la firma,
    no la hora de termino que asento, y el plazo nace entero."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=-6,
                               cotizado=False)
    d = servicio["equipos"][0]["jornadas"][0]
    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=sesion("central"), json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text

    fin_real, firmado, _ = _dia(d["id"])
    assert firmado > fin_real + timedelta(days=5)
    c = _cierre(servicio["id"])
    assert c["abierto_en"] == firmado
    assert c["comprobacion_hasta"] == firmado + H24
    assert _limites(vids) == [firmado + H24]


# ------------------------------------------------------------ reabrir

def test_reabrir_antes_del_visto_bueno_deshace_el_termino(cliente, sesion,
                                                          datos):
    """El cierre se borra con sus plazos y el servicio vuelve a la calle.
    Al cerrar el dia otra vez nace un T0 nuevo."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=-8,
                               cotizado=False)
    d = servicio["equipos"][0]["jornadas"][0]
    hc = sesion("central")
    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=hc, json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    assert _cierre(servicio["id"]) is not None

    r = cliente.post(f"/operacion/jornadas/{d['id']}/reabrir", headers=hc,
                     json={"justificacion": "Me equivoque de jornada al cerrar"})
    assert r.status_code == 200, r.text
    assert _cierre(servicio["id"]) is None, "el termino se deshizo"
    assert _limites(vids) == [None], "y con el, el plazo del personal"
    assert _estatus(cliente, sesion, servicio["id"]) in ("asignado", "planeado")

    r = cliente.post(f"/operacion/jornadas/{d['id']}/cerrar-a-mano",
                     headers=hc, json={"justificacion": MOTIVO})
    assert r.status_code == 200, r.text
    c = _cierre(servicio["id"])
    assert c and c["estatus"] == "abierto"
    assert _limites(vids) == [c["comprobacion_hasta"]]
    assert _estatus(cliente, sesion, servicio["id"]) == "terminado"


def test_con_el_visto_bueno_dado_ya_no_se_reabre(cliente, sesion, datos,
                                                monkeypatch):
    from app import facturacion
    monkeypatch.setattr(facturacion.settings, "odoo_url", "")

    servicio, _, _ = _armar(cliente, sesion, datos, offset=1325, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    c = _cierre(servicio["id"])
    assert cliente.post(f"/cierre/{c['id']}/enviar-finanzas",
                        headers=sesion("consultor")).status_code == 200

    r = cliente.post(f"/operacion/jornadas/{d['id']}/reabrir",
                     headers=sesion("central"),
                     json={"justificacion": "Me equivoque de jornada al cerrar"})
    assert r.status_code == 409, r.text
    assert "visto bueno" in r.json()["detail"]["mensaje"]
    assert _estatus(cliente, sesion, servicio["id"]) == "en_facturacion"


# ------------------------------------------------------------ cancelar

def test_cancelar_con_dinero_afuera_arranca_los_relojes(cliente, sesion, datos):
    """La cancelacion es un termino: T0 es ahora, el viatico que salio
    recibe su plazo, y cuando vuelve el dinero el consultor tiene sus
    24 h para revisar la cancelacion. El servicio se queda cancelado."""
    servicio, vids, juan = _armar(cliente, sesion, datos, offset=1330)
    _sacar_dinero(cliente, sesion, servicio, vids, juan)
    antes = _ahora_del(servicio["id"])

    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"),
                     json={"motivo": "el cliente canceló el viaje"})
    assert r.status_code == 200, r.text
    assert len(r.json()["viaticos_por_devolver"]) == 1
    assert _estatus(cliente, sesion, servicio["id"]) == "cancelado"

    c = _cierre(servicio["id"])
    assert c and c["motivo"] == "cancelacion"
    assert timedelta(0) <= c["abierto_en"] - antes < timedelta(minutes=5)
    assert c["comprobacion_hasta"] == c["abierto_en"] + H24
    assert _limites(vids) == [c["comprobacion_hasta"]]

    # Con el dinero afuera, el consultor espera.
    assert _avanzar(c["id"], c["abierto_en"] + timedelta(hours=1)) is False

    _devolver_y_cerrar(cliente, sesion, vids[0])
    assert _avanzar(c["id"], c["abierto_en"] + timedelta(hours=1)) is True
    assert _cierre(servicio["id"])["estatus"] == "sin_visto_bueno"
    assert _estatus(cliente, sesion, servicio["id"]) == "cancelado", \\
        "cancelado se queda cancelado: su rastro es el cierre"


def test_cancelar_sin_nada_que_cerrar_no_abre_relojes(cliente, sesion, datos):
    """Sin dinero afuera ni dias trabajados no hay nada que revisar."""
    servicio, vids, _ = _armar(cliente, sesion, datos, offset=1335)
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"),
                     json={"motivo": "el cliente canceló el viaje"})
    assert r.status_code == 200, r.text
    assert _cierre(servicio["id"]) is None
    assert _limites(vids) == [None], "el viatico que no salio se cancelo sin plazo"


def test_un_servicio_terminado_ya_no_se_cancela(cliente, sesion, datos):
    """Terminado es terminado: el termino general ya corrio y con el los
    relojes. Lo que haya que ajustar va por la revision del cierre."""
    servicio, _, _ = _armar(cliente, sesion, datos, offset=1340, viaticos=False)
    d = servicio["equipos"][0]["jornadas"][0]
    assert ejecutar_jornada(cliente, sesion("juan"), d).status_code == 200
    r = cliente.post(f"/servicios/{servicio['id']}/cancelar",
                     headers=sesion("consultor"), json={"motivo": "ya no"})
    assert r.status_code == 409, r.text
'''

cambiar("t_zona",
        '    abierto = datetime.fromisoformat(r.json()["abierto_en"])\n'
        '    limite = datetime.fromisoformat(r.json()["limite_consultor"])\n'
        '    # 24 horas exactas, y contadas desde la hora de São Paulo.\n'
        '    assert round((limite - abierto).total_seconds() / 3600) == 24\n',
        '    abierto = datetime.fromisoformat(r.json()["abierto_en"])\n'
        '    hasta = datetime.fromisoformat(r.json()["comprobacion_hasta"])\n'
        '    limite = datetime.fromisoformat(r.json()["limite_consultor"])\n'
        '    # 24 horas exactas para el personal, contadas desde la hora de São\n'
        '    # Paulo; las del consultor, provisionales en 48 hasta que llegue T1.\n'
        '    assert round((hasta - abierto).total_seconds() / 3600) == 24\n'
        '    assert round((limite - abierto).total_seconds() / 3600) == 48\n',
        marca='    hasta = datetime.fromisoformat(r.json()["comprobacion_hasta"])\n')

# ================================================================ bitacora
cambiar("bitacora",
        "## 14. Lo que falta\n",
        "## 50. El cierre en dos relojes\n"
        "\n"
        "Decisión de Salvador, 22 de septiembre (`PROPUESTA_CIERRE_24H.md`).\n"
        "Primera de tres sesiones: reglas, reloj y pruebas del eventual.\n"
        "\n"
        "- **T0, el término general.** La hora real de término del último\n"
        "  día del eventual —o la firma, si la central lo cerró tarde: un\n"
        "  plazo que nace vencido no es un plazo— o el momento de cancelar.\n"
        "  En T0 todos los viáticos del servicio reciben el mismo límite,\n"
        "  T0 + 24 h; cerrar un día intermedio ya no abre plazo. Se respeta\n"
        "  el del relevado, que corre desde su relevo.\n"
        "- **T1, el segundo reloj.** Lo pone la tarea `cierre.avanzar` cada\n"
        "  cinco minutos: al vencer las 24 h del personal —o antes, si todos\n"
        "  los viáticos ya cerraron, se devolvieron o se cancelaron— el cierre\n"
        "  y el servicio pasan a **sin visto bueno** y el consultor tiene hasta\n"
        "  T1 + 24 h; de ahí depende su comisión. Mientras corre la\n"
        "  comprobación el visto bueno ni se abre: no se le pide al consultor\n"
        "  cerrar con descuento un dinero que su gente todavía puede comprobar.\n"
        "- **El visto bueno es el término general.** Al enviar a finanzas el\n"
        "  servicio pasa a **en facturación** y la factura sale a Odoo en ese\n"
        "  momento; si Odoo no contesta queda en *por facturar* con el error a\n"
        "  la vista. Finanzas aprueba, cierra el expediente y detona la\n"
        "  comisión; *facturado* es el último eslabón, cuando las dos cosas ya\n"
        "  pasaron. Devolver a operación regresa el servicio a sin visto bueno.\n"
        "- **Cancelar es un término.** Con dinero afuera o días trabajados,\n"
        "  cancelar arranca los mismos relojes con T0 = ahora y el consultor\n"
        "  revisa la cancelación; sin nada que cerrar no hay relojes. El\n"
        "  servicio se queda *cancelado*; su rastro es el cierre. Un servicio\n"
        "  terminado ya no se cancela.\n"
        "- **Reabrir un día** antes del visto bueno deshace el término: el\n"
        "  cierre se borra con sus plazos y el servicio vuelve a la calle; con\n"
        "  el visto bueno dado ya no se reabre.\n"
        "- **Lo ya terminado no se toca**: un cierre nacido antes conserva su\n"
        "  plazo de siempre. **El implantado no se toca**: sigue día por día\n"
        "  hasta la sesión del cierre por mes.\n"
        "\n"
        "Pendiente para las sesiones que siguen: el cierre por mes del\n"
        "implantado; la consola con la fase y sus relojes, la app con\n"
        "«por comprobar» sin fecha hasta el término, la bandeja de finanzas,\n"
        "el panorama, el bono de puntualidad contra el nuevo límite y el\n"
        "candado de cerrar con descuento antes de que venza el plazo del\n"
        "personal.\n"
        "\n"
        "## 14. Lo que falta\n",
        marca="## 50. El cierre en dos relojes\n")

# ================================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(textos[clave])
        print("escrito ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for ruta, contenido in NUEVOS.items():
    if ruta.exists() and io.open(ruta, encoding="utf-8").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("escrito ", ruta.relative_to(RAIZ))
for s in saltados:
    print("saltado:", s)
