# -*- coding: utf-8 -*-
"""Pegasus: la cuota de eventos del sitio de Centauro Satelital.

Seccion 60. Va encima de parches/gps_conexion.py. La documentacion de
Pegasus pone una cuota a los eventos (/rawdata) de todo el sitio de
Centauro Satelital --60 por minuto, 800 por hora, compartidas con sus
operadores y sus clientes-- y bloquea la IP de quien sigue pidiendo
despues de un 429. Revisar el panico de las 97 unidades cada dos minutos
se llevaba 150 por hora. Ahora:

  * El panico de las unidades en servicio se revisa en cada vuelta; el
    de todas, cada quince minutos (o al instante con el disparador).
  * Si Pegasus contesta 429, no se le pide nada hasta la hora que diga,
    en ningun proceso.
  * Tope de consultas por vuelta para el testigo de las marcas (8) y
    para el cierre del dia (10): lo demas, en la vuelta siguiente.

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
    'bitacora': RAIZ / 'BITACORA.md',
}
NUEVOS = {}
ESPERADO = {'gps': '47debed07fdc8dd192c7537ff8713975', 'pegasus': 'cf453e3cdbba82434d9891e029482c28', 't_gps': 'ab0256bf9f961e3b8082b06345b25863', 'bitacora': 'ecbb0514737873c52a3ba9443967642b'}

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
        '# El aviso de Pegasus no despierta la revision de panicos dos veces en\n# este rato: la ruta es publica y no tiene que servir para martillar.\nSEGUNDOS_ENTRE_AVISOS = 20\nVIVAS = (m.EstatusJornada.PLANEADA, m.EstatusJornada.CONFIRMADA,\n         m.EstatusJornada.PROXIMA_A_INICIAR, m.EstatusJornada.ARRIBADO,\n         m.EstatusJornada.EN_CURSO)\n',
        '# El aviso de Pegasus no despierta la revision de panicos dos veces en\n# este rato: la ruta es publica y no tiene que servir para martillar.\nSEGUNDOS_ENTRE_AVISOS = 20\n# Los eventos de Pegasus (/rawdata) tienen una cuota de todo el sitio de\n# Centauro Satelital: 800 por hora, compartida con sus operadores. El\n# panico de las unidades en servicio se revisa en cada vuelta; el de\n# todas, cada tanto. Con el disparador de Pegasus llega al instante.\nMINUTOS_ENTRE_BARRIDOS = 15\n# Tope de consultas por vuelta, para no gastar la cuota de un jalon a la\n# hora en que todos marcan o terminan: lo demas, en la vuelta siguiente.\nTESTIGOS_POR_VUELTA = 8\nDIAS_POR_VUELTA = 10\nVIVAS = (m.EstatusJornada.PLANEADA, m.EstatusJornada.CONFIRMADA,\n         m.EstatusJornada.PROXIMA_A_INICIAR, m.EstatusJornada.ARRIBADO,\n         m.EstatusJornada.EN_CURSO)\n')

cambiar('gps',
        '                leidas += _leer_unidades(db, cliente, g, ahora)\n        db.flush()\n        resultado["unidades"] = leidas\n        resultado["panicos"] = _revisar_panicos(db, cliente, grupos, ahora)\n        resultado["alertas"] = _alertas_de_la_unidad(db, relojes, ventana,\n                                                     ahora)\n        resultado["camino"] = _camino(db, relojes, ventana, ahora)\n',
        '                leidas += _leer_unidades(db, cliente, g, ahora)\n        db.flush()\n        resultado["unidades"] = leidas\n        en_servicio = {a.vehiculo_id for j, _ in ventana for a in _vigentes(j)}\n        resultado["panicos"] = _revisar_panicos(db, cliente, grupos, ahora,\n                                                en_servicio)\n        resultado["alertas"] = _alertas_de_la_unidad(db, relojes, ventana,\n                                                     ahora)\n        resultado["camino"] = _camino(db, relojes, ventana, ahora)\n')

cambiar('gps',
        '\n\ndef _revisar_panicos(db: Session, cliente, grupos: list[m.GrupoGps],\n                     ahora: datetime) -> int:\n    """El evento "panic" de las unidades de los grupos, desde donde se\n    quedo la vuelta anterior. Cada panico suena una sola vez."""\n    nuevos = 0\n    for grupo in grupos:\n        if grupo.pegasus_id is None:\n            continue\n        ids = [u.pegasus_id for u in db.query(m.UnidadGps)\n               .filter_by(grupo_id=grupo.id, en_el_grupo=True).all()]\n        if not ids:\n            continue\n        desde = grupo.panico_hasta or (ahora - timedelta(minutes=10))\n',
        '\n\ndef _revisar_panicos(db: Session, cliente, grupos: list[m.GrupoGps],\n                     ahora: datetime, en_servicio: set | None = None) -> int:\n    """El evento "panic" de las unidades de los grupos, desde el ultimo\n    barrido. Cada panico suena una sola vez.\n\n    Las unidades en servicio se revisan en cada vuelta; todas, cada\n    MINUTOS_ENTRE_BARRIDOS --o siempre, si no se dice cuales estan en\n    servicio, como con el aviso de Pegasus--."""\n    nuevos = 0\n    for grupo in grupos:\n        if grupo.pegasus_id is None:\n            continue\n        barrido = (en_servicio is None or grupo.panico_hasta is None\n                   or (ahora - grupo.panico_hasta).total_seconds() / 60\n                   >= MINUTOS_ENTRE_BARRIDOS)\n        unidades = (db.query(m.UnidadGps)\n                    .filter_by(grupo_id=grupo.id, en_el_grupo=True).all())\n        ids = [u.pegasus_id for u in unidades\n               if barrido or u.vehiculo_id in en_servicio]\n        if not ids:\n            continue\n        desde = grupo.panico_hasta or (ahora - timedelta(minutes=10))\n')

cambiar('gps',
        '                continue\n            if _alertar_panico(db, grupo, e, cuando):\n                nuevos += 1\n        grupo.panico_hasta = ahora\n    return nuevos\n\n\n',
        '                continue\n            if _alertar_panico(db, grupo, e, cuando):\n                nuevos += 1\n        if barrido:\n            grupo.panico_hasta = ahora\n    return nuevos\n\n\n')

cambiar('gps',
        '                  .filter(m.Hito.unidad_revisada_en.is_(None),\n                          m.Hito.marcado_en >= desde)\n                  .order_by(m.Hito.marcado_en).all())\n    for hito in pendientes:\n        jornada = hito.jornada\n        pais = db.get(m.Pais, reloj.pais_de_la_jornada(jornada))\n',
        '                  .filter(m.Hito.unidad_revisada_en.is_(None),\n                          m.Hito.marcado_en >= desde)\n                  .order_by(m.Hito.marcado_en).all())\n    consultas = 0\n    for hito in pendientes:\n        jornada = hito.jornada\n        pais = db.get(m.Pais, reloj.pais_de_la_jornada(jornada))\n')

cambiar('gps',
        '        if not unidad:\n            hito.unidad_revisada_en = ahora\n            continue\n        if hito.tipo == m.TipoHito.FIN_SERVICIO:\n            tramos = reglas.tramos_ordenados(cliente.tramos(\n                [unidad.pegasus_id],\n',
        '        if not unidad:\n            hito.unidad_revisada_en = ahora\n            continue\n        consultas += 1\n        if consultas > TESTIGOS_POR_VUELTA:\n            break             # lo demas, en la vuelta siguiente\n        if hito.tipo == m.TipoHito.FIN_SERVICIO:\n            tramos = reglas.tramos_ordenados(cliente.tramos(\n                [unidad.pegasus_id],\n')

cambiar('gps',
        '                     m.Jornada.fin_real.isnot(None),\n                     m.Jornada.fecha >= desde_dia,\n                     m.AsignacionVehiculo.gps_cerrado_en.is_(None)).all())\n    cerrados = 0\n    try:\n        for a in filas:\n            if _cerrar_uno(db, cliente, a, ahora):\n                cerrados += 1\n        db.commit()\n    except conexion.NoResponde as e:\n        db.rollback()\n',
        '                     m.Jornada.fin_real.isnot(None),\n                     m.Jornada.fecha >= desde_dia,\n                     m.AsignacionVehiculo.gps_cerrado_en.is_(None)).all())\n    cerrados = hechos = 0\n    try:\n        for a in filas:\n            if hechos >= DIAS_POR_VUELTA:\n                break         # lo demas, en la vuelta de la siguiente hora\n            antes = a.gps_cerrado_en\n            if _cerrar_uno(db, cliente, a, ahora):\n                cerrados += 1\n            if antes is None and a.gps_cerrado_en is not None:\n                hechos += 1\n        db.commit()\n    except conexion.NoResponde as e:\n        db.rollback()\n')

cambiar('pegasus',
        '    rutas de LECTURAS; cualquier otra truena antes de salir a la red.\n  * No guarda la clave: vive en el `.env` del servidor y aqui solo se\n    usa para pedir la sesion.\n  * Pocas llamadas y espaciadas: los limites de Pegasus son de tres por\n    segundo y unos cientos por hora. Los eventos se piden de 25 unidades\n    en 25, que es lo que acepta.\n\nLas horas que manda Pegasus son UTC y las velocidades, millas por hora.\nAqui no se convierte nada: eso es de las reglas (`gps_reglas.py`).\n',
        '    rutas de LECTURAS; cualquier otra truena antes de salir a la red.\n  * No guarda la clave: vive en el `.env` del servidor y aqui solo se\n    usa para pedir la sesion.\n  * Pocas llamadas y espaciadas. Los eventos (/rawdata) tienen una cuota\n    por usuario --30 por minuto, 500 por hora-- y otra de TODO el sitio\n    de Centauro Satelital --60 por minuto, 800 por hora--, que comparte\n    con sus operadores y sus clientes. Se piden de 25 unidades en 25.\n  * Si Pegasus contesta 429 (demasiadas), no se le pide nada hasta la\n    hora que diga. Seguir pidiendo despues de un 429 hace que bloquee la\n    IP: lo dice su documentacion.\n\nLas horas que manda Pegasus son UTC y las velocidades, millas por hora.\nAqui no se convierte nada: eso es de las reglas (`gps_reglas.py`).\n')

cambiar('pegasus',
        '# minutos serian treinta entradas por hora con la misma clave.\n_sesiones: dict[tuple, str] = {}\n\n\nclass NoResponde(Exception):\n    """Pegasus no contesto, o contesto que no. El mensaje es corto y no\n    trae nada de la sesion ni de la clave."""\n\n\ndef lista_de(respuesta) -> list:\n',
        '# minutos serian treinta entradas por hora con la misma clave.\n_sesiones: dict[tuple, str] = {}\n\n# La pausa despues de un 429. Vive en Redis para que la respeten todos los\n# procesos --el worker de Celery tiene varios--; si Redis no contesta, al\n# menos la respeta este.\nLLAVE_PAUSA = "pegasus:pausa_hasta"\nESPERA_SIN_AVISO = 15 * 60      # segundos, si el 429 no dice hasta cuando\nESPERA_MAXIMA = 60 * 60\n_pausa_local = 0.0\n_redis_cliente = None\n\n\nclass NoResponde(Exception):\n    """Pegasus no contesto, o contesto que no. El mensaje es corto y no\n    trae nada de la sesion ni de la clave."""\n\n\ndef _redis():\n    global _redis_cliente\n    if _redis_cliente is None:\n        try:\n            import redis\n\n            from app.config import settings\n            _redis_cliente = redis.Redis.from_url(\n                settings.redis_url, socket_connect_timeout=0.5,\n                socket_timeout=0.5, decode_responses=True)\n            _redis_cliente.ping()\n        except Exception:                                  # noqa: BLE001\n            _redis_cliente = False\n    return _redis_cliente or None\n\n\ndef pausa_hasta() -> float:\n    """Hasta cuando (epoch) no se le pide nada a Pegasus; 0 si se puede."""\n    guardada = 0.0\n    r = _redis()\n    if r is not None:\n        try:\n            guardada = float(r.get(LLAVE_PAUSA) or 0)\n        except Exception:                                  # noqa: BLE001\n            guardada = 0.0\n    return max(guardada, _pausa_local)\n\n\ndef _pausar(respuesta) -> float:\n    """Pegasus dijo 429: hasta cuando no se le pide nada."""\n    global _pausa_local\n    ahora = time.time()\n    try:\n        hasta = float(respuesta.headers.get("X-RateLimit-Reset") or 0)\n    except ValueError:\n        hasta = 0.0\n    if hasta <= ahora:\n        hasta = ahora + ESPERA_SIN_AVISO\n    hasta = min(hasta, ahora + ESPERA_MAXIMA) + 5\n    _pausa_local = hasta\n    r = _redis()\n    if r is not None:\n        try:\n            r.set(LLAVE_PAUSA, hasta, ex=int(hasta - ahora) + 1)\n        except Exception:                                  # noqa: BLE001\n            pass\n    return hasta\n\n\ndef quitar_pausa() -> None:\n    """Para las pruebas: olvida la pausa."""\n    global _pausa_local\n    _pausa_local = 0.0\n    r = _redis()\n    if r is not None:\n        try:\n            r.delete(LLAVE_PAUSA)\n        except Exception:                                  # noqa: BLE001\n            pass\n\n\ndef _mensaje_de_pausa(hasta: float) -> str:\n    minutos = max(1, int((hasta - time.time()) // 60) + 1)\n    return (f"Pegasus pidio bajar el ritmo: no se le vuelve a pedir nada "\n            f"en {minutos} min.")\n\n\ndef lista_de(respuesta) -> list:\n')

cambiar('pegasus',
        '                             "contesta: revisa PEGASUS_SITIO.")\n        except httpx.HTTPError as e:\n            raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")\n        if r.status_code != 200:\n            raise NoResponde(f"Pegasus no dejo entrar ({r.status_code}): "\n                             "revisa el usuario y la clave de la conexion.")\n',
        '                             "contesta: revisa PEGASUS_SITIO.")\n        except httpx.HTTPError as e:\n            raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")\n        if r.status_code == 429:\n            raise NoResponde(_mensaje_de_pausa(_pausar(r)))\n        if r.status_code != 200:\n            raise NoResponde(f"Pegasus no dejo entrar ({r.status_code}): "\n                             "revisa el usuario y la clave de la conexion.")\n')

cambiar('pegasus',
        '        self.http.headers["Authenticate"] = token\n\n    def _esperar(self) -> None:\n        falta = PAUSA - (time.monotonic() - self._ultima)\n        if falta > 0:\n            time.sleep(falta)\n',
        '        self.http.headers["Authenticate"] = token\n\n    def _esperar(self) -> None:\n        hasta = pausa_hasta()\n        if hasta > time.time():\n            raise NoResponde(_mensaje_de_pausa(hasta))\n        falta = PAUSA - (time.monotonic() - self._ultima)\n        if falta > 0:\n            time.sleep(falta)\n')

cambiar('pegasus',
        '                r = self.http.get(f"{self.base}{ruta}", params=params)\n            except httpx.HTTPError as e:\n                raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")\n            if r.status_code == 401 and intento == 1:\n                # La sesion vencio: una vez mas con una nueva.\n                _sesiones.pop((self.sitio, self._usuario), None)\n',
        '                r = self.http.get(f"{self.base}{ruta}", params=params)\n            except httpx.HTTPError as e:\n                raise NoResponde(f"Pegasus no contesto ({type(e).__name__}).")\n            if r.status_code == 429:\n                raise NoResponde(_mensaje_de_pausa(_pausar(r)))\n            if r.status_code == 401 and intento == 1:\n                # La sesion vencio: una vez mas con una nueva.\n                _sesiones.pop((self.sitio, self._usuario), None)\n')

cambiar('t_gps',
        '        self.eventos_ = []\n        self.tramos_ = []\n        self.leidos = []\n\n    def grupos(self):\n        return self.grupos_\n',
        '        self.eventos_ = []\n        self.tramos_ = []\n        self.leidos = []\n        self.pedidos = []         # (etiquetas, unidades) de cada /rawdata\n\n    def grupos(self):\n        return self.grupos_\n')

cambiar('t_gps',
        '    def eventos(self, vehiculos, duracion, etiquetas=None, campos=None,\n                tope=None):\n        vs = {str(v) for v in vehiculos}\n        quiere = set(etiquetas.split(",")) if etiquetas else None\n        return [e for e in self.eventos_ if str(e["vid"]) in vs\n                and (quiere is None or e.get("label") in quiere)]\n',
        '    def eventos(self, vehiculos, duracion, etiquetas=None, campos=None,\n                tope=None):\n        vs = {str(v) for v in vehiculos}\n        self.pedidos.append((etiquetas, {int(v) for v in vehiculos}))\n        quiere = set(etiquetas.split(",")) if etiquetas else None\n        return [e for e in self.eventos_ if str(e["vid"]) in vs\n                and (quiere is None or e.get("label") in quiere)]\n')

cambiar('t_gps',
        '    assert all("PEGASUS_SITIO" in g.error for g in grupos)\n\n\ndef test_sin_usuario_de_pegasus_no_hace_nada(db):\n    assert gps.leer(db) == {"conectado": False}\n    assert gps.cerrar_dias(db) == {"conectado": False}\n',
        '    assert all("PEGASUS_SITIO" in g.error for g in grupos)\n\n\ndef test_si_pegasus_pide_esperar_no_se_le_pide_nada(db):\n    """Un 429 se respeta hasta la hora que diga Pegasus: seguir pidiendo\n    despues de un 429 hace que bloquee la IP."""\n    import time as reloj_real\n\n    import httpx\n    from app import pegasus as conexion\n\n    llamadas = []\n\n    def sitio(peticion):\n        llamadas.append(peticion.url.path)\n        if peticion.url.path.endswith("/login"):\n            return httpx.Response(200, json={"auth": "sesion"})\n        return httpx.Response(429, headers={\n            "X-RateLimit-Reset": str(int(reloj_real.time()) + 120)})\n\n    conexion.quitar_pausa()\n    try:\n        cliente = conexion.Pegasus("https://cuota.invalid", "u", "c")\n        cliente.http = httpx.Client(transport=httpx.MockTransport(sitio))\n        with pytest.raises(conexion.NoResponde, match="bajar el ritmo"):\n            cliente.grupos()\n        antes = len(llamadas)\n        otro = conexion.Pegasus("https://cuota.invalid", "u", "c")\n        otro.http = httpx.Client(transport=httpx.MockTransport(sitio))\n        with pytest.raises(conexion.NoResponde, match="bajar el ritmo"):\n            otro.grupos()\n        assert len(llamadas) == antes          # ni siquiera salio\n        r = gps.leer(db, otro, datetime.now(timezone.utc))\n        assert "bajar el ritmo" in r["error"]\n        assert len(llamadas) == antes\n    finally:\n        conexion.quitar_pausa()\n        conexion._sesiones.clear()\n\n\ndef test_sin_usuario_de_pegasus_no_hace_nada(db):\n    assert gps.leer(db) == {"conectado": False}\n    assert gps.cerrar_dias(db) == {"conectado": False}\n')

cambiar('t_gps',
        '                                                        "Luis Mendoza"}\n    assert ficha["unidad"]["estado"] in ("detenida", "en_movimiento")\n    assert ficha["principal"]["estado"] == "a_bordo"\n\n\ndef test_el_panico_sin_servicio_tambien_suena(db, pegasus, datos):\n',
        '                                                        "Luis Mendoza"}\n    assert ficha["unidad"]["estado"] in ("detenida", "en_movimiento")\n    assert ficha["principal"]["estado"] == "a_bordo"\n\n\ndef test_el_panico_se_revisa_seguido_en_servicio_y_de_todas_cada_tanto(\n        cliente, sesion, datos, db, pegasus):\n    """La cuota de eventos de Pegasus es de todo el sitio de Centauro\n    Satelital. En cada vuelta se revisa el panico de las unidades en\n    servicio; el de todas, cada quince minutos."""\n    servicio, j = _en_curso(cliente, sesion, datos)\n    ahora = datetime.now(timezone.utc)\n    pegasus.unidades_[GRUPO_MX] = [unidad(101, _placa_suburban(datos), ahora),\n                                   unidad(102, "ZZZ999", ahora)]\n\n    def panicos_pedidos():\n        return [u for e, u in pegasus.pedidos if e == reglas.PANICO]\n\n    gps.leer(db, pegasus, ahora)                      # primer barrido\n    assert panicos_pedidos()[-1] == {101, 102}\n    gps.leer(db, pegasus, ahora + timedelta(minutes=2))\n    assert panicos_pedidos()[-1] == {101}             # solo la de servicio\n    gps.leer(db, pegasus, ahora + timedelta(minutes=16))\n    assert panicos_pedidos()[-1] == {101, 102}        # otro barrido\n\n    # Un panico de la que no esta en servicio suena en el barrido.\n    _panico(pegasus, 102, ahora + timedelta(minutes=17))\n    gps.leer(db, pegasus, ahora + timedelta(minutes=18))\n    assert db.query(m.AlertaIncidencia).count() == 0\n    gps.leer(db, pegasus, ahora + timedelta(minutes=32))\n    assert db.query(m.AlertaIncidencia).count() == 1\n\n\ndef test_el_panico_sin_servicio_tambien_suena(db, pegasus, datos):\n')

cambiar('bitacora',
        '  en el mismo «Atender ahora» que el de la app, con canal «Botón del\n  vehículo»: de qué unidad, quién va a bordo con su teléfono, si el\n  principal va con ellos y qué dice la unidad en ese momento. Suena una\n  sola vez por evento. Pegasus puede avisar al instante con un\n  disparador (`POST /gps/pegasus/aviso/{secreto}`); el aviso no trae\n  nada que se crea —solo adelanta la lectura— y sin secreto en el\n  `.env` la ruta no existe.\n- **El inhibidor y la corriente cortada** (más de dos minutos) suenan\n  solo durante el servicio, del camino al punto a la marca de fin, con\n  quién va a bordo. Se cierran solos cuando la unidad vuelve a estar\n',
        '  en el mismo «Atender ahora» que el de la app, con canal «Botón del\n  vehículo»: de qué unidad, quién va a bordo con su teléfono, si el\n  principal va con ellos y qué dice la unidad en ese momento. Suena una\n  sola vez por evento. El de las unidades en servicio se revisa cada\n  dos minutos y el de todas, cada quince: los eventos de Pegasus tienen\n  una cuota de todo el sitio de Centauro Satelital —800 consultas por\n  hora, compartidas con sus operadores y sus clientes— y revisar las\n  97 unidades cada dos minutos se llevaba 150. Pegasus puede avisar al\n  instante con un disparador (`POST /gps/pegasus/aviso/{secreto}`); el\n  aviso no trae nada que se crea —solo adelanta la lectura— y sin\n  secreto en el `.env` la ruta no existe.\n- **Si Pegasus pide bajar el ritmo** (contesta 429), no se le pide nada\n  hasta la hora que diga: seguir pidiendo hace que bloquee la IP. Un\n  sitio mal escrito o una clave que no entra se dicen en la pantalla de\n  Unidades, en vez de tronar la lectura.\n- **El inhibidor y la corriente cortada** (más de dos minutos) suenan\n  solo durante el servicio, del camino al punto a la marca de fin, con\n  quién va a bordo. Se cierran solos cuando la unidad vuelve a estar\n')


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
