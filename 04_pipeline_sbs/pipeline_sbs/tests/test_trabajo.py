"""Pruebas de orquestacion/trabajo.py (documentos digitales: no necesitan Tesseract ni un modelo de lenguaje)."""
import os

import pymupdf

from pipeline_sbs.orquestacion.config import cargar_config
from pipeline_sbs.orquestacion.trabajo import procesar_archivo


def crear_poliza(ruta):
    """Un PDF digital de una página con los rótulos de una póliza."""
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "POLIZA DE SEGURO - CONDICIONES PARTICULARES\nPoliza: PZ-2026-000001\nRUC 20992371634\nRamo: Vehicular")
    pdf.save(str(ruta))
    pdf.close()
    return ruta


def test_el_trabajo_devuelve_el_resultado_con_intentos_segundos_y_proceso(tmp_path):
    r = procesar_archivo(crear_poliza(tmp_path / "POL-0001.pdf"), "poliza", cargar_config())
    assert r["estado"] == "ok" and r["intentos"] == 1 and r["segundos_total"] > 0 and r["proceso"] == os.getpid()
    assert r["campos"]["numero_poliza"] == "PZ-2026-000001"


def test_un_archivo_con_error_no_lanza_nada_y_dice_en_que_etapa_fallo(tmp_path):
    cfg = cargar_config().con(etapas=["ingesta", "ocr", "pln"])
    r = procesar_archivo(tmp_path / "no_existe.pdf", "poliza", cfg)
    assert r["estado"] == "error" and r["motivo"] == "error_en_etapa:ingesta" and "FileNotFoundError" in r["detalle"]
