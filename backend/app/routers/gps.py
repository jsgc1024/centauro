"""El GPS de las unidades (seccion 60)."""
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app import gps as motor
from app import models as m
from app.db import get_db

router = APIRouter(prefix="/gps", tags=["GPS de las unidades"])

# La cabecera con la que Pegasus puede mandar el secreto en vez de
# ponerlo en la ruta (seccion 101): una cabecera no queda en los
# registros de acceso; la ruta si.
CABECERA_DEL_SECRETO = "X-Pegasus-Secreto"


@router.get("/unidades", summary="La flota con su GPS, por pais")
def unidades(pais_id: int, db: Session = Depends(get_db),
             _=Depends(auth.puede("unidades.ver"))):
    """Cada unidad de Odoo con su GPS de Pegasus, ligadas por la placa, y
    lo que hay que arreglar antes de que haga falta. No dice donde esta
    ninguna: eso se usa durante el servicio, en Monitoreo."""
    if not db.get(m.Pais, pais_id):
        raise HTTPException(404, f"No existe el pais {pais_id}")
    return motor.unidades(db, pais_id)


def _con_el_secreto(secreto: str | None) -> None:
    """Sin secreto en el `.env`, la ruta no existe; con el secreto
    equivocado, tampoco: a quien tantea no se le dice que hay algo."""
    from app.config import settings

    esperado = settings.pegasus_secreto_aviso or ""
    if not esperado or not secreto or not hmac.compare_digest(
            secreto.encode(), esperado.encode()):
        raise HTTPException(404, "Not Found")


def _despertar(db: Session) -> dict:
    resultado = motor.revisar_panicos(db)
    return {"recibido": True, "panicos": resultado.get("panicos", 0)}


@router.post("/pegasus/aviso/{secreto}", status_code=202,
             summary="Pegasus avisa que hay un evento de panico")
def aviso_de_pegasus(secreto: str, db: Session = Depends(get_db)):
    """El disparador que Centauro Satelital configura en Pegasus.

    El aviso no trae nada que se crea: solo despierta la revision de
    panicos, que lee de Pegasus lo que paso. Asi da igual como venga
    escrito, y quien conociera la ruta solo podria hacer que Centauro
    mirara antes. Sin secreto en el `.env`, la ruta no existe.

    El secreto en la ruta queda en los registros de acceso: el de Caddy
    salta esta ruta y el de uvicorn la tapa (seccion 101). Si Pegasus
    puede mandarlo como cabecera, mejor la puerta de abajo."""
    _con_el_secreto(secreto)
    return _despertar(db)


@router.post("/pegasus/aviso", status_code=202,
             summary="El mismo aviso, con el secreto en una cabecera")
def aviso_de_pegasus_por_cabecera(
        db: Session = Depends(get_db),
        secreto: str | None = Header(None, alias=CABECERA_DEL_SECRETO)):
    """La misma puerta con el secreto en `X-Pegasus-Secreto` (seccion
    101): una cabecera no queda escrita en ningun registro de acceso. La
    de la ruta sigue existiendo para no romper lo que Pegasus ya manda."""
    _con_el_secreto(secreto)
    return _despertar(db)
