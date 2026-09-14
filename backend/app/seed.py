"""Carga inicial de catalogos.

Los MONTOS son de ejemplo y estan pensados para reemplazarse con los reales
de Centauro. La estructura si es la definitiva.
Es idempotente: se puede correr varias veces sin duplicar.
"""
from datetime import date
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app import models as m
from app.db import SessionLocal


def _obtener_o_crear(db: Session, modelo, filtro: dict, valores: dict | None = None):
    obj = db.query(modelo).filter_by(**filtro).first()
    if obj:
        return obj, False
    obj = modelo(**{**filtro, **(valores or {})})
    db.add(obj)
    db.flush()
    return obj, True


def sembrar() -> dict:
    db = SessionLocal()
    creados = {}
    try:
        # ---------------------------------------------------- paises
        mx, _ = _obtener_o_crear(db, m.Pais, {"codigo": "MX"},
                                 {"nombre": "Mexico", "moneda_local": m.Moneda.MXN,
                                  "lada": "+52"})
        br, _ = _obtener_o_crear(db, m.Pais, {"codigo": "BR"},
                                 {"nombre": "Brasil", "moneda_local": m.Moneda.BRL,
                                  "lada": "+55"})
        # Por si la base ya existia antes de que hubiera lada.
        for pais, lada in ((mx, "+52"), (br, "+55")):
            if not pais.lada:
                pais.lada = lada

        # ------------------------------------- plazas con recurso local
        # Estas cuatro son la operacion de todos los dias: van fijas en la
        # lista, con servicio esta semana o sin el.
        for nombre in ["Ciudad de Mexico", "Guadalajara", "Queretaro", "Monterrey"]:
            _obtener_o_crear(db, m.Plaza, {"pais_id": mx.id, "nombre": nombre},
                             {"tiene_recurso_local": True, "fija": True})
        _obtener_o_crear(db, m.Plaza, {"pais_id": br.id, "nombre": "Sao Paulo"},
                         {"tiene_recurso_local": True})

        # ---------------------------------------------------- perfiles de personal
        perfiles = {}
        # Los cuatro roles con los que se cubre un servicio. Son roles
        # de la tarea, no puestos de la persona: el consultor decide con
        # cual va cada quien, y de ahi salen el precio al cliente y la
        # comision que se le paga.
        for codigo, nombre in [
            ("conductor_seguridad", "Conductor de seguridad"),
            ("agente_seguridad", "Agente de seguridad"),
            ("coordinador_seguridad", "Coordinador de seguridad"),
            ("consultor_seguridad", "Consultor de seguridad"),
        ]:
            obj, _ = _obtener_o_crear(db, m.PerfilPersonal, {"codigo": codigo},
                                      {"nombre": nombre})
            perfiles[codigo] = obj

        # ---------------------------------------------------- categorias de vehiculo
        categorias = {}
        for codigo, nombre, blindado, rend in [
            # Las categorias son de Centauro, no de una marca: el mismo
            # servicio se cubre con la SUV que haya disponible.
            ("cuv", "CUV", False, "12.0"),
            ("minivan", "Minivan", False, "10.0"),
            ("minivan_blindada", "Minivan Blindada", True, "7.5"),
            ("suv", "SUV", False, "7.0"),
            ("suv_blindada", "SUV Blindada", True, "5.5"),
            ("van_10", "Van 10 pax", False, "8.5"),
        ]:
            obj, _ = _obtener_o_crear(db, m.CategoriaVehiculo, {"codigo": codigo},
                                      {"nombre": nombre, "blindado": blindado,
                                       "rendimiento_km_litro": D(rend)})
            categorias[codigo] = obj

        # ---------------------------------------------------- modalidades por pais
        # Mexico: 12 horas con 4 de descanso. Horas extra solo en full day.
        mods_mx = {}
        # Los km son el recorrido tipico del dia, para proponer el
        # combustible sin que nadie adivine.
        for codigo, horas, descanso, he, bloquea, km in [
            (m.CodigoModalidad.FULL_DAY, "12", "4", True, True, 150),
            (m.CodigoModalidad.MEDIO_DIA, "5", "0", False, False, 80),
            (m.CodigoModalidad.TRANSFER, "3", "0", False, False, 40),
        ]:
            obj, _ = _obtener_o_crear(
                db, m.Modalidad, {"pais_id": mx.id, "codigo": codigo},
                {"horas": D(horas), "horas_descanso": D(descanso),
                 "aplica_horas_extra": he, "bloquea_dia_completo": bloquea,
                 "km_estimados": km})
            mods_mx[codigo.value] = obj

        # Brasil: eventual 10 horas con 2 de descanso.
        for codigo, horas, descanso, he, bloquea, km in [
            (m.CodigoModalidad.FULL_DAY, "10", "2", True, True, 150),
            (m.CodigoModalidad.MEDIO_DIA, "5", "0", False, False, 80),
            (m.CodigoModalidad.TRANSFER, "3", "0", False, False, 40),
        ]:
            _obtener_o_crear(
                db, m.Modalidad, {"pais_id": br.id, "codigo": codigo},
                {"horas": D(horas), "horas_descanso": D(descanso),
                 "aplica_horas_extra": he, "bloquea_dia_completo": bloquea})

        # ---------------------------------------------------- tarifario general Mexico
        tarifario, _ = _obtener_o_crear(
            db, m.Tarifario, {"nombre": "General Mexico", "pais_id": mx.id},
            {"moneda": m.Moneda.MXN, "vigencia_desde": date(2026, 1, 1)})

        # MONTOS DE EJEMPLO - reemplazar con el tarifario real
        # Los cuatro roles llevan precio: cualquiera de ellos puede
        # cubrir un servicio, y un rol sin precio es un dia que no se
        # puede cotizar ni cerrar.
        precios_recurso = {
            "conductor_seguridad":  {"full_day": "3200", "medio_dia": "1800", "transfer": "1200"},
            "agente_seguridad":     {"full_day": "3800", "medio_dia": "2100", "transfer": "1400"},
            "coordinador_seguridad": {"full_day": "5200", "medio_dia": "2900", "transfer": "1900"},
            "consultor_seguridad":  {"full_day": "6800", "medio_dia": "3800", "transfer": "2500"},
        }
        hora_extra = {"conductor_seguridad": "320", "agente_seguridad": "380",
                      "coordinador_seguridad": "520", "consultor_seguridad": "680"}
        for perfil_cod, por_mod in precios_recurso.items():
            for mod_cod, precio in por_mod.items():
                _obtener_o_crear(
                    db, m.TarifaRecurso,
                    {"tarifario_id": tarifario.id,
                     "perfil_id": perfiles[perfil_cod].id,
                     "modalidad_id": mods_mx[mod_cod].id},
                    {"precio": D(precio),
                     "precio_hora_extra": D(hora_extra[perfil_cod]) if mod_cod == "full_day" else None})

        precios_vehiculo = {
            "cuv":              {"full_day": "2500", "medio_dia": "1500", "transfer": "1000"},
            "minivan":            {"full_day": "3000", "medio_dia": "1800", "transfer": "1200"},
            "minivan_blindada":   {"full_day": "6500", "medio_dia": "3900", "transfer": "2600"},
            "suv":              {"full_day": "5000", "medio_dia": "3000", "transfer": "2000"},
            "suv_blindada": {"full_day": "8500", "medio_dia": "5100", "transfer": "3400"},
            "van_10":             {"full_day": "4000", "medio_dia": "2400", "transfer": "1600"},
        }
        mensual = {"cuv": "55000", "minivan": "66000", "minivan_blindada": "143000",
                   "suv": "110000", "suv_blindada": "187000", "van_10": "88000"}
        for cat_cod, por_mod in precios_vehiculo.items():
            for mod_cod, precio in por_mod.items():
                _obtener_o_crear(
                    db, m.TarifaVehiculo,
                    {"tarifario_id": tarifario.id,
                     "categoria_id": categorias[cat_cod].id,
                     "modalidad_id": mods_mx[mod_cod].id},
                    {"precio": D(precio),
                     "precio_mensual": D(mensual[cat_cod]) if mod_cod == "full_day" else None})

        # ---------------------------------------------------- tabulador de viaticos Mexico
        # Identico para toda la empresa dentro de cada tipo de servicio.
        # Combustible y otros van en monto abierto.
        C, E, T = m.ConceptoViatico, m.EscenarioViatico, m.TipoServicio
        eventual = [
            # Alimentos se paga en full day. En medio dia y en transfer
            # hoy va en cero, pero el renglon se queda: el dia que la
            # direccion decida cubrir algo ahi, es cambiar el monto y no
            # volver a abrir la tabla.
            (C.ALIMENTOS, E.FULL_DAY_LOCAL, "350", False),
            (C.ALIMENTOS, E.FULL_DAY_FORANEO, "350", False),
            (C.ALIMENTOS, E.MEDIO_DIA, "0", False),
            (C.ALIMENTOS, E.TRANSFER, "0", False),
            (C.HOSPEDAJE, E.FULL_DAY_FORANEO, "1200", False),
            # Traslado del personal: se cubre cuando la presentacion cae
            # antes de las 6:30 —eso lo decide el motor, que si sabe a
            # que hora arranca la jornada—. En medio dia y en transfer
            # hoy va en cero, con el renglon puesto para el futuro.
            (C.TRASLADO_PERSONAL, E.FULL_DAY_LOCAL, "200", False),
            (C.TRASLADO_PERSONAL, E.FULL_DAY_FORANEO, "200", False),
            (C.TRASLADO_PERSONAL, E.MEDIO_DIA, "0", False),
            (C.TRASLADO_PERSONAL, E.TRANSFER, "0", False),
            (C.COMBUSTIBLE, E.FULL_DAY_LOCAL, "0", True),
            (C.COMBUSTIBLE, E.FULL_DAY_FORANEO, "0", True),
            (C.COMBUSTIBLE, E.MEDIO_DIA, "0", True),
            (C.COMBUSTIBLE, E.TRANSFER, "0", True),
            (C.CASETAS, E.FULL_DAY_FORANEO, "0", True),
            (C.OTROS, E.FULL_DAY_LOCAL, "0", True),
            (C.OTROS, E.FULL_DAY_FORANEO, "0", True),
            (C.OTROS, E.MEDIO_DIA, "0", True),
            (C.OTROS, E.TRANSFER, "0", True),
        ]
        # El implantado es otra operacion: la misma persona en el mismo
        # lugar todos los dias del mes, sin aeropuertos ni carretera. Por
        # eso lleva su propia tabla y no hereda la del eventual.
        #
        # OJO: estos montos son de ejemplo, igual que los del eventual.
        # La direccion tiene que definir los suyos antes de operar.
        implantado = [
            (C.ALIMENTOS, E.FULL_DAY_LOCAL, "350", False),
            (C.ALIMENTOS, E.FULL_DAY_FORANEO, "350", False),
            (C.ALIMENTOS, E.MEDIO_DIA, "0", False),
            (C.ALIMENTOS, E.TRANSFER, "0", False),
            (C.HOSPEDAJE, E.FULL_DAY_FORANEO, "1200", False),
            (C.TRASLADO_PERSONAL, E.FULL_DAY_LOCAL, "200", False),
            (C.TRASLADO_PERSONAL, E.FULL_DAY_FORANEO, "200", False),
            (C.TRASLADO_PERSONAL, E.MEDIO_DIA, "0", False),
            (C.TRASLADO_PERSONAL, E.TRANSFER, "0", False),
            (C.COMBUSTIBLE, E.FULL_DAY_LOCAL, "0", True),
            (C.COMBUSTIBLE, E.FULL_DAY_FORANEO, "0", True),
            (C.COMBUSTIBLE, E.MEDIO_DIA, "0", True),
            (C.COMBUSTIBLE, E.TRANSFER, "0", True),
            (C.CASETAS, E.FULL_DAY_FORANEO, "0", True),
            (C.OTROS, E.FULL_DAY_LOCAL, "0", True),
            (C.OTROS, E.FULL_DAY_FORANEO, "0", True),
            (C.OTROS, E.MEDIO_DIA, "0", True),
            (C.OTROS, E.TRANSFER, "0", True),
        ]
        for tipo, tabla in ((T.EVENTUAL, eventual), (T.IMPLANTADO, implantado)):
            for concepto, escenario, monto, abierto in tabla:
                _obtener_o_crear(
                    db, m.TabuladorViatico,
                    {"pais_id": mx.id, "tipo_servicio": tipo,
                     "concepto": concepto, "escenario": escenario},
                    {"monto": D(monto), "monto_abierto": abierto})

        # ---------------------------------------------------- comisiones al personal
        # Igual que los precios: los cuatro roles llevan comision. Sin
        # ella el corte de nomina se detiene, que es lo correcto, pero
        # detenerlo por un rol que nunca se cargo seria absurdo.
        comisiones = {
            "conductor_seguridad":  {"full_day": "700", "medio_dia": "400", "transfer": "250"},
            "agente_seguridad":     {"full_day": "800", "medio_dia": "450", "transfer": "300"},
            "coordinador_seguridad": {"full_day": "1100", "medio_dia": "600", "transfer": "400"},
            "consultor_seguridad":  {"full_day": "1500", "medio_dia": "850", "transfer": "550"},
        }
        comision_he = {"conductor_seguridad": "90", "agente_seguridad": "100",
                       "coordinador_seguridad": "140", "consultor_seguridad": "190"}
        # Las dos tablas arrancan con los mismos numeros. De ahi en
        # adelante cada operacion ajusta la suya: un dia de implantado no
        # se paga igual que un dia suelto que arranca en un aeropuerto.
        for tipo in (m.TipoServicio.EVENTUAL, m.TipoServicio.IMPLANTADO):
            for perfil_cod, por_mod in comisiones.items():
                for mod_cod, monto in por_mod.items():
                    _obtener_o_crear(
                        db, m.ComisionPersonal,
                        {"pais_id": mx.id, "tipo_servicio": tipo,
                         "perfil_id": perfiles[perfil_cod].id,
                         "modalidad_id": mods_mx[mod_cod].id},
                        {"monto": D(monto), "moneda": m.Moneda.MXN,
                         "monto_hora_extra": D(comision_he[perfil_cod]) if mod_cod == "full_day" else None})

        db.commit()

        creados = {
            "paises": db.query(m.Pais).count(),
            "plazas": db.query(m.Plaza).count(),
            "perfiles": db.query(m.PerfilPersonal).count(),
            "categorias_vehiculo": db.query(m.CategoriaVehiculo).count(),
            "modalidades": db.query(m.Modalidad).count(),
            "tarifarios": db.query(m.Tarifario).count(),
            "tarifas_recurso": db.query(m.TarifaRecurso).count(),
            "tarifas_vehiculo": db.query(m.TarifaVehiculo).count(),
            "tabulador_viaticos": db.query(m.TabuladorViatico).count(),
            "comisiones": db.query(m.ComisionPersonal).count(),
        }
    finally:
        db.close()
    return creados


