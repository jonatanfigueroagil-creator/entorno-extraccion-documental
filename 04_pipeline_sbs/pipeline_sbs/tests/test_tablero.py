"""Pruebas del tablero (S07): DuckDB lee el registro tal como está y las alertas comparan las cifras con sus umbrales."""
import json

import pytest

from pipeline_sbs.monitoreo.metricas import alertas, calcular_metricas, tablero, umbrales_de
from pipeline_sbs.orquestacion.config import cargar_config


def escribir_registro(ruta, corrida="c1", segundos=60, fallidos=1, revisar=2, caracteres=500, hora=9):
    """Un registro con una corrida de 10 documentos: los fallidos no traen confianza (claves distintas por evento)."""
    eventos = [{"ts": f"2026-11-20T{hora:02d}:00:00.000+00:00", "evento": "corrida_inicio", "corrida_id": corrida, "version": "s07-v1"}]
    for i in range(10):
        nombre = f"POL-{i + 1:04d}.pdf"
        if i < fallidos:
            eventos.append({"ts": f"2026-11-20T{hora:02d}:00:30.000+00:00", "evento": "documento_fallido", "corrida_id": corrida, "archivo": nombre,
                            "tipo": "poliza", "error": "archivo_vacio"})
        else:
            eventos.append({"ts": f"2026-11-20T{hora:02d}:00:30.000+00:00", "evento": "documento_procesado", "corrida_id": corrida, "archivo": nombre,
                            "tipo": "poliza", "confianza": 0.9, "ruta": "revisar" if i >= 10 - revisar else "aceptar",
                            "causas_revision": ["confianza_baja"] if i >= 10 - revisar else [], "caracteres": caracteres if i != 9 else 60,
                            "paginas": 1, "paginas_ocr": 0, "campos": 13, "campos_nulos": 1})
    eventos.append({"ts": f"2026-11-20T{hora:02d}:{segundos // 60:02d}:{segundos % 60:02d}.000+00:00", "evento": "corrida_fin", "corrida_id": corrida})
    with open(ruta, "a", encoding="utf-8") as archivo:
        for evento in eventos:
            archivo.write(json.dumps(evento) + "\n")
    return ruta


def test_las_cifras_salen_del_registro(tmp_path):
    m = calcular_metricas(escribir_registro(tmp_path / "registro.jsonl"))
    assert (m["documentos"], m["procesados"], m["fallidos"]) == (10, 9, 1)
    assert m["pct_errores"] == 0.1 and m["errores_por_tipo"] == {"archivo_vacio": 1}
    assert m["documentos_por_minuto"] == 10.0 and m["confianza_media"] == 0.9 and m["pct_revision"] == pytest.approx(2 / 9, abs=0.001)
    assert m["causas_revision"] == {"confianza_baja": 2} and m["pct_campos_nulos"] == pytest.approx(1 / 13, abs=0.001)


def test_se_mide_la_ultima_corrida_del_registro(tmp_path):
    ruta = escribir_registro(tmp_path / "registro.jsonl", corrida="antes", fallidos=3)
    escribir_registro(ruta, corrida="despues", fallidos=0, hora=10)
    assert calcular_metricas(ruta)["corrida_id"] == "despues" and calcular_metricas(ruta)["fallidos"] == 0
    assert calcular_metricas(ruta, "antes")["fallidos"] == 3


def test_las_alertas_saltan_cuando_una_cifra_cruza_su_umbral(tmp_path):
    umbrales = umbrales_de(cargar_config())
    m = calcular_metricas(escribir_registro(tmp_path / "registro.jsonl", fallidos=2, revisar=7, caracteres=500))
    avisos = alertas(m, umbrales)
    assert any(a.startswith("Errores") for a in avisos) and any(a.startswith("Revisión") for a in avisos)
    assert any(a.startswith("Texto") for a in avisos), "el PDF de 60 caracteres por página debe delatarse"
    assert "ALERTA" in tablero(m, avisos)


def test_sin_alertas_el_tablero_esta_en_verde(tmp_path):
    m = calcular_metricas(escribir_registro(tmp_path / "registro.jsonl", fallidos=0, revisar=1))
    m["caracteres_por_pagina"]["minimo"] = 500
    assert alertas(m, umbrales_de(cargar_config())) == [] and "Sin alertas" in tablero(m, [])
