"""Fabrica de routers CRUD: evita repetir el mismo codigo por cada catalogo.

Aqui viven diecinueve catalogos --el tarifario que se le cobra al cliente,
lo que se le paga a cada rol, la plantilla, la flota-- y hasta hoy lo que
pasaba con ellos no quedaba escrito en ningun lado. Se podia subir un
precio un viernes y en diciembre no habia forma de saber quien lo subio
ni cuanto valia antes. La bitacora de administracion existia desde el
panel de accesos; faltaba conectarla aqui.

Y faltaba lo de vuelta: `DELETE` desactiva --nunca se borra historia--
pero nada volvia a encender. Como `PersonaIn` y las demas no traen
`activo`, un `PATCH` tampoco podia. Una ciudad, una unidad o una persona
que se desactivaba por error se quedaba apagada para siempre, y el unico
camino de vuelta era un UPDATE a mano en Postgres.
"""
from typing import Type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import accesos, auth
from app import models as m
from app.db import get_db

# Lo que manda Odoo en cada catalogo (secciones 51 y 52): en Centauro no
# se edita, porque la siguiente lectura lo volveria a poner como estaba.
DE_ODOO = {
    m.Persona: ("nombre", "correo", "plaza_id", "odoo_id"),
    m.Vehiculo: ("placa", "categoria_id", "plaza_id", "marca_modelo",
                 "color", "modelo_anio"),
    # Los clientes (seccion 75). Su tarifario tambien, desde que la lectura
    # de tarifarios esta en marcha (seccion 77): se agrega abajo.
    m.Cliente: ("nombre", "pais_id", "odoo_id", "rfc"),
    # Las listas de precios (seccion 77): se capturan en Odoo.
    m.Tarifario: ("nombre", "pais_id", "moneda", "vigencia_desde",
                  "vigencia_hasta"),
}

# Los precios de una lista de Odoo tampoco se tocan aqui: la siguiente
# lectura los volveria a poner como estan alla.
TARIFAS = (m.TarifaRecurso, m.TarifaVehiculo)
LISTA_DE_ODOO = {
    "mensaje": "Este tarifario viene de Odoo: se corrige en Odoo.",
    "que_hacer": "Facturacion lo cambia en Odoo, en Ventas -> Listas de "
                 "precios, y Centauro lo lee en la siguiente hora.",
}


def _de_una_lista_de_odoo(db: Session, tarifario_id) -> bool:
    tarifario = db.get(m.Tarifario, tarifario_id) if tarifario_id else None
    return bool(tarifario and tarifario.odoo_id)


def _como_se_llama(obj) -> str | None:
    """Con que nombre se reconoce este registro en la bitacora.

    Un renglon que dice "registro 47" no sirve dentro de un ano: para
    saber que era hay que ir a buscarlo, y si se borro ya no esta.
    """
    for campo in ("nombre", "placa", "codigo", "correo"):
        valor = getattr(obj, campo, None)
        if valor:
            return str(valor)[:200]
    return None


def _recorte(partes: list[str]) -> str | None:
    """Lo que cupo. La columna son 200 caracteres y un cambio de veinte
    campos no cabe; vale mas media verdad que reventar el guardado."""
    texto = "; ".join(partes)
    return (texto[:197] + "...") if len(texto) > 200 else (texto or None)