def sembrar_recursos() -> dict:
    """Personal y flota de ejemplo, para poder probar el motor de disponibilidad."""
    db = SessionLocal()
    try:
        plazas = {p.nombre: p for p in db.query(m.Plaza).all()}
        perfiles = {p.codigo: p for p in db.query(m.PerfilPersonal).all()}
        categorias = {c.codigo: c for c in db.query(m.CategoriaVehiculo).all()}
        if not plazas or not perfiles:
            return {"error": "Primero hay que sembrar los catalogos"}

        cdmx = plazas.get("Ciudad de Mexico")
        gdl = plazas.get("Guadalajara")

        # Sin puesto: el personal de seguridad es general y el rol se
        # decide al asignarlo a una tarea.
        personal = [
            ("Juan Ramirez", "juan.ramirez@centauro.lat", cdmx, False),
            ("Luis Mendoza", "luis.mendoza@centauro.lat", cdmx, False),
            ("Carlos Vega", "carlos.vega@centauro.lat", gdl, False),
            ("Miguel Torres", "miguel.torres@centauro.lat", cdmx, False),
            ("Hector Palacios", "hector.palacios@centauro.lat", cdmx, False),
            ("Raul Ortiz", "raul.ortiz@freelance.mx", gdl, True),
            ("Ana Solis", "ana.solis@centauro.lat", cdmx, False),
        ]
        for nombre, correo, plaza, freelance in personal:
            if plaza is None:
                continue
            _obtener_o_crear(db, m.Persona, {"correo": correo},
                             {"nombre": nombre, "plaza_id": plaza.id,
                              "es_freelance": freelance})

        flota = [
            ("ABC-1234", "suv_blindada", cdmx, "1800"),
            ("ABC-5678", "suv_blindada", cdmx, "1800"),
            ("DEF-1111", "minivan", cdmx, "900"),
            ("JKL-3333", "minivan_blindada", cdmx, "1500"),
            ("GHI-2222", "cuv", gdl, "700"),
        ]
        for placa, cat_cod, plaza, costo in flota:
            if plaza is None:
                continue
            _obtener_o_crear(db, m.Vehiculo, {"placa": placa},
                             {"categoria_id": categorias[cat_cod].id,
                              "plaza_id": plaza.id, "costo_diario": D(costo)})

        # Un cliente de prueba con el tarifario general
        tarifario = db.query(m.Tarifario).filter_by(nombre="General Mexico").first()
        mx = db.query(m.Pais).filter_by(codigo="MX").first()
        if mx:
            _obtener_o_crear(db, m.Cliente, {"nombre": "Cliente Demo AAA"},
                             {"pais_id": mx.id,
                              "tarifario_id": tarifario.id if tarifario else None})

        db.commit()
        return {
            "personal": db.query(m.Persona).count(),
            "vehiculos": db.query(m.Vehiculo).count(),
            "clientes": db.query(m.Cliente).count(),
        }
    finally:
        db.close()


