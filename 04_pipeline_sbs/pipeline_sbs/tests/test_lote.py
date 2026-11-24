"""Pruebas de orquestacion/lote.py con cuatro archivos (digitales: no necesitan Tesseract ni un modelo de lenguaje)."""
import duckdb
import pymupdf
import pytest

from pipeline_sbs.orquestacion.config import cargar_config
from pipeline_sbs.orquestacion.lote import ejecutar_lote


@pytest.fixture
def bandeja(tmp_path):
    """Una póliza, su copia con otro nombre, un tarifario y un archivo vacío."""
    carpeta = tmp_path / "bandeja"
    carpeta.mkdir()
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "POLIZA DE SEGURO - CONDICIONES PARTICULARES\nPoliza: PZ-2026-000001\nRUC 20992371634\nRamo: Vehicular")
    pdf.save(str(carpeta / "POL-0001.pdf"))
    pdf.close()
    (carpeta / "POL-0002.pdf").write_bytes((carpeta / "POL-0001.pdf").read_bytes())
    (carpeta / "TAR-0001.html").write_text("<html><body><p>RUC 20992371634</p><p>Vigente desde 01/01/2026</p></body></html>", encoding="utf-8")
    (carpeta / "LOT-0016.pdf").write_bytes(b"")
    return carpeta


def filas_del_registro(cfg):
    """Las filas del registro, en orden de archivo."""
    con = duckdb.connect(cfg.almacenamiento.duckdb, read_only=True)
    try:
        return con.execute("SELECT archivo, estado, motivo FROM registro ORDER BY archivo").fetchall()
    finally:
        con.close()


def test_el_lote_en_serie_deja_un_estado_por_archivo_y_un_solo_escritor(bandeja, tmp_path):
    cfg = cargar_config().en_carpeta(tmp_path / "salidas").con(modo="secuencial")
    resumen = ejecutar_lote(bandeja, cfg)
    assert (resumen.archivos, resumen.ok, resumen.cuarentena, resumen.duplicados, resumen.errores) == (4, 2, 1, 1, 0)
    assert resumen.escritos == 4 and filas_del_registro(cfg) == [
        ("LOT-0016.pdf", "cuarentena", "archivo_vacio"), ("POL-0001.pdf", "ok", ""),
        ("POL-0002.pdf", "duplicado", "mismo contenido que POL-0001.pdf"), ("TAR-0001.html", "ok", "")]
    assert (tmp_path / "salidas" / "cuarentena" / "LOT-0016.pdf").is_file()


def test_la_segunda_corrida_no_procesa_nada(bandeja, tmp_path):
    cfg = cargar_config().en_carpeta(tmp_path / "salidas").con(modo="secuencial")
    ejecutar_lote(bandeja, cfg)
    antes = filas_del_registro(cfg)
    segunda = ejecutar_lote(bandeja, cfg)
    assert segunda.saltados == 4 and segunda.resultados == [] and filas_del_registro(cfg) == antes


def test_con_procesos_salen_los_mismos_campos_que_en_serie(bandeja, tmp_path):
    base = cargar_config()
    serie = ejecutar_lote(bandeja, base.en_carpeta(tmp_path / "serie").con(modo="secuencial"))
    procesos = ejecutar_lote(bandeja, base.en_carpeta(tmp_path / "procesos").con(modo="procesos", trabajadores=2))
    campos_de_cada_uno = lambda resumen: {r["archivo"]: r.get("campos") for r in resumen.resultados}
    assert campos_de_cada_uno(serie) == campos_de_cada_uno(procesos) and procesos.trabajadores == 2 and procesos.escritos == 4
