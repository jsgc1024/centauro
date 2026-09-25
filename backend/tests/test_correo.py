"""El correo que sale de la empresa.

Hasta hoy los avisos se escribian en `Notificacion` y ahi se quedaban.
El modelo lo decia desde el primer dia --"en el demo se registra; el
envio real se conecta despues"-- y seguia siendo cierto.

Lo que estas pruebas cuidan no es que el correo llegue --eso depende de
un proveedor que aqui no existe-- sino las tres cosas que si son
nuestras:

  - que apagado no mienta: sin proveedor, la cola espera y nadie cree
    que ya salio;
  - que lo que sale se marque, para que no salga dos veces;
  - que lo que falla se reintente, pero no para siempre.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import correo


@pytest.fixture
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _aviso(db, correo_destino="ejecutivo@cliente.com", asunto="Prueba"):
    from app import models as m
    fila = m.Notificacion(
        destinatario=m.Destinatario.EJECUTIVO, canal=m.Canal.CORREO,
        correo=correo_destino, asunto=asunto, cuerpo="El cuerpo del aviso")
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def _configurado(monkeypatch, si=True):
    monkeypatch.setattr(correo.settings, "correo_host",
                        "smtp.proveedor.com" if si else "")
    monkeypatch.setattr(correo.settings, "correo_de",
                        "Centauro <avisos@centauro.lat>" if si else "")


def test_sin_proveedor_no_sale_nada_y_se_dice(db, monkeypatch):
    """Apagado a medias es peor que apagado: si el sistema se creyera
    configurado, nadie iria a buscar el correo que nunca llego."""
    _configurado(monkeypatch, si=False)
    aviso = _aviso(db)

    r = correo.despachar(db)
    assert r["configurado"] is False
    assert r["enviados"] == 0
    db.refresh(aviso)
    assert aviso.estado == "pendiente", "se marco sin haber salido"


def test_lo_que_sale_se_marca_y_no_sale_dos_veces(db, monkeypatch):
    _configurado(monkeypatch)
    aviso = _aviso(db)
    salieron = []
    monkeypatch.setattr(correo, "entregar",
                        lambda destino, asunto, cuerpo, html=None:
                        salieron.append((destino, asunto, cuerpo, html)))

    r = correo.despachar(db)
    assert r["enviados"] == 1, r
    assert salieron[0][0] == "ejecutivo@cliente.com"

    db.refresh(aviso)
    assert aviso.estado == "enviada"
    assert aviso.salio_en is not None
    assert aviso.intentos == 1

    # La segunda vuelta no lo vuelve a mandar.
    assert correo.despachar(db)["enviados"] == 0
    assert len(salieron) == 1


def test_lo_que_falla_se_reintenta_pero_no_para_siempre(db, monkeypatch):
    """Un proveedor caido se levanta; una direccion mal escrita no se
    arregla sola. Despues del tope, el aviso deja de gastar la cola y se
    queda con lo ultimo que dijo el proveedor escrito al lado."""
    _configurado(monkeypatch)
    aviso = _aviso(db)

    def revienta(destino, asunto, cuerpo, html=None):
        raise RuntimeError("550 direccion inexistente")

    monkeypatch.setattr(correo, "entregar", revienta)

    for vuelta in range(correo.TOPE_INTENTOS):
        correo.despachar(db)
        db.refresh(aviso)
        assert aviso.intentos == vuelta + 1

    assert aviso.estado == "fallida"
    assert "550" in aviso.ultimo_error
    # Y ya no se vuelve a intentar: la cola no lo carga para siempre.
    antes = aviso.intentos
    correo.despachar(db)
    db.refresh(aviso)
    assert aviso.intentos == antes


def test_un_aviso_sin_direccion_no_da_vueltas_en_la_cola(db, monkeypatch):
    _configurado(monkeypatch)
    aviso = _aviso(db, correo_destino=None)
    monkeypatch.setattr(correo, "entregar",
                        lambda *a, **k: pytest.fail("no habia a donde mandarlo"))

    correo.despachar(db)
    db.refresh(aviso)
    assert aviso.estado == "sin_correo"


def test_el_enlace_sale_con_dominio_o_no_sale(monkeypatch):
    """Dentro del sistema los enlaces son rutas porque el navegador ya
    sabe de donde cuelgan. En un correo, una ruta sola no lleva a ningun
    lado: o va completa o no va."""
    monkeypatch.setattr(correo.settings, "url_publica", "https://centauro.lat/")
    assert correo.con_dominio("/encuestas/pagina/abc") == \
        "https://centauro.lat/encuestas/pagina/abc"
    # Lo que ya viene completo no se toca.
    assert correo.con_dominio("https://otro.com/x") == "https://otro.com/x"

    monkeypatch.setattr(correo.settings, "url_publica", "")
    assert correo.con_dominio("/encuestas/pagina/abc") is None


# ------------------------------------------------- la cara del correo

def test_el_correo_sale_en_las_dos_versiones_y_con_la_ficha(db, monkeypatch):
    """HTML y texto plano en el mismo mensaje. Hay buzones que bloquean
    el HTML, y un correo que llega vacio es peor que uno feo.

    Y el telefono de quien va, marcable de un toque: el cliente que abre
    esto suele necesitar algo AHORA. Regla de Salvador (20 sep)."""
    from app import correo_html
    _configurado(monkeypatch)
    aviso = _aviso(db, asunto="EP/E-042: equipo en el punto")
    aviso.datos = correo_html.guardar_datos([
        ("Equipo", "Ernesto Vidal · conductor de seguridad", "5215512345678"),
        ("Unidad", "SUV blindada · placas CTR-2211"),
    ])
    db.commit()

    salieron = []
    monkeypatch.setattr(correo, "entregar",
                        lambda destino, asunto, cuerpo, html=None:
                        salieron.append((cuerpo, html)))
    correo.despachar(db)

    texto, html = salieron[0]
    assert html, "salio sin HTML"
    assert "tel:5215512345678" in html, "el telefono no se puede marcar"
    assert "CTR-2211" in html and "CTR-2211" in texto
    # El que lo recibe en texto tiene que poder hacer lo mismo.
    assert "5215512345678" in texto


def test_la_encuesta_usa_su_propio_correo(cliente, sesion, datos, db,
                                          monkeypatch):
    """La encuesta tiene el suyo desde hace meses --una sola llamada a
    la accion, en tres idiomas--: ahi las estrellas se pican desde el
    mensaje. Meterla en el armazon general seria pedir lo mismo con
    menos."""
    from ayudas import crear_servicio, jornada, manana
    from app import models as m
    _configurado(monkeypatch)
    monkeypatch.setattr(correo.settings, "url_publica", "https://centauro.lat")

    # La encuesta siempre es de un servicio: sin el, no hay nada que
    # calificar y la base no la deja existir.
    servicio = crear_servicio(
        cliente, sesion("consultor"), datos,
        [jornada(manana(480), datos["modalidades"]["full_day"]["id"])])
    encuesta = m.Encuesta(
        servicio_id=servicio["id"],
        tipo=m.TipoEncuesta.EJECUTIVO, destinatario_nombre="Robert Sandoval",
        destinatario_correo="ejecutivo@cliente.com", idioma="es",
        token="tokendeprueba123",
        # El enlace de la encuesta siempre vence: una encuesta abierta
        # para siempre se contesta meses despues y ya no dice nada del
        # servicio.
        expira_en=datetime.now() + timedelta(days=15))
    db.add(encuesta)
    aviso = _aviso(db, asunto="EP/E-042: como estuvo el servicio")
    aviso.plantilla = "encuesta"
    aviso.enlace_seguimiento = f"/encuestas/pagina/{encuesta.token}"
    db.commit()

    salieron = []
    monkeypatch.setattr(correo, "entregar",
                        lambda destino, asunto, cuerpo, html=None:
                        salieron.append((cuerpo, html)))
    correo.despachar(db)

    texto, html = salieron[0]
    assert "tokendeprueba123" in html
    # Y el enlace completo tambien en el texto: sin dominio no lleva a
    # ningun lado.
    assert "https://centauro.lat/encuestas/pagina/tokendeprueba123" in texto


# ------------------------------------------------- lo que ya no vale

def test_un_aviso_viejo_no_sale_y_se_dice(db, monkeypatch):
    """Decisión de Salvador (20 sep): si no salió el mismo día, ya no sale.

    Muerde dos días distintos. El del encendido —hay semanas de avisos
    escritos esperando proveedor, y sin esto saldrían todos de golpe a
    clientes reales— y cada vez que el proveedor se caiga más de un día.

    No se borra: queda en "vencida". "No llegó el correo" y "no se
    mandó" son dos conversaciones distintas.
    """
    _configurado(monkeypatch)
    viejo = _aviso(db, asunto="EP/E-042: equipo en el punto")
    viejo.enviada_en = datetime.now(timezone.utc) - timedelta(days=3)
    de_hoy = _aviso(db, asunto="EP/E-099: equipo en el punto")
    db.commit()

    salieron = []
    monkeypatch.setattr(correo, "entregar",
                        lambda destino, asunto, cuerpo, html=None:
                        salieron.append(asunto))

    r = correo.despachar(db)
    assert r["vencidos"] == 1
    assert r["enviados"] == 1
    assert salieron == ["EP/E-099: equipo en el punto"]

    db.refresh(viejo)
    db.refresh(de_hoy)
    assert viejo.estado == "vencida"
    assert viejo.intentos == 0, "no se gasto un intento en algo que no se manda"
    assert de_hoy.estado == "enviada"


def test_un_aviso_con_el_enlace_muerto_tampoco_sale(db, monkeypatch):
    """Llegaría con un botón que no lleva a ningún lado, y eso es peor
    que no llegar."""
    _configurado(monkeypatch)
    aviso = _aviso(db, asunto="EP/E-042: servicio iniciado")
    aviso.enlace_seguimiento = "/seguimiento/abc123"
    aviso.expira_en = datetime.now() - timedelta(hours=2)
    db.commit()

    monkeypatch.setattr(correo, "entregar",
                        lambda *a, **k: pytest.fail("el enlace ya estaba muerto"))
    r = correo.despachar(db)
    assert r["vencidos"] == 1
    db.refresh(aviso)
    assert aviso.estado == "vencida"


def test_el_estado_dice_cuantos_saldrian_antes_de_encender(db, monkeypatch):
    """Es lo que se mira antes de poner las credenciales."""
    _configurado(monkeypatch, si=False)
    viejo = _aviso(db, asunto="Viejo")
    viejo.enviada_en = datetime.now(timezone.utc) - timedelta(days=10)
    _aviso(db, asunto="De hoy")
    db.commit()

    r = correo.estado(db)
    assert r["configurado"] is False
    assert r["viejos"] == 1
    assert r["saldrian"] == 1
    assert r["horas_de_vida"] == correo.HORAS_DE_VIDA


# ------------------------------------------------ Microsoft 365 (seccion 67)
#
# El correo sale del buzon de la empresa por Microsoft Graph: Microsoft
# apaga el SMTP con usuario y contrasena el 31 de diciembre de 2026. Aqui
# Microsoft no existe: se le contesta como contestaria, y lo que se cuida
# es lo nuestro --que se le mande el mensaje completo al buzon correcto,
# que el permiso no se pida por cada correo y que lo que rechace quede
# escrito sin el secreto--.

class _Respuesta:
    def __init__(self, codigo, datos=None):
        self.status_code = codigo
        self._datos = datos
        self.text = ""

    def json(self):
        if self._datos is None:
            raise ValueError("sin cuerpo")
        return self._datos


def _microsoft(monkeypatch, envio=None):
    """Los tres datos de la aplicacion de Entra puestos, sin SMTP, y un
    Microsoft de mentira que anota lo que se le pidio."""
    monkeypatch.setattr(correo.settings, "correo_host", "")
    monkeypatch.setattr(correo.settings, "correo_de",
                        "Centauro <ai@centauro.lat>")
    monkeypatch.setattr(correo.settings, "correo_ms_tenant", "inquilino-x")
    monkeypatch.setattr(correo.settings, "correo_ms_cliente", "aplicacion-x")
    monkeypatch.setattr(correo.settings, "correo_ms_secreto", "secreto-x")
    monkeypatch.setattr(correo, "_token_microsoft",
                        {"valor": None, "vence": 0.0})
    llamadas = []
    respuestas = iter(envio or [])

    def post(url, **kw):
        llamadas.append((url, kw))
        if url.endswith("/oauth2/v2.0/token"):
            return _Respuesta(200, {"access_token": f"permiso-{len(llamadas)}",
                                    "expires_in": 3600})
        return next(respuestas, _Respuesta(202))

    monkeypatch.setattr(correo.httpx, "post", post)
    return llamadas


def test_microsoft_manda_el_mismo_mensaje_desde_el_buzon_de_la_empresa(
        monkeypatch):
    """Con la aplicacion puesta sale por Graph --no por SMTP--, desde el
    buzon de CORREO_DE y con el texto y el HTML en el mismo mensaje."""
    import base64
    import email

    llamadas = _microsoft(monkeypatch)
    monkeypatch.setattr(correo.smtplib, "SMTP",
                        lambda *a, **k: pytest.fail("salio por SMTP"))
    assert correo.configurado() and correo.por_microsoft()

    correo.entregar("ejecutivo@cliente.com", "Su equipo llego", "Texto",
                    "<p>HTML</p>")

    (permiso, pedido), (envio, mandado) = llamadas
    assert permiso == ("https://login.microsoftonline.com/inquilino-x"
                       "/oauth2/v2.0/token")
    assert pedido["data"]["grant_type"] == "client_credentials"
    assert pedido["data"]["scope"] == "https://graph.microsoft.com/.default"
    assert envio == ("https://graph.microsoft.com/v1.0/users/"
                     "ai@centauro.lat/sendMail")
    assert mandado["headers"]["Authorization"] == "Bearer permiso-1"
    assert mandado["headers"]["Content-Type"] == "text/plain"
    mime = email.message_from_bytes(base64.b64decode(mandado["content"]))
    assert mime["From"] == "Centauro <ai@centauro.lat>"
    assert mime["To"] == "ejecutivo@cliente.com"
    assert mime["Subject"] == "Su equipo llego"
    assert [p.get_content_type() for p in mime.walk()
            if not p.is_multipart()] == ["text/plain", "text/html"]


def test_el_permiso_de_microsoft_se_pide_una_vez_y_no_por_correo(monkeypatch):
    llamadas = _microsoft(monkeypatch)
    for _ in range(3):
        correo.entregar("a@cliente.com", "Aviso", "Texto")
    permisos = [u for u, _ in llamadas if u.endswith("/token")]
    assert len(permisos) == 1, "se pidio permiso por cada correo"

    # Vencido, se pide otro.
    correo._token_microsoft["vence"] = 0.0
    correo.entregar("a@cliente.com", "Aviso", "Texto")
    assert len([u for u, _ in llamadas if u.endswith("/token")]) == 2


def test_si_el_permiso_ya_no_sirve_se_pide_otro_una_vez(monkeypatch):
    llamadas = _microsoft(monkeypatch, envio=[_Respuesta(401, {
        "error": {"code": "InvalidAuthenticationToken",
                  "message": "Lifetime validation failed"}})])
    correo.entregar("a@cliente.com", "Aviso", "Texto")
    assert [u.rsplit("/", 1)[-1] for u, _ in llamadas] == \
        ["token", "sendMail", "token", "sendMail"]


def test_lo_que_rechaza_microsoft_queda_escrito_sin_el_secreto(db,
                                                               monkeypatch):
    """Sin permiso para mandar desde ese buzon, Graph contesta 403. El
    aviso se queda con el porque --es lo que TI necesita para saber que
    falta--, y el secreto no aparece en ningun lado."""
    _microsoft(monkeypatch, envio=[_Respuesta(403, {
        "error": {"code": "ErrorAccessDenied",
                  "message": "Access is denied. Check credentials and try "
                             "again."}})])
    aviso = _aviso(db)

    r = correo.despachar(db)
    assert r["enviados"] == 0
    db.refresh(aviso)
    assert aviso.estado == "pendiente" and aviso.intentos == 1
    assert "ErrorAccessDenied" in aviso.ultimo_error
    assert "secreto-x" not in aviso.ultimo_error


def test_el_secreto_vencido_se_dice(monkeypatch):
    """Entra da el secreto por 24 meses como maximo. El dia que vence, lo
    que queda escrito lo dice."""
    _microsoft(monkeypatch)
    monkeypatch.setattr(correo.httpx, "post", lambda url, **kw: _Respuesta(
        401, {"error": "invalid_client",
              "error_description": "AADSTS7000222: The provided client "
                                   "secret keys are expired."}))
    with pytest.raises(RuntimeError) as falla:
        correo.entregar("a@cliente.com", "Aviso", "Texto")
    assert "AADSTS7000222" in str(falla.value)
    assert "secreto-x" not in str(falla.value)


def test_el_estado_dice_por_donde_sale_y_no_ensena_el_secreto(db,
                                                              monkeypatch):
    _microsoft(monkeypatch)
    r = correo.estado(db)
    assert r["configurado"] is True
    assert r["por"] == "microsoft"
    assert r["servidor"] == "graph.microsoft.com"
    assert r["desde"] == "Centauro <ai@centauro.lat>"
    assert "secreto-x" not in str(r)