def sembrar_parametros() -> dict:
    """Precio del combustible por pais. MONTO DE EJEMPLO."""
    db = SessionLocal()
    try:
        mx = db.query(m.Pais).filter_by(codigo="MX").first()
        if not mx:
            return {"error": "Primero hay que sembrar los catalogos"}
        _obtener_o_crear(
            db, m.ParametroCombustible,
            {"pais_id": mx.id, "vigencia_desde": date(2026, 1, 1)},
            {"precio_litro": D("24.50"), "holgura_pct": D("20")})
        # Si el parametro ya existia, se actualiza la holgura vigente.
        for p in db.query(m.ParametroCombustible).filter_by(pais_id=mx.id).all():
            p.holgura_pct = D("20")
        # Pesos del tablero de profesionalismo. SON DE EJEMPLO: la
        # direccion tiene que definir los suyos, suman 100.
        pesos = {
            m.DimensionProfesionalismo.ESTRELLAS: D("30"),
            m.DimensionProfesionalismo.SATISFACCION: D("25"),
            m.DimensionProfesionalismo.INCIDENCIAS: D("25"),
            m.DimensionProfesionalismo.CAPACITACION: D("10"),
            m.DimensionProfesionalismo.EXPERIENCIA: D("10"),
        }
        for dimension, peso in pesos.items():
            _obtener_o_crear(
                db, m.PesoProfesionalismo,
                {"pais_id": mx.id, "dimension": dimension}, {"peso": peso})
        _obtener_o_crear(db, m.ParametroProfesionalismo, {"pais_id": mx.id}, {})

        db.commit()
        return {"parametros_combustible": db.query(m.ParametroCombustible).count(),
                "pesos_profesionalismo": db.query(m.PesoProfesionalismo).count()}
    finally:
        db.close()


