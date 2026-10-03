# -*- coding: utf-8 -*-
"""Logistica (seccion 151): la carga inicial de la flota desde el Excel
«Costos_unidades_Centauro_Logistica.xlsx», hojas «Unidades» y «Plan
preventivo».

Todo o nada: primero se revisan las dos hojas completas; si un solo
renglon tiene error no se carga nada, y cada error dice su hoja, su
renglon, su columna y que pasa, con la sugerencia cuando la hay. Se
puede subir otra vez cuantas veces haga falta. Despues de la carga, cada
cambio se captura en la unidad y queda en la bitacora.

Las columnas se reconocen por su encabezado, en cualquier orden: el
Excel no tiene que traer un formato exacto, solo nombres claros.
"""
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import lg_flota
from app import models as m
from app.odoo_lg import placa_de

LIMITE = 10 * 1024 * 1024
MAXIMO_RENGLONES = 2000

# Cada columna con los nombres con que puede venir, del mas preciso al
# mas suelto: «llantas por km» antes que «llantas».
UNIDADES = (
    ("placa", ("placas", "placa", "matricula")),
    ("numero_economico", ("numero economico", "no economico", "num economico",
                          "economico", "eco")),
    ("tipo", ("tipo de unidad", "tipo")),
    ("rendimiento_ref", ("rendimiento de referencia", "rendimiento")),
    ("valor_compra", ("valor de compra", "precio de compra", "valor compra", "compra")),
    ("anios_vida", ("anos de vida", "anios de vida", "vida util", "anos", "vida")),
    ("seguro_anual", ("seguro anual", "seguro")),
    ("tenencia_anual", ("tenencia y placas", "tenencia")),
    ("verificacion_anual", ("verificacion",)),
    ("gps_anual", ("gps",)),
    ("llantas_por_km", ("llantas por km", "costo de llantas por km", "llantas km",
                        "llantas")),
    ("mantenimiento_anual", ("mantenimiento anual", "mantenimiento")),
    ("odometro", ("odometro", "kilometraje", "km actual")),
    ("patio", ("patio base", "patio")),
)
PLAN = (
    ("tipo", ("tipo de unidad", "tipo")),
    ("nombre", ("servicio", "nombre")),
    ("cada_km", ("cada cuantos km", "cada km", "intervalo", "cada")),
    ("costo_aprox", ("costo aproximado", "costo aprox", "costo")),
)
NOMBRE_COLUMNA = {"placa": "Placas", "numero_economico": "Número económico",
                  "tipo": "Tipo", "rendimiento_ref": "Rendimiento",
                  "valor_compra": "Valor de compra", "anios_vida": "Años de vida",
                  "seguro_anual": "Seguro anual", "tenencia_anual": "Tenencia",
                  "verificacion_anual": "Verificación", "gps_anual": "GPS",
                  "llantas_por_km": "Llantas por km",
                  "mantenimiento_anual": "Mantenimiento anual", "odometro": "Odómetro",
                  "patio": "Patio", "nombre": "Servicio", "cada_km": "Cada km",
                  "costo_aprox": "Costo aproximado"}
REMOLQUE = ("remolque", "caja", "caja seca")


def normal(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"\(.*?\)|[$%:#.]", " ", t.lower())
    return " ".join(t.split())


def _columnas(encabezado: list, esperadas) -> tuple[dict, list]:
    """{campo: indice} y los encabezados que no se reconocieron."""
    indices: dict = {}
    sobran = []
    for i, celda in enumerate(encabezado):
        texto = normal(celda)
        if not texto:
            continue
        campo = None
        for nombre, pistas in esperadas:
            if nombre in indices:
                continue
            if any(texto == p or texto.startswith(p + " ") or texto.startswith(p)
                   for p in pistas):
                campo = nombre
                break
        if campo:
            indices[campo] = i
        else:
            sobran.append(str(celda))
    return indices, sobran


