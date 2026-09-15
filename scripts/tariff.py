"""
Cálculo de ahorro y estimación de boleta, modelo Net Billing (Ley 21.118)
calibrado contra una boleta real de Enel (tarifa BT1, cliente residencial).

Fórmula (aproximada, validada contra una boleta real dentro de ~0.2%):

  cargo_variable   = compra_red_kwh * (precio_energia_kwh + precio_transporte_kwh)
  credito_inyeccion= inyeccion_red_kwh * precio_inyeccion_kwh
  neto_afecto      = max(0, cargo_variable + cargo_fijo_mensual - credito_inyeccion)
  monto_estimado   = neto_afecto * (1 + iva) + otros_cargos_fijos

  ahorro_autoconsumo = autoconsumo_kwh * (precio_energia_kwh + precio_transporte_kwh) * (1 + iva)
  ahorro_inyeccion    = inyeccion_red_kwh * precio_inyeccion_kwh * (1 + iva)
  ahorro_total        = ahorro_autoconsumo + ahorro_inyeccion

Si el crédito por inyección supera el cargo variable + fijo, el excedente no se
paga en dinero: se banca como remanente para el próximo ciclo (se informa como
"credito_no_usado_clp" pero no se traspasa automáticamente entre ciclos en este
cálculo simplificado).
"""
import calendar
from dataclasses import dataclass, asdict
from datetime import date, timedelta


@dataclass
class EstimacionPeriodo:
    cuenta: str
    nombre: str
    fecha_inicio: str
    fecha_fin: str
    proxima_lectura: str
    produccion_kwh: float
    consumo_kwh: float
    autoconsumo_kwh: float
    compra_red_kwh: float
    inyeccion_red_kwh: float
    ahorro_autoconsumo_clp: float
    ahorro_inyeccion_clp: float
    ahorro_total_clp: float
    monto_estimado_clp: float
    credito_no_usado_clp: float

    def to_dict(self):
        return asdict(self)


def ciclo_actual(dia_lectura: int, fecha_referencia: date = None):
    """
    Aproxima el ciclo de facturación en curso a partir del día del mes de
    lectura del medidor. Ej: si la lectura es el día 24, el ciclo "actual"
    corre desde el 24 del mes pasado hasta el 23 de este mes (o hasta hoy,
    si el ciclo aún no termina).
    """
    fecha_referencia = fecha_referencia or date.today()
    dia_lectura = max(1, min(28, int(dia_lectura)))

    if fecha_referencia.day >= dia_lectura:
        inicio = fecha_referencia.replace(day=dia_lectura)
        mes_prox = fecha_referencia.month % 12 + 1
        anio_prox = fecha_referencia.year + (1 if fecha_referencia.month == 12 else 0)
        ultimo_dia = calendar.monthrange(anio_prox, mes_prox)[1]
        proxima_lectura = date(anio_prox, mes_prox, min(dia_lectura, ultimo_dia))
    else:
        mes_anterior = fecha_referencia.month - 1 or 12
        anio = fecha_referencia.year if fecha_referencia.month > 1 else fecha_referencia.year - 1
        ultimo_dia_mes_anterior = calendar.monthrange(anio, mes_anterior)[1]
        inicio = date(anio, mes_anterior, min(dia_lectura, ultimo_dia_mes_anterior))
        ultimo_dia_este_mes = calendar.monthrange(fecha_referencia.year, fecha_referencia.month)[1]
        proxima_lectura = fecha_referencia.replace(day=min(dia_lectura, ultimo_dia_este_mes))

    fin = min(fecha_referencia, inicio + timedelta(days=29))
    return inicio, fin, proxima_lectura


def calcular_estimacion(clave_cuenta: str, nombre: str, tarifa: dict, lecturas: list) -> EstimacionPeriodo:
    produccion = sum(l["produccion_kwh"] for l in lecturas)
    consumo = sum(l["consumo_kwh"] for l in lecturas)
    autoconsumo = sum(l["autoconsumo_kwh"] for l in lecturas)
    compra = sum(l["compra_red_kwh"] for l in lecturas)
    inyeccion = sum(l["inyeccion_red_kwh"] for l in lecturas)

    precio_energia = float(tarifa["precio_energia_kwh"])
    precio_transporte = float(tarifa.get("precio_transporte_kwh", 0))
    precio_compra = precio_energia + precio_transporte
    precio_inyeccion = float(tarifa["precio_inyeccion_kwh"])
    cargo_fijo = float(tarifa.get("cargo_fijo_mensual", 0))
    otros_cargos = float(tarifa.get("otros_cargos_fijos", 0))
    iva = float(tarifa.get("iva", 0.19))

    cargo_variable = compra * precio_compra
    credito_inyeccion = inyeccion * precio_inyeccion

    neto = cargo_variable + cargo_fijo - credito_inyeccion
    neto_afecto = max(0.0, neto)
    credito_no_usado = max(0.0, -neto)

    monto_estimado = neto_afecto * (1 + iva) + otros_cargos

    ahorro_autoconsumo = autoconsumo * precio_compra * (1 + iva)
    ahorro_inyeccion = inyeccion * precio_inyeccion * (1 + iva)

    fechas = [l["fecha"] for l in lecturas]
    inicio, fin, proxima_lectura = ciclo_actual(tarifa.get("dia_lectura_medidor", 1))

    return EstimacionPeriodo(
        cuenta=clave_cuenta,
        nombre=nombre,
        fecha_inicio=(min(fechas) if fechas else inicio.isoformat()),
        fecha_fin=(max(fechas) if fechas else fin.isoformat()),
        proxima_lectura=proxima_lectura.isoformat(),
        produccion_kwh=round(produccion, 2),
        consumo_kwh=round(consumo, 2),
        autoconsumo_kwh=round(autoconsumo, 2),
        compra_red_kwh=round(compra, 2),
        inyeccion_red_kwh=round(inyeccion, 2),
        ahorro_autoconsumo_clp=round(ahorro_autoconsumo),
        ahorro_inyeccion_clp=round(ahorro_inyeccion),
        ahorro_total_clp=round(ahorro_autoconsumo + ahorro_inyeccion),
        monto_estimado_clp=round(monto_estimado),
        credito_no_usado_clp=round(credito_no_usado),
    )