CONTRASENA_DEMO = "centauro2026"


def sembrar_accesos() -> dict:
    """Usuarios con sus roles.

    OJO: todos quedan con la misma contrasena para poder probar el demo.
    En produccion nadie recibe contrasena: se le manda su enlace de invitacion
    y cada quien crea la suya desde su correo.
    """
    from app.auth import cifrar

    db = SessionLocal()
    try:
        plazas = {p.nombre: p for p in db.query(m.Plaza).all()}
        perfiles = {p.codigo: p for p in db.query(m.PerfilPersonal).all()}
        cdmx = plazas.get("Ciudad de Mexico")
        if not cdmx or not perfiles:
            return {"error": "Primero hay que sembrar los catalogos"}

        # Personal de oficina que aun no existia
        # Lo que distingue a la gente de oficina no es un puesto en su
        # ficha: es el rol con el que entra al sistema, que vive en su
        # usuario. Aqui solo se les crea la persona.
        for nombre, correo in [
            ("Sofia Navarro", "central@centauro.lat"),
            ("Ricardo Lima", "central2@centauro.lat"),
            ("Jorge Diaz", "finanzas@centauro.lat"),
            ("Maria Cruz", "finanzas2@centauro.lat"),
            ("Beatriz Roman", "beatriz.roman@centauro.lat"),
            ("Admin Sistema", "admin@centauro.lat"),
            ("Salvador Garcia Carrasco", "direccion@centauro.lat"),
            ("Jose Luis Pichardo", "operaciones@centauro.lat"),
        ]:
            persona, creada = _obtener_o_crear(
                db, m.Persona, {"correo": correo},
                {"nombre": nombre, "plaza_id": cdmx.id})
            # Si la persona ya existia con un nombre de relleno, se corrige:
            # este nombre sale en el task sheet que ve el cliente.
            if not creada and persona.nombre != nombre:
                persona.nombre = nombre
        db.flush()

        roles = {
            "admin@centauro.lat": m.Rol.ADMIN,
            "direccion@centauro.lat": m.Rol.DIRECTOR_GENERAL,
            "operaciones@centauro.lat": m.Rol.DIRECTOR_OPERACIONES,
            "ana.solis@centauro.lat": m.Rol.CONSULTOR,
            "central@centauro.lat": m.Rol.CENTRAL,
            "central2@centauro.lat": m.Rol.CENTRAL,
            "finanzas@centauro.lat": m.Rol.FINANZAS,
            "finanzas2@centauro.lat": m.Rol.FINANZAS,
            "beatriz.roman@centauro.lat": m.Rol.CONSULTOR,
            "juan.ramirez@centauro.lat": m.Rol.PERSONAL_SEGURIDAD,
            "luis.mendoza@centauro.lat": m.Rol.PERSONAL_SEGURIDAD,
            "carlos.vega@centauro.lat": m.Rol.PERSONAL_SEGURIDAD,
            "miguel.torres@centauro.lat": m.Rol.PERSONAL_SEGURIDAD,
            "raul.ortiz@freelance.mx": m.Rol.PERSONAL_SEGURIDAD,
        }

        hash_demo = cifrar(CONTRASENA_DEMO)
        for correo, rol in roles.items():
            persona = db.query(m.Persona).filter_by(correo=correo).first()
            if not persona:
                continue
            usuario, creado = _obtener_o_crear(
                db, m.Usuario, {"persona_id": persona.id},
                {"correo": correo, "rol": rol, "hash_contrasena": hash_demo})
            if not creado:
                usuario.rol = rol
                usuario.hash_contrasena = hash_demo

        db.commit()
        return {
            "usuarios": db.query(m.Usuario).count(),
            "contrasena_demo": CONTRASENA_DEMO,
            "aviso": "Contrasena unica solo para el demo",
        }
    finally:
        db.close()