def _numero(valor, entero: bool = False) -> Decimal | None:
    """Un numero de una celda. Los de Excel llegan como numero; los que
    llegan como texto se aceptan con «$» y comas de miles, nunca con la
    coma como punto decimal."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool):
        raise ValueError("no es un número")
    if isinstance(valor, (int, float, Decimal)):
        d = Decimal(str(valor))
    else:
        texto = str(valor).strip().replace("$", "").replace(" ", "")
        if "," in texto and "." not in texto:
            raise ValueError(f"«{valor}» lleva coma: escríbelo con punto decimal")
        texto = texto.replace(",", "")
        try:
            d = Decimal(texto)
        except InvalidOperation:
            raise ValueError(f"«{valor}» no es un número")
    if not d.is_finite():
        raise ValueError("no es un número")
    if entero and d != d.to_integral_value():
        raise ValueError(f"«{valor}» va sin decimales")
    return d


def _distancia(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 99
    previo = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(previo[j] + 1, actual[j - 1] + 1,
                              previo[j - 1] + (ca != cb)))
        previo = actual
    return previo[-1]


def _parecida(placa: str, placas: dict) -> str | None:
    mejores = sorted((p for p in placas if _distancia(placa, p) <= 2),
                     key=lambda p: _distancia(placa, p))
    return placas[mejores[0]].placa if mejores else None


def _hoja(libro, *pistas):
    for hoja in libro.worksheets:
        nombre = normal(hoja.title)
        if any(p in nombre for p in pistas):
            return hoja
    return None


def _renglones(hoja) -> list[tuple[int, list]]:
    salida = []
    for i, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
        if i > MAXIMO_RENGLONES:
            break
        salida.append((i, list(fila)))
    return salida


def _abrir(contenido: bytes):
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")
    if len(contenido) > LIMITE:
        raise HTTPException(400, "El Excel pasa de 10 MB.")
    try:
        from openpyxl import load_workbook
        return load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:                                      # noqa: BLE001
        raise HTTPException(400, {
            "mensaje": "No se pudo abrir el archivo como Excel.",
            "que_hacer": "Súbelo como .xlsx, guardado desde Excel."})


def _tipo_de(texto, tipos: list[m.LgTipoUnidad]) -> m.LgTipoUnidad | None:
    t = normal(texto)
    for tipo in tipos:
        if t in (normal(tipo.nombre), normal(tipo.nombre_tango)):
            return tipo
    for tipo in tipos:
        if t and (t in normal(tipo.nombre) or normal(tipo.nombre).startswith(t)):
            return tipo
    return None


def revisar(db: Session, contenido: bytes) -> dict:
    """Lee y revisa todo, sin tocar la base."""
    libro = _abrir(contenido)
    errores: list[dict] = []

    def error(hoja, renglon, columna, que):
        errores.append({"hoja": hoja, "renglon": renglon,
                        "columna": NOMBRE_COLUMNA.get(columna, columna), "que": que})

    unidades = {placa_de(u.placa): u for u in db.query(m.LgUnidad)
                .filter(m.LgUnidad.activo.is_(True)).all()}
    tipos = db.query(m.LgTipoUnidad).filter(m.LgTipoUnidad.activo.is_(True)).all()
    patios = {normal(p.nombre): p for p in db.query(m.LgPatio)
              .filter(m.LgPatio.activo.is_(True)).all()}

    hoja_u = _hoja(libro, "unidad")
    hoja_p = _hoja(libro, "plan", "preventivo")
    filas_u, filas_p, sobran = [], [], {}
    if hoja_u is None:
        error("Unidades", None, "", "No está la hoja «Unidades».")
    else:
        renglones = _renglones(hoja_u)
        encabezado = renglones[0][1] if renglones else []
        cols, sobran["Unidades"] = _columnas(encabezado, UNIDADES)
        if "placa" not in cols:
            error(hoja_u.title, 1, "placa", "Falta la columna de las placas: con ella "
                                           "se encuentra cada unidad.")
        else:
            vistos_eco, vistas_placas = {}, {}
            for n, fila in renglones[1:]:
                if not any(c not in (None, "") for c in fila):
                    continue

                def celda(campo):
                    i = cols.get(campo)
                    return fila[i] if i is not None and i < len(fila) else None
                placa = placa_de(celda("placa"))
                if not placa:
                    error(hoja_u.title, n, "placa", "Falta la placa.")
                    continue
                unidad = unidades.get(placa)
                if unidad is None:
                    sugerida = _parecida(placa, unidades)
                    error(hoja_u.title, n, "placa",
                          f"«{celda('placa')}» no es de ninguna unidad de Centauro "
                          f"Logistic en Odoo." + (f" ¿Será «{sugerida}»?" if sugerida else ""))
                    continue
                if placa in vistas_placas:
                    error(hoja_u.title, n, "placa",
                          f"La placa ya está en el renglón {vistas_placas[placa]}.")
                    continue
                vistas_placas[placa] = n
                datos = {"unidad": unidad, "renglon": n}
                eco = celda("numero_economico")
                if eco not in (None, ""):
                    texto = str(int(eco)) if isinstance(eco, float) and eco.is_integer() else str(eco)
                    llave = lg_flota.llave_economico(texto)
                    if llave in vistos_eco:
                        error(hoja_u.title, n, "numero_economico",
                              f"«{texto}» ya está en el renglón {vistos_eco[llave]}. Cada "
                              f"unidad necesita su propio número económico.")
                    else:
                        vistos_eco[llave] = n
                        datos["numero_economico"] = (
                            re.sub(r"^(eco)\s*", "", texto.strip(), flags=re.I) or texto.strip())
                        datos["economico_llave"] = llave
                tipo_txt = celda("tipo")
                if tipo_txt not in (None, ""):
                    if normal(tipo_txt) in REMOLQUE:
                        if unidad.clase != "remolque":
                            error(hoja_u.title, n, "tipo", "En Odoo no es una caja seca.")
                    elif unidad.clase == "remolque":
                        error(hoja_u.title, n, "tipo", "Es una caja seca: su tipo va vacío "
                                                       "o «Remolque».")
                    else:
                        tipo = _tipo_de(tipo_txt, tipos)
                        if tipo is None:
                            error(hoja_u.title, n, "tipo",
                                  f"«{tipo_txt}» no es un tipo de unidad. Son: "
                                  + ", ".join(t.nombre for t in tipos) + ".")
                        else:
                            datos["tipo_id"] = tipo.id
                for campo, entero, tope, mayor in (
                        ("rendimiento_ref", False, 30, True),
                        ("valor_compra", False, 20_000_000, False),
                        ("anios_vida", False, 40, True),
                        ("seguro_anual", False, 2_000_000, False),
                        ("tenencia_anual", False, 500_000, False),
                        ("verificacion_anual", False, 200_000, False),
                        ("gps_anual", False, 200_000, False),
                        ("llantas_por_km", False, 100, False),
                        ("mantenimiento_anual", False, 2_000_000, False),
                        ("odometro", True, 5_000_000, False)):
                    try:
                        valor = _numero(celda(campo), entero)
                    except ValueError as e:
                        error(hoja_u.title, n, campo, str(e) + ".")
                        continue
                    if valor is None:
                        continue
                    if valor < 0 or (mayor and valor <= 0):
                        error(hoja_u.title, n, campo, "Tiene que ser mayor que cero.")
                    elif valor > tope:
                        error(hoja_u.title, n, campo, f"No puede pasar de {tope:,}: revisa "
                                                      f"el punto decimal.")
                    else:
                        datos[campo] = valor
                patio_txt = celda("patio")
                if patio_txt not in (None, ""):
                    patio = patios.get(normal(patio_txt))
                    if patio is None:
                        error(hoja_u.title, n, "patio", f"«{patio_txt}» no es un patio.")
                    else:
                        datos["patio_id"] = patio.id
                filas_u.append(datos)
            # Los economicos como quedarian despues de la carga: los del
            # Excel encima de los que ya estan. Asi un intercambio entre
            # dos unidades del mismo Excel no se toma por repetido.
            final = {u.id: u.economico_llave for u in unidades.values() if u.economico_llave}
            for datos in filas_u:
                if "economico_llave" in datos:
                    final[datos["unidad"].id] = datos["economico_llave"]
            for datos in filas_u:
                llave = datos.get("economico_llave")
                if not llave:
                    continue
                otra = next((u for u in unidades.values()
                             if u.id != datos["unidad"].id and final.get(u.id) == llave), None)
                if otra:
                    error(hoja_u.title, datos["renglon"], "numero_economico",
                          f"«{datos['numero_economico']}» ya es de la unidad con placas "
                          f"{otra.placa}.")

    if hoja_p is not None:
        renglones = _renglones(hoja_p)
        encabezado = renglones[0][1] if renglones else []
        cols, sobran["Plan preventivo"] = _columnas(encabezado, PLAN)
        faltan = [c for c in ("tipo", "nombre", "cada_km") if c not in cols]
        if faltan:
            error(hoja_p.title, 1, faltan[0], "Falta la columna "
                  + ", ".join(NOMBRE_COLUMNA[c] for c in faltan) + ".")
        else:
            vistos = {}
            for n, fila in renglones[1:]:
                if not any(c not in (None, "") for c in fila):
                    continue

                def celda(campo):
                    i = cols.get(campo)
                    return fila[i] if i is not None and i < len(fila) else None
                tipo_txt, nombre = celda("tipo"), lg_flota._texto(celda("nombre"), 80)
                if not nombre:
                    error(hoja_p.title, n, "nombre", "Falta el servicio.")
                    continue
                datos = {"renglon": n, "nombre": nombre}
                if normal(tipo_txt) in REMOLQUE:
                    datos["clase"], datos["tipo_id"] = "remolque", None
                else:
                    tipo = _tipo_de(tipo_txt, tipos)
                    if tipo is None:
                        error(hoja_p.title, n, "tipo", f"«{tipo_txt}» no es un tipo de unidad.")
                        continue
                    datos["clase"], datos["tipo_id"] = "unidad", tipo.id
                llave = (datos["clase"], datos["tipo_id"], normal(nombre))
                if llave in vistos:
                    error(hoja_p.title, n, "nombre",
                          f"«{nombre}» ya está para ese tipo en el renglón {vistos[llave]}.")
                    continue
                vistos[llave] = n
                try:
                    cada = _numero(celda("cada_km"), True)
                    costo = _numero(celda("costo_aprox"))
                except ValueError as e:
                    error(hoja_p.title, n, "cada_km", str(e) + ".")
                    continue
                if not cada or cada <= 0:
                    error(hoja_p.title, n, "cada_km", "Falta cada cuántos km.")
                    continue
                if cada > 1_000_000:
                    error(hoja_p.title, n, "cada_km", "Pasa de 1,000,000 km: revísalo.")
                    continue
                datos["cada_km"], datos["costo_aprox"] = int(cada), costo
                filas_p.append(datos)

    return {"ok": not errores, "errores": errores, "unidades": len(filas_u),
            "plan": len(filas_p), "sin_columna": {k: v for k, v in sobran.items() if v},
            "_filas": (filas_u, filas_p)}


def cargar(db: Session, actor: m.Usuario, contenido: bytes, aplicar: bool) -> dict:
    """Revisa; si todo esta bien y se pide, carga todo en una sola vuelta."""
    revision = revisar(db, contenido)
    filas_u, filas_p = revision.pop("_filas")
    if not revision["ok"] or not aplicar:
        return {**revision, "cargado": False}
    hoy = lg_flota.hoy()
    # Primero se sueltan los economicos que cambian: un intercambio entre
    # dos unidades no choca a media carga con el que no se repite.
    for datos in filas_u:
        if "economico_llave" in datos:
            datos["unidad"].economico_llave = None
    db.flush()
    for datos in filas_u:
        unidad = datos["unidad"]
        for campo in ("numero_economico", "economico_llave", "tipo_id", "patio_id",
                      "rendimiento_ref") + lg_flota.CAMPOS_COSTO:
            if campo in datos:
                setattr(unidad, campo, datos[campo])
        if "odometro" in datos and (unidad.odometro_km is None
                                    or int(datos["odometro"]) >= unidad.odometro_km):
            lg_flota.capturar_odometro(db, actor, unidad, int(datos["odometro"]), hoy,
                                       fuente="carga")
    db.flush()
    for datos in filas_p:
        consulta = db.query(m.LgPlanServicio).filter(
            m.LgPlanServicio.clase == datos["clase"])
        consulta = (consulta.filter(m.LgPlanServicio.tipo_id == datos["tipo_id"])
                    if datos["tipo_id"] else consulta.filter(m.LgPlanServicio.tipo_id.is_(None)))
        fila = next((p for p in consulta.all() if normal(p.nombre) == normal(datos["nombre"])),
                    None)
        if fila is None:
            db.add(m.LgPlanServicio(tipo_id=datos["tipo_id"], clase=datos["clase"],
                                    nombre=datos["nombre"], cada_km=datos["cada_km"],
                                    costo_aprox=datos["costo_aprox"],
                                    orden=datos["renglon"]))
        else:
            fila.cada_km, fila.costo_aprox, fila.activo = (datos["cada_km"],
                                                          datos["costo_aprox"], True)
    db.flush()
    for datos in filas_u:
        lg_flota.guardar_costo(db, datos["unidad"], lg_flota.primero_del_mes(hoy), "carga",
                               actor)
    lg_flota._anotar(db, actor, "lg carga inicial", "lg_carga", None,
                     {"k": "carga", "n": len(filas_u), "pl": len(filas_p)})
    db.commit()
    return {**revision, "cargado": True}
