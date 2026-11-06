"""Pruebas del primer pipeline: el lote de 6 trampas termina, deja un registro por archivo y es idempotente."""
from pathlib import Path

import pandas as pd
import pytest

from pipeline_sbs.ingesta.cargador import CargadorDocumentos, tabla_resultados
from pipeline_sbs.orquestacion.pipeline import (
    COLUMNAS,
    calcular_estadisticas,
    ejecutar_pipeline,
    leer_lote,
    normalizar_lote,
    registrar_errores,
)

MOTIVOS = {
    "A03_extension_falsa.pdf": "extension_falsa",
    "A04_docx_corrupto.docx": "docx_corrupto",
    "A05_cifrado.pdf": "pdf_cifrado",
    "A06_truncado.pdf": "pdf_danado",
    "A07_vacio.pdf": "archivo_vacio",
}


def _config(tmp_path: Path) -> dict:
    return {"cuarentena": tmp_path / "q"}


def test_termina_con_un_registro_por_archivo(lote_trampas, tmp_path):
    tabla = ejecutar_pipeline(lote_trampas, _config(tmp_path))
    assert isinstance(tabla, pd.DataFrame) and list(tabla.columns) == COLUMNAS
    assert tabla["archivo"].tolist() == sorted(p.name for p in lote_trampas.iterdir())
    assert len(tabla) == 12


def test_cada_trampa_tiene_su_motivo_y_va_a_cuarentena(lote_trampas, tmp_path):
    tabla = ejecutar_pipeline(lote_trampas, _config(tmp_path)).set_index("archivo")
    for archivo, motivo in MOTIVOS.items():
        assert tabla.loc[archivo, "estado"] == "fallo" and tabla.loc[archivo, "motivo"] == motivo, archivo
    assert tabla.loc["A08_copia.pdf", "estado"] == "duplicado"
    assert tabla.loc["A08_copia.pdf", "duplicado_de"] == "A01_nativo.pdf"
    copias = sorted(p.name for p in (tmp_path / "q").iterdir() if not p.name.endswith((".json", ".jsonl")))
    assert copias == sorted(MOTIVOS)
    assert all((lote_trampas / archivo).exists() for archivo in MOTIVOS), "la cuarentena copia, no mueve"


def test_escaneado_e_imagen_requieren_ocr(lote_trampas, tmp_path):
    tabla = ejecutar_pipeline(lote_trampas, _config(tmp_path)).set_index("archivo")
    assert tabla.loc[["A02_escaneado.pdf", "A12_voucher.png"], "requiere_ocr"].all()
    assert not tabla.loc[["A01_nativo.pdf", "A09_contrato.docx", "A10_reclamo.eml", "A11_tarifario.html"],
                         "requiere_ocr"].any()


def test_es_idempotente(lote_trampas, tmp_path):
    primera = ejecutar_pipeline(lote_trampas, _config(tmp_path))
    segunda = ejecutar_pipeline(lote_trampas, _config(tmp_path))
    clave = [c for c in COLUMNAS if c not in ("segundos", "detalle")]
    assert primera[clave].equals(segunda[clave])
    assert primera.attrs["estadisticas"].equals(segunda.attrs["estadisticas"])
    nombres = sorted(p.name for p in (tmp_path / "q").iterdir())
    assert len(nombres) == len(set(nombres)) and not any(n.endswith(".tmp") for n in nombres)


def test_coincide_con_el_cargador_de_la_clase(lote_trampas, tmp_path):
    tabla = ejecutar_pipeline(lote_trampas, _config(tmp_path))
    esperado = tabla_resultados(CargadorDocumentos(lote_trampas, tmp_path / "q2", esperas=(0, 0, 0)).cargar_lote())
    clave = ["archivo", "tipo", "formato", "estado", "motivo", "paginas", "caracteres", "requiere_ocr", "sha256",
             "duplicado_de"]
    assert tabla[clave].equals(esperado[clave])


def test_estadisticas_con_total_y_pct_sobre_ok(lote_trampas, tmp_path):
    estadisticas = ejecutar_pipeline(lote_trampas, _config(tmp_path)).attrs["estadisticas"]
    total = estadisticas.loc["TOTAL"]
    assert (total["n"], total["ok"], total["fallo"], total["duplicado"]) == (12, 6, 5, 1)
    assert total["requiere_ocr"] == 2 and total["pct_requiere_ocr"] == round(100 * 2 / 6, 1)


def test_las_etapas_se_pueden_usar_por_separado(lote_trampas, tmp_path):
    registros = normalizar_lote(leer_lote(lote_trampas))
    assert len(registros) == 12 and all("texto" in fila for fila in registros)
    assert registrar_errores(registros, tmp_path / "q") == 5
    assert (tmp_path / "q" / "registro_errores.jsonl").read_text(encoding="utf-8").count("\n") == 5
    assert calcular_estadisticas(pd.DataFrame(columns=["tipo", "estado", "requiere_ocr"])).empty


def test_carpeta_inexistente_avisa(tmp_path):
    with pytest.raises(NotADirectoryError):
        ejecutar_pipeline(tmp_path / "no_existe", _config(tmp_path))
