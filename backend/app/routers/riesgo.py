"""El mapa de riesgo de la Central de Inteligencia (seccion 130)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import riesgo as motor
from app.db import get_db

router = APIRouter(prefix="/riesgo", tags=["Central de Inteligencia"])

VER = auth.puede("riesgo.ver")
PUBLICAR = auth.puede("riesgo.publicar")
CONFIRMAR = auth.puede("riesgo.confirmar")
CATALOGO = auth.puede("riesgo.catalogo")


class Evento(BaseModel):
    pais_id: int | None = None
    region_id: int | None = None
    municipio: str | None = Field(None, max_length=120)
    tipo_id: int | None = None
    nivel: int | None = None
    titulo: str | None = Field(None, max_length=160)
    texto_cliente: str | None = Field(None, max_length=2000)
    lat: float | None = None
    lon: float | None = None
    radio_m: int | None = None
    lugar: str | None = Field(None, max_length=300)
    ocurrio_en: datetime | None = None
    vigente_hasta: datetime | None = None
    tendencia: str | None = None


class Motivo(BaseModel):
    motivo: str = Field("", max_length=400)


class Fuente(BaseModel):
    descripcion: str = Field(..., max_length=300)
    url: str | None = Field(None, max_length=600)
    oficial: bool = False


class Tipo(BaseModel):
    pais_id: int | None = None
    nombre: str | None = Field(None, max_length=80)
    definicion: str | None = Field(None, max_length=3000)
    radio_m: int | None = None
    orden: int | None = None
    activo: bool | None = None


def _salida(db: Session, evento: m.EventoRiesgo) -> dict:
    datos = motor.vista(evento)
    datos["bitacora"] = motor.bitacora(db, evento)
    return datos


@router.get("/catalogos", summary="Estados, tipos y niveles de un pais")
def catalogos(pais_id: int, db: Session = Depends(get_db), _=Depends(VER)):
    regiones = (db.query(m.Region).filter_by(pais_id=pais_id, activo=True)
                .order_by(m.Region.nombre).all())
    tipos = (db.query(m.TipoEvento).filter_by(pais_id=pais_id)
             .order_by(m.TipoEvento.orden, m.TipoEvento.nombre).all())
    return {
        "regiones": [{"id": r.id, "nombre": r.nombre, "clave": r.clave}
                     for r in regiones],
        "tipos": [{"id": t.id, "nombre": t.nombre, "definicion": t.definicion,
                   "radio_m": t.radio_m, "activo": t.activo} for t in tipos],
        "niveles": [{"nivel": n, "nombre": nombre}
                    for n, nombre in motor.NIVELES.items()],
        "tendencias": [t.value for t in m.TendenciaEvento],
    }


@router.get("/mapa-llave", summary="La llave de Google del mapa interactivo")
def mapa_llave(_=Depends(VER)):
    """Solo a quien ve el mapa. La llave va limitada en Google a las
    direcciones del sistema: aun copiada, no sirve en otro sitio."""
    from app.config import settings
    return {"llave": settings.google_maps_key_navegador or None}


@router.get("/mapa", summary="Lo vigente y la cola del analista")
def mapa(pais_id: int | None = None, db: Session = Depends(get_db),
         ahora: datetime | None = None, _=Depends(VER)):
    return motor.del_mapa(db, pais_id, ahora)


@router.get("/eventos/{evento_id}", summary="Un evento con su bitacora")
def ver(evento_id: int, db: Session = Depends(get_db), _=Depends(VER)):
    return _salida(db, motor.evento_de(db, evento_id))


@router.post("/eventos", summary="Capturar un evento (queda propuesto)")
def crear(datos: Evento, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.crear(db, usuario, datos.model_dump(exclude_none=True))
    db.commit()
    return _salida(db, evento)


@router.patch("/eventos/{evento_id}", summary="Corregir o actualizar un evento")
def editar(evento_id: int, datos: Evento, db: Session = Depends(get_db),
           ahora: datetime | None = None,
           usuario: m.Usuario = Depends(PUBLICAR)):
    cambios = datos.model_dump(exclude_unset=True)
    cambios.pop("pais_id", None)
    evento = motor.editar(db, usuario, motor.evento_de(db, evento_id),
                          cambios, ahora)
    db.commit()
    return _salida(db, evento)


@router.post("/eventos/{evento_id}/publicar",
             summary="Publicarlo: el cliente lo ve (el nivel 4 espera al jefe)")
def publicar(evento_id: int, db: Session = Depends(get_db),
             ahora: datetime | None = None,
             usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.publicar(db, usuario, motor.evento_de(db, evento_id), ahora)
    db.commit()
    return _salida(db, evento)


@router.post("/eventos/{evento_id}/confirmar",
             summary="El jefe de turno confirma el nivel 4")
def confirmar(evento_id: int, db: Session = Depends(get_db),
              ahora: datetime | None = None,
              usuario: m.Usuario = Depends(CONFIRMAR)):
    evento = motor.confirmar_critico(db, usuario,
                                     motor.evento_de(db, evento_id), ahora)
    db.commit()
    return _salida(db, evento)


@router.post("/eventos/{evento_id}/devolver",
             summary="El jefe de turno no confirma el nivel 4")
def devolver(evento_id: int, datos: Motivo, db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(CONFIRMAR)):
    evento = motor.devolver_critico(db, usuario,
                                    motor.evento_de(db, evento_id),
                                    datos.motivo)
    db.commit()
    return _salida(db, evento)


@router.post("/eventos/{evento_id}/cerrar", summary="Darlo por terminado")
def cerrar(evento_id: int, datos: Motivo, db: Session = Depends(get_db),
           usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.cerrar(db, usuario, motor.evento_de(db, evento_id),
                          datos.motivo)
    db.commit()
    return _salida(db, evento)


@router.post("/eventos/{evento_id}/descartar",
             summary="Descartar lo que no se confirmo")
def descartar(evento_id: int, datos: Motivo, db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.descartar(db, usuario, motor.evento_de(db, evento_id),
                             datos.motivo)
    db.commit()
    return _salida(db, evento)


@router.post("/eventos/{evento_id}/fuentes", summary="Agregar una fuente")
def agregar_fuente(evento_id: int, datos: Fuente,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.evento_de(db, evento_id)
    motor.agregar_fuente(db, usuario, evento, datos.descripcion, datos.url,
                         datos.oficial)
    db.commit()
    return _salida(db, evento)


@router.delete("/eventos/{evento_id}/fuentes/{fuente_id}",
               summary="Quitar una fuente")
def quitar_fuente(evento_id: int, fuente_id: int,
                  db: Session = Depends(get_db),
                  usuario: m.Usuario = Depends(PUBLICAR)):
    evento = motor.evento_de(db, evento_id)
    motor.quitar_fuente(db, usuario, evento, fuente_id)
    db.commit()
    return _salida(db, evento)


# ------------------------------------------------- el catalogo de tipos

@router.post("/tipos", summary="Agregar un tipo de evento")
def crear_tipo(datos: Tipo, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(CATALOGO)):
    if not datos.pais_id or not db.get(m.Pais, datos.pais_id):
        raise HTTPException(400, "Falta el país del tipo de evento")
    nombre = (datos.nombre or "").strip()
    if len(nombre) < 3:
        raise HTTPException(400, "Falta el nombre del tipo de evento")
    if db.query(m.TipoEvento).filter_by(pais_id=datos.pais_id,
                                        nombre=nombre).first():
        raise HTTPException(409, f"Ya existe «{nombre}» en ese país")
    tipo = m.TipoEvento(pais_id=datos.pais_id, nombre=nombre,
                        definicion=(datos.definicion or "").strip(),
                        radio_m=_radio(datos.radio_m) or 2000,
                        orden=datos.orden or 0)
    db.add(tipo)
    db.commit()
    return {"id": tipo.id}


@router.patch("/tipos/{tipo_id}", summary="Corregir un tipo de evento")
def editar_tipo(tipo_id: int, datos: Tipo, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(CATALOGO)):
    tipo = db.get(m.TipoEvento, tipo_id)
    if not tipo:
        raise HTTPException(404, f"No existe el tipo {tipo_id}")
    if datos.nombre is not None:
        nombre = datos.nombre.strip()
        if len(nombre) < 3:
            raise HTTPException(400, "Falta el nombre del tipo de evento")
        otro = (db.query(m.TipoEvento)
                .filter_by(pais_id=tipo.pais_id, nombre=nombre).first())
        if otro and otro.id != tipo.id:
            raise HTTPException(409, f"Ya existe «{nombre}» en ese país")
        tipo.nombre = nombre
    if datos.definicion is not None:
        tipo.definicion = datos.definicion.strip()
    if datos.radio_m is not None:
        tipo.radio_m = _radio(datos.radio_m)
    if datos.orden is not None:
        tipo.orden = datos.orden
    if datos.activo is not None:
        tipo.activo = datos.activo
    db.commit()
    return {"id": tipo.id}


def _radio(valor: int | None) -> int | None:
    if valor is None:
        return None
    if not 50 <= valor <= 200000:
        raise HTTPException(400, "El radio va de 50 metros a 200 km")
    return valor


# ------------------------------------- los clientes de la Central (131)

import re  # noqa: E402

from app import alertas_riesgo  # noqa: E402

CLIENTES = auth.puede("riesgo.clientes")
CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AltaCliente(BaseModel):
    cliente_id: int


class EstadoCliente(BaseModel):
    activo: bool


class Zonas(BaseModel):
    region_ids: list[int]


class Gente(BaseModel):
    nombre: str | None = Field(None, max_length=80)
    apellidos: str | None = Field(None, max_length=120)
    correo: str | None = Field(None, max_length=160)
    telefono: str | None = Field(None, max_length=40)
    perfil: str | None = None
    idioma: str | None = None
    activo: bool | None = None


class Llamada(BaseModel):
    nota: str = Field("", max_length=400)


def _cliente_central(db: Session, cc_id: int) -> m.ClienteCentral:
    cc = db.get(m.ClienteCentral, cc_id)
    if not cc:
        raise HTTPException(404, f"No existe el cliente de la Central {cc_id}")
    return cc


def _vista_cliente(db: Session, cc: m.ClienteCentral) -> dict:
    gente = (db.query(m.UsuarioCliente).filter_by(cliente_central_id=cc.id)
             .order_by(m.UsuarioCliente.nombre).all())
    return {
        "id": cc.id, "cliente_id": cc.cliente_id,
        "cliente": cc.cliente.nombre, "pais_id": cc.cliente.pais_id,
        "activo": cc.activo,
        "zonas": sorted(({"region_id": z.region_id, "nombre": z.region.nombre}
                         for z in cc.zonas), key=lambda z: z["nombre"]),
        "gente": [{"id": g.id, "nombre": g.nombre, "apellidos": g.apellidos,
                   "correo": g.correo, "telefono": g.telefono,
                   "perfil": g.perfil.value, "idioma": g.idioma,
                   "activo": g.activo,
                   "con_contrasena": g.hash_contrasena is not None,
                   "ultimo_acceso": (g.ultimo_acceso.isoformat()
                                     if g.ultimo_acceso else None)}
                  for g in gente],
    }


@router.get("/clientes", summary="Los clientes con el servicio de la Central")
def clientes(db: Session = Depends(get_db), _=Depends(VER)):
    filas = (db.query(m.ClienteCentral).join(m.Cliente)
             .order_by(m.Cliente.nombre).all())
    return [_vista_cliente(db, cc) for cc in filas]


@router.post("/clientes", summary="Darle a un cliente el servicio de la Central")
def alta_cliente(datos: AltaCliente, db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(CLIENTES)):
    cliente = db.get(m.Cliente, datos.cliente_id)
    if not cliente or not cliente.activo:
        raise HTTPException(404, "Ese cliente no existe o no está activo en "
                                 "Odoo")
    cc = db.query(m.ClienteCentral).filter_by(cliente_id=cliente.id).first()
    if cc:
        cc.activo = True
    else:
        cc = m.ClienteCentral(cliente_id=cliente.id, alta_por_id=usuario.id)
        db.add(cc)
    db.commit()
    return _vista_cliente(db, cc)


@router.patch("/clientes/{cc_id}", summary="Encender o apagar el servicio")
def estado_cliente(cc_id: int, datos: EstadoCliente,
                   db: Session = Depends(get_db),
                   usuario: m.Usuario = Depends(CLIENTES)):
    cc = _cliente_central(db, cc_id)
    cc.activo = datos.activo
    db.commit()
    return _vista_cliente(db, cc)


@router.put("/clientes/{cc_id}/zonas", summary="Los estados que sigue")
def zonas(cc_id: int, datos: Zonas, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(CLIENTES)):
    cc = _cliente_central(db, cc_id)
    pedidas = set(datos.region_ids)
    regiones = db.query(m.Region).filter(m.Region.id.in_(pedidas)).all() \
        if pedidas else []
    if len(regiones) != len(pedidas):
        raise HTTPException(400, "Uno de esos estados no existe")
    if any(r.pais_id != cc.cliente.pais_id for r in regiones):
        raise HTTPException(400, {
            "mensaje": "Un estado no es del país del cliente",
            "que_hacer": "El cliente sigue estados de su país. Para otro "
                         "país, se da de alta su cliente de ese país."})
    actuales = {z.region_id: z for z in cc.zonas}
    for region_id, zona in actuales.items():
        if region_id not in pedidas:
            cc.zonas.remove(zona)
    for region_id in pedidas - set(actuales):
        cc.zonas.append(m.ZonaCliente(region_id=region_id))
    db.commit()
    return _vista_cliente(db, cc)


def _datos_de_gente(datos: Gente, nueva: bool) -> dict:
    salida = {}
    if datos.nombre is not None or nueva:
        nombre = (datos.nombre or "").strip()
        if len(nombre) < 2:
            raise HTTPException(400, "Falta el nombre")
        salida["nombre"] = nombre
    if datos.apellidos is not None or nueva:
        apellidos = (datos.apellidos or "").strip()
        if len(apellidos) < 2:
            raise HTTPException(400, "Faltan los apellidos")
        salida["apellidos"] = apellidos
    if datos.correo is not None or nueva:
        correo = (datos.correo or "").strip().lower()
        if not CORREO.match(correo):
            raise HTTPException(400, "Ese correo no es válido")
        salida["correo"] = correo
    if datos.telefono is not None:
        telefono = datos.telefono.strip() or None
        if telefono and not telefono.startswith("+"):
            raise HTTPException(400, "El teléfono va con su clave de país: "
                                     "+52, +55…")
        salida["telefono"] = telefono
    if datos.perfil is not None:
        try:
            salida["perfil"] = m.PerfilCliente(datos.perfil)
        except ValueError:
            raise HTTPException(400, "El perfil es gerente, viajero u "
                                     "operador")
    if datos.idioma is not None:
        if datos.idioma not in ("es", "pt", "en"):
            raise HTTPException(400, "El idioma es es, pt o en")
        salida["idioma"] = datos.idioma
    if datos.activo is not None:
        salida["activo"] = datos.activo
    return salida


@router.post("/clientes/{cc_id}/gente",
             summary="Dar de alta a alguien del cliente en su app")
def alta_gente(cc_id: int, datos: Gente, db: Session = Depends(get_db),
               usuario: m.Usuario = Depends(CLIENTES)):
    cc = _cliente_central(db, cc_id)
    campos = _datos_de_gente(datos, nueva=True)
    if db.query(m.UsuarioCliente).filter_by(correo=campos["correo"]).first():
        raise HTTPException(409, "Ese correo ya entra a la app de la Central")
    campos.setdefault("perfil", m.PerfilCliente.GERENTE)
    campos.setdefault("idioma", "es")
    gente = m.UsuarioCliente(cliente_central_id=cc.id,
                             alta_por_usuario_id=usuario.id, **campos)
    db.add(gente)
    db.commit()
    return _vista_cliente(db, cc)


@router.patch("/clientes/{cc_id}/gente/{gente_id}",
              summary="Corregir o cerrar el acceso de alguien del cliente")
def editar_gente(cc_id: int, gente_id: int, datos: Gente,
                 db: Session = Depends(get_db),
                 usuario: m.Usuario = Depends(CLIENTES)):
    cc = _cliente_central(db, cc_id)
    gente = db.get(m.UsuarioCliente, gente_id)
    if not gente or gente.cliente_central_id != cc.id:
        raise HTTPException(404, "Esa persona no es de este cliente")
    campos = _datos_de_gente(datos, nueva=False)
    if "correo" in campos and campos["correo"] != gente.correo:
        if db.query(m.UsuarioCliente).filter_by(
                correo=campos["correo"]).first():
            raise HTTPException(409, "Ese correo ya entra a la app de la "
                                     "Central")
    for clave, valor in campos.items():
        setattr(gente, clave, valor)
    if campos.get("activo") is False or "correo" in campos:
        # Cerrar el acceso o cambiar el correo tira las sesiones abiertas.
        gente.sesiones_desde = datetime.now().astimezone()
    db.commit()
    return _vista_cliente(db, cc)


@router.get("/eventos/{evento_id}/avisos",
            summary="A quien le llego el evento y si lo vio")
def avisos(evento_id: int, db: Session = Depends(get_db), _=Depends(VER)):
    return alertas_riesgo.del_evento(db, motor.evento_de(db, evento_id))


@router.get("/por-llamar", summary="Nivel 4 sin acuse: la central llama")
def por_llamar(db: Session = Depends(get_db), ahora: datetime | None = None,
               _=Depends(VER)):
    return alertas_riesgo.por_llamar(db, ahora)


@router.post("/avisos/{alerta_id}/llamada",
             summary="Lo que paso en la llamada al cliente")
def llamada(alerta_id: int, datos: Llamada, db: Session = Depends(get_db),
            usuario: m.Usuario = Depends(PUBLICAR)):
    alerta = alertas_riesgo.registrar_llamada(db, usuario, alerta_id,
                                              datos.nota)
    db.commit()
    return alertas_riesgo.vista_alerta(alerta)
