# -*- coding: utf-8 -*-
"""El freelance en Connect (seccion 111): su alta con foto, sus costos,
su expediente de Recursos Humanos y la urgencia autorizada.

Las reglas viven en `app/freelance.py`; aqui solo las puertas. Quien
asigna ve si esta listo; los documentos los abren Recursos Humanos,
direccion de operaciones y direccion general (decision 6).
"""
import json
from datetime import date, datetime

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Response,
                     UploadFile)
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import accesos, auth, experiencia, imagenes, reloj, telefonos
from app import freelance as motor
from app import models as m
from app import schemas as s
from app.db import get_db

router = APIRouter(prefix="/freelance", tags=["Freelance"])

VER = auth.puede("freelance.ver")
ALTA = auth.puede("freelance.alta")
EXPEDIENTE = auth.puede("freelance.expediente")
VALIDA = auth.puede("freelance.validar")
AUTORIZA = auth.puede("freelance.autorizar")
DINERO = auth.puede("catalogos.dinero")
ASIGNA = auth.puede("asignaciones.mover")

BAJA_DEL_FREELANCE = "baja del freelance"


# ================================================================ apoyo

def _plaza(db: Session, plaza_id: int) -> m.Plaza:
    plaza = db.get(m.Plaza, plaza_id)
    if not plaza or not plaza.activo:
        raise HTTPException(404, "Esa ciudad no existe o está desactivada.")
    return plaza


def _correo_libre(db: Session, correo: str, persona_id: int | None = None,
                  o_quien_vuelve: bool = False) -> str | tuple[str, m.Persona]:
    """El correo, limpio y de nadie mas. Con `o_quien_vuelve`, el alta
    acepta el correo de quien ya estuvo en Centauro y esta dado de baja
    sin ser freelance --se fue de Odoo-- y devuelve a esa persona
    (seccion 132, decision 6): vuelve como freelance con su historia."""
    correo = (correo or "").strip().lower()
    if "@" not in correo or "." not in correo.split("@")[-1]:
        raise HTTPException(400, "Ese correo no tiene forma de correo.")
    otra = (db.query(m.Persona)
            .filter(func.lower(func.trim(m.Persona.correo)) == correo,
                    m.Persona.id != (persona_id or 0)).first())
    if otra is None:
        return (correo, None) if o_quien_vuelve else correo
    if o_quien_vuelve and not otra.activo and not otra.es_freelance:
        return correo, otra
    if o_quien_vuelve and not otra.activo:
        raise HTTPException(409, {
            "mensaje": f"Ese correo ya es de {otra.nombre}, dado de baja como "
                       "freelance.",
            "que_hacer": "No se da de alta dos veces: búscalo en la lista con "
                         "el filtro «De baja» y vuelve a darlo de alta desde "
                         "su ficha."})
    raise HTTPException(409, {
        "mensaje": f"Ese correo ya es de {otra.nombre}.",
        "que_hacer": "Cada quien entra a la app con el suyo: pide el "
                     "correo personal del freelance."})


def _telefono(db: Session, lada: str | None, numero: str, pais_id: int) -> str:
    numero = " ".join(str(numero or "").split())
    lada = (lada or "").strip()
    if lada and not numero.startswith("+"):
        if not lada.startswith("+"):
            lada = "+" + lada.lstrip("0")
        numero = f"{lada} {numero}"
    return telefonos.normalizar(db, numero, pais_id)


def _usuario_de(db: Session, persona_ids: list[int]) -> dict[int, m.Usuario]:
    if not persona_ids:
        return {}
    return {u.persona_id: u for u in db.query(m.Usuario).filter(
        m.Usuario.persona_id.in_(persona_ids)).all()}


def _acceso(u: m.Usuario | None) -> dict | None:
    if u is None:
        return None
    return {"usuario_id": u.id, "activo": u.activo,
            "ya_puso_contrasena": u.hash_contrasena is not None,
            "ultimo_acceso": (u.ultimo_acceso.isoformat()
                              if u.ultimo_acceso else None)}


