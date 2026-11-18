"""Pruebas de almacenamiento/reporte.py (no necesitan Tesseract ni un modelo de lenguaje)."""
from pipeline_sbs.almacenamiento.guardar import exportar_parquet, guardar_resultados, leer_tabla
from pipeline_sbs.almacenamiento.reporte import escribir_reporte, tabla_exactitud
from pipeline_sbs.orquestacion.registro import abrir_registro, marcar

RESULTADOS = [
    {"archivo": "POL-0001.pdf", "tipo": "poliza", "formato": "pdf", "sha256": "aaa", "estado": "ok", "motivo": "", "paginas_ocr": 0, "caracteres": 500,
     "campos": {"numero_poliza": "PZ-1", "prima_anual": 2643.0, "beneficiario": None},
     "fases": {"ingesta": {"numero_poliza": "PZ-1", "prima_anual": None, "beneficiario": None},
               "ocr": {"numero_poliza": "PZ-1", "prima_anual": None, "beneficiario": None},
               "pln": {"numero_poliza": "PZ-1", "prima_anual": 2643.0, "beneficiario": None}},
     "segundos": {"control": 0.01, "ingesta": 0.02, "ocr": 1.5, "pln": 0.1}},
    {"archivo": "LOT-0007.pdf", "tipo": "", "formato": "pdf", "sha256": "bbb", "estado": "cuarentena", "motivo": "pdf_cifrado", "segundos": {"control": 0.01}},
]


def base_de_prueba(tmp_path):
    """Una base con el registro de dos archivos y sus resultados."""
    base = tmp_path / "resultados.duckdb"
    con = abrir_registro(base)
    marcar(con, "aaa", "POL-0001.pdf", "ok")
    marcar(con, "bbb", "LOT-0007.pdf", "cuarentena", "pdf_cifrado")
    con.close()
    guardar_resultados(base, RESULTADOS)
    return base


def test_la_exactitud_se_mide_despues_de_cada_etapa(tmp_path):
    campos = leer_tabla(base_de_prueba(tmp_path), "campos")
    correctos = {"POL-0001": {"numero_poliza": "PZ-1", "prima_anual": 2643.0, "beneficiario": "Ana Paz Ruiz"}}
    por_fase, por_tipo = tabla_exactitud(campos, correctos, lambda valor, correcto: valor == correcto)
    assert list(por_fase["correctos"]) == [1, 1, 2] and list(por_fase["esperados"]) == [3, 3, 3]
    assert por_tipo.to_dict("records") == [{"tipo": "poliza", "ingesta": "1/3", "ocr": "1/3", "pln": "2/3"}]


def test_el_reporte_sale_de_la_base_o_del_parquet_y_muestra_cuarentena_y_revisar(tmp_path):
    base = base_de_prueba(tmp_path)
    exportar_parquet(base, tmp_path / "parquet")
    for origen, nombre in ((base, "desde_base.html"), (tmp_path / "parquet", "desde_parquet.html")):
        pagina = escribir_reporte(origen, tmp_path / nombre).read_text(encoding="utf-8")
        assert "pdf_cifrado" in pagina and "beneficiario" in pagina and "Tiempo por etapa" in pagina and 'charset="utf-8"' in pagina
