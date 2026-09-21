import pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "BITACORA.md"
s = R.read_text()

VIEJO = """- **La moneda.** `Cotizacion.tipo_cambio` existe y no se lee en ninguna
  parte. Hoy no duele porque todo está en pesos; el día que entre un
  tarifario en dólares, la utilidad y la comisión salen sin sentido.
"""
NUEVO = """- **La moneda.** Ver `PROPUESTA_MONEDA.md`. Decisión de Salvador
  (18 sep): **la rentabilidad se deja para el final**, es la cereza del
  pastel. Pero el defecto queda escrito aquí para que no se pierda:

  En `cierre.rentabilidad()`, `utilidad = facturacion - costo_total`
  resta la moneda del tarifario menos la moneda local. Los costos
  —comisiones, viáticos, unidad— **siempre** son locales; el tarifario
  tiene su propia moneda. Un servicio en México cotizado en 5,000 USD
  con 80,000 MXN de costo diría margen **−1,500%**, rotulado con la
  moneda de la cotización, o sea con cara de número normal.

  Hoy no muerde porque no hay tarifarios en dólares cargados. **El día
  que se cargue uno, muerde en silencio.** Por eso lo único que
  conviene adelantar es el candado: que no se autorice una cotización en
  moneda distinta a la local sin tipo de cambio. Son pocas líneas y no
  depende de ninguna decisión pendiente.

  Lo que sí quedó cerrado, y acota el problema: **el costo nunca
  necesita conversión.** Los viáticos se crean en cinco lugares y los
  cinco toman `servicio.pais_id → pais.moneda_local`; el país del
  servicio se captura en el alta y ningún endpoint lo reasigna; la
  nómina se calcula por país. El tipo de cambio solo toca el precio.
"""
assert s.count(VIEJO) == 1, "no encontre el pendiente de la moneda"
s = s.replace(VIEJO, NUEVO)
R.write_text(s)
print("BITACORA.md: la moneda queda escrita y aparcada")