def _servicios_de(db: Session, persona_ids: list[int]) -> dict[int, list]:
    """Los dias de cada quien, del mas reciente al mas viejo, con su
    servicio: para el ultimo servicio de la lista y la pestana Servicios."""
    salida: dict[int, list] = {}
    if not persona_ids:
        return salida
    filas = (db.query(m.AsignacionPersonal.persona_id, m.Jornada.fecha,
                      m.Servicio)
             .join(m.Jornada, m.Jornada.id == m.AsignacionPersonal.jornada_id)
             .join(m.Equipo, m.Equipo.id == m.Jornada.equipo_id)
             .join(m.Servicio, m.Servicio.id == m.Equipo.servicio_id)
             .filter(m.AsignacionPersonal.persona_id.in_(persona_ids),
                     m.Jornada.estatus != m.EstatusJornada.CANCELADA)
             .order_by(m.Jornada.fecha.desc()).all())
    for persona_id, fecha, servicio in filas:
        salida.setdefault(persona_id, []).append((fecha, servicio))
    return salida


def _ultimo(dias: list, hoy: date) -> tuple[dict | None, dict | None]:
    pasados = [(f, sv) for f, sv in dias if f <= hoy]
    futuros = [(f, sv) for f, sv in dias if f > hoy]
    ultimo = ({"fecha": pasados[0][0].isoformat(), "folio": pasados[0][1].folio,
               "servicio_id": pasados[0][1].id} if pasados else None)
    proximo = ({"fecha": futuros[-1][0].isoformat(),
                "folio": futuros[-1][1].folio,
                "servicio_id": futuros[-1][1].id} if futuros else None)
    return ultimo, proximo


def _fila(p: m.Persona, ficha: m.Freelance, info: dict, costos: dict,
          dias: list, horas: int, usuario: m.Usuario | None,
          hoy: date) -> dict:
    ultimo, proximo = _ultimo(dias, hoy)
    return {
        "persona_id": p.id, "nombre": p.nombre,
        "nombre_de_pila": ficha.nombre, "apellidos": ficha.apellidos,
        "foto": p.foto_url, "telefono": p.telefono, "correo": p.correo,
        "plaza_id": p.plaza_id, "plaza": p.plaza.nombre if p.plaza else None,
        "pais_id": p.plaza.pais_id if p.plaza else None,
        "tipo": ficha.tipo, "activo": p.activo,
        "alta_en": ficha.alta_en.isoformat() if ficha.alta_en else None,
        "expediente": info,
        "costos": {k: costos.get(k) for k in (*motor.MODALIDADES, "hora_extra")},
        "moneda": costos.get("moneda") or (
            p.plaza.pais.moneda_local.value if p.plaza and p.plaza.pais else None),
        "ultimo_servicio": ultimo, "proximo_servicio": proximo,
        "horas_en_centauro": horas,
        "acceso": _acceso(usuario),
        # El que ya paso a planta (seccion 132, decision 6): su ficha es
        # historia y la lista lo dice.
        "planta_en": ficha.planta_en.isoformat() if ficha.planta_en else None,
    }


def _filas(db: Session, personas: list, ahora: datetime | None = None) -> list[dict]:
    ids = [p.id for p in personas]
    fichas = {f.persona_id: f for f in db.query(m.Freelance).filter(
        m.Freelance.persona_id.in_(ids)).all()} if ids else {}
    for p in personas:
        if p.id not in fichas:
            fichas[p.id] = motor.ficha_de(db, p.id)[1]
    resumenes = motor.resumen_por_persona(db, personas, fichas, ahora)
    costos = motor.costos_por_persona(db, ids)
    dias = _servicios_de(db, ids)
    horas = experiencia.horas_por_persona(db, ids) if ids else {}
    usuarios = _usuario_de(db, ids)
    relojes = reloj.Relojes(db, ahora)
    return [_fila(p, fichas[p.id], resumenes[p.id], costos.get(p.id, {}),
                  dias.get(p.id, []), horas.get(p.id, 0), usuarios.get(p.id),
                  relojes.hoy(p.plaza.pais_id if p.plaza else None))
            for p in personas]


def _puede(db: Session, u: m.Usuario, persona: m.Persona | None = None) -> dict:
    """Lo que este usuario puede hacer en la ficha. La del que ya paso a
    planta (seccion 132) se lee y nada mas: lo suyo lo lleva Odoo."""
    tiene = accesos.actividades_de(db, u)
    vivo = persona is None or persona.es_freelance
    return {"editar": vivo and "freelance.alta" in tiene,
            "costos": vivo and "catalogos.dinero" in tiene,
            "expediente": "freelance.expediente" in tiene,
            "validar": vivo and "freelance.validar" in tiene,
            "tipo": vivo and "freelance.validar" in tiene,
            "autorizar": vivo and "freelance.autorizar" in tiene,
            "a_planta": vivo and "freelance.validar" in tiene,
            "ve_cuenta": "viaticos.transferir" in tiene}


