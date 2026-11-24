"""Pruebas de la línea de comandos, __main__.py (documentos digitales: no necesitan Tesseract ni un modelo de lenguaje)."""
import subprocess
import sys
from pathlib import Path

import pymupdf

import pipeline_sbs
from pipeline_sbs.__main__ import main


def crear_bandeja(tmp_path):
    """Una póliza digital y un archivo vacío."""
    carpeta = tmp_path / "bandeja"
    carpeta.mkdir()
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "POLIZA DE SEGURO - CONDICIONES PARTICULARES\nPoliza: PZ-2026-000001\nRUC 20992371634\nRamo: Vehicular")
    pdf.save(str(carpeta / "POL-0001.pdf"))
    pdf.close()
    (carpeta / "LOT-0016.pdf").write_bytes(b"")
    return carpeta


def test_la_linea_de_comandos_corre_de_punta_a_punta_y_deja_el_reporte(tmp_path, capsys):
    salida = tmp_path / "salidas"
    assert main(["--entrada", str(crear_bandeja(tmp_path)), "--salida", str(salida), "--modo", "secuencial"]) == 0
    assert (salida / "reporte.html").is_file() and (salida / "parquet" / "registro.parquet").is_file() and (salida / "resultados.duckdb").is_file()
    assert "1 ok | 1 en cuarentena" in capsys.readouterr().out


def test_una_clave_mal_escrita_detiene_el_comando_antes_de_procesar(tmp_path, capsys):
    ruta = tmp_path / "pipeline.yaml"
    ruta.write_text("orquestacion:\n  trabajdores: 8\nreintentos: {}\ncuarentena: {}\nalmacenamiento: {}\n", encoding="utf-8")
    assert main(["--entrada", str(crear_bandeja(tmp_path)), "--config", str(ruta), "--salida", str(tmp_path / "salidas")]) == 2
    assert "trabajdores" in capsys.readouterr().err and not (tmp_path / "salidas").exists()


def test_el_paquete_se_ejecuta_con_python_m_y_muestra_su_ayuda():
    corrida = subprocess.run([sys.executable, "-m", "pipeline_sbs", "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(Path(pipeline_sbs.__file__).resolve().parents[1]))
    assert corrida.returncode == 0 and "--trabajadores" in corrida.stdout and "--entrada" in corrida.stdout
