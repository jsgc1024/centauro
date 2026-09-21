import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

ANCLA = """### Lo que un humano todavía entrega a mano"""
NUEVO = """### El panel

`#/accesos`, para administración y dirección general. Lo que aporta no
son los datos —esos ya se podían pedir uno por uno— sino **juntarlos y
levantar la ceja**:

| | |
|---|---|
| **Sin estrenar** | Se le dio el acceso y nunca lo usó |
| **Lleva meses sin entrar** | Una puerta abierta a nombre de alguien que quizá ya no está |
| **Dado de baja y con el acceso abierto** | El caso feo. Hoy no debería pasar; el día que Odoo mande las bajas, es la señal de que algo quedó a medias |

Y las tres acciones en el mismo lugar, con el motivo que se lee un año
después cuando alguien pregunta por qué se cerró esa cuenta. Al cerrar
una puerta avisa los días que quedan sin cubrir: cerrarla no saca a nadie
de la operación.

El personal de campo lleva su renglón —"recupera su contraseña con su
consultor, no por correo"— porque es lo primero que alguien va a
preguntar al verlo en la lista con un gmail.

### Lo que un humano todavía entrega a mano"""
assert s.count(ANCLA) == 1
s = s.replace(ANCLA, NUEVO)
R.write_text(s)
print("BITACORA.md: el panel")