# ============================================================ la lista

@router.get("", summary="Los freelance de un pais, con su expediente")
def lista(pais_id: int | None = None, incluir_bajas: bool = False,
          db: Session = Depends(get_db), _=Depends(VER)):
    """La pestana Freelance de Personal de seguridad: su foto, su tipo,
    como va su expediente, sus costos y su ultimo servicio. Con
    `incluir_bajas` salen tambien los dados de baja y los que pasaron a
    planta (seccion 132), para su filtro."""
    q = (db.query(m.Persona).join(m.Plaza, m.Plaza.id == m.Persona.plaza_id)
         .outerjoin(m.Freelance, m.Freelance.persona_id == m.Persona.id))
    if incluir_bajas:
        q = q.filter(or_(m.Persona.es_freelance.is_(True),
                         m.Freelance.planta_en.isnot(None)))
    else:
        q = q.filter(m.Persona.es_freelance.is_(True),
                     m.Persona.activo.is_(True))
    if pais_id:
        q = q.filter(m.Plaza.pais_id == pais_id)
    filas = _filas(db, q.order_by(m.Persona.nombre).all())
    # Por si a alguno de antes le faltaba su ficha y se le armo aqui.
    db.commit()
    return filas


@router.post("", status_code=201, summary="Dar de alta un freelance")
def alta(datos: s.FreelanceIn, db: Session = Depends(get_db),
         actor: m.Usuario = Depends(ALTA)):
    """Nace con su ficha y sin expediente: se asigna cuando Recursos
    Humanos lo valida y tiene sus costos. Si el correo es de alguien que
    ya estuvo en Centauro y se dio de baja en Odoo, vuelve esa misma
    persona (seccion 132, decision 6)."""
    plaza = _plaza(db, datos.plaza_id)
    correo, vuelve = _correo_libre(db, datos.correo, o_quien_vuelve=True)
    telefono = _telefono(db, datos.lada, datos.telefono, plaza.pais_id)
    if vuelve is not None:
        motor.volver_de_odoo(db, actor, vuelve, datos.tipo, datos.nombre,
                             datos.apellidos, plaza, telefono)
        db.commit()
        return {"persona_id": vuelve.id, "nombre": vuelve.nombre,
                "vuelve": True,
                "aviso": f"{vuelve.nombre} ya estaba en Centauro y se había "
                         "dado de baja: vuelve como freelance con su misma "
                         "historia."}
    persona = m.Persona(nombre=motor.nombre_completo(datos.nombre, datos.apellidos),
                        correo=correo, plaza_id=plaza.id, es_freelance=True,
                        activo=True, oficina=False, telefono=telefono)
    db.add(persona)
    db.flush()
    ficha = m.Freelance(persona_id=persona.id, tipo=datos.tipo,
                        nombre=datos.nombre.strip(),
                        apellidos=datos.apellidos.strip(),
                        alta_por_id=actor.persona_id)
    db.add(ficha)
    db.flush()
    motor._anotar(db, actor, persona, "alta", despues=datos.tipo,
                  detalle=f"{persona.nombre} · {plaza.nombre}")
    db.commit()
    return {"persona_id": persona.id, "nombre": persona.nombre}


# ================================================ la urgencia (direccion)

@router.get("/urgencias", summary="Las urgencias pedidas o resueltas")
def lista_de_urgencias(estado: str | None = "pedida",
                       db: Session = Depends(get_db), _=Depends(VER)):
    return motor.urgencias(db, estado or None)


@router.post("/urgencias/{urgencia_id}/autorizar",
             summary="Autorizar al freelance para ese servicio")
def autorizar(urgencia_id: int, datos: s.RespuestaUrgenciaIn,
              db: Session = Depends(get_db),
              actor: m.Usuario = Depends(AUTORIZA)):
    fila = db.get(m.AutorizacionFreelance, urgencia_id)
    if not fila:
        raise HTTPException(404, f"No existe la urgencia {urgencia_id}")
    motor.resolver_urgencia(db, actor, fila, True, datos.respuesta)
    db.commit()
    return {"resultado": "autorizada"}


@router.post("/urgencias/{urgencia_id}/rechazar",
             summary="No autorizar al freelance para ese servicio")
