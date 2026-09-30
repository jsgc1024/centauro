"""La ventana del director de operaciones (seccion 105): su bandeja de
autorizaciones y el tablero de hoy."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth
from app import direccion_operaciones as motor
from app import reloj
from app.db import get_db

router = APIRouter(prefix="/direccion", tags=["Direccion de operaciones"])

LECTURA = auth.puede("direccion.ver")


@router.get("/bandeja", summary="Las autorizaciones pendientes y el tablero")
def bandeja(db: Session = Depends(get_db), ahora: datetime | None = None,
            _=Depends(LECTURA)):
    """Cada seccion sale lista para pintar: las incidencias sin visto
    bueno, los plazos del cierre que vencieron, el hueco del cobro al
    cancelar, y las cuentas de hoy por pais. Las firmas se dan con las
    rutas de cada cosa --`POST /incidencias/{id}/visto-bueno`--; aqui
    solo se lee. `ahora` solo mueve el reloj en las pruebas."""
    return motor.bandeja(db, reloj.de_prueba(ahora))