def _enesimo_lunes(anio: int, mes: int, n: int) -> date:
    """El n-esimo lunes de un mes. La ley mexicana recorre varios feriados
    al lunes, asi que se calculan en vez de capturarse a mano cada anio."""
    import calendar as _cal
    primero = date(anio, mes, 1)
    desplazamiento = (0 - primero.weekday()) % 7      # 0 = lunes
    dia = 1 + desplazamiento + (n - 1) * 7
    if dia > _cal.monthrange(anio, mes)[1]:
        raise ValueError(f"No hay {n} lunes en {mes}/{anio}")
    return date(anio, mes, dia)


def festivos_mexico(anio: int) -> list[tuple]:
    """Descanso obligatorio segun la Ley Federal del Trabajo.
    No incluye los que cada empresa da por costumbre (2 de noviembre,
    12 de diciembre, jueves y viernes santo)."""
    return [
        (date(anio, 1, 1), "Ano nuevo"),
        (_enesimo_lunes(anio, 2, 1), "Dia de la Constitucion"),
        (_enesimo_lunes(anio, 3, 3), "Natalicio de Benito Juarez"),
        (date(anio, 5, 1), "Dia del Trabajo"),
        (date(anio, 9, 16), "Independencia"),
        (_enesimo_lunes(anio, 11, 3), "Revolucion Mexicana"),
        (date(anio, 12, 25), "Navidad"),
    ]