def rechazar_urgencia(urgencia_id: int, datos: s.RespuestaUrgenciaIn,
                      db: Session = Depends(get_db),
                      actor: m.Usuario = Depends(AUTORIZA)):
    fila = db.get(m.AutorizacionFreelance, urgencia_id)
    if not fila:
        raise HTTPException(404, f"No existe la urgencia {urgencia_id}")
    motor.resolver_urgencia(db, actor, fila, False, datos.respuesta)
    db.commit()
    return {"resultado": "rechazada"}


# ================================================== los documentos

def _documento(db: Session, doc_id: int) -> m.DocumentoFreelance:
    doc = db.get(m.DocumentoFreelance, doc_id)
    if not doc:
        raise HTTPException(404, f"No existe el documento {doc_id}")
    return doc


@router.post("/documentos/{doc_id}/validar",
             summary="Recursos Humanos valida un documento")
def validar(doc_id: int, db: Session = Depends(get_db),
            actor: m.Usuario = Depends(VALIDA)):
    motor.validar(db, actor, _documento(db, doc_id))
    db.commit()
    return {"resultado": "validado"}


@router.post("/documentos/{doc_id}/rechazar",
             summary="Recursos Humanos rechaza un documento, con el motivo")
def rechazar(doc_id: int, datos: s.MotivoIn, db: Session = Depends(get_db),
             actor: m.Usuario = Depends(VALIDA)):
    motor.rechazar(db, actor, _documento(db, doc_id), datos.motivo)
    db.commit()
    return {"resultado": "rechazado"}


@router.get("/archivos/{archivo_id}", summary="Abrir un archivo del expediente")
def ver_archivo(archivo_id: int, db: Session = Depends(get_db),
                _=Depends(EXPEDIENTE)):
    fila = db.get(m.ArchivoFreelance, archivo_id)
    if not fila:
        raise HTTPException(404, f"No existe el archivo {archivo_id}")
    from app.archivo import cabecera_de_archivo
    contenido = motor.leer_archivo(fila)
    return Response(content=contenido, media_type=fila.tipo,
                    headers=cabecera_de_archivo(fila.nombre))


# ======================================================== la ficha

def _servicios(dias: list) -> list[dict]:
    por_servicio: dict[int, dict] = {}
    for fecha, sv in dias:
        caja = por_servicio.setdefault(sv.id, {
            "servicio_id": sv.id, "folio": sv.folio,
            "cliente": sv.cliente.nombre if sv.cliente else None,
            "tipo": sv.tipo.value, "desde": fecha, "hasta": fecha, "dias": 0})
        caja["desde"] = min(caja["desde"], fecha)
        caja["hasta"] = max(caja["hasta"], fecha)
        caja["dias"] += 1
    salida = sorted(por_servicio.values(), key=lambda x: x["hasta"],
                    reverse=True)[:60]
    for x in salida:
        x["desde"], x["hasta"] = x["desde"].isoformat(), x["hasta"].isoformat()
    return salida


# Lo que el historial cuenta del expediente: solo para quien puede verlo
# (seccion 129, hallazgo r6-13). La central y el consultor ven si esta
# listo, no «documento rechazado · Antecedentes penales · trae un
# registro de 2019».
DEL_EXPEDIENTE = ("documento cargado", "documento validado",
                  "documento rechazado")


def _historial(db: Session, persona_id: int,
               con_expediente: bool = True) -> list[dict]:
    filas = (db.query(m.RegistroAdmin)
             .filter_by(objeto="freelance", objeto_id=persona_id)
             .order_by(m.RegistroAdmin.id.desc()).limit(80).all())
    return [{"accion": r.accion, "antes": r.antes, "despues": r.despues,
             "detalle": r.detalle,
             "quien": r.persona.nombre if r.persona else None,
             "cuando": r.creado_en.isoformat() if r.creado_en else None}
            for r in filas
            if con_expediente or r.accion not in DEL_EXPEDIENTE]


