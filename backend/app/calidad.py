# -*- coding: utf-8 -*-
"""Calidad: el mes en cifras (seccion 89).

Cuarto paso de lo aprobado el 27 de septiembre: la pantalla de Calidad
del puesto de administracion del sistema y calidad. Como salio el
servicio en el mes --lo que dijo el cliente, lo que paso en la calle,
como se cerro, la gente y los datos--, y de cada cifra al detalle.

No se captura nada nuevo. Cada cifra sale de lo que el sistema ya
registra, y cada una se mide con la misma regla que ya existe donde la
hay: la puntualidad y el reporte completo, con las del bono; el cierre en
24 horas, con el plazo que decide la comision; el dinero comprobado a
tiempo, con el bolson del personal. Una cifra que aqui dijera otra cosa
que el bono seria una discusion en cada junta.

El mes en curso va al dia de hoy; los anteriores, cada uno contra el mes
de antes. La ven sistema y calidad, direccion de operaciones y direccion
general (`calidad.ver`); los consultores no, porque compara a unos con
otros. Mide, no juzga: clasificar una calificacion o una incidencia
sigue siendo del consultor, con el visto bueno de operaciones.

Las frases se arman aqui y no en la pantalla, en el idioma de quien lee:
el reporte en Excel dice lo mismo que la pantalla, y dos copias de la
misma frase se separan.
"""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import excel, reloj
from app import models as m

UMBRAL_MALA = 3              # como en app.encuestas: de 3 para abajo
DIAS_POR_VENCER = 30         # como el aviso del certificado
MESES_ATRAS = 24             # lo que se ofrece para escoger

# Lo planeado no es contingencia: unas vacaciones, un descanso o el
# mantenimiento que ya estaba en el calendario.
PLANEADOS = {m.MotivoCambio.VACACIONES, m.MotivoCambio.DESCANSO,
             m.MotivoCambio.MANTENIMIENTO_PREVENTIVO}
REQUERIDOS = {m.TipoHito.LLEGADA_ORIGEN, m.TipoHito.CONTACTO_EJECUTIVO,
              m.TipoHito.FIN_SERVICIO}
SIN_VISTO_BUENO = (m.EstatusCierre.ABIERTO, m.EstatusCierre.SIN_VISTO_BUENO,
                   m.EstatusCierre.EN_REVISION_IA)

# ------------------------------------------------------------- los textos

MESES = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
}
CORTOS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
           "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec"],
    "pt": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
           "out", "nov", "dez"],
}

