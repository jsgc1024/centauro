# -*- coding: utf-8 -*-
"""Pegasus: un sitio mal escrito se dice en pantalla y no truena la lectura.

Seccion 60. En el ensayo del 24 de septiembre el sitio quedo mal escrito
y la entrada a Pegasus tronaba con un error de red en vez de decir que
no hay conexion. Ahora:

  * Si el sitio no existe o no contesta, la conexion lo dice con todas
    sus letras ("revisa PEGASUS_SITIO") y la lectura de cada dos minutos
    lo deja escrito en la pantalla de Unidades, en vez de tronar.
  * Si falla la primera vuelta, los renglones de los grupos se quedan
    con el error: antes la pantalla decia "todavia no se ha leido".

Sin migracion. Idempotente. Todo se arma en memoria, se comprueba contra
lo que se probo (md5 por archivo) y solo entonces se escribe.
"""
import hashlib
import io
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
B = RAIZ / "backend"

ARCHIVOS = {
    'gps': RAIZ / 'backend/app/gps.py',
    'pegasus': RAIZ / 'backend/app/pegasus.py',
    't_gps': RAIZ / 'backend/tests/test_gps.py',
}
NUEVOS = {}
ESPERADO = {'gps': 'a62c3f8881bd3e6da54527f7b70d69cf', 'pegasus': '1915114381f97839fce5c5900f9e5eff', 't_gps': '499e90bae43ce579a137ff6b5ca2aae3'}

textos = {k: io.open(v, encoding="utf-8", newline="").read()
          for k, v in ARCHIVOS.items()}
saltados = []


def cambiar(clave, viejo, nuevo, marca=None):
    t = textos[clave]
    if (marca or nuevo) in t:
        saltados.append(clave)
        return
    assert t.count(viejo) == 1, (
        f"{clave}: '{viejo[:70]}...' esta {t.count(viejo)} veces. "
        "No se escribio nada.")
    textos[clave] = t.replace(viejo, nuevo)


cambiar('gps',
        '\n# ================================================================ la lectura\n\ndef _grupos(db: Session, cliente, ahora: datetime) -> list[m.GrupoGps]:\n    """Los grupos del `.env`, uno por pais, con su numero de Pegasus."""\n    config = grupos_configurados()\n    paises = {p.codigo: p for p in db.query(m.Pais).all()}\n    filas, sin_numero = [], []\n    for codigo, nombre in config.items():\n        pais = paises.get(codigo)\n        if not pais:\n',
        '\n# ================================================================ la lectura\n\ndef _filas_de_grupo(db: Session) -> list[m.GrupoGps]:\n    """Un renglon por pais del `.env`, sin preguntarle nada a Pegasus."""\n    config = grupos_configurados()\n    paises = {p.codigo: p for p in db.query(m.Pais).all()}\n    filas = []\n    for codigo, nombre in config.items():\n        pais = paises.get(codigo)\n        if not pais:\n')

cambiar('gps',
        '        elif fila.nombre != nombre:\n            fila.nombre, fila.pegasus_id = nombre, None\n        filas.append(fila)\n        if fila.pegasus_id is None:\n            sin_numero.append(fila)\n    if sin_numero:\n        # De los demas grupos no se guarda ni el nombre.\n        todos = cliente.grupos()\n',
        '        elif fila.nombre != nombre:\n            fila.nombre, fila.pegasus_id = nombre, None\n        filas.append(fila)\n    return filas\n\n\ndef _grupos(db: Session, cliente, ahora: datetime) -> list[m.GrupoGps]:\n    """Los grupos del `.env`, uno por pais, con su numero de Pegasus."""\n    filas = _filas_de_grupo(db)\n    sin_numero = [f for f in filas if f.pegasus_id is None]\n    if sin_numero:\n        # De los demas grupos no se guarda ni el nombre.\n        todos = cliente.grupos()\n')

cambiar('gps',
        '        db.commit()\n    except conexion.NoResponde as e:\n        db.rollback()\n        for g in db.query(m.GrupoGps).all():\n            g.error, g.error_en = str(e)[:300], ahora\n        db.commit()\n',
        '        db.commit()\n    except conexion.NoResponde as e:\n        db.rollback()\n        # Si fallo la primera vuelta, los renglones de los grupos se fueron\n        # con el rollback: se vuelven a poner para que la pantalla diga\n        # por que no hay lectura, en vez de "todavia no se ha leido".\n        _filas_de_grupo(db)\n        for g in db.query(m.GrupoGps).all():\n            g.error, g.error_en = str(e)[:300], ahora\n        db.commit()\n')

