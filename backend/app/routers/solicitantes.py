"""Quien pide servicios a nombre de cada cliente.

Se da de alta la primera vez que pide un servicio y queda guardado. En los
siguientes el consultor lo elige de la lista en vez de volver a capturar
correo y telefono, y la lista sirve ademas para saber quien esta
autorizado a solicitar servicios de ese cliente.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import auth
from app import models as m
from app import schemas as s
from app import telefonos
from app.db import get_db

router = APIRouter(prefix="/solicitantes", tags=["Solicitantes"])


def _limpio(texto: str | None) -> str | None:
    texto = (texto or "").strip()
    return texto or None


def _con_clave_de_pais(db: Session, cliente_id: int,
                       telefono: str | None) -> str | None:
    """El telefono se guarda con la clave del pais del cliente."""
    cliente = db.get(m.Cliente, cliente_id)
    return telefonos.normalizar(db, telefono,
                                cliente.pais_id if cliente else None)


def buscar_o_crear(db: Session, cliente_id: int, nombre: str | None,
                   apellidos: str | None, correo: str | None,
                   telefono: str | None) -> m.Solicitante | None:
    """El contacto que corresponde a esos datos, dandolo de alta si es nuevo.

    Se reconoce por el correo cuando lo hay, porque es lo unico que no se
    escribe de dos formas distintas; si no hay correo, por nombre y
    apellidos. Lo que llegue nuevo (un telefono que antes faltaba) se
    guarda; lo que ya estaba no se pisa con un campo vacio.
    """
    nombre, apellidos = _limpio(nombre), _limpio(apellidos)
    correo, telefono = _limpio(correo), _limpio(telefono)
    if not nombre:
        return None
    telefono = _con_clave_de_pais(db, cliente_id, telefono)

    consulta = db.query(m.Solicitante).filter_by(cliente_id=cliente_id)
    encontrado = (consulta.filter(m.Solicitante.correo.ilike(correo)).first()
                  if correo else
                  consulta.filter(
                      m.Solicitante.nombre.ilike(nombre),
                      func.coalesce(m.Solicitante.apellidos, "")
                      .ilike(apellidos or "")).first())

    if encontrado:
        for campo, valor in (("apellidos", apellidos), ("correo", correo),
                             ("telefono", telefono)):
            if valor and not getattr(encontrado, campo):
                setattr(encontrado, campo, valor)
        return encontrado

    nuevo = m.Solicitante(cliente_id=cliente_id, nombre=nombre,
                          apellidos=apellidos, correo=correo, telefono=telefono)
    db.add(nuevo)
    db.flush()
    return nuevo


@router.get("", response_model=list[s.SolicitanteOut],
            summary="Quien puede solicitar servicios de un cliente")
def listar(cliente_id: int | None = None, db: Session = Depends(get_db),
           _=Depends(auth.puede("solicitantes.ver"))):
    consulta = db.query(m.Solicitante).filter_by(activo=True)
    if cliente_id:
        consulta = consulta.filter_by(cliente_id=cliente_id)
    return consulta.order_by(m.Solicitante.nombre).all()


@router.post("", response_model=s.SolicitanteOut, status_code=201,
             summary="Dar de alta a quien solicita")
def crear(datos: s.SolicitanteIn, db: Session = Depends(get_db),
          _=Depends(auth.puede("solicitantes.alta"))):
    if not db.get(m.Cliente, datos.cliente_id):
        raise HTTPException(404, f"No existe el cliente {datos.cliente_id}")
    contacto = m.Solicitante(**datos.model_dump())
    contacto.telefono = _con_clave_de_pais(db, datos.cliente_id, contacto.telefono)
    db.add(contacto)
    db.commit()
    db.refresh(contacto)
    return contacto


@router.patch("/{solicitante_id}", response_model=s.SolicitanteOut,
              summary="Corregir los datos de quien solicita")
def editar(solicitante_id: int, datos: s.SolicitanteIn,
           db: Session = Depends(get_db),
           _=Depends(auth.puede("solicitantes.editar"))):
    """Corrige el contacto de aqui en adelante. Los servicios ya dados de
    alta conservan los datos con los que se hicieron."""
    contacto = db.get(m.Solicitante, solicitante_id)
    if not contacto:
        raise HTTPException(404, f"No existe el solicitante {solicitante_id}")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(contacto, campo, valor)
    contacto.telefono = _con_clave_de_pais(db, contacto.cliente_id,
                                           contacto.telefono)
    db.commit()
    db.refresh(contacto)
    return contacto


@router.delete("/{solicitante_id}", status_code=204,
               summary="Dar de baja a quien ya no solicita")
def desactivar(solicitante_id: int, db: Session = Depends(get_db),
               _=Depends(auth.puede("solicitantes.editar"))):
    """No se borra: deja de aparecer en la lista, pero los servicios que
    pidio siguen diciendo quien los pidio."""
    contacto = db.get(m.Solicitante, solicitante_id)
    if not contacto:
        raise HTTPException(404, f"No existe el solicitante {solicitante_id}")
    contacto.activo = False
    db.commit()