TEXTOS = {
    "es": {
        "al_dia": "{mes} · al día de hoy",
        "vs": "{flecha} {mes}: {valor}",
        "sin_datos": "sin datos",
        "principales": "Las cifras del mes",
        "arriba": {
            "satisfaccion": "Satisfacción del cliente, de 5",
            "puntualidad": "Puntualidad · {a} de {b} jornadas",
            "reporte": "Jornadas con su reporte completo · {a} de {b}",
            "cierres": "Cierres en 24 horas · {a} de {b}",
            "bajas": "Calificaciones de 3 o menos",
        },
        "sin_revisar": ("{n} sin revisar", "{n} sin revisar"),
        "todas_revisadas": "todas revisadas",
        "bloques": {"cliente": "Lo que dijo el cliente", "calle": "En la calle",
                    "cierre": "El cierre", "gente": "La gente",
                    "datos": "Los datos"},
        "contestaron": "Contestaron la encuesta",
        "de": "{a} de {b}",
        "vencidas": ("{n} se venció sin contestar", "{n} se vencieron sin contestar"),
        "esperando": ("{n} sigue esperando", "{n} siguen esperando"),
        "bajas": "Calificación de 3 o menos",
        "fue_incidencia": ("{n} fue incidencia", "{n} fueron incidencia"),
        "no_castiga": ("{n} no castiga", "{n} no castigan"),
        "solicitantes": "Los solicitantes califican al consultor",
        "respuestas": ("{n} respuesta", "{n} respuestas"),
        "bajas_de": ("{n} de 3 o menos", "{n} de 3 o menos"),
        "lejos": "Marcas intentadas lejos del punto",
        "personas": ("{n} persona", "{n} personas"),
        "cuantas": "{nombre}, {n}",
        "por_validar": "Marcas esperando a la central",
        "las_valida": "las valida el supervisor de la central",
        "relevos": "Relevos por contingencia",
        "de_personal": ("{n} de personal", "{n} de personal"),
        "de_unidad": ("{n} de unidad", "{n} de unidad"),
        "unidades": "Unidades entregadas sin revisión",
        "con_dano": ("{n} volvió con daño nuevo", "{n} volvieron con daño nuevo"),
        "tarde": "Cerrados después de las 24 horas",
        "regresados": "Regresados por finanzas",
        "viaticos": "Viáticos comprobados a tiempo",
        "por_el_personal": "{a} de {b} · por el personal, en sus 24 horas",
        "incidencias": "Incidencias autorizadas",
        "leves": ("{n} leve", "{n} leves"),
        "graves": ("{n} grave", "{n} graves"),
        "menores": ("{n} error menor", "{n} errores menores"),
        "por_autorizar": ("{n} por autorizar", "{n} por autorizar"),
        "ninguna": "ninguna",
        "certificados": "Certificados vencidos",
        "trabajando": "personas trabajando con su curso vencido",
        "vencen": ("{n} vence en 30 días", "{n} vencen en 30 días"),
        "sin_padron": "Odoo todavía no manda los cursos",
        "bono": "Bono completo en {mes}",
        "de_personas": "{a} de {b} personas",
        "sin_bono": "el de {mes} todavía no se calcula",
        "anulados": ("{n} sin bono por incidencia", "{n} sin bono por incidencia"),
        "profesionalismo": "Profesionalismo",
        "promedio": ("promedio de {n} persona, de 100",
                     "promedio de {n} personas, de 100"),
        "pocos_datos": ("{n} sin datos suficientes", "{n} sin datos suficientes"),
        "al_dia_solo": "se mide al día: se ve en el mes en curso",
        "odoo": "En Odoo · se corrige allá",
        "en_catalogos": "En Catálogos · se corrige aquí",
        "sin_foto": ("{n} persona de seguridad sin foto: la hoja del servicio sale sin su cara",
                     "{n} personas de seguridad sin foto: la hoja del servicio sale sin su cara"),
        "sin_celular": ("{n} persona de seguridad sin celular",
                        "{n} personas de seguridad sin celular"),
        "sin_rfc": ("{n} cliente sin RFC", "{n} clientes sin RFC"),
        "sin_fiscal": ("{n} cliente sin identificación fiscal",
                       "{n} clientes sin identificación fiscal"),
        "gps": ("{n} unidad del GPS no liga con la flota: su placa falta o no coincide en Odoo",
                "{n} unidades del GPS no ligan con la flota: su placa falta o no coincide en Odoo"),
        "festivos": "No hay días festivos de {anio}",
        "combustible_falta": "No hay precio del combustible",
        "combustible_ejemplo": "El combustible sigue en el de ejemplo: {precio} por litro desde el {fecha}",
        "hoteles": ("{n} hotel sin ubicación", "{n} hoteles sin ubicación"),
        "hospitales": "{ciudades}: sin hospitales",
        "tabulador": "No hay tabulador de viáticos",
        "modalidades": "Faltan las horas de alguna modalidad",
        "pesos": "Los pesos del profesionalismo son los de ejemplo",
        "fotos_categoria": ("{n} categoría de unidad sin foto",
                            "{n} categorías de unidad sin foto"),
        "nada": "Nada pendiente.",
        "col": {"dia": "Día", "servicio": "Servicio", "persona": "Persona",
                "que": "Qué pasó", "calificacion": "Calificación",
                "estado": "Revisión", "consultor": "Consultor",
                "limite": "Límite", "visto_bueno": "Visto bueno",
                "motivo": "Motivo", "plazo": "Plazo", "curso": "Curso",
                "vencio": "Venció", "dias": "Días trabajados",
                "gravedad": "Gravedad", "unidad": "Unidad",
                "marca": "Marca", "cuando": "Cuándo", "tipo": "Tipo"},
        "estado": {"incidencia": "fue incidencia", "no_castiga": "no castiga",
                   "sin_revisar": "sin revisar"},
        "marca": {"llegada_origen": "llegada", "contacto_ejecutivo": "contacto",
                  "llegada_destino": "llegada al destino",
                  "salida_ruta": "salida a ruta", "standby": "en espera",
                  "fin_servicio": "fin"},
        "tipo_recurso": {"personal": "personal", "vehiculo": "unidad"},
        "motivo": {"vacaciones": "vacaciones", "enfermedad": "enfermedad",
                   "descanso": "descanso", "contingencia": "contingencia",
                   "baja": "baja", "mantenimiento_preventivo": "mantenimiento preventivo",
                   "mantenimiento_correctivo": "mantenimiento correctivo",
                   "otro": "otro"},
        "sin_motivo": "contingencia",
        "entrega_sin": "sin revisión al recibirla",
        "volvio_danada": "volvió con daño nuevo",
        "sin_vb": "sin visto bueno",
        "con_descuento": "se cerró con descuento",
        "no_termino": "no terminó de comprobar",
        "termino": "terminó {cuando}",
        "gravedad": {"error_menor": "error menor", "leve": "leve", "grave": "grave"},
        "inc_estado": {"autorizada": "autorizada", "descartada": "descartada",
                       "pendiente": "por autorizar"},
        "excel": {"archivo": "calidad", "resumen": "Resumen",
                  "columnas": ["Sección", "Cifra", "{mes}", "{anterior}", "Detalle"],
                  "hojas": {"bajas": "Calificaciones bajas", "lejos": "Marcas lejos",
                            "por_validar": "Marcas por validar",
                            "relevos": "Relevos", "unidades": "Unidades",
                            "tarde": "Cierres tarde", "regresados": "Regresos",
                            "viaticos": "Viáticos tarde",
                            "incidencias": "Incidencias",
                            "certificados": "Certificados", "datos": "Los datos"},
                  "donde": "Dónde", "que_falta": "Qué falta",
                  "cuales": "Cuáles"},
    },
    "en": {
        "al_dia": "{mes} · to date",
        "vs": "{flecha} {mes}: {valor}",
        "sin_datos": "no data",
        "principales": "The month's figures",
        "arriba": {
            "satisfaccion": "Client satisfaction, out of 5",
            "puntualidad": "Punctuality · {a} of {b} days",
            "reporte": "Days with a complete report · {a} of {b}",
            "cierres": "Closed within 24 hours · {a} of {b}",
            "bajas": "Ratings of 3 or less",
        },
        "sin_revisar": ("{n} not reviewed", "{n} not reviewed"),
        "todas_revisadas": "all reviewed",
        "bloques": {"cliente": "What the client said", "calle": "In the field",
                    "cierre": "Closing", "gente": "The people",
                    "datos": "The data"},
        "contestaron": "Answered the survey",
        "de": "{a} of {b}",
        "vencidas": ("{n} expired unanswered", "{n} expired unanswered"),
        "esperando": ("{n} still waiting", "{n} still waiting"),
        "bajas": "Rated 3 or less",
        "fue_incidencia": ("{n} became an incident", "{n} became incidents"),
        "no_castiga": ("{n} no penalty", "{n} no penalty"),
        "solicitantes": "Requesters rate the consultant",
        "respuestas": ("{n} answer", "{n} answers"),
        "bajas_de": ("{n} rated 3 or less", "{n} rated 3 or less"),
        "lejos": "Marks attempted away from the point",
        "personas": ("{n} person", "{n} people"),
        "cuantas": "{nombre}, {n}",
        "por_validar": "Marks waiting for the control center",
        "las_valida": "the control center supervisor validates them",
        "relevos": "Contingency replacements",
        "de_personal": ("{n} of staff", "{n} of staff"),
        "de_unidad": ("{n} of vehicle", "{n} of vehicles"),
        "unidades": "Vehicles handed over without inspection",
        "con_dano": ("{n} came back with new damage", "{n} came back with new damage"),
        "tarde": "Closed after 24 hours",
        "regresados": "Returned by finance",
        "viaticos": "Expenses accounted for on time",
        "por_el_personal": "{a} of {b} · by the staff, within their 24 hours",
        "incidencias": "Authorized incidents",
        "leves": ("{n} minor", "{n} minor"),
        "graves": ("{n} serious", "{n} serious"),
        "menores": ("{n} small error", "{n} small errors"),
        "por_autorizar": ("{n} pending approval", "{n} pending approval"),
        "ninguna": "none",
        "certificados": "Expired certificates",
        "trabajando": "people working with an expired course",
        "vencen": ("{n} expires within 30 days", "{n} expire within 30 days"),
        "sin_padron": "Odoo doesn't send the courses yet",
        "bono": "Full bonus in {mes}",
        "de_personas": "{a} of {b} people",
        "sin_bono": "{mes} isn't calculated yet",
        "anulados": ("{n} without bonus due to an incident",
                     "{n} without bonus due to an incident"),
        "profesionalismo": "Professionalism",
        "promedio": ("average of {n} person, out of 100",
                     "average of {n} people, out of 100"),
        "pocos_datos": ("{n} without enough data", "{n} without enough data"),
        "al_dia_solo": "measured as of today: shown in the current month",
        "odoo": "In Odoo · fixed there",
        "en_catalogos": "In Catalogs · fixed here",
        "sin_foto": ("{n} security staff member without a photo: the service sheet goes out without their face",
                     "{n} security staff without a photo: the service sheet goes out without their face"),
        "sin_celular": ("{n} security staff member without a cell phone",
                        "{n} security staff without a cell phone"),
        "sin_rfc": ("{n} client without RFC", "{n} clients without RFC"),
        "sin_fiscal": ("{n} client without a tax ID", "{n} clients without a tax ID"),
        "gps": ("{n} GPS vehicle doesn't match the fleet: its plate is missing or different in Odoo",
                "{n} GPS vehicles don't match the fleet: their plate is missing or different in Odoo"),
        "festivos": "No holidays for {anio}",
        "combustible_falta": "No fuel price",
        "combustible_ejemplo": "Fuel is still the sample price: {precio} per liter since {fecha}",
        "hoteles": ("{n} hotel without a location", "{n} hotels without a location"),
        "hospitales": "{ciudades}: no hospitals",
        "tabulador": "No travel expense table",
        "modalidades": "Some modality is missing its hours",
        "pesos": "The professionalism weights are the sample ones",
        "fotos_categoria": ("{n} vehicle category without a photo",
                            "{n} vehicle categories without a photo"),
        "nada": "Nothing pending.",
        "col": {"dia": "Day", "servicio": "Service", "persona": "Person",
                "que": "What happened", "calificacion": "Rating",
                "estado": "Review", "consultor": "Consultant",
                "limite": "Deadline", "visto_bueno": "Sign-off",
                "motivo": "Reason", "plazo": "Deadline", "curso": "Course",
                "vencio": "Expired", "dias": "Days worked",
                "gravedad": "Severity", "unidad": "Vehicle",
                "marca": "Mark", "cuando": "When", "tipo": "Type"},
        "estado": {"incidencia": "became an incident", "no_castiga": "no penalty",
                   "sin_revisar": "not reviewed"},
        "marca": {"llegada_origen": "arrival", "contacto_ejecutivo": "contact",
                  "llegada_destino": "arrival at destination",
                  "salida_ruta": "departure", "standby": "standby",
                  "fin_servicio": "end"},
        "tipo_recurso": {"personal": "staff", "vehiculo": "vehicle"},
        "motivo": {"vacaciones": "vacation", "enfermedad": "illness",
                   "descanso": "day off", "contingencia": "contingency",
                   "baja": "left the company",
                   "mantenimiento_preventivo": "preventive maintenance",
                   "mantenimiento_correctivo": "corrective maintenance",
                   "otro": "other"},
        "sin_motivo": "contingency",
        "entrega_sin": "no inspection when received",
        "volvio_danada": "came back with new damage",
        "sin_vb": "no sign-off",
        "con_descuento": "closed with a deduction",
        "no_termino": "didn't finish accounting",
        "termino": "finished {cuando}",
        "gravedad": {"error_menor": "small error", "leve": "minor", "grave": "serious"},
        "inc_estado": {"autorizada": "authorized", "descartada": "dismissed",
                       "pendiente": "pending approval"},
        "excel": {"archivo": "quality", "resumen": "Summary",
                  "columnas": ["Section", "Figure", "{mes}", "{anterior}", "Detail"],
                  "hojas": {"bajas": "Low ratings", "lejos": "Marks away",
                            "por_validar": "Marks to validate",
                            "relevos": "Replacements", "unidades": "Vehicles",
                            "tarde": "Late closings", "regresados": "Returns",
                            "viaticos": "Late expenses",
                            "incidencias": "Incidents",
                            "certificados": "Certificates", "datos": "The data"},
                  "donde": "Where", "que_falta": "What's missing",
                  "cuales": "Which"},
    },
    "pt": {
        "al_dia": "{mes} · até hoje",
        "vs": "{flecha} {mes}: {valor}",
        "sin_datos": "sem dados",
        "principales": "Os números do mês",
        "arriba": {
            "satisfaccion": "Satisfação do cliente, de 5",
            "puntualidad": "Pontualidade · {a} de {b} jornadas",
            "reporte": "Jornadas com relatório completo · {a} de {b}",
            "cierres": "Fechamentos em 24 horas · {a} de {b}",
            "bajas": "Avaliações de 3 ou menos",
        },
        "sin_revisar": ("{n} sem revisar", "{n} sem revisar"),
        "todas_revisadas": "todas revisadas",
        "bloques": {"cliente": "O que o cliente disse", "calle": "Na rua",
                    "cierre": "O fechamento", "gente": "As pessoas",
                    "datos": "Os dados"},
        "contestaron": "Responderam a pesquisa",
        "de": "{a} de {b}",
        "vencidas": ("{n} venceu sem resposta", "{n} venceram sem resposta"),
        "esperando": ("{n} ainda aguardando", "{n} ainda aguardando"),
        "bajas": "Avaliação de 3 ou menos",
        "fue_incidencia": ("{n} virou ocorrência", "{n} viraram ocorrência"),
        "no_castiga": ("{n} sem penalidade", "{n} sem penalidade"),
        "solicitantes": "Os solicitantes avaliam o consultor",
        "respuestas": ("{n} resposta", "{n} respostas"),
        "bajas_de": ("{n} de 3 ou menos", "{n} de 3 ou menos"),
        "lejos": "Marcações tentadas longe do ponto",
        "personas": ("{n} pessoa", "{n} pessoas"),
        "cuantas": "{nombre}, {n}",
        "por_validar": "Marcações aguardando a central",
        "las_valida": "o supervisor da central as valida",
        "relevos": "Substituições por contingência",
        "de_personal": ("{n} de pessoal", "{n} de pessoal"),
        "de_unidad": ("{n} de veículo", "{n} de veículos"),
        "unidades": "Veículos entregues sem vistoria",
        "con_dano": ("{n} voltou com dano novo", "{n} voltaram com dano novo"),
        "tarde": "Fechados depois de 24 horas",
        "regresados": "Devolvidos pelo financeiro",
        "viaticos": "Diárias comprovadas no prazo",
        "por_el_personal": "{a} de {b} · pelo pessoal, nas suas 24 horas",
        "incidencias": "Ocorrências autorizadas",
        "leves": ("{n} leve", "{n} leves"),
        "graves": ("{n} grave", "{n} graves"),
        "menores": ("{n} erro menor", "{n} erros menores"),
        "por_autorizar": ("{n} por autorizar", "{n} por autorizar"),
        "ninguna": "nenhuma",
        "certificados": "Certificados vencidos",
        "trabajando": "pessoas trabalhando com o curso vencido",
        "vencen": ("{n} vence em 30 dias", "{n} vencem em 30 dias"),
        "sin_padron": "O Odoo ainda não envia os cursos",
        "bono": "Bônus completo em {mes}",
        "de_personas": "{a} de {b} pessoas",
        "sin_bono": "o de {mes} ainda não foi calculado",
        "anulados": ("{n} sem bônus por ocorrência", "{n} sem bônus por ocorrência"),
        "profesionalismo": "Profissionalismo",
        "promedio": ("média de {n} pessoa, de 100", "média de {n} pessoas, de 100"),
        "pocos_datos": ("{n} sem dados suficientes", "{n} sem dados suficientes"),
        "al_dia_solo": "medido no dia: aparece no mês em curso",
        "odoo": "No Odoo · corrige-se lá",
        "en_catalogos": "Em Catálogos · corrige-se aqui",
        "sin_foto": ("{n} pessoa de segurança sem foto: a ficha do serviço sai sem o rosto",
                     "{n} pessoas de segurança sem foto: a ficha do serviço sai sem o rosto"),
        "sin_celular": ("{n} pessoa de segurança sem celular",
                        "{n} pessoas de segurança sem celular"),
        "sin_rfc": ("{n} cliente sem RFC", "{n} clientes sem RFC"),
        "sin_fiscal": ("{n} cliente sem identificação fiscal",
                       "{n} clientes sem identificação fiscal"),
        "gps": ("{n} veículo do GPS não liga com a frota: a placa falta ou não coincide no Odoo",
                "{n} veículos do GPS não ligam com a frota: a placa falta ou não coincide no Odoo"),
        "festivos": "Não há feriados de {anio}",
        "combustible_falta": "Não há preço do combustível",
        "combustible_ejemplo": "O combustível continua no de exemplo: {precio} por litro desde {fecha}",
        "hoteles": ("{n} hotel sem localização", "{n} hotéis sem localização"),
        "hospitales": "{ciudades}: sem hospitais",
        "tabulador": "Não há tabela de diárias",
        "modalidades": "Faltam as horas de alguma modalidade",
        "pesos": "Os pesos do profissionalismo são os de exemplo",
        "fotos_categoria": ("{n} categoria de veículo sem foto",
                            "{n} categorias de veículo sem foto"),
        "nada": "Nada pendente.",
        "col": {"dia": "Dia", "servicio": "Serviço", "persona": "Pessoa",
                "que": "O que aconteceu", "calificacion": "Avaliação",
                "estado": "Revisão", "consultor": "Consultor",
                "limite": "Limite", "visto_bueno": "Visto",
                "motivo": "Motivo", "plazo": "Prazo", "curso": "Curso",
                "vencio": "Venceu", "dias": "Dias trabalhados",
                "gravedad": "Gravidade", "unidad": "Veículo",
                "marca": "Marcação", "cuando": "Quando", "tipo": "Tipo"},
        "estado": {"incidencia": "virou ocorrência", "no_castiga": "sem penalidade",
                   "sin_revisar": "sem revisar"},
        "marca": {"llegada_origen": "chegada", "contacto_ejecutivo": "contato",
                  "llegada_destino": "chegada ao destino",
                  "salida_ruta": "saída", "standby": "em espera",
                  "fin_servicio": "fim"},
        "tipo_recurso": {"personal": "pessoal", "vehiculo": "veículo"},
        "motivo": {"vacaciones": "férias", "enfermedad": "doença",
                   "descanso": "folga", "contingencia": "contingência",
                   "baja": "desligamento",
                   "mantenimiento_preventivo": "manutenção preventiva",
                   "mantenimiento_correctivo": "manutenção corretiva",
                   "otro": "outro"},
        "sin_motivo": "contingência",
        "entrega_sin": "sem vistoria ao receber",
        "volvio_danada": "voltou com dano novo",
        "sin_vb": "sem visto",
        "con_descuento": "fechado com desconto",
        "no_termino": "não terminou de comprovar",
        "termino": "terminou {cuando}",
        "gravedad": {"error_menor": "erro menor", "leve": "leve", "grave": "grave"},
        "inc_estado": {"autorizada": "autorizada", "descartada": "descartada",
                       "pendiente": "por autorizar"},
        "excel": {"archivo": "qualidade", "resumen": "Resumo",
                  "columnas": ["Seção", "Número", "{mes}", "{anterior}", "Detalhe"],
                  "hojas": {"bajas": "Avaliações baixas", "lejos": "Marcações longe",
                            "por_validar": "Marcações a validar",
                            "relevos": "Substituições", "unidades": "Veículos",
                            "tarde": "Fechamentos tarde", "regresados": "Devoluções",
                            "viaticos": "Diárias tarde",
                            "incidencias": "Ocorrências",
                            "certificados": "Certificados", "datos": "Os dados"},
                  "donde": "Onde", "que_falta": "O que falta",
                  "cuales": "Quais"},
    },
}


