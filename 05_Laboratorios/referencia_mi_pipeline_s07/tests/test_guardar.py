"""Pruebas de almacenamiento/guardar.py (no necesitan Tesseract ni un modelo de lenguaje)."""
from mi_pipeline.almacenamiento.guardar import exportar_parquet, guardar_resultados, leer_tabla

RESULTADOS = [
    {"archivo": "POL-0001.pdf", "tipo": "poliza", "formato": "pdf", "sha256": "aaa", "estado": "ok", "motivo": "", "paginas_ocr": 0, "caracteres": 500,
     "campos": {"numero_poliza": "PZ-1", "prima_anual": 2643.0, "beneficiario": None},
     "fases": {"ingesta": {"numero_poliza": "PZ-1", "prima_anual": None, "beneficiario": None},
               "ocr": {"numero_poliza": "PZ-1", "prima_anual": None, "beneficiario": None},
               "pln": {"numero_poliza": "PZ-1", "prima_anual": 2643.0, "beneficiario": None}},
     "segundos": {"control": 0.01, "ingesta": 0.02, "ocr": 0.0, "pln": 0.1}},
    {"archivo": "LOT-0007.pdf", "tipo": "", "formato": "pdf", "sha256": "bbb", "estado": "cuarentena", "motivo": "pdf_cifrado", "segundos": {"control": 0.01}},
    {"archivo": "LOT-0019.pdf", "tipo": "poliza", "formato": "pdf", "sha256": "aaa", "estado": "duplicado", "motivo": "mismo contenido que POL-0001.pdf"},
]


def test_guardar_dos_veces_deja_las_mismas_filas(tmp_path):
    base = tmp_path / "resultados.duckdb"
    primera = guardar_resultados(base, RESULTADOS)
    segunda = guardar_resultados(base, RESULTADOS)
    assert primera == segunda and (primera["documentos"], primera["campos"]) == (2, 3)
    assert guardar_resultados(base, []) == primera


def test_la_tabla_campos_dice_que_etapa_lleno_cada_campo_y_que_queda_por_revisar(tmp_path):
    guardar_resultados(tmp_path / "resultados.duckdb", RESULTADOS)
    campos = leer_tabla(tmp_path / "resultados.duckdb", "campos").set_index("campo")
    assert campos.loc["numero_poliza", "etapa"] == "ingesta" and campos.loc["prima_anual", "etapa"] == "pln"
    assert campos.loc["prima_anual", "tras_pln"] == "2643.0" and bool(campos.loc["beneficiario", "revisar"])


def test_el_parquet_trae_las_mismas_filas_que_la_base(tmp_path):
    base = tmp_path / "resultados.duckdb"
    guardar_resultados(base, RESULTADOS)
    filas = exportar_parquet(base, tmp_path / "parquet")
    assert filas == {"documentos": 2, "campos": 3} and (tmp_path / "parquet" / "campos.parquet").is_file()
    assert len(leer_tabla(tmp_path / "parquet", "campos")) == len(leer_tabla(base, "campos")) == 3