def crud_router(
    *,
    modelo: Type,
    esquema_in: Type[BaseModel],
    esquema_out: Type[BaseModel],
    prefijo: str,
    etiqueta: str,
    actividad: str | None = None,
) -> APIRouter:
    """Un catalogo se administra desde el rol de administracion, salvo que
    se le nombre una actividad: entonces lo puede tocar quien la tenga.

    Lo primero vale para el tarifario, que nadie mas debe mover. Lo
    segundo para catalogos que crecen durante la operacion, como las
    ciudades: el consultor da de alta el servicio y la ciudad al mismo
    tiempo, sin esperar a que alguien se la de de alta.
    """
    router = APIRouter(prefix=prefijo, tags=[etiqueta])
    escribir = (auth.puede(actividad) if actividad
                else auth.requiere(m.Rol.ADMIN))

    # Con que nombre entra este catalogo a la bitacora: "personal",
    # "tarifarios", "vehiculos". Sale del prefijo y no de la etiqueta
    # porque la etiqueta esta escrita para el humano --"Tarifas de
    # recurso por modalidad"-- y la columna son cuarenta caracteres.
    clave = prefijo.strip("/")[:40]

    # Leer un catalogo es cosa de la consola. Aqui viven la plantilla
    # completa con telefonos, el tarifario que se le cobra al cliente y
    # lo que se le paga a cada rol: con la sesion de un elemento de
    # campo se sacaba todo de corrido. La app de campo no toca
    # /catalogos —lo suyo va por /campo—, asi que esto no le quita nada.
    #
    # Recursos Humanos tambien: abre Desempeno y Personal, y las dos
    # pantallas leen de aqui los paises, los perfiles y la plantilla. Se
    # habia quedado fuera --las cuatro rutas de catalogos.py si la
    # tenian-- y Desempeno le abria con "Tu rol no tiene permiso"; lo
    # encontro la prueba de humo de los puestos (seccion 73).
    leer = auth.requiere(m.Rol.ADMIN, m.Rol.CONSULTOR, m.Rol.CENTRAL,
                         m.Rol.FINANZAS, m.Rol.DIRECTOR_OPERACIONES,
                         m.Rol.DIRECTOR_GENERAL, m.Rol.RECURSOS_HUMANOS)

    @router.get("", response_model=list[esquema_out], summary=f"Listar {etiqueta}")
    def listar(db: Session = Depends(get_db), limite: int = 5000,
               incluir_inactivos: bool = False,
               _=Depends(leer)):
        """Lo dado de baja no se ofrece: si una ciudad, una persona o una
        unidad se desactivo, no tiene por que seguir apareciendo en las
        listas donde se elige. La pantalla de administracion la pide con
        incluir_inactivos para poder reactivarla.

        El limite es alto a proposito. Estaba en 200 y las pantallas lo
        piden sin parametro, asi que con mas de 200 personas de campo la
        201 desaparecia: no salia en el selector para asignarla, ni en
        la lista para registrarle un ajuste, y nada avisaba. Un catalogo
        que se corta en silencio es peor que uno que tarda.

        Y sale ordenado: sin ORDER BY, Postgres no promete un orden, asi
        que dos cargas de la misma pantalla podian traer las filas
        distintas.
        """
        consulta = db.query(modelo)
        if hasattr(modelo, "activo") and not incluir_inactivos:
            consulta = consulta.filter(modelo.activo.is_(True))
        orden = getattr(modelo, "nombre", None)
        consulta = consulta.order_by(orden if orden is not None else modelo.id)
        return consulta.limit(limite).all()

    @router.get("/{item_id}", response_model=esquema_out, summary=f"Ver {etiqueta}")
    def ver(item_id: int, db: Session = Depends(get_db),
            _=Depends(leer)):
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")
        return obj

    @router.post("", response_model=esquema_out, status_code=201, summary=f"Crear {etiqueta}")
    def crear(datos: esquema_in, db: Session = Depends(get_db),
              actor: m.Usuario = Depends(escribir)):
        if modelo in TARIFAS and _de_una_lista_de_odoo(db, datos.tarifario_id):
            raise HTTPException(409, LISTA_DE_ODOO)
        obj = modelo(**datos.model_dump())
        db.add(obj)
        db.flush()
        accesos.anotar(db, actor, "catalogo creado", clave, obj.id,
                       despues=_como_se_llama(obj))
        db.commit()
        db.refresh(obj)
        return obj

    @router.patch("/{item_id}", response_model=esquema_out, summary=f"Editar {etiqueta}")
    def editar(item_id: int, datos: esquema_in, db: Session = Depends(get_db),
               actor: m.Usuario = Depends(escribir)):
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")

        # Lo que llega de Odoo se corrige en Odoo (secciones 51 y 52).
        # El cliente ligado a mano en el ensayo (seccion 75) todavia no
        # trae nada de Odoo: hasta la primera lectura, el ligado se puede
        # deshacer --un error al escoger en la lista no se queda pegado.
        de_odoo = DE_ODOO.get(modelo)
        if modelo is m.Cliente and obj.odoo_sincronizado_en is None:
            de_odoo = None
        if modelo is m.Cliente and de_odoo:
            from app import odoo_tarifarios
            if odoo_tarifarios.en_marcha(db):
                de_odoo = de_odoo + ("tarifario_id",)
        if modelo in TARIFAS and (
                _de_una_lista_de_odoo(db, obj.tarifario_id)
                or _de_una_lista_de_odoo(db, datos.tarifario_id)):
            raise HTTPException(409, LISTA_DE_ODOO)
        if de_odoo and obj.odoo_id:
            nuevos = datos.model_dump(exclude_unset=True)
            tocados = [c for c in de_odoo
                       if c in nuevos and nuevos[c] != getattr(obj, c)]
            if tocados:
                raise HTTPException(409, {
                    "mensaje": "Viene de Odoo: se corrige en Odoo.",
                    "que_hacer": "Se cambia en Odoo --Recursos Humanos en la "
                                 "ficha del empleado, Flotilla en la de la "
                                 "unidad, Facturacion en la del cliente-- y "
                                 "Centauro lo toma en la siguiente lectura.",
                    "campos": tocados,
                })

        # Se apunta solo lo que de verdad cambio, con su valor viejo al
        # lado. El estado entero no sirve: lo que alguien busca en
        # diciembre es que se le movio a ese precio y cuando, no como
        # estaba todo lo demas ese dia.
        antes, despues = [], []
        for campo, valor in datos.model_dump(exclude_unset=True).items():
            previo = getattr(obj, campo, None)
            if previo != valor:
                antes.append(f"{campo}: {previo}")
                despues.append(f"{campo}: {valor}")
            setattr(obj, campo, valor)

        if antes:
            accesos.anotar(db, actor, "catalogo cambiado", clave, obj.id,
                           antes=_recorte(antes), despues=_recorte(despues),
                           detalle=_como_se_llama(obj))
        db.commit()
        db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=204, summary=f"Desactivar {etiqueta}")
    def desactivar(item_id: int, db: Session = Depends(get_db),
                   actor: m.Usuario = Depends(escribir)):
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")
        # Una lista de Odoo, o un precio suyo, se archiva o se quita alla.
        if ((modelo is m.Tarifario and obj.odoo_id)
                or (modelo in TARIFAS
                    and _de_una_lista_de_odoo(db, obj.tarifario_id))):
            raise HTTPException(409, LISTA_DE_ODOO)

        # La regla que ya cuidaba el panel de accesos, que aqui faltaba:
        # quien trae dinero de la empresa no se va hasta comprobarlo.
        # Eran dos puertas a la misma baja y solo una tenia candado.
        if modelo is m.Persona:
            debiendo = accesos.viaticos_sin_cerrar(db, obj.id)
            if debiendo:
                falta = sum(f["monto"] - f["comprobado"] for f in debiendo)
                raise HTTPException(409, {
                    "mensaje": (f"No se puede dar de baja a {obj.nombre}: "
                                f"tiene {len(debiendo)} viatico(s) sin "
                                f"cerrar, por {falta:,.2f}."),
                    "que_hacer": "Tiene que terminar su ciclo: comprobar lo "
                                 "que recibio. Si ya no va a volver, "
                                 "finanzas puede cerrarlo con el ajuste que "
                                 "corresponda.",
                    "viaticos": debiendo,
                })

        if hasattr(obj, "activo"):
            obj.activo = False          # nunca borramos historia, solo desactivamos
            accesos.anotar(db, actor, "catalogo desactivado", clave, obj.id,
                           antes="activo", despues="desactivado",
                           detalle=_como_se_llama(obj))
        else:
            # Sin columna `activo` no hay a que volver: el renglon se va de
            # verdad, asi que el nombre se guarda antes de perderlo.
            accesos.anotar(db, actor, "catalogo borrado", clave, obj.id,
                           antes=_como_se_llama(obj))
            db.delete(obj)
        db.commit()

    @router.post("/{item_id}/reactivar", response_model=esquema_out,
                 summary=f"Reactivar {etiqueta}")
    def reactivar(item_id: int, db: Session = Depends(get_db),
                  actor: m.Usuario = Depends(escribir)):
        """Vuelve a encender lo que se apago.

        Existia la baja y no existia el alta: como los esquemas de
        entrada no traen `activo`, ni el PATCH servia. Una unidad
        desactivada por error se quedaba fuera de todas las listas para
        siempre.

        No reabre el acceso al sistema de nadie. Si esta persona ademas
        tenia usuario, ese se reabre desde el panel de accesos, que es
        donde se ve a quien se le esta abriendo la puerta.
        """
        obj = db.get(modelo, item_id)
        if not obj:
            raise HTTPException(404, f"No existe el registro {item_id}")
        if not hasattr(obj, "activo"):
            raise HTTPException(409, "Este catalogo no se desactiva, se borra")
        if obj.activo:
            raise HTTPException(409, "Ese registro ya estaba activo")

        obj.activo = True
        accesos.anotar(db, actor, "catalogo reactivado", clave, obj.id,
                       antes="desactivado", despues="activo",
                       detalle=_como_se_llama(obj))
        db.commit()
        db.refresh(obj)
        return obj

    @router.get("/{item_id}/historial",
                summary=f"Que se le ha hecho a este registro de {etiqueta}")
    def historial(item_id: int, db: Session = Depends(get_db),
                  limite: int = 50, _=Depends(leer)):
        """Una bitacora que nadie puede leer es media bitacora.

        Va con `leer` y no con `escribir`: saber quien movio un precio no
        es lo mismo que poder moverlo, y la pregunta la hace quien ve el
        numero raro, no quien lo escribio.
        """
        filas = (db.query(m.RegistroAdmin)
                 .filter_by(objeto=clave, objeto_id=item_id)
                 .order_by(m.RegistroAdmin.creado_en.desc())
                 .limit(limite).all())
        return [{
            "accion": r.accion, "antes": r.antes, "despues": r.despues,
            "detalle": r.detalle,
            "quien": r.persona.nombre if r.persona else None,
            "rol_de_quien": r.rol.value,
            "cuando": r.creado_en.isoformat() if r.creado_en else None,
        } for r in filas]

    return router
