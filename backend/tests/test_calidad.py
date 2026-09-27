"""La pantalla de Calidad y su reporte (seccion 89).

Agosto de 2026 en Mexico, armado a mano para que cada cifra se pueda
contar con el dedo, y julio para compararlo. Cada cifra se mide con la
regla que ya existe donde la hay --la del bono, la del plazo del
consultor--: aqui se revisa que la pantalla diga lo mismo.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app import calidad, excel
from app import models as m
from app.reloj import zona

MX = zona("America/Mexico_City")
AHORA = datetime(2026, 9, 27, 12, 0)      # hora de pared de Mexico


def _en_mx(*a) -> datetime:
    return datetime(*a, tzinfo=MX)


class Mes:
    """Arma servicios, marcas y lo demas directo en la base."""

    def __init__(self, db: Session, datos):
        self.db, self.datos = db, datos
        self.n = 0

    def persona(self, nombre) -> int:
        return self.datos["personal"][nombre]["id"]

    def servicio(self, dia: date, consultor: str, estatus=m.EstatusJornada.TERMINADA):
        self.n += 1
        s = m.Servicio(folio=f"CAL-{self.n:02d}", cliente_id=self.datos["cliente_id"],
                       pais_id=self.datos["mx"]["id"],
                       plaza_id=self.datos["cdmx"]["id"],
                       tipo=m.TipoServicio.EVENTUAL,
                       estatus=m.EstatusServicio.TERMINADO,
                       consultor_id=self.persona(consultor))
        self.db.add(s)
        self.db.flush()
        e = m.Equipo(servicio_id=s.id, clave="EQ-1")
        self.db.add(e)
        self.db.flush()
        j = m.Jornada(equipo_id=e.id, fecha=dia,
                      modalidad_id=self.datos["modalidades"]["full_day"]["id"],
                      inicio_programado=datetime.combine(dia, datetime.min.time())
                      + timedelta(hours=8),
                      fin_programado=datetime.combine(dia, datetime.min.time())
                      + timedelta(hours=18),
                      estatus=estatus)
        self.db.add(j)
        self.db.flush()
        return s, j

    def gente(self, j, nombre):
        self.db.add(m.AsignacionPersonal(jornada_id=j.id, persona_id=self.persona(nombre)))

    def marca(self, j, nombre, tipo, hora, minuto, **extra):
        h = m.Hito(jornada_id=j.id, persona_id=self.persona(nombre), tipo=tipo,
                   marcado_en=datetime.combine(j.fecha, datetime.min.time())
                   + timedelta(hours=hora, minutes=minuto), **extra)
        self.db.add(h)
        return h

    def dia_completo(self, j, nombre, llegada=(7, 50), **extra):
        self.gente(j, nombre)
        self.marca(j, nombre, m.TipoHito.LLEGADA_ORIGEN, *llegada,
                   dentro_geocerca=True, **extra)
        self.marca(j, nombre, m.TipoHito.CONTACTO_EJECUTIVO, 8, 5)
        self.marca(j, nombre, m.TipoHito.FIN_SERVICIO, 17, 0)

    def alerta(self, j, tipo, nombre=None, mensaje="aviso de prueba"):
        self.db.add(m.Alerta(jornada_id=j.id, tipo=tipo, mensaje=mensaje,
                             persona_id=self.persona(nombre) if nombre else None))

    def encuesta(self, s, enviada, calificacion=None, tipo=m.TipoEncuesta.EJECUTIVO,
                 estatus=m.EstatusEncuesta.RESPONDIDA, clasificada=False):
        self.n += 1
        self.db.add(m.Encuesta(
            servicio_id=s.id, tipo=tipo, token=f"cal-{self.n}",
            expira_en=enviada.replace(tzinfo=None) + timedelta(days=15),
            enviada_en=enviada, estatus=estatus, calificacion=calificacion,
            respondida_en=(enviada.replace(tzinfo=None) + timedelta(days=1)
                           if calificacion else None),
            requiere_clasificacion=bool(calificacion and calificacion <= 3),
            clasificada_en=(enviada.replace(tzinfo=None) + timedelta(days=2)
                            if clasificada else None),
            consultor_id=(s.consultor_id if tipo == m.TipoEncuesta.SOLICITANTE
                          else None)))

    def cierre(self, s, limite, dentro=None, estatus=m.EstatusCierre.ENVIADO_FINANZAS):
        self.db.add(m.Cierre(servicio_id=s.id, abierto_en=limite - timedelta(hours=48),
                             limite_consultor=limite, estatus=estatus,
                             dentro_de_plazo=dentro,
                             visto_bueno_en=(limite - timedelta(hours=2) if dentro
                                             else limite + timedelta(hours=5)
                                             if dentro is False else None)))


@pytest.fixture
def agosto(base_de_pruebas, datos):
    """Julio con un dia bueno; agosto con de todo un poco."""
    with Session(base_de_pruebas) as db:
        x = Mes(db, datos)

        # ------------------------------------------------ julio, para comparar
        s0, j0 = x.servicio(date(2026, 7, 20), "Ana Solis")
        x.dia_completo(j0, "Juan Ramirez")
        x.encuesta(s0, _en_mx(2026, 7, 21, 10), 4)
        x.cierre(s0, datetime(2026, 7, 22, 10), dentro=True)

        # ------------------------------------------------ agosto
        # 10: Juan a tiempo y completo; Luis tarde, completo.
        s1, j1 = x.servicio(date(2026, 8, 10), "Ana Solis")
        x.dia_completo(j1, "Juan Ramirez")
        x.dia_completo(j1, "Luis Mendoza", llegada=(8, 12))
        x.db.add(m.AsignacionVehiculo(jornada_id=j1.id,
                                      vehiculo_id=datos["suburban"]["id"]))
        # 12: Carlos marco fuera del punto y no cerro; dos intentos lejos.
        s2, j2 = x.servicio(date(2026, 8, 12), "Beatriz Roman")
        x.gente(j2, "Carlos Vega")
        x.marca(j2, "Carlos Vega", m.TipoHito.LLEGADA_ORIGEN, 7, 40,
                dentro_geocerca=False)
        x.marca(j2, "Carlos Vega", m.TipoHito.CONTACTO_EJECUTIVO, 8, 5)
        x.alerta(j2, m.TipoAlerta.FUERA_DE_GEOCERCA, "Carlos Vega", "a 900 m del punto")
        x.alerta(j2, m.TipoAlerta.FUERA_DE_GEOCERCA, "Carlos Vega", "a 700 m del punto")
        # 15: la llegada de Miguel la asento la central (no se mide); se
        # quedo callado dos horas; su contacto espera a la central.
        s3, j3 = x.servicio(date(2026, 8, 15), "Ana Solis")
        x.gente(j3, "Miguel Torres")
        x.marca(j3, "Miguel Torres", m.TipoHito.LLEGADA_ORIGEN, 7, 30,
                dentro_geocerca=True, registrado_a_mano_en=datetime(2026, 8, 15, 9))
        x.marca(j3, "Miguel Torres", m.TipoHito.CONTACTO_EJECUTIVO, 8, 20,
                requiere_revision=True)
        x.marca(j3, "Miguel Torres", m.TipoHito.FIN_SERVICIO, 17, 0)
        x.marca(j3, "Miguel Torres", m.TipoHito.STANDBY, 12, 0,
                requiere_revision=True, anulado_en=datetime(2026, 8, 15, 13))
        x.alerta(j3, m.TipoAlerta.SIN_REPORTE)
        # 20: Juan a tiempo; lo relevo Luis por enfermedad. La unidad se
        # recibio con su revision y volvio golpeada.
        s4, j4 = x.servicio(date(2026, 8, 20), "Ana Solis")
        x.dia_completo(j4, "Juan Ramirez", llegada=(7, 59))
        otra = next(v for v in datos["vehiculos"] if v["id"] != datos["suburban"]["id"])
        x.db.add(m.AsignacionVehiculo(jornada_id=j4.id, vehiculo_id=otra["id"]))
        for tipo, dano, hora in ((m.TipoRevision.RECIBE, False, 7),
                                 (m.TipoRevision.ENTREGA, True, 18)):
            x.db.add(m.RevisionUnidad(servicio_id=s4.id, vehiculo_id=otra["id"],
                                      persona_id=x.persona("Juan Ramirez"),
                                      tipo=tipo.value, hubo_dano=dano,
                                      momento=datetime(2026, 8, 20, hora)))
        x.db.add(m.ReemplazoRecurso(servicio_id=s4.id, desde_jornada_id=j4.id,
                                    tipo=m.TipoRecurso.PERSONAL,
                                    motivo_tipo=m.MotivoCambio.ENFERMEDAD,
                                    motivo="Se enfermo a media jornada",
                                    sale_persona_id=x.persona("Juan Ramirez"),
                                    entra_persona_id=x.persona("Luis Mendoza")))
        x.db.add(m.ReemplazoRecurso(servicio_id=s4.id, desde_jornada_id=j4.id,
                                    tipo=m.TipoRecurso.VEHICULO,
                                    motivo_tipo=m.MotivoCambio.MANTENIMIENTO_PREVENTIVO,
                                    motivo="Afinacion", sale_vehiculo_id=otra["id"],
                                    entra_vehiculo_id=datos["suburban"]["id"]))
        # 21: cancelado, no cuenta para nada.
        _, j5 = x.servicio(date(2026, 8, 21), "Ana Solis",
                           estatus=m.EstatusJornada.CANCELADA)
        x.gente(j5, "Juan Ramirez")

        # Lo que dijo el cliente.
        x.encuesta(s1, _en_mx(2026, 8, 11, 10), 5)
        x.encuesta(s2, _en_mx(2026, 8, 13, 10), 2)
        x.encuesta(s3, _en_mx(2026, 8, 16, 10), 3, clasificada=True)
        x.encuesta(s4, _en_mx(2026, 8, 21, 10), estatus=m.EstatusEncuesta.EXPIRADA)
        x.encuesta(s1, _en_mx(2026, 8, 11, 10), 4, tipo=m.TipoEncuesta.SOLICITANTE)

        # El cierre: uno en plazo, uno tarde, uno vencido sin visto bueno y
        # uno que vence en septiembre.
        x.cierre(s1, datetime(2026, 8, 12, 10), dentro=True)
        x.cierre(s2, datetime(2026, 8, 14, 10), dentro=False)
        x.cierre(s3, datetime(2026, 8, 17, 10), estatus=m.EstatusCierre.SIN_VISTO_BUENO)
        x.cierre(s4, datetime(2026, 9, 2, 10), dentro=True)
        finanzas = db.query(m.Usuario).filter_by(correo="finanzas@centauro.lat").one()
        db.add(m.RegistroAccion(servicio_id=s1.id, usuario_id=finanzas.id,
                                persona_id=finanzas.persona_id, rol=finanzas.rol,
                                accion="devolver a operacion",
                                detalle=f"{s1.folio}: Falta el comprobante del hotel",
                                creado_en=_en_mx(2026, 8, 13, 12)))

        # La gente.
        ana = x.persona("Ana Solis")
        G = m.GravedadIncidencia
        for nombre, gravedad, autorizada, visto in (
                ("Juan Ramirez", G.LEVE, True, True),
                ("Luis Mendoza", G.ERROR_MENOR, True, True),
                ("Carlos Vega", G.GRAVE, False, False),
                ("Miguel Torres", G.LEVE, False, True)):
            db.add(m.Incidencia(persona_id=x.persona(nombre), fecha=date(2026, 8, 14),
                                gravedad=gravedad, autorizada=autorizada,
                                descripcion="Descripcion de la incidencia de prueba",
                                clasificada_por_id=ana,
                                visto_bueno_por_id=ana if visto else None))
        for nombre, hasta in (("Juan Ramirez", date(2026, 8, 15)),
                              ("Luis Mendoza", date(2026, 12, 31)),
                              ("Carlos Vega", date(2026, 9, 10))):
            db.add(m.Capacitacion(persona_id=x.persona(nombre),
                                  nombre="Manejo defensivo", vigencia_hasta=hasta))
        criterios = (db.query(m.CriterioEstrella)
                     .filter_by(pais_id=datos["mx"]["id"]).limit(3).all())
        assert len(criterios) == 3
        for nombre, estrellas, anulado in (("Juan Ramirez", 3, False),
                                           ("Luis Mendoza", 2, False),
                                           ("Carlos Vega", 3, True)):
            ev = m.EvaluacionMensual(persona_id=x.persona(nombre), anio=2026, mes=8,
                                     estrellas=estrellas, moneda=m.Moneda.MXN,
                                     anulado_por_incidencia=anulado)
            db.add(ev)
            db.flush()
            for i, c in enumerate(criterios):
                db.add(m.ResultadoCriterio(evaluacion_id=ev.id, criterio_id=c.id,
                                           valor_medido=100, umbral=100,
                                           cumplido=i < estrellas, aplica=True))
        db.commit()
        return {"s1": s1.id, "s2": s2.id, "s3": s3.id}


def _reporte(base_de_pruebas, datos, idioma="es"):
    with Session(base_de_pruebas) as db:
        return calidad.reporte(db, datos["mx"]["id"], 2026, 8, idioma, ahora=AHORA)


def _renglon(r, bloque, clave):
    b = next(x for x in r["bloques"] if x["clave"] == bloque)
    return next(x for x in b["renglones"] if x["clave"] == clave)


def _nota(renglon):
    return " · ".join(p["t"] for p in renglon["nota"])


# ================================================== las cinco de arriba

def test_las_cinco_de_arriba_contra_julio(base_de_pruebas, datos, agosto):
    r = _reporte(base_de_pruebas, datos)
    arriba = {x["clave"]: x for x in r["arriba"]}
    # (5 + 2 + 3) / 3; la vencida no califica.
    assert arriba["satisfaccion"]["valor"] == "3.3"
    assert arriba["satisfaccion"]["comparacion"] == {"t": "▼ julio: 4.0",
                                                     "tono": "alerta"}
    # A tiempo: Juan dos veces. Luis tarde, Carlos fuera del punto; la de
    # Miguel la asento la central y no se mide. El cancelado no cuenta.
    assert arriba["puntualidad"]["texto"] == "Puntualidad · 2 de 4 jornadas"
    assert arriba["puntualidad"]["valor"] == "50 %"
    assert arriba["puntualidad"]["comparacion"]["t"] == "▼ julio: 100 %"
    # Completos: Juan dos veces y Luis. Carlos no cerro; Miguel se quedo
    # callado.
    assert arriba["reporte"]["texto"] == "Jornadas con su reporte completo · 3 de 5"
    # En plazo uno de tres: el de septiembre no es de agosto.
    assert arriba["cierres"]["texto"] == "Cierres en 24 horas · 1 de 3"
    assert arriba["cierres"]["valor"] == "33 %"
    assert arriba["bajas"]["valor"] == "2"
    assert arriba["bajas"]["comparacion"]["t"] == "1 sin revisar"


def test_lo_que_dijo_el_cliente(base_de_pruebas, datos, agosto):
    r = _reporte(base_de_pruebas, datos)
    contestaron = _renglon(r, "cliente", "contestaron")
    assert contestaron["valor"] == "3 de 4"
    assert _nota(contestaron) == "1 se venció sin contestar"
    bajas = _renglon(r, "cliente", "bajas")
    assert _nota(bajas) == "1 no castiga · 1 sin revisar"
    assert [f[1]["servicio"] for f in bajas["ver"]["filas"]] == [agosto["s2"],
                                                                 agosto["s3"]]
    assert [f[2]["t"] for f in bajas["ver"]["filas"]] == ["2", "3"]
    solicitantes = _renglon(r, "cliente", "solicitantes")
    assert solicitantes["valor"] == "4.0"
    assert _nota(solicitantes) == "1 respuesta"


def test_en_la_calle(base_de_pruebas, datos, agosto):
    r = _reporte(base_de_pruebas, datos)
    lejos = _renglon(r, "calle", "lejos")
    assert lejos["valor"] == "2"
    assert _nota(lejos) == "1 persona · Carlos Vega, 2"
    # La anulada ya no espera a nadie.
    assert _renglon(r, "calle", "por_validar")["valor"] == "1"
    # El mantenimiento preventivo estaba en el calendario: no es
    # contingencia.
    relevos = _renglon(r, "calle", "relevos")
    assert relevos["valor"] == "1"
    assert _nota(relevos) == "1 de personal"
    unidades = _renglon(r, "calle", "unidades")
    assert unidades["valor"] == "1"
    assert _nota(unidades) == "1 volvió con daño nuevo"


def test_el_cierre(base_de_pruebas, datos, agosto):
    r = _reporte(base_de_pruebas, datos)
    tarde = _renglon(r, "cierre", "tarde")
    assert tarde["valor"] == "2"
    assert _nota(tarde) in ("Ana Solis 1 · Beatriz Roman 1",
                            "Beatriz Roman 1 · Ana Solis 1")
    visto = {f[0]["t"]: f[3]["t"] for f in tarde["ver"]["filas"]}
    assert "sin visto bueno" in visto.values()
    regresados = _renglon(r, "cierre", "regresados")
    assert regresados["valor"] == "1"
    assert regresados["ver"]["filas"][0][3]["t"] == "Falta el comprobante del hotel"
    # Sin dinero con plazo en agosto: no hay que medir.
    assert _renglon(r, "cierre", "viaticos")["valor"] == "—"


def test_la_gente(base_de_pruebas, datos, agosto):
    r = _reporte(base_de_pruebas, datos)
    inc = _renglon(r, "gente", "incidencias")
    # La leve de Juan; la de Miguel se descarto y la grave de Carlos
    # espera su visto bueno.
    assert inc["valor"] == "1"
    assert _nota(inc) == "1 leve · 1 error menor · 1 por autorizar"
    cert = _renglon(r, "gente", "certificados")
    # Juan trabajo el 20 con el curso vencido el 15; el de Carlos vence
    # el 10 de septiembre.
    assert cert["valor"] == "1"
    assert _nota(cert) == "personas trabajando con su curso vencido · 1 vence en 30 días"
    assert cert["ver"]["filas"][0][0]["t"] == "Juan Ramirez"
    bono = _renglon(r, "gente", "bono")
    assert bono["texto"] == "Bono completo en agosto"
    # El anulado por incidencia no es completo aunque traiga sus estrellas.
    assert bono["valor"] == "33 %"
    assert _nota(bono) == "1 de 3 personas · 1 sin bono por incidencia"
    prof = _renglon(r, "gente", "profesionalismo")
    assert prof["valor"] == "—"


def test_en_ingles_y_portugues(base_de_pruebas, datos, agosto):
    en = _reporte(base_de_pruebas, datos, "en")
    assert en["arriba"][1]["texto"] == "Punctuality · 2 of 4 days"
    assert en["arriba"][0]["comparacion"]["t"] == "▼ July: 4.0"
    pt = _reporte(base_de_pruebas, datos, "pt")
    assert pt["arriba"][0]["valor"] == "3,3"
    assert _renglon(pt, "cliente", "contestaron")["valor"] == "3 de 4"


# ================================================== quien la ve

@pytest.mark.parametrize("quien,codigo", [
    ("dirgeneral", 200), ("diroperaciones", 200), ("admin", 200),
    ("consultor", 403), ("central", 403), ("finanzas", 403), ("rrhh", 403)])
def test_quien_la_ve(cliente, sesion, quien, codigo):
    r = cliente.get("/calidad", headers=sesion(quien))
    assert r.status_code == codigo, r.text


def test_la_pantalla_y_el_excel(cliente, sesion, datos, agosto):
    h = sesion("diroperaciones")
    r = cliente.get(f"/calidad?pais_id={datos['mx']['id']}&mes=2026-08", headers=h)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["mes"] == "2026-08" and cuerpo["en_curso"] is False
    assert "detalles" not in cuerpo
    assert cuerpo["opciones"]["paises"]
    # Un mes que no ha llegado se vuelve el de hoy.
    r = cliente.get("/calidad?mes=2999-01", headers=h)
    assert r.json()["en_curso"] is True

    r = cliente.get(f"/calidad/excel?pais_id={datos['mx']['id']}&mes=2026-08",
                    headers=h)
    assert r.status_code == 200, r.text
    assert 'filename="calidad_mx_2026-08.xlsx"' in r.headers["content-disposition"]
    hojas = excel.leer(r.content)
    resumen = hojas["Resumen 2026-08"]
    assert resumen[0]["C"] == "agosto 2026" and resumen[0]["D"] == "julio 2026"
    fila = next(f for f in resumen if f.get("B", "").startswith("Puntualidad"))
    # Como numero: 0.5 se lee 50 % en Excel.
    assert fila["C"] == "0.5000" and fila["D"] == "1.0000"
    assert "Cierres tarde" in hojas and "Incidencias" in hojas
    assert any(f.get("B") == "Falta el comprobante del hotel"
               or "Falta el comprobante del hotel" in f.values()
               for f in hojas["Regresos"])


def test_los_datos_del_combustible_de_ejemplo(base_de_pruebas, datos):
    """El sistema arranca con $24.50: mientras nadie lo cambie, se dice."""
    with Session(base_de_pruebas) as db:
        r = calidad.reporte(db, datos["mx"]["id"], 2026, 8, "es", ahora=AHORA)
    textos = [c["t"] for c in r["datos"]["catalogos"]["cosas"]]
    assert ("El combustible sigue en el de ejemplo: $24.50 por litro desde el "
            "1 de enero") in textos
    # Los pesos se vacian entre pruebas: sin los suyos, son los de ejemplo.
    assert "Los pesos del profesionalismo son los de ejemplo" in textos


# ================================================== el menu

def test_la_pantalla_esta_en_el_menu_de_quien_la_ve(cliente, sesion):
    from app import permisos, puestos_base
    assert "calidad" in permisos.PANTALLAS
    for nombre in ("Dirección de operaciones", "Administración del sistema y calidad"):
        p = next(x for x in puestos_base.PUESTOS if x["nombre"] == nombre)
        assert "calidad" in p["pantallas"], nombre
        assert "calidad.ver" in p["actividades"], nombre


def test_bonos_el_anulado_no_es_completo(cliente, sesion, datos, agosto):
    """Bonos contaba el mes anulado por incidencia como completo y en cero
    a la vez: con sus estrellas intactas y el bono en cero."""
    r = cliente.get(f"/mes/{datos['mx']['id']}/2026/8",
                    headers=sesion("dirgeneral"))
    assert r.status_code == 200, r.text
    assert r.json()["bono_completo"] == 1
