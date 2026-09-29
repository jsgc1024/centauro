# -*- coding: utf-8 -*-
"""La bitacora de administracion, para leerla (seccion 86).

Desde el panel de accesos cada cambio de administracion deja su renglon
en `RegistroAdmin`: quien le abrio o cerro la puerta a quien, quien le
cambio el puesto, quien movio un precio o un festivo, quien puso el tipo
de cambio. Se escribia bien y se leia a pedazos: el historial de un
acceso, el de un renglon de catalogo. Para saber que cambio en el mes no
habia donde mirar.

Aqui se lee junta, con filtros --que, quien, que mes-- y en Excel.
Decision de Salvador, 27 de septiembre (propuesta del puesto de
administracion del sistema y calidad): la lee quien trae `bitacora.ver`.

Cada renglon se cuenta en el idioma de quien lo lee: donde fue y que
cambio, con los nombres y no con los numeros de la base --"ciudad
Queretaro -> Monterrey", no "plaza_id: 3 -> 5"--. Se arma aqui y no en
la pantalla porque el Excel dice lo mismo que la pantalla, y dos copias
de la misma frase se separan.
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app import excel, permisos
from app import models as m
from app import textos_aviso as ta

# ------------------------------------------------------------- los grupos

# Con que nombre entra cada catalogo a la bitacora: el prefijo de su
# ruta (crud.py). Mas los que se escriben a mano: la foto de una
# categoria de vehiculo, los pesos del profesionalismo y los paquetes
# con viaticos de un tarifario.
CATALOGOS = ("paises", "plazas", "perfiles", "categorias-vehiculo",
             "categoria_vehiculo", "modalidades", "clientes", "tarifarios",
             "tarifario", "tarifas-recurso", "tarifas-vehiculo",
             "tabulador-viaticos", "comisiones", "personal",
             "tarifas-freelance", "vehiculos", "parametros-combustible",
             "dias-festivos", "hospitales", "hoteles", "profesionalismo",
             # Lo que vale cada criterio del bono y lo que el arranque
             # confirma a mano (seccion 97).
             "criterio_estrella", "arranque")

GRUPOS = {
    "accesos": ("usuario",),
    "puestos": ("categoria",),
    "catalogos": CATALOGOS,
    "tipo_cambio": ("tipo_cambio",),
    # Las lecturas de Odoo dejan un renglon cada hora, se haya movido algo
    # o no: se ven aparte, para que no tapen lo que hizo una persona.
    "odoo": ("sincronizacion_odoo", "producto_odoo"),
}
# "Todo" es lo que hace la gente: sin las lecturas de cada hora.
TODO = ("accesos", "puestos", "catalogos", "tipo_cambio")

# Lo que la pantalla de Catalogos ensena abajo de cada catalogo.
DE_CADA_CATALOGO = {
    "dias-festivos": ("dias-festivos",),
    "hospitales": ("hospitales",),
    "hoteles": ("hoteles",),
    "plazas": ("plazas",),
    "parametros-combustible": ("parametros-combustible",),
    "categorias-vehiculo": ("categorias-vehiculo", "categoria_vehiculo"),
    "paises": ("paises", "perfiles"),
    "tabulador-viaticos": ("tabulador-viaticos",),
    "modalidades": ("modalidades",),
    "tarifas-freelance": ("tarifas-freelance",),
    "profesionalismo": ("profesionalismo",),
}

POR_PAGINA = 100
# El Excel trae lo filtrado completo, hasta aqui: un mes de todo cabe de
# sobra, y un tope evita que un filtro vacio arme un archivo de un ano.
TOPE_EXCEL = 20000

# --------------------------------------------------------------- los textos

TEXTOS = {
    "es": {
        "donde": {
            "usuario": "Accesos", "categoria": "Puestos",
            "tipo_cambio": "Tipo de cambio",
            "sincronizacion_odoo": "Odoo", "producto_odoo": "Productos de Odoo",
            "paises": "Países", "plazas": "Ciudades", "perfiles": "Perfiles",
            "categorias-vehiculo": "Unidades por categoría",
            "categoria_vehiculo": "Unidades por categoría",
            "modalidades": "Horas de cada modalidad", "clientes": "Clientes",
            "tarifarios": "Tarifarios", "tarifario": "Tarifarios",
            "tarifas-recurso": "Tarifarios", "tarifas-vehiculo": "Tarifarios",
            "tabulador-viaticos": "Tabulador de viáticos",
            "comisiones": "Lo que se paga por día", "personal": "Personal",
            "tarifas-freelance": "Tarifas de freelance", "vehiculos": "Flota",
            "parametros-combustible": "Combustible",
            "dias-festivos": "Días festivos", "hospitales": "Hospitales",
            "hoteles": "Hoteles", "profesionalismo": "Pesos del profesionalismo",
            "criterio_estrella": "Criterios del bono", "arranque": "El arranque",
        },
        "accion": {
            "catalogo creado": "Agregó «{nombre}»",
            "catalogo cambiado": "«{nombre}»: {cambios}",
            "catalogo desactivado": "Quitó «{nombre}»",
            "catalogo reactivado": "Volvió a poner «{nombre}»",
            "catalogo borrado": "Borró «{nombre}»",
            "foto de categoria": "Puso la foto de «{nombre}», {color}",
            "foto de categoria quitada": "Quitó la foto de «{nombre}», {color}",
            "tipo de cambio": "{antes} → {despues} pesos por dólar",
            "tabulador de comisiones cambiado": "{detalle}: {antes} → {despues}",
            "correo reintentado": "Regresó a la cola {despues} avisos de correo que habían fallado",
            "criterio del bono cambiado": "«{detalle}»: {antes} → {despues}",
            "arranque confirmado": "Confirmó a mano: {detalle}",
            "arranque sin confirmar": "Quitó la confirmación: {detalle}",
            "acceso creado": "Le dio acceso a {persona}, como {despues}",
            "acceso desactivado": "Cerró el acceso de {persona}: «{detalle}»",
            "acceso cerrado": "Cerró el acceso de {persona}: {detalle}",
            "acceso reactivado": "Reabrió el acceso de {persona}: «{detalle}»",
            "rol cambiado": "{persona}: rol {antes} → {despues}",
            "categoria asignada": "{persona}: puesto {antes} → {despues}",
            "permiso de mas dado": "Le dio a {persona} «{despues}»",
            "permiso de mas quitado": "Le quitó a {persona} «{antes}»",
            "categoria creada": "Creó el puesto «{despues}»",
            "categoria cambiada": "«{detalle}»: {cambios}",
            "contrasena puesta": "{persona} creó su contraseña",
            "contrasena cambiada": "{persona} cambió su contraseña",
            "recuperacion pedida": "{persona} pidió recuperar su contraseña",
            "invitacion reenviada": "Reenvió la invitación de {persona}",
            "enlace entregado": "Copió el enlace de {persona}",
            "codigo de campo entregado": "Dictó el código de campo a {persona}",
            "paquetes con viaticos": "«{detalle}»: paquetes con viáticos {antes} → {despues}",
            "producto de odoo confirmado": "Confirmó el producto «{detalle}»",
            "producto de odoo preferido": "«{detalle}»: preferido {despues}",
        },
        "ninguno": "ninguno", "si": "sí", "no": "no", "base": "la base",
        "baja_odoo": "baja en Odoo",
        "agrego": "agregó {que}", "quito": "quitó {que}",
        "sin_actividades": "cambió su menú o sus datos",
        "campos": {
            "nombre": "nombre", "codigo": "código", "fecha": "fecha",
            "factor_comision": "comisión ×", "precio_litro": "precio por litro",
            "holgura_pct": "holgura %", "vigencia_desde": "vigente desde",
            "nivel_atencion": "nivel de atención", "lat": "latitud",
            "lon": "longitud", "direccion": "dirección", "telefono": "teléfono",
            "plaza_id": "ciudad", "pais_id": "país", "persona_id": "persona",
            "modalidad_id": "modalidad", "categoria_id": "categoría",
            "perfil_id": "perfil", "tarifario_id": "tarifario",
            "tiene_recurso_local": "personal propio",
            "rendimiento_km_litro": "rendimiento km/l", "blindado": "blindada",
            "horas": "horas", "horas_descanso": "horas de descanso",
            "aplica_horas_extra": "horas extra",
            "bloquea_dia_completo": "bloquea el día",
            "km_estimados": "km estimados", "monto": "monto",
            "monto_abierto": "monto abierto", "concepto": "concepto",
            "escenario": "escenario", "tipo_servicio": "tipo",
            "costo": "costo", "costo_hora_extra": "costo de la hora extra",
            "moneda": "moneda", "moneda_local": "moneda", "lada": "lada",
            "anticipacion_aeropuerto_min": "anticipación en aeropuerto (min)",
            "anticipacion_min": "anticipación (min)",
            "zona_horaria": "zona horaria", "idioma": "idioma",
            "estrellas": "estrellas", "satisfaccion": "satisfacción",
            "incidencias": "incidencias", "capacitacion": "capacitación",
            "experiencia": "experiencia", "manejo": "manejo",
            "meses_ventana": "meses que mira",
            "horas_referencia": "horas de experiencia plena",
            "castigo_error_menor": "castigo por error menor",
            "castigo_leve": "castigo por incidencia leve",
            "castigo_grave": "castigo por incidencia grave",
            "puntos_por_evento_manejo": "puntos por evento de manejo",
            "odoo_id": "liga con Odoo",
        },
        "excel": {
            "hoja": "Bitácora", "archivo": "bitacora",
            "columnas": ("Cuándo", "Quién", "Con qué rol", "Dónde",
                         "Qué cambió", "Acción", "Antes", "Después",
                         "Detalle"),
        },
    },
    "en": {
        "donde": {
            "usuario": "Access", "categoria": "Jobs",
            "tipo_cambio": "Exchange rate",
            "sincronizacion_odoo": "Odoo", "producto_odoo": "Odoo products",
            "paises": "Countries", "plazas": "Cities", "perfiles": "Profiles",
            "categorias-vehiculo": "Vehicles by category",
            "categoria_vehiculo": "Vehicles by category",
            "modalidades": "Hours per service type", "clientes": "Clients",
            "tarifarios": "Price lists", "tarifario": "Price lists",
            "tarifas-recurso": "Price lists", "tarifas-vehiculo": "Price lists",
            "tabulador-viaticos": "Allowance table",
            "comisiones": "Daily pay", "personal": "Staff",
            "tarifas-freelance": "Freelance rates", "vehiculos": "Fleet",
            "parametros-combustible": "Fuel",
            "dias-festivos": "Public holidays", "hospitales": "Hospitals",
            "hoteles": "Hotels", "profesionalismo": "Professionalism weights",
            "criterio_estrella": "Bonus criteria", "arranque": "The go-live",
        },
        "accion": {
            "catalogo creado": "Added “{nombre}”",
            "catalogo cambiado": "“{nombre}”: {cambios}",
            "catalogo desactivado": "Removed “{nombre}”",
            "catalogo reactivado": "Put “{nombre}” back",
            "catalogo borrado": "Deleted “{nombre}”",
            "foto de categoria": "Set the photo of “{nombre}”, {color}",
            "foto de categoria quitada": "Removed the photo of “{nombre}”, {color}",
            "tipo de cambio": "{antes} → {despues} pesos per dollar",
            "tabulador de comisiones cambiado": "{detalle}: {antes} → {despues}",
            "correo reintentado": "Sent {despues} failed emails back to the queue",
            "criterio del bono cambiado": "«{detalle}»: {antes} → {despues}",
            "arranque confirmado": "Confirmed by hand: {detalle}",
            "arranque sin confirmar": "Removed the confirmation: {detalle}",
            "acceso creado": "Gave access to {persona}, as {despues}",
            "acceso desactivado": "Closed {persona}'s access: “{detalle}”",
            "acceso cerrado": "Closed {persona}'s access: {detalle}",
            "acceso reactivado": "Reopened {persona}'s access: “{detalle}”",
            "rol cambiado": "{persona}: role {antes} → {despues}",
            "categoria asignada": "{persona}: job {antes} → {despues}",
            "permiso de mas dado": "Gave {persona} “{despues}”",
            "permiso de mas quitado": "Took “{antes}” away from {persona}",
            "categoria creada": "Created the job “{despues}”",
            "categoria cambiada": "“{detalle}”: {cambios}",
            "contrasena puesta": "{persona} created their password",
            "contrasena cambiada": "{persona} changed their password",
            "recuperacion pedida": "{persona} asked to recover their password",
            "invitacion reenviada": "Resent {persona}'s invitation",
            "enlace entregado": "Copied {persona}'s link",
            "codigo de campo entregado": "Read out the field code to {persona}",
            "paquetes con viaticos": "“{detalle}”: packages with allowances {antes} → {despues}",
            "producto de odoo confirmado": "Confirmed the product “{detalle}”",
            "producto de odoo preferido": "“{detalle}”: preferred {despues}",
        },
        "ninguno": "none", "si": "yes", "no": "no", "base": "the base one",
        "baja_odoo": "left the company in Odoo",
        "agrego": "added {que}", "quito": "removed {que}",
        "sin_actividades": "changed its menu or its details",
        "campos": {
            "nombre": "name", "codigo": "code", "fecha": "date",
            "factor_comision": "commission ×", "precio_litro": "price per litre",
            "holgura_pct": "margin %", "vigencia_desde": "valid from",
            "nivel_atencion": "level of care", "lat": "latitude",
            "lon": "longitude", "direccion": "address", "telefono": "phone",
            "plaza_id": "city", "pais_id": "country", "persona_id": "person",
            "modalidad_id": "service type", "categoria_id": "category",
            "perfil_id": "profile", "tarifario_id": "price list",
            "tiene_recurso_local": "own staff",
            "rendimiento_km_litro": "km per litre", "blindado": "armoured",
            "horas": "hours", "horas_descanso": "rest hours",
            "aplica_horas_extra": "overtime",
            "bloquea_dia_completo": "blocks the day",
            "km_estimados": "estimated km", "monto": "amount",
            "monto_abierto": "open amount", "concepto": "item",
            "escenario": "scenario", "tipo_servicio": "type",
            "costo": "cost", "costo_hora_extra": "overtime hour cost",
            "moneda": "currency", "moneda_local": "currency", "lada": "dialling code",
            "anticipacion_aeropuerto_min": "arrival ahead at airports (min)",
            "anticipacion_min": "arrival ahead (min)",
            "zona_horaria": "time zone", "idioma": "language",
            "estrellas": "stars", "satisfaccion": "satisfaction",
            "incidencias": "incidents", "capacitacion": "training",
            "experiencia": "experience", "manejo": "driving",
            "meses_ventana": "months looked at",
            "horas_referencia": "hours for full experience",
            "castigo_error_menor": "penalty for a minor error",
            "castigo_leve": "penalty for a minor incident",
            "castigo_grave": "penalty for a serious incident",
            "puntos_por_evento_manejo": "points per driving event",
            "odoo_id": "Odoo link",
        },
        "excel": {
            "hoja": "Log", "archivo": "log",
            "columnas": ("When", "Who", "With role", "Where", "What changed",
                         "Action", "Before", "After", "Detail"),
        },
    },
    "pt": {
        "donde": {
            "usuario": "Acessos", "categoria": "Cargos",
            "tipo_cambio": "Câmbio",
            "sincronizacion_odoo": "Odoo", "producto_odoo": "Produtos do Odoo",
            "paises": "Países", "plazas": "Cidades", "perfiles": "Perfis",
            "categorias-vehiculo": "Veículos por categoria",
            "categoria_vehiculo": "Veículos por categoria",
            "modalidades": "Horas de cada modalidade", "clientes": "Clientes",
            "tarifarios": "Tabelas de preço", "tarifario": "Tabelas de preço",
            "tarifas-recurso": "Tabelas de preço",
            "tarifas-vehiculo": "Tabelas de preço",
            "tabulador-viaticos": "Tabela de diárias",
            "comisiones": "O que se paga por dia", "personal": "Pessoal",
            "tarifas-freelance": "Tarifas de freelance", "vehiculos": "Frota",
            "parametros-combustible": "Combustível",
            "dias-festivos": "Feriados", "hospitales": "Hospitais",
            "hoteles": "Hotéis", "profesionalismo": "Pesos do profissionalismo",
            "criterio_estrella": "Critérios do bônus", "arranque": "O arranque",
        },
        "accion": {
            "catalogo creado": "Adicionou “{nombre}”",
            "catalogo cambiado": "“{nombre}”: {cambios}",
            "catalogo desactivado": "Tirou “{nombre}”",
            "catalogo reactivado": "Voltou a pôr “{nombre}”",
            "catalogo borrado": "Apagou “{nombre}”",
            "foto de categoria": "Pôs a foto de “{nombre}”, {color}",
            "foto de categoria quitada": "Tirou a foto de “{nombre}”, {color}",
            "tipo de cambio": "{antes} → {despues} pesos por dólar",
            "tabulador de comisiones cambiado": "{detalle}: {antes} → {despues}",
            "correo reintentado": "Devolveu à fila {despues} e-mails que tinham falhado",
            "criterio del bono cambiado": "«{detalle}»: {antes} → {despues}",
            "arranque confirmado": "Confirmou à mão: {detalle}",
            "arranque sin confirmar": "Retirou a confirmação: {detalle}",
            "acceso creado": "Deu acesso a {persona}, como {despues}",
            "acceso desactivado": "Fechou o acesso de {persona}: “{detalle}”",
            "acceso cerrado": "Fechou o acesso de {persona}: {detalle}",
            "acceso reactivado": "Reabriu o acesso de {persona}: “{detalle}”",
            "rol cambiado": "{persona}: papel {antes} → {despues}",
            "categoria asignada": "{persona}: cargo {antes} → {despues}",
            "permiso de mas dado": "Deu a {persona} “{despues}”",
            "permiso de mas quitado": "Tirou de {persona} “{antes}”",
            "categoria creada": "Criou o cargo “{despues}”",
            "categoria cambiada": "“{detalle}”: {cambios}",
            "contrasena puesta": "{persona} criou sua senha",
            "contrasena cambiada": "{persona} trocou sua senha",
            "recuperacion pedida": "{persona} pediu para recuperar a senha",
            "invitacion reenviada": "Reenviou o convite de {persona}",
            "enlace entregado": "Copiou o link de {persona}",
            "codigo de campo entregado": "Ditou o código de campo a {persona}",
            "paquetes con viaticos": "“{detalle}”: pacotes com diárias {antes} → {despues}",
            "producto de odoo confirmado": "Confirmou o produto “{detalle}”",
            "producto de odoo preferido": "“{detalle}”: preferido {despues}",
        },
        "ninguno": "nenhum", "si": "sim", "no": "não", "base": "a base",
        "baja_odoo": "desligado no Odoo",
        "agrego": "adicionou {que}", "quito": "tirou {que}",
        "sin_actividades": "mudou o menu ou os dados",
        "campos": {
            "nombre": "nome", "codigo": "código", "fecha": "data",
            "factor_comision": "comissão ×", "precio_litro": "preço por litro",
            "holgura_pct": "folga %", "vigencia_desde": "vigente desde",
            "nivel_atencion": "nível de atendimento", "lat": "latitude",
            "lon": "longitude", "direccion": "endereço", "telefono": "telefone",
            "plaza_id": "cidade", "pais_id": "país", "persona_id": "pessoa",
            "modalidad_id": "modalidade", "categoria_id": "categoria",
            "perfil_id": "perfil", "tarifario_id": "tabela de preço",
            "tiene_recurso_local": "pessoal próprio",
            "rendimiento_km_litro": "km por litro", "blindado": "blindado",
            "horas": "horas", "horas_descanso": "horas de descanso",
            "aplica_horas_extra": "horas extras",
            "bloquea_dia_completo": "bloqueia o dia",
            "km_estimados": "km estimados", "monto": "valor",
            "monto_abierto": "valor aberto", "concepto": "conceito",
            "escenario": "cenário", "tipo_servicio": "tipo",
            "costo": "custo", "costo_hora_extra": "custo da hora extra",
            "moneda": "moeda", "moneda_local": "moeda", "lada": "DDI",
            "anticipacion_aeropuerto_min": "antecedência no aeroporto (min)",
            "anticipacion_min": "antecedência (min)",
            "zona_horaria": "fuso horário", "idioma": "idioma",
            "estrellas": "estrelas", "satisfaccion": "satisfação",
            "incidencias": "incidentes", "capacitacion": "treinamento",
            "experiencia": "experiência", "manejo": "direção",
            "meses_ventana": "meses considerados",
            "horas_referencia": "horas de experiência plena",
            "castigo_error_menor": "punição por erro menor",
            "castigo_leve": "punição por incidente leve",
            "castigo_grave": "punição por incidente grave",
            "puntos_por_evento_manejo": "pontos por evento de direção",
            "odoo_id": "vínculo com o Odoo",
        },
        "excel": {
            "hoja": "Registro", "archivo": "registro",
            "columnas": ("Quando", "Quem", "Com qual papel", "Onde",
                         "O que mudou", "Ação", "Antes", "Depois", "Detalhe"),
        },
    },
}

# Los campos que guardan el numero de otro registro: se lee su nombre.
QUIEN_ES = {
    "plaza_id": m.Plaza, "pais_id": m.Pais, "persona_id": m.Persona,
    "categoria_id": m.CategoriaVehiculo, "perfil_id": m.PerfilPersonal,
    "tarifario_id": m.Tarifario, "modalidad_id": m.Modalidad,
}


def _t(idioma: str) -> dict:
    return TEXTOS.get(idioma, TEXTOS["es"])


def objetos_de(que: str | None) -> tuple:
    """Los objetos de la bitacora que entran con este filtro."""
    if que in GRUPOS:
        return GRUPOS[que]
    return tuple(o for g in TODO for o in GRUPOS[g])


def grupo_de(objeto: str) -> str:
    for grupo, objetos in GRUPOS.items():
        if objeto in objetos:
            return grupo
    return "catalogos"


def mes_de(texto: str | None) -> tuple[datetime, datetime] | None:
    """"2026-09" -> del 1 de septiembre al 1 de octubre, en la hora del
    servidor, que es la misma con la que el Excel escribe la hora."""
    if not texto:
        return None
    try:
        anio, mes = (int(x) for x in texto.split("-")[:2])
        desde = datetime(anio, mes, 1).astimezone()
    except (ValueError, TypeError):
        return None
    siguiente = datetime(anio + (mes == 12), mes % 12 + 1, 1).astimezone()
    return desde, siguiente


def _consulta(db: Session, que=None, quien=None, mes=None, objetos=None):
    consulta = db.query(m.RegistroAdmin).filter(
        m.RegistroAdmin.objeto.in_(objetos or objetos_de(que)))
    if quien:
        consulta = consulta.filter(m.RegistroAdmin.usuario_id == quien)
    rango = mes_de(mes)
    if rango:
        consulta = consulta.filter(m.RegistroAdmin.creado_en >= rango[0],
                                   m.RegistroAdmin.creado_en < rango[1])
    return consulta.order_by(m.RegistroAdmin.creado_en.desc(),
                             m.RegistroAdmin.id.desc())


# ------------------------------------------------------ contar un renglon

class _Nombres:
    """Los nombres que hacen falta para contar varios renglones, pedidos
    de una vez y no uno por uno."""

    def __init__(self, db: Session, filas: list):
        self.db = db
        usuarios = {r.objeto_id for r in filas
                    if r.objeto == "usuario" and r.objeto_id}
        self.de_usuario = {}
        if usuarios:
            for u in (db.query(m.Usuario)
                      .filter(m.Usuario.id.in_(usuarios)).all()):
                self.de_usuario[u.id] = (u.persona.nombre if u.persona
                                         else u.correo)
        self._cache = {}

    def usuario(self, usuario_id) -> str:
        return self.de_usuario.get(usuario_id) or f"#{usuario_id}"

    def de(self, campo: str, valor: str) -> str | None:
        modelo = QUIEN_ES.get(campo)
        if not modelo:
            return None
        try:
            clave = (campo, int(valor))
        except (TypeError, ValueError):
            return None
        if clave not in self._cache:
            obj = self.db.get(modelo, clave[1])
            nombre = None
            if obj is not None:
                nombre = (getattr(obj, "nombre", None)
                          or getattr(obj, "codigo", None))
                if isinstance(obj, m.Modalidad):
                    pais = obj.pais.nombre if obj.pais else ""
                    nombre = f"{obj.codigo.value} {pais}".strip()
            self._cache[clave] = nombre
        return self._cache[clave]


def _numero(valor: str) -> str:
    """"24.5000" -> "24.5"; lo que no es numero se queda como esta."""
    try:
        d = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return valor
    if d == d.to_integral_value():
        return str(d.quantize(Decimal(1)))
    return format(d.normalize(), "f")


def _tasa(valor: str) -> str:
    """"17.4000" -> "17.40": un tipo de cambio se lee con dos decimales,
    y los que traiga de mas se quedan ("17.4523")."""
    numero = _numero(valor)
    enteros, _, decimales = numero.partition(".")
    return f"{enteros}.{decimales.ljust(2, '0')}" if enteros.lstrip("-").isdigit() else valor


def _valor(campo: str, valor: str, t: dict, nombres: _Nombres) -> str:
    valor = (valor or "").strip()
    if valor in ("", "None"):
        return t["ninguno"]
    if valor == "True":
        return t["si"]
    if valor == "False":
        return t["no"]
    nombre = nombres.de(campo, valor)
    if nombre:
        return nombre
    return _numero(valor)


def _partes(texto: str | None) -> dict:
    """"horas: 12; km_estimados: None" -> {"horas": "12", ...}. Lo que no
    tiene esa forma --un texto cortado a los 200-- se deja pasar."""
    salida = {}
    for pedazo in (texto or "").split("; "):
        campo, dos, valor = pedazo.partition(": ")
        if dos and campo and " " not in campo:
            salida[campo] = valor
    return salida


def _cambios(r: m.RegistroAdmin, t: dict, nombres: _Nombres) -> str:
    antes, despues = _partes(r.antes), _partes(r.despues)
    dichos = []
    for campo in list(dict.fromkeys([*despues, *antes])):
        etiqueta = t["campos"].get(campo, campo.replace("_", " "))
        dichos.append(f"{etiqueta} {_valor(campo, antes.get(campo), t, nombres)}"
                      f" → {_valor(campo, despues.get(campo), t, nombres)}")
    if dichos:
        return "; ".join(dichos)
    return f"{r.antes or t['ninguno']} → {r.despues or t['ninguno']}"


def _rol(valor: str | None, idioma: str) -> str:
    if not valor:
        return ""
    textos = ta.TEXTOS.get(idioma, ta.TEXTOS["es"])
    return textos.get(f"rol_{valor}", valor.replace("_", " "))


def _actividad(codigo: str | None) -> str:
    if not codigo:
        return ""
    datos = permisos.ACTIVIDADES.get(codigo)
    return datos["descripcion"] if datos else codigo


PERFILES_CORTOS = {"conductor_seguridad": "conductor", "agente_seguridad": "agente",
                   "coordinador_seguridad": "coordinador",
                   "consultor_seguridad": "consultor"}
MODALIDADES_CORTAS = {"es": {"full_day": "full day", "medio_dia": "medio día", "transfer": "transfer"},
                      "en": {"full_day": "full day", "medio_dia": "half day", "transfer": "transfer"},
                      "pt": {"full_day": "full day", "medio_dia": "meio dia", "transfer": "transfer"}}


def _tabulador(texto: str, idioma: str) -> str:
    """"conductor_seguridad/full_day 700 (+90)" -> "conductor · full day 700 (+90)"."""
    partes = []
    for renglon in (texto or "").split(";"):
        renglon = renglon.strip()
        m_ = re.match(r"(\w+)/(\w+) (.*)", renglon)
        if not m_:
            partes.append(renglon)
            continue
        perfil, modalidad, montos = m_.groups()
        partes.append(f"{PERFILES_CORTOS.get(perfil, perfil)} · "
                      f"{MODALIDADES_CORTAS.get(idioma, {}).get(modalidad, modalidad)} {montos}")
    return "; ".join(partes)


def que_cambio(r: m.RegistroAdmin, idioma: str, nombres: _Nombres) -> str:
    """El renglon contado en una frase."""
    t = _t(idioma)
    plantilla = t["accion"].get(r.accion)
    persona = nombres.usuario(r.objeto_id) if r.objeto == "usuario" else ""
    nombre = r.detalle or r.despues or r.antes or ""
    antes, despues, detalle = r.antes or "", r.despues or "", r.detalle or ""

    if r.accion == "catalogo cambiado":
        cambios = _cambios(r, t, nombres)
    elif r.accion == "categoria cambiada":
        partes = []
        if despues:
            partes.append(t["agrego"].replace("{que}", despues))
        if antes:
            partes.append(t["quito"].replace("{que}", antes))
        cambios = "; ".join(partes) or t["sin_actividades"]
    else:
        cambios = ""

    if r.accion == "catalogo creado":
        nombre = despues
    elif r.accion == "catalogo borrado":
        nombre = antes
    elif r.accion in ("foto de categoria", "foto de categoria quitada"):
        nombre = detalle or nombres.de("categoria_id", str(r.objeto_id)) or ""
    color = despues if r.accion == "foto de categoria" else antes
    if color == "base":
        color = t["base"]

    if r.accion in ("rol cambiado", "acceso creado"):
        antes, despues = _rol(antes, idioma), _rol(despues, idioma)
    if r.accion == "categoria asignada":
        antes, despues = antes or t["ninguno"], despues or t["ninguno"]
    if r.accion == "tipo de cambio":
        antes = _tasa(antes) if antes else t["ninguno"]
        despues = _tasa(despues)
    if r.accion == "tabulador de comisiones cambiado":
        antes, despues = _tabulador(antes, idioma), _tabulador(despues, idioma)
        detalle = detalle.split(":")[0].replace("MX", "México").replace("BR", "Brasil")
    if r.accion == "acceso cerrado" and detalle == "baja en Odoo":
        detalle = t["baja_odoo"]
    if r.accion == "permiso de mas dado":
        despues = _actividad(despues)
    if r.accion == "permiso de mas quitado":
        antes = _actividad(antes)
    if r.accion in ("paquetes con viaticos", "producto de odoo preferido"):
        antes = t["si"] if antes == "true" else t["no"] if antes == "false" else antes
        despues = (t["si"] if despues == "true"
                   else t["no"] if despues == "false" else despues)

    if not plantilla:
        # Una accion que no tiene frase todavia --una lectura de Odoo, por
        # ejemplo-- se dice como se escribio: la accion y lo que dejo.
        extra = " → ".join(x for x in (r.antes, r.despues) if x)
        return f"{r.accion}: {extra}" if extra else r.accion

    texto = (plantilla.replace("{persona}", persona)
             .replace("{nombre}", nombre).replace("{cambios}", cambios)
             .replace("{color}", color or "").replace("{antes}", antes)
             .replace("{despues}", despues).replace("{detalle}", detalle))
    return texto


def renglon(r: m.RegistroAdmin, idioma: str, nombres: _Nombres) -> dict:
    t = _t(idioma)
    return {
        "id": r.id,
        "cuando": r.creado_en.isoformat() if r.creado_en else None,
        "quien": r.persona.nombre if r.persona else None,
        "usuario_id": r.usuario_id,
        "rol": r.rol.value if r.rol else None,
        "rol_texto": _rol(r.rol.value if r.rol else None, idioma),
        "grupo": grupo_de(r.objeto),
        "objeto": r.objeto,
        "objeto_id": r.objeto_id,
        "donde": t["donde"].get(r.objeto, r.objeto),
        "que": que_cambio(r, idioma, nombres),
        "accion": r.accion, "antes": r.antes, "despues": r.despues,
        "detalle": r.detalle,
    }


# ------------------------------------------------------------- las consultas

def consultar(db: Session, que=None, quien=None, mes=None, pagina: int = 1,
              idioma: str = "es") -> dict:
    """Una pagina de lo filtrado, y lo que la pantalla necesita para sus
    filtros: quien aparece y que meses tienen algo."""
    pagina = max(1, pagina)
    consulta = _consulta(db, que, quien, mes)
    total = consulta.count()
    filas = consulta.offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()
    nombres = _Nombres(db, filas)
    return {
        "filas": [renglon(r, idioma, nombres) for r in filas],
        "total": total, "pagina": pagina, "por_pagina": POR_PAGINA,
        "opciones": opciones(db),
    }


def opciones(db: Session) -> dict:
    """Quien ha hecho algo y en que meses, de todo menos las lecturas de
    cada hora."""
    todo = objetos_de(None)
    quienes = {}
    for usuario_id, persona in (
            db.query(m.RegistroAdmin.usuario_id, m.Persona.nombre)
            .outerjoin(m.Persona, m.Persona.id == m.RegistroAdmin.persona_id)
            .filter(m.RegistroAdmin.objeto.in_(todo))
            .distinct().all()):
        quienes[usuario_id] = persona or f"#{usuario_id}"
    meses = set()
    for (momento,) in (db.query(m.RegistroAdmin.creado_en)
                       .filter(m.RegistroAdmin.objeto.in_(todo)).all()):
        if momento:
            local = momento.astimezone()
            meses.add(f"{local.year:04d}-{local.month:02d}")
    return {
        "quienes": sorted(({"usuario_id": k, "nombre": v}
                           for k, v in quienes.items()),
                          key=lambda x: x["nombre"].lower()),
        "meses": sorted(meses, reverse=True),
    }


def de_un_catalogo(db: Session, clave: str, idioma: str = "es",
                   limite: int = 20) -> dict:
    """Lo ultimo que le paso a un catalogo, para la pantalla de Catalogos.
    Con cuantos cambios lleva en total: cero quiere decir que nadie lo ha
    tocado desde que se cargo."""
    objetos = DE_CADA_CATALOGO.get(clave)
    if not objetos:
        return {"clave": clave, "total": 0, "filas": []}
    consulta = _consulta(db, objetos=objetos)
    filas = consulta.limit(limite).all()
    nombres = _Nombres(db, filas)
    return {"clave": clave, "total": consulta.count(),
            "filas": [renglon(r, idioma, nombres) for r in filas]}


def excel_de(db: Session, que=None, quien=None, mes=None,
             idioma: str = "es") -> tuple[bytes, str]:
    """Lo filtrado completo, en una hoja: lo que dice la pantalla y, a su
    lado, lo que se escribio tal cual --para quien audita--."""
    t = _t(idioma)
    filas = _consulta(db, que, quien, mes).limit(TOPE_EXCEL).all()
    nombres = _Nombres(db, filas)
    renglones = []
    for r in filas:
        x = renglon(r, idioma, nombres)
        renglones.append([r.creado_en, x["quien"], x["rol_texto"], x["donde"],
                          x["que"], r.accion, r.antes, r.despues, r.detalle])
    tipos = ("momento", "texto", "texto", "texto", "texto", "texto", "texto",
             "texto", "texto")
    anchos = (17, 24, 18, 22, 60, 22, 30, 30, 30)
    contenido = excel.libro([{
        "nombre": t["excel"]["hoja"],
        "columnas": list(zip(t["excel"]["columnas"], tipos, anchos)),
        "filas": renglones,
    }])
    sufijo = mes or datetime.now().strftime("%Y%m%d")
    return contenido, f"{t['excel']['archivo']}_{sufijo}.xlsx"