cambiar('pegasus',
        '    def _entrar(self) -> None:\n        """La unica escritura permitida: pedir la sesion."""\n        credenciales = {"username": self._usuario, "password": self._clave}\n        self._esperar()\n        r = self.http.post(f"{self.base}/login", json=credenciales)\n        if r.status_code in (400, 415, 422):\n            # Hay sitios que la piden como formulario.\n            self._esperar()\n            r = self.http.post(f"{self.base}/login", data=credenciales)\n        if r.status_code != 200:\n            raise NoResponde(f"Pegasus no dejo entrar ({r.status_code}): "\n                             "revisa el usuario y la clave de la conexion.")\n',
        '    def _entrar(self) -> None:\n        """La unica escritura permitida: pedir la sesion."""\n        credenciales = {"username": self._usuario, "password": self._clave}\n        try:\n            self._esperar()\n            r = self.http.post(f"{self.base}/login", json=credenciales)\n            if r.status_code in (400, 415, 422):\n                # Hay sitios que la piden como formulario.\n                self._esperar()\n                r = self.http.post(f"{self.base}/login", data=credenciales)\n        except httpx.ConnectError:\n            # Un sitio mal escrito o que no existe cae aqui, antes de que\n            # haya sesion. Sin esto la lectura tronaba cada dos minutos en\n            # vez de decir en pantalla que no hay conexion.\n            raise NoResponde("No se encontro el sitio de Pegasus o no "\n                             "contesta: revisa PEGASUS_SITIO.")\n        except httpx.HTTPError as e:\n            raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")\n        if r.status_code != 200:\n            raise NoResponde(f"Pegasus no dejo entrar ({r.status_code}): "\n                             "revisa el usuario y la clave de la conexion.")\n')

cambiar('t_gps',
        '\n\n# ================================================================ la lectura\n\ndef test_sin_usuario_de_pegasus_no_hace_nada(db):\n    assert gps.leer(db) == {"conectado": False}\n',
        '\n\n# ================================================================ la lectura\n\ndef test_un_sitio_que_no_existe_se_dice_y_no_truena(db):\n    """El sitio mal escrito no llega a Pegasus: se dice en la pantalla,\n    en vez de tronar la lectura cada dos minutos."""\n    import httpx\n    from app import pegasus as conexion\n\n    def sin_sitio(peticion):\n        raise httpx.ConnectError("Name or service not known", request=peticion)\n\n    cliente = conexion.Pegasus("https://no-existe.invalid", "u", "c")\n    cliente.http = httpx.Client(transport=httpx.MockTransport(sin_sitio))\n    with pytest.raises(conexion.NoResponde, match="PEGASUS_SITIO"):\n        cliente.grupos()\n\n    # Aunque sea la primera vuelta, la pantalla dice por que no hay lectura.\n    r = gps.leer(db, cliente, datetime.now(timezone.utc))\n    assert "PEGASUS_SITIO" in r["error"]\n    grupos = db.query(m.GrupoGps).all()\n    assert {g.nombre for g in grupos} == {"2025 P.E.", "CENTAURO BRASIL"}\n    assert all("PEGASUS_SITIO" in g.error for g in grupos)\n\n\ndef test_sin_usuario_de_pegasus_no_hace_nada(db):\n    assert gps.leer(db) == {"conectado": False}\n')


# ============================================================ comprobar
def _md5(texto):
    return hashlib.md5(texto.encode("utf-8")).hexdigest()


distintos = [clave for clave in ARCHIVOS
             if _md5(textos[clave]) != ESPERADO[clave]]
distintos += [rel for rel, contenido in NUEVOS.items()
              if _md5(contenido) != ESPERADO["nuevo:" + rel]]
if distintos:
    raise SystemExit("Estos archivos no quedarian como los que se probaron: "
                     + ", ".join(distintos) + ". No se escribio nada.")

# ============================================================ escrituras
for clave, ruta in ARCHIVOS.items():
    actual = io.open(ruta, encoding="utf-8", newline="").read()
    if actual != textos[clave]:
        with io.open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(textos[clave])
        print("escrito  ", ruta.relative_to(RAIZ))
    else:
        print("sin cambio", ruta.relative_to(RAIZ))
for relativa, contenido in NUEVOS.items():
    ruta = B / relativa
    if ruta.exists() and io.open(ruta, encoding="utf-8", newline="").read() == contenido:
        print("sin cambio", ruta.relative_to(RAIZ))
    else:
        with io.open(ruta, "w", encoding="utf-8", newline="") as f:
            f.write(contenido)
        print("escrito  ", ruta.relative_to(RAIZ))
if saltados:
    print("ya estaban:", len(saltados), "cambios")