def sembrar_festivos(anios: tuple = (2026, 2027)) -> dict:
    """Festivos oficiales de Mexico. REVISAR antes de usar en produccion:
    faltan los de costumbre de la empresa y los de Brasil."""
    db = SessionLocal()
    try:
        mx = db.query(m.Pais).filter_by(codigo="MX").first()
        if not mx:
            return {"error": "Primero hay que sembrar los catalogos"}
        for anio in anios:
            for fecha, nombre in festivos_mexico(anio):
                _obtener_o_crear(db, m.DiaFestivo,
                                 {"pais_id": mx.id, "fecha": fecha},
                                 {"nombre": nombre, "factor_comision": D("2")})
        db.commit()
        return {"dias_festivos": db.query(m.DiaFestivo).count(),
                "aviso": "Solo los de ley. Revisar los de costumbre de la empresa."}
    finally:
        db.close()


def sembrar_bonos() -> dict:
    """Criterios de estrella y porcentajes de comision. MONTOS DE EJEMPLO."""
    db = SessionLocal()
    try:
        mx = db.query(m.Pais).filter_by(codigo="MX").first()
        if not mx:
            return {"error": "Primero hay que sembrar los catalogos"}

        criterios = [
            (m.CodigoCriterio.PUNTUALIDAD, "Puntualidad", "100", "800"),
            (m.CodigoCriterio.SEGUIMIENTO_APP, "Seguimiento en la app", "90", "600"),
            (m.CodigoCriterio.CAPACITACION, "Capacitacion del mes", "100", "500"),
            (m.CodigoCriterio.CIERRE_VIATICOS, "Cierre de viaticos", "100", "700"),
        ]
        for codigo, nombre, umbral, monto in criterios:
            _obtener_o_crear(db, m.CriterioEstrella,
                             {"pais_id": mx.id, "codigo": codigo},
                             {"nombre": nombre, "umbral_pct": D(umbral),
                              "monto_mensual": D(monto), "moneda": m.Moneda.MXN})

        for tipo, pct in [(m.TipoServicio.EVENTUAL, "3"),
                          (m.TipoServicio.IMPLANTADO, "1")]:
            _obtener_o_crear(db, m.PorcentajeComision,
                             {"pais_id": mx.id, "tipo_servicio": tipo},
                             {"porcentaje": D(pct)})

        db.commit()
        return {"criterios_estrella": db.query(m.CriterioEstrella).count(),
                "porcentajes_comision": db.query(m.PorcentajeComision).count()}
    finally:
        db.close()


