#!/usr/bin/env python3
"""
Se ejecuta diariamente desde GitHub Actions (ver .github/workflows/actualizar-datos.yml).

1. Inicia sesión en FusionSolar para cada cuenta (casa / padres) usando las
   credenciales de las variables de entorno (vienen de GitHub Secrets, nunca
   están escritas en el código).
2. Guarda el snapshot de hoy en docs/data/historial.json (uno por cuenta).
3. Calcula el ahorro y la estimación de boleta del ciclo de facturación
   actual y lo guarda en docs/data/resumen.json.
4. Regenera docs/data/auth.json con el hash del PIN (nunca el PIN en texto
   plano), para que el sitio pueda validar el acceso sin exponerlo.

Si a una cuenta le faltan credenciales (no configuradas como secret), se
omite con una advertencia en vez de fallar todo el proceso.
"""
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tariff  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "docs" / "data"
HISTORIAL_PATH = DATA_DIR / "historial.json"
RESUMEN_PATH = DATA_DIR / "resumen.json"
AUTH_PATH = DATA_DIR / "auth.json"

CUENTAS_ENV = {
    "casa": {"usuario": "CASA_USUARIO", "password": "CASA_PASSWORD", "subdomain": "CASA_SUBDOMAIN"},
    "padres": {"usuario": "PADRES_USUARIO", "password": "PADRES_PASSWORD", "subdomain": "PADRES_SUBDOMAIN"},
}

# Ventana de historial que se conserva en el JSON servido al sitio (para no
# hacer crecer el archivo indefinidamente). Se guardan igual todos los días,
# pero solo se sirven los últimos N al front-end.
DIAS_HISTORIAL_VISIBLE = 120


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def cargar_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cargar_historial() -> dict:
    if HISTORIAL_PATH.exists():
        with open(HISTORIAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"casa": [], "padres": []}


def guardar_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def obtener_snapshot_hoy(usuario: str, password: str, subdomain: str) -> dict:
    from fusion_solar_py.client import FusionSolarClient

    client = FusionSolarClient(usuario, password, huawei_subdomain=subdomain)
    try:
        plant_ids = client.get_plant_ids()
        if not plant_ids:
            raise RuntimeError("La cuenta no tiene ninguna planta asociada en FusionSolar.")

        totales = dict(produccion_kwh=0.0, consumo_kwh=0.0, autoconsumo_kwh=0.0,
                        compra_red_kwh=0.0, inyeccion_red_kwh=0.0)

        for plant_id in plant_ids:
            plant_data = client.get_plant_stats(plant_id)
            last_values = client.get_last_plant_data(plant_data)
            totales["produccion_kwh"] += _num(last_values.get("totalProductPower"))
            totales["consumo_kwh"] += _num(last_values.get("totalUsePower"))
            totales["autoconsumo_kwh"] += _num(last_values.get("totalSelfUsePower"))
            totales["compra_red_kwh"] += _num(last_values.get("totalBuyPower"))
            totales["inyeccion_red_kwh"] += _num(last_values.get("totalOnGridPower"))

        totales["fecha"] = date.today().isoformat()
        return totales
    finally:
        try:
            client.log_out()
        except Exception:
            pass


def upsert_dia(historial_cuenta: list, snapshot: dict) -> list:
    historial_cuenta = [d for d in historial_cuenta if d["fecha"] != snapshot["fecha"]]
    historial_cuenta.append(snapshot)
    historial_cuenta.sort(key=lambda d: d["fecha"])
    return historial_cuenta


def actualizar_auth() -> None:
    pin = os.getenv("SITE_PIN")
    if not pin:
        print("[auth] SITE_PIN no configurado, se omite (el sitio quedará sin PIN).")
        return
    pin_hash = hashlib.sha256(pin.strip().encode("utf-8")).hexdigest()
    guardar_json(AUTH_PATH, {"pin_hash": pin_hash})
    print("[auth] auth.json actualizado (solo contiene el hash del PIN, no el PIN).")


def main():
    config = cargar_config()
    historial = cargar_historial()
    resumen = {"generado_en": date.today().isoformat(), "casas": {}}

    for clave_cuenta, env in CUENTAS_ENV.items():
        cfg_cuenta = config["cuentas"][clave_cuenta]
        nombre = cfg_cuenta["nombre"]
        usuario = os.getenv(env["usuario"])
        password = os.getenv(env["password"])
        subdomain = os.getenv(env["subdomain"], "la5")

        if not usuario or not password:
            print(f"[{nombre}] Faltan credenciales ({env['usuario']}/{env['password']}), se omite el fetch.")
        else:
            print(f"[{nombre}] Conectando a FusionSolar...")
            try:
                snap = obtener_snapshot_hoy(usuario, password, subdomain)
                historial[clave_cuenta] = upsert_dia(historial.get(clave_cuenta, []), snap)
                print(f"[{nombre}] OK: producción {snap['produccion_kwh']:.1f} kWh, "
                      f"inyección {snap['inyeccion_red_kwh']:.1f} kWh.")
            except Exception as exc:
                print(f"[{nombre}] ERROR al obtener datos de FusionSolar: {exc}")

        # Recalcular resumen del ciclo actual con lo que haya en el historial,
        # aunque el fetch de hoy haya fallado (usa lo guardado hasta ahora).
        tarifa = cfg_cuenta.get("tarifa", {})
        if not tarifa.get("precio_energia_kwh"):
            print(f"[{nombre}] config.yaml sin tarifa configurada todavía, se omite del resumen.")
            continue

        inicio, fin, _ = tariff.ciclo_actual(tarifa.get("dia_lectura_medidor", 1))
        lecturas_ciclo = [
            d for d in historial.get(clave_cuenta, [])
            if inicio.isoformat() <= d["fecha"] <= fin.isoformat()
        ]
        if lecturas_ciclo:
            estimacion = tariff.calcular_estimacion(clave_cuenta, nombre, tarifa, lecturas_ciclo)
            resumen["casas"][clave_cuenta] = estimacion.to_dict()

    # recortar historial servido al front-end a los últimos N días por cuenta
    historial_recortado = {
        clave: sorted(dias, key=lambda d: d["fecha"])[-DIAS_HISTORIAL_VISIBLE:]
        for clave, dias in historial.items()
    }

    guardar_json(HISTORIAL_PATH, historial_recortado)
    guardar_json(RESUMEN_PATH, resumen)
    actualizar_auth()
    print("Listo: historial.json, resumen.json y auth.json actualizados.")


if __name__ == "__main__":
    main()
