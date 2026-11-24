"""Pruebas del arranque seguro (S07): si falta algo, el pipeline se detiene antes de procesar, con un mensaje claro."""
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pymupdf

import pipeline_sbs
from pipeline_sbs.__main__ import main
from pipeline_sbs.config.secretos import verificar_arranque
from pipeline_sbs.orquestacion.config import cargar_config
from pipeline_sbs.orquestacion.lote import ejecutar_lote


def crear_bandeja(tmp_path):
    """Dos pólizas digitales."""
    carpeta = tmp_path / "bandeja"
    carpeta.mkdir()
    for n in (1, 2):
        pdf = pymupdf.open()
        pdf.new_page().insert_text((72, 72), f"POLIZA DE SEGURO - CONDICIONES PARTICULARES\nPoliza: PZ-2026-00000{n}\nRamo: Vehicular")
        pdf.save(str(carpeta / f"POL-000{n}.pdf"))
        pdf.close()
    return carpeta


def test_con_todo_en_orden_no_hay_problemas(tmp_path):
    assert verificar_arranque(cargar_config(), crear_bandeja(tmp_path), tmp_path / "salidas") == []


def test_sin_tesseract_el_arranque_lo_dice(tmp_path, monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", str(tmp_path / "no_existe" / "tesseract.exe"))
    problemas = verificar_arranque(cargar_config(), crear_bandeja(tmp_path), tmp_path / "salidas")
    assert len(problemas) == 1 and "Tesseract" in problemas[0]


def test_la_salida_no_puede_estar_dentro_de_la_entrada(tmp_path):
    bandeja = crear_bandeja(tmp_path)
    problemas = verificar_arranque(cargar_config(), bandeja, bandeja / "salidas")
    assert any("dentro de la de entrada" in p for p in problemas)
    assert any("no existe" in p for p in verificar_arranque(cargar_config(), tmp_path / "otra", tmp_path / "salidas"))


def test_el_comando_se_detiene_antes_de_procesar_y_deja_constancia(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESSERACT_CMD", str(tmp_path / "no_existe" / "tesseract.exe"))
    salida = tmp_path / "salidas"
    assert main(["--entrada", str(crear_bandeja(tmp_path)), "--salida", str(salida)]) == 3
    assert "Arranque detenido" in capsys.readouterr().err
    assert not (salida / "resultados.duckdb").exists(), "no se procesa nada"
    evento = json.loads((salida / "registro.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert evento["evento"] == "arranque_fallido" and "Tesseract" in evento["problemas"][0]


def test_el_comando_informa_su_version():
    corrida = subprocess.run([sys.executable, "-m", "pipeline_sbs", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(Path(pipeline_sbs.__file__).resolve().parents[1]))
    assert corrida.returncode == 0 and "0.7.0" in corrida.stdout


def test_los_datos_de_entrada_se_abren_solo_para_leer(tmp_path):
    bandeja = crear_bandeja(tmp_path)
    huellas = {r.name: hashlib.sha256(r.read_bytes()).hexdigest() for r in bandeja.iterdir()}
    for ruta in bandeja.iterdir():
        os.chmod(ruta, stat.S_IREAD)        # solo lectura: si el pipeline intentara escribir, fallaría
    try:
        resumen = ejecutar_lote(bandeja, cargar_config().con(modo="secuencial").en_carpeta(tmp_path / "salidas"))
        assert resumen.ok == 2
        assert {r.name: hashlib.sha256(r.read_bytes()).hexdigest() for r in bandeja.iterdir()} == huellas
    finally:
        for ruta in bandeja.iterdir():
            os.chmod(ruta, stat.S_IREAD | stat.S_IWRITE)