def sembrar_lugares() -> dict:
    """Hospitales y hoteles de las tres ciudades de Mexico.

    OJO: nombres reales pero UBICACIONES APROXIMADAS y sin telefonos.
    Hay que verificarlos y completarlos antes de usarlos en operacion,
    porque de aqui sale la referencia medica en una emergencia. La
    consola los completa desde Google —nombre oficial, direccion,
    telefono y coordenadas—; el nivel de atencion lo marca Centauro,
    porque Google no lo sabe y no se adivina.
    """
    db = SessionLocal()
    try:
        mx = db.query(m.Pais).filter_by(codigo="MX").first()
        cdmx = db.query(m.Plaza).filter_by(nombre="Ciudad de Mexico").first()
        if not mx or not cdmx:
            return {"error": "Primero hay que sembrar los catalogos"}
        mty = db.query(m.Plaza).filter_by(nombre="Monterrey").first()
        gdl = db.query(m.Plaza).filter_by(nombre="Guadalajara").first()

        TERCERO = m.NivelHospital.TERCERO
        hospitales = [
            (cdmx, "Hospital Espanol", "19.4425", "-99.1855", TERCERO),
            (cdmx, "Hospital Angeles Mocel", "19.4130", "-99.1910", TERCERO),
            (cdmx, "Centro Medico ABC Observatorio", "19.3907", "-99.2130", TERCERO),
            (cdmx, "Hospital Angeles Metropolitano", "19.3796", "-99.1750", TERCERO),
            (cdmx, "Medica Sur", "19.2960", "-99.1610", TERCERO),
            # Monterrey
            (mty, "Hospital Zambrano Hellion", "25.6285", "-100.3160", TERCERO),
            (mty, "Hospital San Jose TecSalud", "25.6510", "-100.3450", TERCERO),
            (mty, "Christus Muguerza Alta Especialidad", "25.6720", "-100.3170", TERCERO),
            (mty, "Hospital Angeles Valle Oriente", "25.6250", "-100.3060", TERCERO),
            (mty, "OCA Hospital", "25.6840", "-100.3310", TERCERO),
            # Guadalajara
            (gdl, "Hospital Country 2000", "20.6790", "-103.3890", TERCERO),
            (gdl, "Hospital San Javier", "20.7080", "-103.4070", TERCERO),
            (gdl, "Hospital Puerta de Hierro Andares", "20.7130", "-103.4180", TERCERO),
            (gdl, "Hospital Angeles del Carmen", "20.6720", "-103.3880", TERCERO),
            (gdl, "Hospital Real San Jose", "20.6950", "-103.4010", TERCERO),
        ]
        for plaza, nombre, lat, lon, nivel in hospitales:
            if not plaza:
                continue          # esa ciudad no esta en el catalogo
            _obtener_o_crear(db, m.Hospital, {"pais_id": mx.id, "nombre": nombre},
                             {"plaza_id": plaza.id, "lat": D(lat), "lon": D(lon),
                              "nivel_atencion": nivel})

        hoteles = [
            ("Four Seasons Mexico City", "Paseo de la Reforma 500",
             "19.4247", "-99.1700"),
            ("The St. Regis Mexico City", "Paseo de la Reforma 439",
             "19.4250", "-99.1742"),
            ("Marquis Reforma", "Paseo de la Reforma 465", "19.4260", "-99.1710"),
            ("Sheraton Mexico City Maria Isabel", "Paseo de la Reforma 325",
             "19.4268", "-99.1690"),
        ]
        for nombre, direccion, lat, lon in hoteles:
            _obtener_o_crear(db, m.Hotel, {"pais_id": mx.id, "nombre": nombre},
                             {"plaza_id": cdmx.id, "direccion": direccion,
                              "lat": D(lat), "lon": D(lon)})

        # Datos que el task sheet muestra del equipo y la unidad
        telefonos = {
            "juan.ramirez@centauro.lat": "55 1234 5601",
            "luis.mendoza@centauro.lat": "55 1234 5602",
            "carlos.vega@centauro.lat": "33 1234 5603",
            "miguel.torres@centauro.lat": "55 1234 5604",
            "hector.palacios@centauro.lat": "55 1234 5605",
            "ana.solis@centauro.lat": "55 1234 5610",
            "operaciones@centauro.lat": "55 1234 5620",
            "central@centauro.lat": "55 1234 5600",
        }
        for correo, telefono in telefonos.items():
            persona = db.query(m.Persona).filter_by(correo=correo).first()
            if persona and not persona.telefono:
                persona.telefono = telefono

        colores = {"ABC-1234": ("Negro", 2024), "ABC-5678": ("Gris Oxford", 2023),
                   "DEF-1111": ("Blanco", 2024), "GHI-2222": ("Plata", 2022),
                   "JKL-3333": ("Negro", 2025)}
        for placa, (color, anio) in colores.items():
            vehiculo = db.query(m.Vehiculo).filter_by(placa=placa).first()
            if vehiculo and not vehiculo.color:
                vehiculo.color = color
                vehiculo.modelo_anio = anio

        db.commit()
        return {"hospitales": db.query(m.Hospital).count(),
                "hoteles": db.query(m.Hotel).count(),
                "aviso": "Ubicaciones aproximadas y sin telefonos: verificar"}
    finally:
        db.close()
