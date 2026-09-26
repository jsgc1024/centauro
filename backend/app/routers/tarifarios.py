# -*- coding: utf-8 -*-
"""Los tarifarios que vienen de Odoo, vistos desde Centauro (seccion 77).

Dos cosas viven aqui:

  * **Que es cada producto de Odoo.** La tabla que confirma finanzas: sin
    ella no se sabe que precio de la lista es el del conductor y cual el
    de la Suburban. Se lee de Odoo desde aqui mismo --finanzas no espera
    a nadie-- y lo confirmado ya no lo toca ninguna lectura. Es la misma
    tabla con que saldra la factura del paso 4.
  * **El tarifario de un cliente**, tal como quedo de su lista de Odoo:
    que precio tiene cada rol, cada unidad y cada paquete, y de donde
    salio cada uno. Lo ven quienes cotizan y quienes facturan; aqui no se
    edita: se corrige en Odoo.

La lectura de las listas --ensayo, aplicar y cada hora-- vive en la
pantalla de Odoo (`/odoo/tarifarios`), como las otras cuatro.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import accesos, auth, odoo_api, odoo_tarifarios
from app import cotizacion as cot
from app import models as m
from app import odoo_tarifarios_reglas as reglas
from app.db import get_db

router = APIRouter(prefix="/tarifarios", tags=["Tarifarios"])

# Ver lo mismo que se ve en el cierre: quien cotiza, quien cierra y quien
# factura. Decir que es cada producto es de finanzas --de ahi sale lo que
# se le cobra al cliente--, la misma puerta que facturar.
VER = auth.puede("cierre.ver")
PRODUCTOS = auth.puede("cierre.facturar")


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ================================================================ productos

class ProductoIn(BaseModel):
    clase: str | None = None
    perfil_id: int | None = None
    categoria_id: int | None = None
    modalidad: str | None = None


def _catalogo(db: Session) -> dict:
    return {
        "perfiles": [{"id": p.id, "nombre": p.nombre} for p in
                     db.query(m.PerfilPersonal).filter_by(activo=True)
                     .order_by(m.PerfilPersonal.id)],
        "categorias": [{"id": c.id, "nombre": c.nombre} for c in
                       db.query(m.CategoriaVehiculo).filter_by(activo=True)
                       .order_by(m.CategoriaVehiculo.nombre)],
    }


@router.get("/productos", summary="Que es en Centauro cada producto de Odoo")
def productos(db: Session = Depends(get_db),
              usuario: m.Usuario = Depends(VER)):
    """La tabla de productos, con los roles y las unidades para escoger, y
    si quien pregunta puede cambiarla."""
    filas = odoo_tarifarios.tabla_de_productos(db)
    leido = max((p.odoo_sincronizado_en for p in db.query(m.ProductoOdoo)
                 if p.odoo_sincronizado_en), default=None)
    return {"productos": filas, **_catalogo(db),
            "puede_editar": auth.puede_el_usuario(db, usuario, "cierre.facturar"),
            "conectado": odoo_api.hay_conexion(),
            "leidos_en": leido.isoformat() if leido else None}


@router.post("/productos/leer", summary="Traer los productos de Odoo")
def leer(db: Session = Depends(get_db),
         usuario: m.Usuario = Depends(PRODUCTOS)):
    """Trae de Odoo los productos que se venden, con su sugerencia. Lo ya
    confirmado no se toca. No espera a la lectura de los tarifarios: asi
    finanzas confirma antes de que alguien aplique."""
    try:
        odoo = odoo_api.cliente()
    except odoo_api.SinConexion:
        raise HTTPException(503, {
            "mensaje": "Odoo no esta conectado en este servidor.",
            "que_hacer": "Falta ODOO_BASE y ODOO_API_KEY en el .env del servidor.",
        })
    try:
        cuenta = odoo_tarifarios.leer_productos(db, odoo)
    except odoo_api.NoResponde as error:
        db.rollback()
        raise HTTPException(502, {"mensaje": str(error),
                                  "que_hacer": "La llave de Odoo tiene que poder "
                                               "leer Ventas: productos y listas "
                                               "de precios."})
    accesos.anotar(db, usuario, "productos leidos de odoo", "producto_odoo", None,
                   despues=f"{cuenta['leidos']} leidos, {cuenta['nuevos']} nuevos")
    db.commit()
    return cuenta


def _validar(db: Session, datos: ProductoIn) -> dict:
    """Que lo que se dice de un producto este completo y exista."""
    clase = datos.clase
    if clase is not None and clase not in reglas.CLASES:
        raise HTTPException(422, f"Clase desconocida: {clase}")
    necesita = {reglas.ROL: ("perfil_id", "modalidad"),
                reglas.UNIDAD: ("categoria_id", "modalidad"),
                reglas.PAQUETE: ("perfil_id", "categoria_id", "modalidad")}
    valores = {"clase": clase, "perfil_id": None, "categoria_id": None,
               "modalidad": None}
    for campo in necesita.get(clase, ()):
        valor = getattr(datos, campo)
        if valor in (None, ""):
            raise HTTPException(422, {
                "mensaje": "Falta decir " + {"perfil_id": "el rol",
                                              "categoria_id": "la unidad",
                                              "modalidad": "la modalidad"}[campo],
                "campo": campo})
        valores[campo] = valor
    if clase == reglas.HORA_EXTRA and datos.perfil_id:
        valores["perfil_id"] = datos.perfil_id        # la de un solo rol
    if valores["modalidad"] and valores["modalidad"] not in reglas.MODALIDADES:
        raise HTTPException(422, f"Modalidad desconocida: {valores['modalidad']}")
    if valores["perfil_id"] and not db.get(m.PerfilPersonal, valores["perfil_id"]):
        raise HTTPException(422, "Ese rol no existe")
    if valores["categoria_id"] and not db.get(m.CategoriaVehiculo,
                                              valores["categoria_id"]):
        raise HTTPException(422, "Esa unidad no existe")
    return valores


@router.patch("/productos/{producto_id}",
              summary="Decir que es un producto de Odoo")
def decir(producto_id: int, datos: ProductoIn, db: Session = Depends(get_db),
          usuario: m.Usuario = Depends(PRODUCTOS)):
    """Guardar lo que es un producto lo deja confirmado: ninguna lectura lo
    vuelve a sugerir. Sin clase, se queda por decidir."""
    producto = db.get(m.ProductoOdoo, producto_id)
    if producto is None:
        raise HTTPException(404, "Ese producto no esta en la tabla")
    valores = _validar(db, datos)
    antes = f"{producto.clase} {producto.perfil_id} {producto.categoria_id} {producto.modalidad}"
    if any(getattr(producto, c) != v for c, v in valores.items()):
        # Dice otra cosa: ya no es el que manda entre los que decian lo
        # mismo que antes.
        producto.preferido = False
    for campo, valor in valores.items():
        setattr(producto, campo, valor)
    producto.confirmado = valores["clase"] is not None
    producto.confirmado_por_id = usuario.persona_id if producto.confirmado else None
    producto.confirmado_en = _utc() if producto.confirmado else None
    accesos.anotar(db, usuario, "producto de odoo confirmado", "producto_odoo",
                   producto.id, antes=antes,
                   despues=f"{producto.clase} {producto.perfil_id} "
                           f"{producto.categoria_id} {producto.modalidad}",
                   detalle=producto.nombre[:200])
    db.commit()
    return next(p for p in odoo_tarifarios.tabla_de_productos(db)
                if p["id"] == producto.id)


class PreferidoIn(BaseModel):
    preferido: bool = True


@router.post("/productos/{producto_id}/preferido",
             summary="Que mande este producto entre los que dicen lo mismo")
def preferir(producto_id: int, datos: PreferidoIn = PreferidoIn(),
             db: Session = Depends(get_db),
             usuario: m.Usuario = Depends(PRODUCTOS)):
    """«Agente de Seguridad Bilingue» y «Bilingual Security Agent» dicen
    lo mismo. Si la lista no pacta ninguno, sin esto no se sabe cual
    precio tomar y ese concepto se queda sin precio. El que manda es uno:
    marcar este le quita la marca a los demas que dicen lo mismo."""
    producto = db.get(m.ProductoOdoo, producto_id)
    if producto is None:
        raise HTTPException(404, "Ese producto no esta en la tabla")
    concepto = reglas.concepto_de({"clase": producto.clase,
                                   "perfil_id": producto.perfil_id,
                                   "categoria_id": producto.categoria_id,
                                   "modalidad": producto.modalidad})
    if not producto.confirmado or concepto is None:
        raise HTTPException(409, "Primero se confirma que es: un rol, una "
                                 "unidad, un paquete o la hora extra.")
    if datos.preferido:
        for otro in db.query(m.ProductoOdoo).filter(
                m.ProductoOdoo.id != producto.id,
                m.ProductoOdoo.clase == producto.clase,
                m.ProductoOdoo.preferido.is_(True)):
            if reglas.concepto_de({"clase": otro.clase, "perfil_id": otro.perfil_id,
                                   "categoria_id": otro.categoria_id,
                                   "modalidad": otro.modalidad}) == concepto:
                otro.preferido = False
    producto.preferido = datos.preferido
    accesos.anotar(db, usuario, "producto de odoo preferido", "producto_odoo",
                   producto.id, despues=str(datos.preferido).lower(),
                   detalle=producto.nombre[:200])
    db.commit()
    return next(p for p in odoo_tarifarios.tabla_de_productos(db)
                if p["id"] == producto.id)


@router.post("/productos/confirmar",
             summary="Confirmar lo que Centauro sugirio")
def confirmar_sugeridos(db: Session = Depends(get_db),
                        usuario: m.Usuario = Depends(PRODUCTOS)):
    """Confirma de un golpe cada sugerencia completa. Lo que no se supo
    que es se queda para decidirlo uno por uno."""
    ahora, cuenta = _utc(), 0
    for p in db.query(m.ProductoOdoo).filter_by(confirmado=False).all():
        if p.clase is None:
            continue
        try:
            _validar(db, ProductoIn(clase=p.clase, perfil_id=p.perfil_id,
                                    categoria_id=p.categoria_id,
                                    modalidad=p.modalidad))
        except HTTPException:
            continue
        p.confirmado, p.confirmado_por_id, p.confirmado_en = True, usuario.persona_id, ahora
        cuenta += 1
    accesos.anotar(db, usuario, "productos de odoo confirmados", "producto_odoo",
                   None, despues=f"{cuenta} confirmados")
    db.commit()
    return {"confirmados": cuenta}


# ================================================================ el tarifario

def _tarifario(t: m.Tarifario | None) -> dict | None:
    """Un tarifario en tres tablas --personal, unidades y paquetes-- con de
    donde salio cada precio."""
    if t is None:
        return None
    def fila(x, **llave):
        return {**llave, "modalidad": x.modalidad.codigo.value,
                "precio": x.precio, "origen": x.origen}
    return {
        "id": t.id, "nombre": t.nombre, "moneda": t.moneda.value,
        "de_odoo": t.odoo_id is not None, "general": t.general,
        "activo": t.activo, "resto_de": t.resto_de,
        "precio_hora_extra": t.precio_hora_extra,
        "paquetes_con_viaticos": t.paquetes_con_viaticos,
        "leido_en": (t.odoo_sincronizado_en.isoformat()
                     if t.odoo_sincronizado_en else None),
        "personal": [fila(x, perfil=x.perfil.nombre, perfil_id=x.perfil_id,
                          precio_hora_extra=x.precio_hora_extra)
                     for x in sorted(t.tarifas_recurso, key=lambda x: x.perfil_id)],
        "unidades": [fila(x, categoria=x.categoria.nombre, categoria_id=x.categoria_id)
                     for x in sorted(t.tarifas_vehiculo, key=lambda x: x.categoria.nombre)],
        # Solo los que la lista pacta, que son los que se cobran: la
        # lectura le pone a toda lista todos los paquetes, y con el
        # «Precio de venta» en gris pareceria que Control Risks tiene
        # paquetes (seccion 79).
        "paquetes": [fila(x, perfil=x.perfil.nombre, categoria=x.categoria.nombre,
                          perfil_id=x.perfil_id, categoria_id=x.categoria_id)
                     for x in sorted(t.tarifas_paquete,
                                     key=lambda x: (x.perfil_id, x.categoria.nombre))
                     if cot.es_pactado(x)],
    }


@router.get("/cliente/{cliente_id}", summary="El tarifario de un cliente")
def del_cliente(cliente_id: int, db: Session = Depends(get_db),
                usuario: m.Usuario = Depends(VER)):
    """Lo que se le cobra a un cliente: su lista de siempre y, si tiene, la
    de sus implantados. De solo lectura: se corrige en Odoo. Trae los
    roles y las unidades para pintar tambien lo que no tiene precio."""
    cliente = db.get(m.Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(404, "No existe ese cliente")
    return {"cliente": {"id": cliente.id, "nombre": cliente.nombre,
                        "de_odoo": cliente.odoo_id is not None},
            "tarifario": _tarifario(cliente.tarifario),
            "implantados": _tarifario(cliente.tarifario_implantado),
            "desde_odoo": odoo_tarifarios.en_marcha(db),
            # Si quien mira puede decir si los paquetes traen los viaticos.
            "puede_editar": auth.puede_el_usuario(db, usuario, "cierre.facturar"),
            **_catalogo(db)}


class ViaticosIn(BaseModel):
    incluidos: bool


@router.patch("/{tarifario_id}/viaticos",
              summary="Si los paquetes de la lista traen los viaticos del dia")
def paquetes_con_viaticos(tarifario_id: int, datos: ViaticosIn,
                          db: Session = Depends(get_db),
                          usuario: m.Usuario = Depends(PRODUCTOS)):
    """Los paquetes de HASBRO traen los viaticos del dia: el dia que se
    cobra el paquete, los de quien fue en el no se facturan aparte
    (seccion 79). Odoo no lo dice, asi que lo marca finanzas aqui, y
    ninguna lectura de Odoo lo toca."""
    tarifario = db.get(m.Tarifario, tarifario_id)
    if tarifario is None:
        raise HTTPException(404, "No existe ese tarifario")
    antes = tarifario.paquetes_con_viaticos
    tarifario.paquetes_con_viaticos = datos.incluidos
    accesos.anotar(db, usuario, "paquetes con viaticos", "tarifario",
                   tarifario.id, antes=str(antes).lower(),
                   despues=str(datos.incluidos).lower(),
                   detalle=tarifario.nombre[:200])
    db.commit()
    return {"id": tarifario.id, "paquetes_con_viaticos": tarifario.paquetes_con_viaticos}


@router.get("", summary="Los tarifarios y a cuantos clientes les tocan")
def listar(db: Session = Depends(get_db), _=Depends(VER)):
    salida = []
    for t in db.query(m.Tarifario).filter_by(activo=True).order_by(
            m.Tarifario.general.desc(), m.Tarifario.nombre):
        salida.append({"id": t.id, "nombre": t.nombre, "moneda": t.moneda.value,
                       "de_odoo": t.odoo_id is not None, "general": t.general,
                       "clientes": len([c for c in t.clientes if c.activo])})
    return salida