@router.get("/{persona_id}", summary="La ficha de un freelance")
def ver(persona_id: int, db: Session = Depends(get_db),
        actor: m.Usuario = Depends(VER)):
    # La del que ya paso a planta se abre tambien: como historia.
    persona, ficha = motor.ficha_de(db, persona_id, solo_vivo=False)
    fila = _filas(db, [persona])[0]
    dias = _servicios_de(db, [persona.id]).get(persona.id, [])
    alta_por = db.get(m.Persona, ficha.alta_por_id) if ficha.alta_por_id else None
    planta_por = (db.get(m.Persona, ficha.planta_por_id)
                  if ficha.planta_por_id else None)
    puede = _puede(db, actor, persona)
    fila.update({
        "alta_por": alta_por.nombre if alta_por else None,
        "planta_por": planta_por.nombre if planta_por else None,
        "lada": persona.plaza.pais.lada if persona.plaza and persona.plaza.pais else "",
        "servicios": _servicios(dias),
        "urgencias": [u for u in motor.urgencias(db, None)
                      if u["persona_id"] == persona.id],
        "historial": _historial(db, persona.id, puede["expediente"]),
        "puede": puede,
        # Si ya se le puede dar su acceso: expediente listo o urgencia
        # autorizada de un servicio vivo (seccion 128).
        "puede_acceso": (persona.es_freelance
                         and motor.puede_tener_acceso(db, persona, fila["expediente"])),
        # Lo bancario: si tiene cuenta, y el numero solo a quien deposita
        # (decision 9).
        "cuenta": "tiene" if persona.clabe else "falta",
        **({"banco": persona.banco, "clabe": persona.clabe,
            "titular_cuenta": persona.titular_cuenta}
           if puede["ve_cuenta"] else
           {"banco": persona.banco, "clabe_recortada": motor.recorte(persona.clabe)}),
    })
    db.commit()
    return fila


@router.patch("/{persona_id}", summary="Corregir los datos de un freelance")
def cambiar(persona_id: int, datos: s.FreelanceCambioIn,
            db: Session = Depends(get_db), actor: m.Usuario = Depends(ALTA)):
    persona, ficha = motor.ficha_de(db, persona_id)
    nuevos = datos.model_dump(exclude_unset=True)
    antes = {"nombre": persona.nombre, "correo": persona.correo,
             "telefono": persona.telefono,
             "plaza": persona.plaza.nombre if persona.plaza else None,
             "tipo": ficha.tipo}

    if "tipo" in nuevos and nuevos["tipo"] != ficha.tipo:
        # Cambiar el tipo cambia que se le pide: lo decide quien valida.
        if not auth.puede_el_usuario(db, actor, "freelance.validar"):
            raise HTTPException(403, "El tipo lo cambia Recursos Humanos: "
                                     "decide qué documentos se le piden.")
        ficha.tipo = nuevos["tipo"]
        if ficha.tipo == motor.PROGRAMADO:
            ficha.plazo_programado = None
            ficha.plazo_puesto_en = None
            ficha.plazo_avisado_en = None
    if "plaza_id" in nuevos and nuevos["plaza_id"]:
        plaza = _plaza(db, nuevos["plaza_id"])
        if persona.plaza and plaza.pais_id != persona.plaza.pais_id:
            raise HTTPException(409, "La ciudad nueva es de otro país: sus "
                                     "requisitos y su moneda son otros. Dalo "
                                     "de alta de nuevo en ese país.")
        persona.plaza_id = plaza.id
    if nuevos.get("nombre"):
        ficha.nombre = nuevos["nombre"].strip()
    if nuevos.get("apellidos"):
        ficha.apellidos = nuevos["apellidos"].strip()
    persona.nombre = motor.nombre_completo(ficha.nombre, ficha.apellidos)
    if nuevos.get("correo"):
        correo = _correo_libre(db, nuevos["correo"], persona.id)
        if correo != persona.correo:
            usuario = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
            if usuario is not None:
                otro = (db.query(m.Usuario)
                        .filter(func.lower(m.Usuario.correo) == correo,
                                m.Usuario.id != usuario.id).first())
                if otro is not None:
                    raise HTTPException(409, "Ese correo ya es el acceso de "
                                             "otra persona.")
                usuario.correo = correo
            persona.correo = correo
    if nuevos.get("telefono"):
        persona.telefono = _telefono(db, nuevos.get("lada"), nuevos["telefono"],
                                     persona.plaza.pais_id)
    db.flush()
    despues = {"nombre": persona.nombre, "correo": persona.correo,
               "telefono": persona.telefono,
               "plaza": persona.plaza.nombre if persona.plaza else None,
               "tipo": ficha.tipo}
    cambios = [k for k in antes if antes[k] != despues[k]]
    if cambios:
        motor._anotar(db, actor, persona, "datos",
                      antes="; ".join(f"{k}: {antes[k]}" for k in cambios),
                      despues="; ".join(f"{k}: {despues[k]}" for k in cambios),
                      detalle=persona.nombre)
    db.commit()
    return {"persona_id": persona.id, "nombre": persona.nombre,
            "cambios": cambios}