def _t(idioma: str | None) -> dict:
    return TEXTOS.get((idioma or "es")[:2], TEXTOS["es"])


def _idioma(idioma: str | None) -> str:
    clave = (idioma or "es")[:2]
    return clave if clave in TEXTOS else "es"


def _n(par: tuple, n: int) -> str:
    """Singular o plural, con el numero puesto."""
    return (par[0] if n == 1 else par[1]).replace("{n}", str(n))


def _decimal(valor, idioma: str, digitos: int = 1) -> str:
    q = Decimal(1).scaleb(-digitos)
    texto = str(Decimal(str(valor)).quantize(q, rounding=ROUND_HALF_UP))
    return texto.replace(".", ",") if idioma == "pt" else texto


def _pct(valor, idioma: str) -> str:
    entero = int(Decimal(str(valor)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return f"{entero}%" if idioma == "en" else f"{entero} %"


def nombre_del_mes(anio: int, mes: int, idioma: str, con_anio=True) -> str:
    nombre = MESES[_idioma(idioma)][mes - 1]
    return f"{nombre} {anio}" if con_anio else nombre


def _dia(d: date | None, idioma: str) -> str:
    if d is None:
        return "—"
    corto = CORTOS[_idioma(idioma)][d.month - 1]
    return f"{corto} {d.day}" if idioma == "en" else f"{d.day} {corto}"


def _momento(x: datetime | None, idioma: str) -> str:
    if x is None:
        return "—"
    return f"{_dia(x.date(), idioma)} {x:%H:%M}"


def _largo(d: date, idioma: str) -> str:
    """"1 de enero", "January 1"."""
    mes = MESES[_idioma(idioma)][d.month - 1]
    if idioma == "en":
        return f"{mes} {d.day}"
    return f"{d.day} de {mes}"


SIMBOLO = {"MXN": "$", "BRL": "R$ ", "USD": "US$ ", "VES": "Bs. "}


def _dinero(monto, moneda) -> str:
    codigo = getattr(moneda, "value", moneda) or "MXN"
    return f"{SIMBOLO.get(str(codigo).upper(), '$')}{Decimal(str(monto)):,.2f}"


# ---------------------------------------------------------------- el mes

@dataclass
class Periodo:
    anio: int
    mes: int
    desde: date            # el primer dia
    hasta: date            # el ultimo
    inicio: datetime       # hora de pared del pais: las columnas naive
    fin: datetime          # el primer instante del mes que sigue
    inicio_z: datetime     # con zona: las columnas que guardan instantes
    fin_z: datetime
    ahora: datetime        # hora de pared del pais
    hoy: date
    en_curso: bool


def periodo(pais: m.Pais | None, anio: int, mes: int,
            ahora: datetime | None = None) -> Periodo:
    ultimo = calendar.monthrange(anio, mes)[1]
    desde, hasta = date(anio, mes, 1), date(anio, mes, ultimo)
    inicio = datetime.combine(desde, time.min)
    fin = datetime.combine(hasta + timedelta(days=1), time.min)
    zona = reloj.zona(getattr(pais, "zona_horaria", None))
    ahora_pais = reloj.ahora_en(pais, ahora)
    return Periodo(anio, mes, desde, hasta, inicio, fin,
                   inicio.replace(tzinfo=zona), fin.replace(tzinfo=zona),
                   ahora_pais, ahora_pais.date(),
                   desde <= ahora_pais.date() <= hasta)


def anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def _servidor(p: Periodo) -> datetime:
    """Las columnas que se escriben con `datetime.now()` del servidor --la
    encuesta vencida-- se comparan con la hora del servidor."""
    return datetime.now()


# ----------------------------------------------------------- lo de base

def _jornadas(db: Session, pais_id: int, p: Periodo) -> list[m.Jornada]:
    return (db.query(m.Jornada)
            .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
            .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
            .filter(m.Servicio.pais_id == pais_id,
                    m.Jornada.fecha >= p.desde, m.Jornada.fecha <= p.hasta,
                    m.Jornada.estatus != m.EstatusJornada.CANCELADA)
            .all())


def _hecha(j: m.Jornada, p: Periodo) -> bool:
    """Un dia que ya paso, o el de hoy si ya termino: lo que sigue
    corriendo no se juzga a medias."""
    return j.fecha < p.hoy or j.estatus == m.EstatusJornada.TERMINADA


def _servicio(j: m.Jornada) -> m.Servicio:
    return j.equipo.servicio


def _liga(s: m.Servicio) -> dict:
    return {"t": s.folio, "servicio": s.id,
            "implantado": s.tipo == m.TipoServicio.IMPLANTADO}


def _persona(persona: m.Persona | None) -> dict:
    if persona is None:
        return {"t": "—"}
    return {"t": persona.nombre, "persona": persona.id}


def _celda(texto) -> dict:
    return {"t": "—" if texto is None or texto == "" else str(texto)}


class _Contexto:
    """Lo que varias cifras del mismo mes necesitan: se trae una vez."""

    def __init__(self, db: Session, pais: m.Pais, p: Periodo):
        self.db, self.pais, self.p = db, pais, p
        self.jornadas = _jornadas(db, pais.id, p)
        self.ids = [j.id for j in self.jornadas]
        self.por_id = {j.id: j for j in self.jornadas}
        self._asignaciones = None
        self._hitos = None

    @property
    def asignaciones(self) -> list[m.AsignacionPersonal]:
        if self._asignaciones is None:
            self._asignaciones = (
                self.db.query(m.AsignacionPersonal)
                .filter(m.AsignacionPersonal.jornada_id.in_(self.ids)).all()
                if self.ids else [])
        return self._asignaciones

    @property
    def hitos(self) -> list[m.Hito]:
        if self._hitos is None:
            self._hitos = (self.db.query(m.Hito)
                           .filter(m.Hito.jornada_id.in_(self.ids)).all()
                           if self.ids else [])
        return self._hitos

    def dias_de_la_gente(self) -> list[tuple[m.Jornada, int]]:
        """Cada persona en cada dia que ya paso, como los mide el bono: el
        dia en que alguien entro a media jornada, relevando a otro, es de
        quien lo empezo (`bonos.jornadas_del_mes`)."""
        entro_a_media = {(a.jornada_id, a.relevado_por_id)
                         for a in self.asignaciones
                         if a.relevado_en is not None and a.relevado_por_id}
        vistos, pares = set(), []
        for a in self.asignaciones:
            j = self.por_id.get(a.jornada_id)
            clave = (a.jornada_id, a.persona_id)
            if (j is None or not _hecha(j, self.p) or clave in vistos
                    or clave in entro_a_media):
                continue
            vistos.add(clave)
            pares.append((j, a.persona_id))
        return pares


# ------------------------------------------------ lo que dijo el cliente

def _encuestas(db: Session, pais_id: int, p: Periodo, tipo) -> list[m.Encuesta]:
    return (db.query(m.Encuesta)
            .join(m.Servicio, m.Encuesta.servicio_id == m.Servicio.id)
            .filter(m.Servicio.pais_id == pais_id,
                    m.Servicio.estatus != m.EstatusServicio.CANCELADO,
                    m.Encuesta.tipo == tipo,
                    m.Encuesta.enviada_en >= p.inicio_z,
                    m.Encuesta.enviada_en < p.fin_z)
            .order_by(m.Encuesta.enviada_en).all())


def _vencida(e: m.Encuesta, ahora_servidor: datetime) -> bool:
    # La tarea que las vence corre a las 8:00; la que ya paso su fecha
    # esta vencida aunque la tarea no haya pasado todavia.
    return (e.estatus == m.EstatusEncuesta.EXPIRADA
            or (e.estatus == m.EstatusEncuesta.ENVIADA and e.expira_en is not None
                and e.expira_en <= ahora_servidor))


def _promedio(valores: list) -> Decimal | None:
    if not valores:
        return None
    return Decimal(sum(valores)) / Decimal(len(valores))


def satisfaccion(db: Session, pais_id: int, p: Periodo) -> dict:
    """La del ejecutivo, que califica el servicio y al equipo. La del
    solicitante califica al consultor y va aparte."""
    ejecutivo = _encuestas(db, pais_id, p, m.TipoEncuesta.EJECUTIVO)
    calificadas = [e for e in ejecutivo if e.estatus == m.EstatusEncuesta.RESPONDIDA
                   and e.calificacion is not None]
    return {"encuestas": ejecutivo, "calificadas": calificadas,
            "promedio": _promedio([e.calificacion for e in calificadas])}


def _estado_de_la_baja(e: m.Encuesta) -> str:
    if e.clasificada_en is None:
        return "sin_revisar"
    return "incidencia" if e.incidencia_id else "no_castiga"


def lo_que_dijo_el_cliente(db: Session, pais: m.Pais, p: Periodo,
                           idioma: str) -> tuple[dict, list, dict]:
    t = _t(idioma)
    pais_id = pais.id
    s = satisfaccion(db, pais_id, p)
    ejecutivo, calificadas = s["encuestas"], s["calificadas"]
    ahora_servidor = _servidor(p)
    vencidas = [e for e in ejecutivo if _vencida(e, ahora_servidor)]
    esperando = [e for e in ejecutivo if e.estatus == m.EstatusEncuesta.ENVIADA
                 and e not in vencidas]
    bajas = [e for e in calificadas if e.calificacion <= UMBRAL_MALA]
    estados = {"incidencia": 0, "no_castiga": 0, "sin_revisar": 0}
    for e in bajas:
        estados[_estado_de_la_baja(e)] += 1

    solicitante = _encuestas(db, pais_id, p, m.TipoEncuesta.SOLICITANTE)
    del_solicitante = [e.calificacion for e in solicitante
                       if e.estatus == m.EstatusEncuesta.RESPONDIDA
                       and e.calificacion is not None]
    prom_sol = _promedio(del_solicitante)

    nota_contestaron = []
    if vencidas:
        nota_contestaron.append({"t": _n(t["vencidas"], len(vencidas))})
    if esperando:
        nota_contestaron.append({"t": _n(t["esperando"], len(esperando))})

    nota_bajas = []
    if estados["incidencia"]:
        nota_bajas.append({"t": _n(t["fue_incidencia"], estados["incidencia"])})
    if estados["no_castiga"]:
        nota_bajas.append({"t": _n(t["no_castiga"], estados["no_castiga"])})
    if estados["sin_revisar"]:
        nota_bajas.append({"t": _n(t["sin_revisar"], estados["sin_revisar"]),
                           "tono": "ambar"})

    detalle_bajas = {
        "columnas": [t["col"]["dia"], t["col"]["servicio"],
                     t["col"]["calificacion"], t["col"]["estado"],
                     t["col"]["motivo"]],
        "filas": [[_celda(_dia(reloj.ahora_en(pais, e.enviada_en).date()
                                if e.enviada_en else None, idioma)),
                   _liga(e.servicio),
                   _celda(str(e.calificacion)),
                   _celda(t["estado"][_estado_de_la_baja(e)]),
                   _celda(e.nota_clasificacion)]
                  for e in bajas],
    }

    nota_sol = [{"t": _n(t["respuestas"], len(del_solicitante))}]
    bajas_sol = sum(1 for c in del_solicitante if c <= UMBRAL_MALA)
    if bajas_sol:
        nota_sol.append({"t": _n(t["bajas_de"], bajas_sol), "tono": "ambar"})

    bloque = {"clave": "cliente", "titulo": t["bloques"]["cliente"],
              "ir": "encuestas",
              "renglones": [
                  {"clave": "contestaron", "texto": t["contestaron"],
                   "valor": t["de"].replace("{a}", str(len(calificadas)))
                                  .replace("{b}", str(len(ejecutivo))),
                   "nota": nota_contestaron},
                  {"clave": "bajas", "texto": t["bajas"],
                   "valor": str(len(bajas)), "nota": nota_bajas,
                   "ver": detalle_bajas if bajas else None},
                  {"clave": "solicitantes", "texto": t["solicitantes"],
                   "valor": (_decimal(prom_sol, idioma) if prom_sol is not None
                             else "—"),
                   "nota": nota_sol if del_solicitante else
                   [{"t": t["sin_datos"]}]},
              ]}
    cifras = {"bajas": len(bajas), "sin_revisar": estados["sin_revisar"],
              "satisfaccion": s["promedio"],
              "contestaron": (len(calificadas), len(ejecutivo)),
              "vencidas": len(vencidas),
              "solicitante": prom_sol, "respuestas_solicitante": len(del_solicitante)}
    return bloque, [("bajas", detalle_bajas)], cifras


# --------------------------------------------------------------- la calle

def puntualidad_y_reporte(ctx: _Contexto) -> dict:
    """Las dos reglas del bono, dia por dia (`bonos.medir_puntualidad` y
    `bonos.medir_seguimiento`), sin el margen del mes: el margen es un
    perdon del bono, y aqui se mide.

    A tiempo es haber marcado la llegada dentro del punto y no despues de
    la hora citada. El dia cuya llegada asento la central a mano no se
    mide --no hay como probar la hora--. Completo es traer llegada,
    contacto y fin, sin alertas de silencio."""
    llegadas: dict[tuple, m.Hito] = {}
    tipos: dict[tuple, set] = {}
    for h in ctx.hitos:
        if h.anulado_en is not None:
            continue
        clave = (h.jornada_id, h.persona_id)
        tipos.setdefault(clave, set()).add(h.tipo)
        if h.tipo == m.TipoHito.LLEGADA_ORIGEN:
            otra = llegadas.get(clave)
            if otra is None or (h.marcado_en and otra.marcado_en
                                and h.marcado_en < otra.marcado_en):
                llegadas[clave] = h
    silencios = {}
    if ctx.ids:
        for jornada_id, n in (ctx.db.query(m.Alerta.jornada_id, func.count())
                              .filter(m.Alerta.jornada_id.in_(ctx.ids),
                                      m.Alerta.tipo == m.TipoAlerta.SIN_REPORTE)
                              .group_by(m.Alerta.jornada_id).all()):
            silencios[jornada_id] = n

    a_tiempo = medidos = completos = dias = 0
    for j, persona_id in ctx.dias_de_la_gente():
        clave = (j.id, persona_id)
        dias += 1
        if REQUERIDOS.issubset(tipos.get(clave, set())) and not silencios.get(j.id):
            completos += 1
        marca = llegadas.get(clave)
        if marca is not None and marca.registrado_a_mano_en is not None:
            continue
        medidos += 1
        momento = marca.marcado_en if marca is not None else j.inicio_real
        if momento is None or (marca is not None and marca.dentro_geocerca is False):
            continue
        if (momento - j.inicio_programado).total_seconds() <= 0:
            a_tiempo += 1
    return {"a_tiempo": a_tiempo, "medidos": medidos,
            "completos": completos, "dias": dias}


def en_la_calle(ctx: _Contexto, idioma: str) -> tuple[dict, list, dict]:
    t = _t(idioma)
    db, p = ctx.db, ctx.p

    # Una llegada marcada lejos del punto no se guarda: deja alerta. Lo que
    # se cuenta son los intentos (como en Panorama).
    lejos = (db.query(m.Alerta)
             .filter(m.Alerta.jornada_id.in_(ctx.ids),
                     m.Alerta.tipo == m.TipoAlerta.FUERA_DE_GEOCERCA)
             .order_by(m.Alerta.creada_en).all() if ctx.ids else [])
    por_persona: dict = {}
    for a in lejos:
        if a.persona_id:
            por_persona[a.persona_id] = por_persona.get(a.persona_id, 0) + 1
    nota_lejos = []
    if lejos:
        nota_lejos.append({"t": _n(t["personas"], len(por_persona))})
        if por_persona:
            quien, cuantas = max(por_persona.items(), key=lambda x: (x[1], -x[0]))
            persona = db.get(m.Persona, quien)
            nota_lejos.append({"t": t["cuantas"].replace("{nombre}", persona.nombre)
                                               .replace("{n}", str(cuantas))})
    detalle_lejos = {
        "columnas": [t["col"]["dia"], t["col"]["servicio"], t["col"]["persona"],
                     t["col"]["que"]],
        "filas": [[_celda(_dia(ctx.por_id[a.jornada_id].fecha, idioma)),
                   _liga(_servicio(ctx.por_id[a.jornada_id])),
                   _persona(a.persona), _celda(a.mensaje)] for a in lejos],
    }

    # Las marcas que la central tiene que validar: la llegada fuera de
    # hora, el reloj del telefono adelantado, la que llego tarde.
    por_validar = sorted((h for h in ctx.hitos
                          if h.requiere_revision and h.anulado_en is None),
                         key=lambda h: h.marcado_en or datetime.min)
    detalle_validar = {
        "columnas": [t["col"]["dia"], t["col"]["servicio"], t["col"]["persona"],
                     t["col"]["marca"], t["col"]["cuando"]],
        "filas": [[_celda(_dia(ctx.por_id[h.jornada_id].fecha, idioma)),
                   _liga(_servicio(ctx.por_id[h.jornada_id])),
                   _persona(db.get(m.Persona, h.persona_id)),
                   _celda(t["marca"].get(h.tipo.value, h.tipo.value)),
                   _celda(_momento(h.marcado_en, idioma))] for h in por_validar],
    }

    # Los relevos: los de la contingencia, no lo planeado.
    relevos = (db.query(m.ReemplazoRecurso)
               .filter(m.ReemplazoRecurso.desde_jornada_id.in_(ctx.ids))
               .all() if ctx.ids else [])
    relevos = [r for r in relevos if r.motivo_tipo not in PLANEADOS]
    viejos = (db.query(m.Reemplazo)
              .filter(m.Reemplazo.jornada_id.in_(ctx.ids),
                      m.Reemplazo.motivo != m.MotivoReemplazo.DESCANSO)
              .all() if ctx.ids else [])
    de_personal = (sum(1 for r in relevos if r.tipo == m.TipoRecurso.PERSONAL)
                   + len(viejos))
    de_unidad = sum(1 for r in relevos if r.tipo == m.TipoRecurso.VEHICULO)
    filas_relevos = []
    for r in sorted(relevos, key=lambda r: ctx.por_id[r.desde_jornada_id].fecha):
        j = ctx.por_id[r.desde_jornada_id]
        if r.tipo == m.TipoRecurso.PERSONAL:
            sale = db.get(m.Persona, r.sale_persona_id) if r.sale_persona_id else None
            entra = db.get(m.Persona, r.entra_persona_id) if r.entra_persona_id else None
            quien = f"{sale.nombre if sale else '—'} → {entra.nombre if entra else '—'}"
        else:
            sale = db.get(m.Vehiculo, r.sale_vehiculo_id) if r.sale_vehiculo_id else None
            entra = db.get(m.Vehiculo, r.entra_vehiculo_id) if r.entra_vehiculo_id else None
            quien = f"{sale.placa if sale else '—'} → {entra.placa if entra else '—'}"
        motivo = (t["motivo"].get(r.motivo_tipo.value, r.motivo_tipo.value)
                  if r.motivo_tipo else t["sin_motivo"])
        filas_relevos.append([_celda(_dia(j.fecha, idioma)), _liga(_servicio(j)),
                              _celda(t["tipo_recurso"][r.tipo.value]),
                              _celda(motivo), _celda(quien)])
    for r in viejos:
        j = ctx.por_id[r.jornada_id]
        filas_relevos.append([
            _celda(_dia(j.fecha, idioma)), _liga(_servicio(j)),
            _celda(t["tipo_recurso"]["personal"]),
            _celda(t["motivo"].get(r.motivo.value, r.motivo.value)),
            _celda(f"{r.sale.nombre} → {r.entra.nombre}")])
    detalle_relevos = {
        "columnas": [t["col"]["dia"], t["col"]["servicio"], t["col"]["tipo"],
                     t["col"]["motivo"], t["col"]["que"]],
        "filas": filas_relevos,
    }

    # Las unidades: la que se entrego al equipo sin su revision al
    # recibirla es un dano que despues no se le puede atribuir a nadie.
    en_la_calle_ya = [j for j in ctx.jornadas
                      if j.fecha < p.hoy or j.estatus in (
                          m.EstatusJornada.ARRIBADO, m.EstatusJornada.EN_CURSO,
                          m.EstatusJornada.TERMINADA)]
    pares: dict[tuple, m.Jornada] = {}
    for j in sorted(en_la_calle_ya, key=lambda j: j.fecha):
        for a in j.vehiculos:
            pares.setdefault((j.equipo.servicio_id, a.vehiculo_id), j)
    recibidas = set()
    if pares:
        servicios = {s for s, _ in pares}
        recibidas = {(r.servicio_id, r.vehiculo_id) for r in (
            db.query(m.RevisionUnidad)
            .filter(m.RevisionUnidad.servicio_id.in_(servicios),
                    m.RevisionUnidad.tipo == m.TipoRevision.RECIBE.value).all())}
    sin_revision = [(clave, j) for clave, j in pares.items() if clave not in recibidas]
    danadas = (db.query(m.RevisionUnidad)
               .join(m.Servicio, m.RevisionUnidad.servicio_id == m.Servicio.id)
               .filter(m.Servicio.pais_id == ctx.pais.id,
                       m.RevisionUnidad.tipo == m.TipoRevision.ENTREGA.value,
                       m.RevisionUnidad.hubo_dano.is_(True),
                       m.RevisionUnidad.momento >= p.inicio,
                       m.RevisionUnidad.momento < p.fin)
               .order_by(m.RevisionUnidad.momento).all())
    filas_unidades = []
    for (servicio_id, vehiculo_id), j in sin_revision:
        v = db.get(m.Vehiculo, vehiculo_id)
        filas_unidades.append([_celda(_dia(j.fecha, idioma)), _liga(_servicio(j)),
                               _celda(v.placa if v else "—"),
                               _celda(t["entrega_sin"])])
    for r in danadas:
        s = db.get(m.Servicio, r.servicio_id)
        filas_unidades.append([_celda(_dia(r.momento.date(), idioma)), _liga(s),
                               _celda(r.vehiculo.placa if r.vehiculo else "—"),
                               _celda(t["volvio_danada"]
                                      + (f": {r.dano_nota}" if r.dano_nota else ""))])
    detalle_unidades = {
        "columnas": [t["col"]["dia"], t["col"]["servicio"], t["col"]["unidad"],
                     t["col"]["que"]],
        "filas": filas_unidades,
    }

    nota_relevos = [{"t": _n(par, n)} for par, n in
                    ((t["de_personal"], de_personal), (t["de_unidad"], de_unidad))
                    if n]
    bloque = {"clave": "calle", "titulo": t["bloques"]["calle"],
              "renglones": [
                  {"clave": "lejos", "texto": t["lejos"], "valor": str(len(lejos)),
                   "nota": nota_lejos, "ver": detalle_lejos if lejos else None},
                  {"clave": "por_validar", "texto": t["por_validar"],
                   "valor": str(len(por_validar)),
                   "nota": [{"t": t["las_valida"]}] if por_validar else [],
                   "ver": detalle_validar if por_validar else None},
                  {"clave": "relevos", "texto": t["relevos"],
                   "valor": str(de_personal + de_unidad), "nota": nota_relevos,
                   "ver": detalle_relevos if filas_relevos else None},
                  {"clave": "unidades", "texto": t["unidades"],
                   "valor": str(len(sin_revision)),
                   "nota": ([{"t": _n(t["con_dano"], len(danadas)), "tono": "ambar"}]
                            if danadas else []),
                   "ver": detalle_unidades if filas_unidades else None},
              ]}
    cifras = {"lejos": len(lejos), "por_validar": len(por_validar),
              "relevos": de_personal + de_unidad, "relevos_personal": de_personal,
              "relevos_unidad": de_unidad, "sin_revision": len(sin_revision),
              "con_dano": len(danadas)}
    detalles = [("lejos", detalle_lejos), ("por_validar", detalle_validar),
                ("relevos", detalle_relevos), ("unidades", detalle_unidades)]
    return bloque, detalles, cifras


# ----------------------------------------------------------------- el cierre

def cierres(db: Session, pais_id: int, p: Periodo) -> dict:
    """El visto bueno del consultor en su plazo: el mismo que decide su
    comision (`cierre.dar_visto_bueno`). Cuenta en el mes en que vence el
    plazo. El que vencio sin visto bueno es tarde; el que todavia esta en
    plazo no se cuenta."""
    filas = (db.query(m.Cierre)
             .join(m.Servicio, m.Cierre.servicio_id == m.Servicio.id)
             .filter(m.Servicio.pais_id == pais_id,
                     m.Cierre.limite_consultor >= p.inicio,
                     m.Cierre.limite_consultor < p.fin)
             .order_by(m.Cierre.limite_consultor).all())
    a_tiempo, tarde = [], []
    for c in filas:
        if c.dentro_de_plazo is True:
            a_tiempo.append(c)
        elif c.dentro_de_plazo is False:
            tarde.append(c)
        elif c.estatus in SIN_VISTO_BUENO and c.limite_consultor < p.ahora:
            tarde.append(c)
    return {"a_tiempo": a_tiempo, "tarde": tarde}


def _por_consultor(db: Session, servicios: list[m.Servicio]) -> list[tuple[str, int]]:
    cuenta: dict = {}
    for s in servicios:
        cuenta[s.consultor_id] = cuenta.get(s.consultor_id, 0) + 1
    nombres = []
    for consultor_id, n in sorted(cuenta.items(), key=lambda x: (-x[1], x[0] or 0)):
        persona = db.get(m.Persona, consultor_id) if consultor_id else None
        nombres.append((persona.nombre if persona else "—", n))
    return nombres


def _nota_consultores(nombres: list[tuple[str, int]]) -> list[dict]:
    return [{"t": f"{nombre} {n}"} for nombre, n in nombres[:3]]


def viaticos_a_tiempo(db: Session, pais_id: int, p: Periodo) -> dict:
    """El dinero del personal, comprobado antes de su plazo: la regla del
    bono (`bonos.medir_cierre_viaticos`), para todo el pais. Cuenta en el
    mes en que cae su plazo; el que sigue en plazo no se cuenta; el cierre
    con descuento es tarde."""
    from app import bolson

    candidatos = (db.query(m.AsignacionViatico)
                  .join(m.Jornada, m.AsignacionViatico.jornada_id == m.Jornada.id)
                  .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                  .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
                  .filter(m.Servicio.pais_id == pais_id,
                          m.AsignacionViatico.estatus != m.EstatusViatico.CANCELADO,
                          m.AsignacionViatico.limite_comprobacion
                          >= p.inicio - timedelta(days=45),
                          m.AsignacionViatico.limite_comprobacion < p.fin)
                  .all())
    bolsones: dict[tuple, m.AsignacionViatico] = {}
    for v in candidatos:
        servicio = v.jornada.equipo.servicio
        clave = (v.persona_id, servicio.id,
                 (v.jornada.fecha.year, v.jornada.fecha.month)
                 if servicio.tipo == m.TipoServicio.IMPLANTADO else None)
        bolsones.setdefault(clave, v)

    pais = db.get(m.Pais, pais_id)
    bien, problemas = 0, []
    medidos = 0
    for uno in bolsones.values():
        suyos = bolson.de_la_persona(db, uno)
        limites = [v.limite_comprobacion for v in suyos if v.limite_comprobacion]
        plazo = max(limites) if limites else None
        if not plazo or not (p.inicio <= plazo < p.fin):
            continue
        cuenta = bolson.cuenta(suyos)
        if cuenta["depositado"] <= 0:
            continue
        servicio = suyos[0].jornada.equipo.servicio
        persona = suyos[0].persona
        if cuenta["estatus"] == "con_descuento":
            medidos += 1
            problemas.append((servicio, persona, plazo, "con_descuento", None))
            continue
        termino = bolson.termino_de_comprobar(suyos, pais)
        if termino is None and p.ahora < plazo:
            continue
        medidos += 1
        if termino and termino <= plazo:
            bien += 1
        else:
            problemas.append((servicio, persona, plazo,
                              "termino" if termino else "no_termino", termino))
    return {"bien": bien, "medidos": medidos, "problemas": problemas}


def el_cierre(db: Session, pais: m.Pais, p: Periodo,
              idioma: str) -> tuple[dict, list, dict]:
    t = _t(idioma)
    pais_id = pais.id
    c = cierres(db, pais_id, p)
    tarde = c["tarde"]
    nombres_tarde = _por_consultor(db, [x.servicio for x in tarde])
    detalle_tarde = {
        "columnas": [t["col"]["servicio"], t["col"]["consultor"],
                     t["col"]["limite"], t["col"]["visto_bueno"]],
        "filas": [[_liga(x.servicio),
                   _persona(db.get(m.Persona, x.servicio.consultor_id)
                            if x.servicio.consultor_id else None),
                   _celda(_momento(x.limite_consultor, idioma)),
                   _celda(_momento(x.visto_bueno_en, idioma) if x.visto_bueno_en
                          else t["sin_vb"])] for x in tarde],
    }

    # Lo que finanzas regreso. El motivo lo escribe finanzas a mano: se
    # ensena tal cual, no se adivina de que tipo fue.
    regresos = (db.query(m.RegistroAccion)
                .join(m.Servicio, m.RegistroAccion.servicio_id == m.Servicio.id)
                .filter(m.Servicio.pais_id == pais_id,
                        m.RegistroAccion.accion == "devolver a operacion",
                        m.RegistroAccion.creado_en >= p.inicio_z,
                        m.RegistroAccion.creado_en < p.fin_z)
                .order_by(m.RegistroAccion.creado_en).all())
    servicios_regreso = [db.get(m.Servicio, r.servicio_id) for r in regresos]
    detalle_regresos = {
        "columnas": [t["col"]["dia"], t["col"]["servicio"], t["col"]["consultor"],
                     t["col"]["motivo"]],
        "filas": [[_celda(_dia(reloj.ahora_en(pais, r.creado_en).date(), idioma)),
                   _liga(s),
                   _persona(db.get(m.Persona, s.consultor_id) if s.consultor_id else None),
                   _celda((r.detalle or "").split(": ", 1)[-1])]
                  for r, s in zip(regresos, servicios_regreso)],
    }

    v = viaticos_a_tiempo(db, pais_id, p)
    filas_viaticos = []
    for servicio, persona, plazo, que, termino in v["problemas"]:
        texto = (t["con_descuento"] if que == "con_descuento" else
                 t["no_termino"] if que == "no_termino" else
                 t["termino"].replace("{cuando}", _momento(termino, idioma)))
        filas_viaticos.append([_liga(servicio), _persona(persona),
                               _celda(_momento(plazo, idioma)), _celda(texto)])
    detalle_viaticos = {
        "columnas": [t["col"]["servicio"], t["col"]["persona"], t["col"]["plazo"],
                     t["col"]["que"]],
        "filas": filas_viaticos,
    }
    pct_viaticos = (Decimal(v["bien"]) * 100 / Decimal(v["medidos"])
                    if v["medidos"] else None)

    bloque = {"clave": "cierre", "titulo": t["bloques"]["cierre"],
              "renglones": [
                  {"clave": "tarde", "texto": t["tarde"], "valor": str(len(tarde)),
                   "nota": _nota_consultores(nombres_tarde),
                   "ver": detalle_tarde if tarde else None},
                  {"clave": "regresados", "texto": t["regresados"],
                   "valor": str(len(regresos)),
                   "nota": _nota_consultores(_por_consultor(db, servicios_regreso)),
                   "ver": detalle_regresos if regresos else None},
                  {"clave": "viaticos", "texto": t["viaticos"],
                   "valor": _pct(pct_viaticos, idioma) if pct_viaticos is not None else "—",
                   "nota": ([{"t": t["por_el_personal"].replace("{a}", str(v["bien"]))
                                                      .replace("{b}", str(v["medidos"]))}]
                            if v["medidos"] else [{"t": t["sin_datos"]}]),
                   "ver": detalle_viaticos if filas_viaticos else None},
              ]}
    cifras = {"cierres": (len(c["a_tiempo"]), len(c["a_tiempo"]) + len(tarde)),
              "tarde": len(tarde), "regresados": len(regresos),
              "viaticos": (v["bien"], v["medidos"])}
    detalles = [("tarde", detalle_tarde), ("regresados", detalle_regresos),
                ("viaticos", detalle_viaticos)]
    return bloque, detalles, cifras


# ----------------------------------------------------------------- la gente

def _bono(db: Session, pais_id: int, anio: int, mes: int) -> dict | None:
    evaluaciones = (db.query(m.EvaluacionMensual)
                    .join(m.Persona, m.Persona.id == m.EvaluacionMensual.persona_id)
                    .join(m.Plaza, m.Plaza.id == m.Persona.plaza_id)
                    .filter(m.Plaza.pais_id == pais_id,
                            m.EvaluacionMensual.anio == anio,
                            m.EvaluacionMensual.mes == mes).all())
    if not evaluaciones:
        return None
    completos = anulados = 0
    for e in evaluaciones:
        posibles = sum(1 for r in e.detalle if r.aplica)
        if e.anulado_por_incidencia:
            anulados += 1
        elif posibles and e.estrellas == posibles:
            completos += 1
    return {"completos": completos, "evaluados": len(evaluaciones),
            "anulados": anulados}


def la_gente(db: Session, ctx: _Contexto, idioma: str) -> tuple[dict, list, dict]:
    t = _t(idioma)
    p, pais_id = ctx.p, ctx.pais.id

    incidencias = (db.query(m.Incidencia)
                   .join(m.Persona, m.Persona.id == m.Incidencia.persona_id)
                   .join(m.Plaza, m.Plaza.id == m.Persona.plaza_id)
                   .filter(m.Plaza.pais_id == pais_id,
                           m.Incidencia.fecha >= p.desde,
                           m.Incidencia.fecha <= p.hasta)
                   .order_by(m.Incidencia.fecha).all())
    G = m.GravedadIncidencia
    autorizadas = [i for i in incidencias if i.autorizada]
    leves = sum(1 for i in autorizadas if i.gravedad == G.LEVE)
    graves = sum(1 for i in autorizadas if i.gravedad == G.GRAVE)
    menores = sum(1 for i in autorizadas if i.gravedad == G.ERROR_MENOR)
    pendientes = sum(1 for i in incidencias if i.visto_bueno_por_id is None)
    nota_inc = []
    for par, n in ((t["leves"], leves), (t["graves"], graves), (t["menores"], menores)):
        if n:
            nota_inc.append({"t": _n(par, n)})
    if not nota_inc and not pendientes:
        nota_inc.append({"t": t["ninguna"]})
    if pendientes:
        nota_inc.append({"t": _n(t["por_autorizar"], pendientes), "tono": "ambar"})

    def estado(i):
        if i.visto_bueno_por_id is None:
            return t["inc_estado"]["pendiente"]
        return t["inc_estado"]["autorizada" if i.autorizada else "descartada"]

    detalle_inc = {
        "columnas": [t["col"]["dia"], t["col"]["persona"], t["col"]["gravedad"],
                     t["col"]["estado"], t["col"]["que"]],
        "filas": [[_celda(_dia(i.fecha, idioma)), _persona(i.persona),
                   _celda(t["gravedad"][i.gravedad.value]), _celda(estado(i)),
                   _celda(i.descripcion)] for i in incidencias],
    }

    # Los certificados: quien trabajo en el mes con un curso ya vencido.
    hay_padron = db.query(m.Capacitacion.id).filter(
        m.Capacitacion.activo.is_(True)).first() is not None
    trabajo: dict[int, list[date]] = {}
    for a in ctx.asignaciones:
        j = ctx.por_id.get(a.jornada_id)
        if j is not None and j.fecha <= min(p.hasta, p.hoy):
            trabajo.setdefault(a.persona_id, []).append(j.fecha)
    cursos: dict[int, list[m.Capacitacion]] = {}
    if trabajo:
        for c in (db.query(m.Capacitacion)
                  .filter(m.Capacitacion.persona_id.in_(list(trabajo)),
                          m.Capacitacion.activo.is_(True),
                          m.Capacitacion.vigencia_hasta.isnot(None)).all()):
            cursos.setdefault(c.persona_id, []).append(c)
    vencidos = []
    for persona_id, fechas in trabajo.items():
        suyos = cursos.get(persona_id, [])
        dias = sorted({f for f in fechas
                       if any(c.vigencia_hasta < f for c in suyos)})
        if dias:
            curso = min((c for c in suyos if c.vigencia_hasta < dias[0]),
                        key=lambda c: c.vigencia_hasta)
            vencidos.append((db.get(m.Persona, persona_id), curso, len(dias)))
    vencidos.sort(key=lambda x: x[0].nombre)
    referencia = p.hoy if p.en_curso else p.hasta
    por_vencer = (db.query(m.Capacitacion.persona_id)
                  .join(m.Persona, m.Persona.id == m.Capacitacion.persona_id)
                  .join(m.Plaza, m.Plaza.id == m.Persona.plaza_id)
                  .filter(m.Plaza.pais_id == pais_id,
                          m.Persona.activo.is_(True),
                          m.Capacitacion.activo.is_(True),
                          m.Capacitacion.vigencia_hasta >= referencia,
                          m.Capacitacion.vigencia_hasta
                          <= referencia + timedelta(days=DIAS_POR_VENCER))
                  .distinct().count())
    detalle_cert = {
        "columnas": [t["col"]["persona"], t["col"]["curso"], t["col"]["vencio"],
                     t["col"]["dias"]],
        "filas": [[_persona(persona), _celda(curso.nombre),
                   _celda(_dia(curso.vigencia_hasta, idioma)
                          + f" {curso.vigencia_hasta.year}"),
                   _celda(str(dias))] for persona, curso, dias in vencidos],
    }
    if hay_padron:
        nota_cert = []
        if vencidos:
            nota_cert.append({"t": t["trabajando"], "tono": "ambar"})
        if por_vencer:
            nota_cert.append({"t": _n(t["vencen"], por_vencer)})
        renglon_cert = {"clave": "certificados", "texto": t["certificados"],
                        "valor": str(len(vencidos)), "nota": nota_cert,
                        "ver": detalle_cert if vencidos else None}
    else:
        renglon_cert = {"clave": "certificados", "texto": t["certificados"],
                        "valor": "—", "nota": [{"t": t["sin_padron"]}]}

    # El bono: el del mes si ya se calculo --se calcula el dia 3 del
    # siguiente--; si no, el del mes de antes, y se dice cual.
    anio_b, mes_b = p.anio, p.mes
    bono = _bono(db, pais_id, anio_b, mes_b)
    if bono is None and p.en_curso:
        anio_b, mes_b = anterior(p.anio, p.mes)
        bono = _bono(db, pais_id, anio_b, mes_b)
    nombre_b = nombre_del_mes(anio_b, mes_b, idioma, con_anio=False)
    if bono:
        pct_bono = Decimal(bono["completos"]) * 100 / Decimal(bono["evaluados"])
        nota_bono = [{"t": t["de_personas"].replace("{a}", str(bono["completos"]))
                                          .replace("{b}", str(bono["evaluados"]))}]
        if bono["anulados"]:
            nota_bono.append({"t": _n(t["anulados"], bono["anulados"])})
        renglon_bono = {"clave": "bono",
                        "texto": t["bono"].replace("{mes}", nombre_b),
                        "valor": _pct(pct_bono, idioma), "nota": nota_bono}
    else:
        renglon_bono = {"clave": "bono",
                        "texto": t["bono"].replace("{mes}", nombre_b),
                        "valor": "—",
                        "nota": [{"t": t["sin_bono"].replace("{mes}", nombre_b)}]}

    # El profesionalismo se mide al dia --ventana de seis meses hacia atras
    # desde hoy--: un mes pasado no tiene el suyo guardado.
    if p.en_curso:
        prof = profesionalismo_promedio(db, pais_id, p.hoy)
        if prof["personas"]:
            nota_prof = [{"t": _n(t["promedio"], prof["personas"])}]
            if prof["pocos_datos"]:
                nota_prof.append({"t": _n(t["pocos_datos"], prof["pocos_datos"])})
            renglon_prof = {"clave": "profesionalismo", "texto": t["profesionalismo"],
                            "valor": _decimal(prof["promedio"], idioma, 0),
                            "nota": nota_prof}
        else:
            renglon_prof = {"clave": "profesionalismo", "texto": t["profesionalismo"],
                            "valor": "—", "nota": [{"t": t["sin_datos"]}]}
    else:
        prof = None
        renglon_prof = {"clave": "profesionalismo", "texto": t["profesionalismo"],
                        "valor": "—", "nota": [{"t": t["al_dia_solo"]}]}

    bloque = {"clave": "gente", "titulo": t["bloques"]["gente"],
              "renglones": [
                  {"clave": "incidencias", "texto": t["incidencias"],
                   "valor": str(leves + graves), "nota": nota_inc,
                   "ver": detalle_inc if incidencias else None},
                  renglon_cert, renglon_bono, renglon_prof]}
    cifras = {"incidencias": leves + graves, "leves": leves, "graves": graves,
              "errores_menores": menores, "incidencias_por_autorizar": pendientes,
              "certificados_vencidos": len(vencidos) if hay_padron else None,
              "por_vencer": por_vencer,
              "bono": bono, "bono_mes": (anio_b, mes_b),
              "profesionalismo": prof}
    detalles = [("incidencias", detalle_inc), ("certificados", detalle_cert)]
    return bloque, detalles, cifras


def profesionalismo_promedio(db: Session, pais_id: int,
                             hoy: date | None = None) -> dict:
    """El promedio de la calificacion de 0 a 100 de quien trabajo en la
    calle en los ultimos seis meses --la ventana del profesionalismo--,
    como la ensena la pantalla de Personal. Quien casi no tiene datos --dos
    o mas dimensiones sin medir, como quien acaba de entrar-- no entra al
    promedio: bajaria la cifra por falta de datos, no por como trabaja."""
    from app import profesionalismo

    desde = (hoy or date.today()) - timedelta(days=183)
    trabajaron = (db.query(m.AsignacionPersonal.persona_id)
                  .join(m.Jornada, m.AsignacionPersonal.jornada_id == m.Jornada.id)
                  .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
                  .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
                  .filter(m.Servicio.pais_id == pais_id, m.Jornada.fecha >= desde,
                          m.Jornada.estatus != m.EstatusJornada.CANCELADA)
                  .distinct())
    gente = (db.query(m.Persona.id)
             .filter(m.Persona.id.in_(trabajaron), m.Persona.activo.is_(True),
                     m.Persona.oficina.is_(False)).all())
    valores, pocos = [], 0
    # Las fichas de todos de un golpe (seccion 101): una por una eran
    # una docena de consultas por persona.
    fichas = profesionalismo.fichas(db, [persona_id for (persona_id,) in gente])
    for f in fichas.values():
        if f["confianza"] == "baja":
            pocos += 1
            continue
        valores.append(Decimal(str(f["calificacion"])))
    return {"promedio": _promedio(valores), "personas": len(valores),
            "pocos_datos": pocos}


# ----------------------------------------------------------------- los datos

def _lista(nombres: list[str], tope: int = 12) -> str:
    return ", ".join(nombres[:tope]) + (" …" if len(nombres) > tope else "")


def los_datos(db: Session, pais: m.Pais, p: Periodo, idioma: str) -> dict:
    """Lo que falta para que el sistema calcule bien y la hoja del servicio
    salga completa: lo de Odoo se corrige alla --aqui llega en la lectura
    de cada hora--, lo de Catalogos se corrige aqui."""
    from app import odoo_personal_reglas as reglas
    from app import seed

    t = _t(idioma)
    gente = (db.query(m.Persona)
             .join(m.Plaza, m.Persona.plaza_id == m.Plaza.id)
             .filter(m.Plaza.pais_id == pais.id, m.Persona.activo.is_(True),
                     m.Persona.oficina.is_(False),
                     m.Persona.es_freelance.is_(False),
                     m.Persona.odoo_id.isnot(None))
             .order_by(m.Persona.nombre).all())
    odoo = []
    sin_foto = [x.nombre for x in gente if not (x.foto_url or "").strip()]
    if sin_foto:
        odoo.append({"clave": "sin_foto", "t": _n(t["sin_foto"], len(sin_foto)),
                     "n": len(sin_foto), "cuales": sin_foto})
    sin_celular = [x.nombre for x in gente if not reglas.es_celular(x.telefono)]
    if sin_celular:
        odoo.append({"clave": "sin_celular",
                     "t": _n(t["sin_celular"], len(sin_celular)),
                     "n": len(sin_celular), "cuales": sin_celular})
    clientes = [c.nombre for c in (db.query(m.Cliente)
                                   .filter(m.Cliente.pais_id == pais.id,
                                           m.Cliente.activo.is_(True),
                                           m.Cliente.odoo_id.isnot(None))
                                   .order_by(m.Cliente.nombre).all())
                if not (c.rfc or "").strip()]
    if clientes:
        clave = "sin_rfc" if pais.codigo == "MX" else "sin_fiscal"
        odoo.append({"clave": clave, "t": _n(t[clave], len(clientes)),
                     "n": len(clientes), "cuales": clientes})
    grupo = db.query(m.GrupoGps).filter_by(pais_id=pais.id).first()
    if grupo:
        sueltas = (db.query(m.UnidadGps)
                   .filter_by(grupo_id=grupo.id, en_el_grupo=True)
                   .filter(m.UnidadGps.vehiculo_id.is_(None))
                   .order_by(m.UnidadGps.placa).all())
        if sueltas:
            odoo.append({"clave": "gps", "t": _n(t["gps"], len(sueltas)),
                         "n": len(sueltas),
                         "cuales": [u.placa or f"Pegasus {u.pegasus_id}"
                                    for u in sueltas]})

    catalogos = []
    anio = p.hoy.year if p.en_curso else p.anio
    festivos = (db.query(m.DiaFestivo.id)
                .filter(m.DiaFestivo.pais_id == pais.id,
                        m.DiaFestivo.activo.is_(True),
                        m.DiaFestivo.fecha >= date(anio, 1, 1),
                        m.DiaFestivo.fecha <= date(anio, 12, 31)).first())
    if festivos is None:
        catalogos.append({"clave": "festivos",
                          "t": t["festivos"].replace("{anio}", str(anio)), "n": 1})
    vigente = (db.query(m.ParametroCombustible)
               .filter(m.ParametroCombustible.pais_id == pais.id,
                       m.ParametroCombustible.activo.is_(True),
                       m.ParametroCombustible.vigencia_desde <= p.hoy)
               .order_by(m.ParametroCombustible.vigencia_desde.desc()).first())
    if vigente is None:
        catalogos.append({"clave": "combustible", "t": t["combustible_falta"], "n": 1})
    elif (vigente.vigencia_desde, Decimal(str(vigente.precio_litro))) == \
            seed.COMBUSTIBLE_DE_EJEMPLO:
        catalogos.append({"clave": "combustible", "n": 1,
                          "t": t["combustible_ejemplo"]
                          .replace("{precio}", _dinero(vigente.precio_litro,
                                                       pais.moneda_local))
                          .replace("{fecha}", _largo(vigente.vigencia_desde, idioma))})
    hoteles = [h.nombre for h in (db.query(m.Hotel)
                                  .filter(m.Hotel.pais_id == pais.id,
                                          m.Hotel.activo.is_(True),
                                          m.Hotel.lat.is_(None))
                                  .order_by(m.Hotel.nombre).all())]
    if hoteles:
        catalogos.append({"clave": "hoteles", "t": _n(t["hoteles"], len(hoteles)),
                          "n": len(hoteles), "cuales": hoteles})
    con_hospital = {x for (x,) in db.query(m.Hospital.plaza_id)
                    .filter(m.Hospital.activo.is_(True),
                            m.Hospital.plaza_id.isnot(None)).distinct().all()}
    ciudades = [c.nombre for c in (db.query(m.Plaza)
                                   .filter(m.Plaza.pais_id == pais.id,
                                           m.Plaza.activo.is_(True),
                                           m.Plaza.tiene_recurso_local.is_(True))
                                   .order_by(m.Plaza.nombre).all())
                if c.id not in con_hospital]
    if ciudades:
        catalogos.append({"clave": "hospitales", "n": len(ciudades),
                          "t": t["hospitales"].replace("{ciudades}", _lista(ciudades, 4)),
                          "cuales": ciudades})
    if db.query(m.TabuladorViatico.id).filter_by(pais_id=pais.id).first() is None:
        catalogos.append({"clave": "tabulador", "t": t["tabulador"], "n": 1})
    codigos = {x for (x,) in db.query(m.Modalidad.codigo)
               .filter(m.Modalidad.pais_id == pais.id).all()}
    if any(c not in codigos for c in m.CodigoModalidad):
        catalogos.append({"clave": "modalidades", "t": t["modalidades"], "n": 1})
    pesos = {x.dimension: Decimal(str(x.peso)) for x in
             db.query(m.PesoProfesionalismo).filter_by(pais_id=pais.id).all()}
    if not pesos or pesos == seed.PESOS_DE_EJEMPLO:
        catalogos.append({"clave": "pesos", "t": t["pesos"], "n": 1})
    sin_foto_cat = [c.nombre for c in db.query(m.CategoriaVehiculo)
                    .filter(m.CategoriaVehiculo.activo.is_(True))
                    .order_by(m.CategoriaVehiculo.nombre).all()
                    if not c.fotos]
    if sin_foto_cat:
        catalogos.append({"clave": "fotos_categoria", "n": len(sin_foto_cat),
                          "t": _n(t["fotos_categoria"], len(sin_foto_cat)),
                          "cuales": sin_foto_cat})
    return {"titulo": t["bloques"]["datos"],
            "odoo": {"titulo": t["odoo"], "cosas": odoo},
            "catalogos": {"titulo": t["en_catalogos"], "cosas": catalogos},
            "nada": t["nada"]}


# ------------------------------------------------------------ todo junto

def _flecha(actual, antes, mejor_arriba=True) -> tuple[str, str]:
    if actual is None or antes is None:
        return "", "gris"
    if actual == antes:
        return "=", "gris"
    sube = actual > antes
    return ("▲" if sube else "▼"), ("ok" if sube == mejor_arriba else "alerta")


def _redondo_pct(a: int, b: int) -> Decimal | None:
    return Decimal(a) * 100 / Decimal(b) if b else None


def _arriba(t, idioma, actual: dict, antes: dict, nombre_antes: str) -> list[dict]:
    def comparacion(valor, previo, texto_previo, mejor_arriba=True):
        if valor is None or previo is None:
            return None
        flecha, tono = _flecha(Decimal(str(valor)).quantize(Decimal("0.1")),
                               Decimal(str(previo)).quantize(Decimal("0.1")),
                               mejor_arriba)
        return {"t": t["vs"].replace("{flecha}", flecha).replace("{mes}", nombre_antes)
                            .replace("{valor}", texto_previo).strip(),
                "tono": tono}

    def tile(clave, valor_txt, etiqueta, valor, previo, previo_txt, ir=None):
        return {"clave": clave, "valor": valor_txt, "texto": etiqueta,
                "comparacion": comparacion(valor, previo, previo_txt),
                "ir": ir}

    sat, sat_antes = actual["satisfaccion"], antes["satisfaccion"]
    pa, pb = actual["puntualidad"]
    pa0, pb0 = antes["puntualidad"]
    ra, rb = actual["reporte"]
    ra0, rb0 = antes["reporte"]
    ca, cb = actual["cierres"]
    ca0, cb0 = antes["cierres"]
    pct = {"puntualidad": (_redondo_pct(pa, pb), _redondo_pct(pa0, pb0)),
           "reporte": (_redondo_pct(ra, rb), _redondo_pct(ra0, rb0)),
           "cierres": (_redondo_pct(ca, cb), _redondo_pct(ca0, cb0))}

    def txt_pct(v):
        return _pct(v, idioma) if v is not None else "—"

    tiles = [
        tile("satisfaccion",
             _decimal(sat, idioma) if sat is not None else "—",
             t["arriba"]["satisfaccion"], sat, sat_antes,
             _decimal(sat_antes, idioma) if sat_antes is not None else "", "encuestas"),
        tile("puntualidad", txt_pct(pct["puntualidad"][0]),
             t["arriba"]["puntualidad"].replace("{a}", str(pa)).replace("{b}", str(pb)),
             pct["puntualidad"][0], pct["puntualidad"][1], txt_pct(pct["puntualidad"][1])),
        tile("reporte", txt_pct(pct["reporte"][0]),
             t["arriba"]["reporte"].replace("{a}", str(ra)).replace("{b}", str(rb)),
             pct["reporte"][0], pct["reporte"][1], txt_pct(pct["reporte"][1])),
        tile("cierres", txt_pct(pct["cierres"][0]),
             t["arriba"]["cierres"].replace("{a}", str(ca)).replace("{b}", str(cb)),
             pct["cierres"][0], pct["cierres"][1], txt_pct(pct["cierres"][1])),
    ]
    bajas = actual["bajas"]
    tiles.append({"clave": "bajas", "valor": str(bajas),
                  "texto": t["arriba"]["bajas"], "tono": "rojo" if bajas else None,
                  "comparacion": ({"t": _n(t["sin_revisar"], actual["sin_revisar"]),
                                   "tono": "ambar"} if actual["sin_revisar"] else
                                  {"t": t["todas_revisadas"], "tono": "gris"}
                                  if bajas else None),
                  "ir": "encuestas"})
    for x in tiles:
        x["numero"] = {"satisfaccion": sat, "bajas": bajas}.get(
            x["clave"], pct.get(x["clave"], (None,))[0])
        x["numero_antes"] = {"satisfaccion": sat_antes}.get(
            x["clave"], pct.get(x["clave"], (None, None))[1])
    return tiles


def _lo_de_arriba(db: Session, pais: m.Pais, p: Periodo) -> dict:
    """Las cuatro cifras que se comparan contra el mes de antes."""
    ctx = _Contexto(db, pais, p)
    pr = puntualidad_y_reporte(ctx)
    c = cierres(db, pais.id, p)
    return {"satisfaccion": satisfaccion(db, pais.id, p)["promedio"],
            "puntualidad": (pr["a_tiempo"], pr["medidos"]),
            "reporte": (pr["completos"], pr["dias"]),
            "cierres": (len(c["a_tiempo"]), len(c["a_tiempo"]) + len(c["tarde"]))}


def opciones(db: Session, pais: m.Pais, ahora: datetime | None = None,
             idioma: str = "es") -> dict:
    """Los paises y los meses que se pueden escoger: desde el primer mes
    con operacion en ese pais, a lo mas dos anos, hasta el de hoy."""
    hoy = reloj.ahora_en(pais, ahora).date()
    primero = (db.query(func.min(m.Jornada.fecha))
               .join(m.Equipo, m.Jornada.equipo_id == m.Equipo.id)
               .join(m.Servicio, m.Equipo.servicio_id == m.Servicio.id)
               .filter(m.Servicio.pais_id == pais.id).scalar())
    meses = []
    anio, mes = hoy.year, hoy.month
    for i in range(MESES_ATRAS):
        meses.append({"valor": f"{anio}-{mes:02d}",
                      "texto": (_t(idioma)["al_dia"].replace(
                          "{mes}", nombre_del_mes(anio, mes, idioma)) if i == 0
                          else nombre_del_mes(anio, mes, idioma))})
        if primero is None or (anio, mes) <= (primero.year, primero.month):
            break
        anio, mes = anterior(anio, mes)
    paises = [{"id": x.id, "nombre": x.nombre, "codigo": x.codigo}
              for x in db.query(m.Pais).filter(m.Pais.activo.is_(True))
              .order_by(m.Pais.nombre).all()]
    return {"paises": paises, "meses": meses}


def mes_pedido(texto: str | None, pais: m.Pais,
               ahora: datetime | None = None) -> tuple[int, int]:
    """"2026-09" -> (2026, 9). Sin mes, o uno que todavia no llega: el de
    hoy."""
    hoy = reloj.ahora_en(pais, ahora).date()
    try:
        anio, mes = (int(x) for x in (texto or "").split("-"))
        date(anio, mes, 1)
    except (ValueError, TypeError):
        return hoy.year, hoy.month
    if (anio, mes) > (hoy.year, hoy.month):
        return hoy.year, hoy.month
    return anio, mes


def reporte(db: Session, pais_id: int, anio: int, mes: int,
            idioma: str = "es", ahora: datetime | None = None) -> dict:
    """El mes en cifras, con el detalle de cada una, listo para pintarse."""
    idioma = _idioma(idioma)
    t = _t(idioma)
    pais = db.get(m.Pais, pais_id)
    p = periodo(pais, anio, mes, ahora)
    antes = periodo(pais, *anterior(anio, mes), ahora)
    ctx = _Contexto(db, pais, p)

    cliente, det_cliente, c_cliente = lo_que_dijo_el_cliente(db, pais, p, idioma)
    calle, det_calle, c_calle = en_la_calle(ctx, idioma)
    cierre, det_cierre, c_cierre = el_cierre(db, pais, p, idioma)
    gente, det_gente, c_gente = la_gente(db, ctx, idioma)
    datos = los_datos(db, pais, p, idioma)

    pr = puntualidad_y_reporte(ctx)
    actual = {"satisfaccion": c_cliente["satisfaccion"],
              "puntualidad": (pr["a_tiempo"], pr["medidos"]),
              "reporte": (pr["completos"], pr["dias"]),
              "cierres": c_cierre["cierres"],
              "bajas": c_cliente["bajas"], "sin_revisar": c_cliente["sin_revisar"]}
    previo = _lo_de_arriba(db, pais, antes)
    nombre_antes = nombre_del_mes(antes.anio, antes.mes, idioma, con_anio=False)
    arriba = _arriba(t, idioma, actual, previo, nombre_antes)

    return {
        "pais": {"id": pais.id, "nombre": pais.nombre, "codigo": pais.codigo},
        "mes": f"{anio}-{mes:02d}",
        "nombre_mes": nombre_del_mes(anio, mes, idioma),
        "anterior": f"{antes.anio}-{antes.mes:02d}",
        "nombre_anterior": nombre_del_mes(antes.anio, antes.mes, idioma),
        "en_curso": p.en_curso,
        "al": p.hoy.isoformat() if p.en_curso else p.hasta.isoformat(),
        "arriba": arriba,
        "bloques": [cliente, calle, cierre, gente],
        "datos": datos,
        "detalles": det_cliente + det_calle + det_cierre + det_gente,
        "cifras": {**c_cliente, **c_calle, **c_cierre, **c_gente,
                   "puntualidad": actual["puntualidad"],
                   "reporte": actual["reporte"], "antes": previo},
    }


# ------------------------------------------------------------- el reporte

def _numero_excel(valor, tipo):
    if valor is None:
        return None
    if tipo == "porcentaje":
        return ((Decimal(str(valor)) / 100).quantize(Decimal("0.0001")),
                "porcentaje")
    if tipo == "decimal":
        return (Decimal(str(valor)).quantize(Decimal("0.01")), "decimal")
    return (int(valor), "entero")


def excel_de(db: Session, pais_id: int, anio: int, mes: int,
             idioma: str = "es", ahora: datetime | None = None) -> tuple[bytes, str]:
    """El reporte del mes para la junta: el resumen con el mes de antes a
    su lado, y una hoja por cada detalle. Dice lo mismo que la pantalla."""
    idioma = _idioma(idioma)
    t = _t(idioma)
    r = reporte(db, pais_id, anio, mes, idioma, ahora)
    tx = t["excel"]
    columnas = [x.replace("{mes}", r["nombre_mes"]).replace("{anterior}",
                                                             r["nombre_anterior"])
                for x in tx["columnas"]]

    def nota(renglon):
        return " · ".join(x["t"] for x in renglon.get("nota") or [])

    tipos_arriba = {"satisfaccion": "decimal", "puntualidad": "porcentaje",
                    "reporte": "porcentaje", "cierres": "porcentaje",
                    "bajas": "entero"}
    filas = []
    for x in r["arriba"]:
        tipo = tipos_arriba[x["clave"]]
        filas.append([t["principales"], x["texto"],
                      _numero_excel(x.get("numero"), tipo) or x["valor"],
                      _numero_excel(x.get("numero_antes"), tipo)
                      if x["clave"] != "bajas" else None,
                      (x.get("comparacion") or {}).get("t", "")
                      if x["clave"] == "bajas" else ""])
    for bloque in r["bloques"]:
        for renglon in bloque["renglones"]:
            filas.append([bloque["titulo"], renglon["texto"], renglon["valor"],
                          None, nota(renglon)])
    for lado in ("odoo", "catalogos"):
        for cosa in r["datos"][lado]["cosas"]:
            filas.append([r["datos"]["titulo"], cosa["t"], cosa["n"], None,
                          r["datos"][lado]["titulo"]])
    hojas = [{"nombre": f"{tx['resumen']} {r['mes']}",
              "columnas": list(zip(columnas,
                                   ("texto", "texto", "texto", "texto", "texto"),
                                   (22, 52, 16, 16, 60))),
              "filas": filas}]
    for clave, detalle in r["detalles"]:
        if not detalle["filas"]:
            continue
        hojas.append({"nombre": tx["hojas"][clave],
                      "columnas": [(c, "texto", 22 if i else 14)
                                   for i, c in enumerate(detalle["columnas"])],
                      "filas": [[celda["t"] for celda in fila]
                                for fila in detalle["filas"]]})
    cosas = [(r["datos"][lado]["titulo"], cosa)
             for lado in ("odoo", "catalogos")
             for cosa in r["datos"][lado]["cosas"]]
    if cosas:
        hojas.append({"nombre": tx["hojas"]["datos"],
                      "columnas": [(tx["donde"], "texto", 26),
                                   (tx["que_falta"], "texto", 60),
                                   (tx["cuales"], "texto", 80)],
                      "filas": [[donde, cosa["t"], ", ".join(cosa.get("cuales") or [])]
                                for donde, cosa in cosas]})
    return (excel.libro(hojas),
            f"{tx['archivo']}_{r['pais']['codigo'].lower()}_{r['mes']}.xlsx")