@router.put("/{persona_id}/foto", summary="La foto que sale en la hoja")
async def foto(persona_id: int, archivo: UploadFile = File(...),
               db: Session = Depends(get_db), actor: m.Usuario = Depends(ALTA)):
    """De frente y con fondo claro: es la que ve el ejecutivo en la hoja
    del servicio. La consola la reduce antes de mandarla."""
    persona, _ = motor.ficha_de(db, persona_id)
    persona.foto_url = await imagenes.leer(archivo)
    motor._anotar(db, actor, persona, "foto", detalle=persona.nombre)
    db.commit()
    return {"persona_id": persona.id, "foto": persona.foto_url}


@router.put("/{persona_id}/costos", summary="Sus costos: día completo, medio "
                                            "día, transfer y hora extra")
def costos(persona_id: int, datos: s.CostosFreelanceIn,
           db: Session = Depends(get_db), actor: m.Usuario = Depends(DINERO)):
    persona, _ = motor.ficha_de(db, persona_id)
    salida = motor.poner_costos(db, actor, persona, datos.dia_completo,
                                datos.medio_dia, datos.transfer,
                                datos.hora_extra)
    db.commit()
    return salida


@router.post("/{persona_id}/acceso", summary="Darle su acceso a EP Connect")
def acceso(persona_id: int, db: Session = Depends(get_db),
           actor: m.Usuario = Depends(ALTA)):
    persona, ficha = motor.ficha_de(db, persona_id)
    usuario = motor.dar_acceso(db, actor, persona, ficha)
    db.commit()
    return {"usuario_id": usuario.id, "correo": usuario.correo,
            # Al que vuelve con el acceso que ya tenia (seccion 132) le
            # sirve su misma contrasena.
            "que_sigue": ("Entra con su correo y la contraseña que ya tenía; "
                          "si la olvidó, la central le dicta su código en "
                          "Central → Código."
                          if usuario.hash_contrasena else
                          "La central le dicta su código de cuatro dígitos en "
                          "Central → Código y él pone su contraseña en la app.")}


@router.post("/{persona_id}/urgencias", status_code=201,
             summary="Pedir la autorizacion de urgencia para un servicio")
def pedir_urgencia(persona_id: int, datos: s.UrgenciaIn,
                   db: Session = Depends(get_db),
                   actor: m.Usuario = Depends(ASIGNA)):
    persona, _ = motor.ficha_de(db, persona_id)
    servicio = db.get(m.Servicio, datos.servicio_id)
    if not servicio:
        raise HTTPException(404, f"No existe el servicio {datos.servicio_id}")
    fila = motor.pedir_urgencia(db, actor, persona, servicio, datos.motivo)
    db.commit()
    return {"id": fila.id, "estado": fila.estado}


@router.post("/{persona_id}/baja", summary="Dar de baja a un freelance")
def baja(persona_id: int, datos: s.MotivoIn, db: Session = Depends(get_db),
         actor: m.Usuario = Depends(ALTA)):
    """Deja de ofrecerse y se le cierra el acceso. Su expediente se queda
    (decision 7): mientras colaboro y seis anos despues."""
    persona, _ = motor.ficha_de(db, persona_id)
    if not persona.activo:
        raise HTTPException(409, f"{persona.nombre} ya estaba dado de baja.")
    debiendo = accesos.viaticos_sin_cerrar(db, persona.id)
    if debiendo:
        raise HTTPException(409, {
            "mensaje": f"No se puede dar de baja a {persona.nombre}: tiene "
                       f"{len(debiendo)} viático(s) sin cerrar.",
            "que_hacer": "Primero tiene que comprobar lo que recibió.",
            "viaticos": debiendo})
    persona.activo = False
    usuario = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
    if usuario is not None and usuario.activo:
        usuario.activo = False
        accesos.anotar(db, actor, "acceso cerrado", "usuario", usuario.id,
                       antes="activo", despues="desactivado",
                       detalle=BAJA_DEL_FREELANCE)
    motor._anotar(db, actor, persona, "baja", detalle=datos.motivo[:400])
    # Los dias a los que sigue asignado no se quedan sin nadie que lo
    # sepa (seccion 128, hallazgo r6-04): la alerta en cada dia y el
    # aviso al consultor, como en la baja de Odoo; y la lista de lo que
    # queda por cubrir en la respuesta, como en el panel de accesos.
    from app.odoo_personal import alertas_de_baja
    alertas_de_baja(db, persona,
                    f"{persona.nombre} (freelance) fue dado de baja y esta "
                    "asignado a este dia: hay que reemplazarlo.")
    pendientes = accesos.jornadas_por_cubrir(db, persona.id)
    db.commit()
    return {"resultado": "baja", "jornadas_por_cubrir": pendientes,
            "aviso": (f"Sigue asignado a {sum(f['dias'] for f in pendientes)} "
                      f"dia(s) en {len(pendientes)} servicio(s). Hay que "
                      "cubrirlos." if pendientes else None)}


@router.post("/{persona_id}/reactivar", summary="Volver a dar de alta")
def reactivar(persona_id: int, db: Session = Depends(get_db),
              actor: m.Usuario = Depends(ALTA)):
    persona, _ = motor.ficha_de(db, persona_id)
    if persona.activo:
        raise HTTPException(409, f"{persona.nombre} ya está activo.")
    persona.activo = True
    usuario = db.query(m.Usuario).filter_by(persona_id=persona.id).first()
    if usuario is not None and not usuario.activo:
        ultimo = (db.query(m.RegistroAdmin)
                  .filter_by(objeto="usuario", objeto_id=usuario.id)
                  .order_by(m.RegistroAdmin.id.desc()).first())
        if ultimo is not None and ultimo.detalle == BAJA_DEL_FREELANCE:
            usuario.activo = True
            accesos.anotar(db, actor, "acceso reactivado", "usuario",
                           usuario.id, antes="desactivado", despues="activo",
                           detalle="se deshizo la baja del freelance")
    motor._anotar(db, actor, persona, "reactivado")
    db.commit()
    return {"resultado": "activo"}


@router.post("/{persona_id}/a-planta", summary="Pasarlo a planta: Centauro lo "
                                               "contrató y Odoo ya lo tiene")
def a_planta(persona_id: int, db: Session = Depends(get_db),
             actor: m.Usuario = Depends(VALIDA)):
    """Lo pide Recursos Humanos cuando Odoo ya lo tiene dado de alta con
    su mismo correo (seccion 132, decision 6). La ficha se cierra como
    historia; la persona sigue, ya de planta, y la siguiente lectura de
    personal la reconoce por su correo."""
    persona, ficha = motor.ficha_de(db, persona_id)
    salida = motor.a_planta(db, actor, persona, ficha)
    db.commit()
    return salida


# ===================================================== el expediente

def _doc(d: m.DocumentoFreelance | None, ve_cuenta: bool,
         nombres: dict) -> dict | None:
    if d is None:
        return None
    datos = json.loads(d.datos) if d.datos else {}
    if "numero" in datos:
        datos["numero_recortado"] = motor.recorte(datos["numero"])
    if "clabe" in datos:
        datos["clabe_recortada"] = motor.recorte(datos["clabe"])
        if not ve_cuenta:
            datos.pop("clabe")
    return {
        "id": d.id, "estado": d.estado, "datos": datos,
        "fecha_documento": d.fecha_documento.isoformat() if d.fecha_documento else None,
        "vence_en": d.vence_en.isoformat() if d.vence_en else None,
        "subido_por": nombres.get(d.subido_por_id),
        "subido_en": d.subido_en.isoformat() if d.subido_en else None,
        "revisado_por": nombres.get(d.revisado_por_id),
        "revisado_en": d.revisado_en.isoformat() if d.revisado_en else None,
        "motivo_rechazo": d.motivo_rechazo,
        "archivos": [{"id": a.id, "nombre": a.nombre, "tipo": a.tipo,
                      "tamano": a.tamano, "en_google": bool(a.objeto)}
                     for a in d.archivos],
    }


@router.get("/{persona_id}/expediente", summary="Su expediente, requisito por "
                                                "requisito")
def ver_expediente(persona_id: int, db: Session = Depends(get_db),
                   actor: m.Usuario = Depends(EXPEDIENTE)):
    # El del que paso a planta se sigue leyendo: es su historia.
    persona, ficha = motor.ficha_de(db, persona_id, solo_vivo=False)
    hoy = motor._hoy(db, persona)
    pais_id = persona.plaza.pais_id if persona.plaza else None
    requisitos = motor.requisitos_de(db, pais_id)
    suyos = motor.documentos_de(db, [persona.id]).get(persona.id, {})
    anteriores = dict(db.query(m.DocumentoFreelance.requisito_id,
                               func.count(m.DocumentoFreelance.id))
                      .filter(m.DocumentoFreelance.persona_id == persona.id,
                              m.DocumentoFreelance.reemplazado_en.isnot(None))
                      .group_by(m.DocumentoFreelance.requisito_id).all())
    ids = {d.subido_por_id for ds in suyos.values() for d in ds} | {
        d.revisado_por_id for ds in suyos.values() for d in ds}
    nombres = {p.id: p.nombre for p in db.query(m.Persona).filter(
        m.Persona.id.in_([i for i in ids if i]))} if ids else {}
    ve_cuenta = auth.puede_el_usuario(db, actor, "viaticos.transferir")
    propios = motor.del_tipo(requisitos, ficha.tipo)
    extra = ([r for r in motor.del_tipo(requisitos, motor.PROGRAMADO)
              if r not in propios] if ficha.tipo == motor.EMERGENCIA else [])
    renglones = []
    for r, para_programado in ([(r, False) for r in propios]
                               + [(r, True) for r in extra]):
        x = motor.renglon(r, suyos.get(r.id, []), hoy)
        renglones.append({
            "requisito_id": r.id, "clave": r.clave, "nombre": r.nombre,
            "detalle": r.detalle, "captura": r.captura, "vigencia": r.vigencia,
            "vigencia_meses": r.vigencia_meses,
            "antiguedad_meses": r.antiguedad_meses,
            "estado": x["estado"], "cuenta": x["cuenta"], "dias": x["dias"],
            "para_programado": para_programado,
            "efectivo": _doc(x["efectivo"], ve_cuenta, nombres),
            "pendiente": _doc(x["pendiente"], ve_cuenta, nombres),
            "anteriores": anteriores.get(r.id, 0),
        })
    db.commit()
    return {"persona_id": persona.id, "nombre": persona.nombre,
            "tipo": ficha.tipo,
            "resumen": motor.expediente(db, persona, ficha, hoy, requisitos,
                                        suyos),
            "requisitos": renglones,
            "puede_validar": (persona.es_freelance
                              and auth.puede_el_usuario(db, actor,
                                                        "freelance.validar")),
            # Al que paso a planta ya no se le carga nada: es historia.
            "puede_cargar": persona.es_freelance,
            "ve_cuenta": ve_cuenta,
            "limite_mb": motor.LIMITE_ARCHIVO // (1024 * 1024)}


@router.post("/{persona_id}/expediente/{requisito_id}", status_code=201,
             summary="Cargar un documento del expediente")
async def cargar(persona_id: int, requisito_id: int,
                 datos: str = Form("{}"),
                 fecha_documento: str | None = Form(None),
                 vence_en: str | None = Form(None),
                 validar: bool = Form(False),
                 archivos: list[UploadFile] = File(default=[]),
                 db: Session = Depends(get_db),
                 actor: m.Usuario = Depends(EXPEDIENTE)):
    persona, ficha = motor.ficha_de(db, persona_id)
    requisito = db.get(m.RequisitoFreelance, requisito_id)
    if not requisito:
        raise HTTPException(404, f"No existe el requisito {requisito_id}")
    try:
        crudo = json.loads(datos or "{}")
    except ValueError:
        raise HTTPException(400, "Los datos no llegaron completos.")
    leidos = []
    for a in archivos or []:
        contenido = await a.read()
        if not contenido and not a.filename:
            continue
        nombre, tipo = motor.revisar_archivo(a.filename, a.content_type,
                                             contenido)
        leidos.append((nombre, tipo, contenido))
    hoy = motor._hoy(db, persona)
    preparado = motor.preparar(db, persona, requisito, crudo, fecha_documento,
                               vence_en, leidos, hoy)
    doc = motor.cargar(db, actor, persona, ficha, requisito, preparado,
                       leidos, validar)
    db.commit()
    return {"documento_id": doc.id, "estado": doc.estado,
            "vence_en": doc.vence_en.isoformat() if doc.vence_en else None}
