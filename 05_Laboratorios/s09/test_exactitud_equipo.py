"""Pruebas de calidad/exactitud_equipo.py (sesión 9): la exactitud del lote contra las respuestas correctas de insumos/respuestas."""
import csv
import json

from mi_pipeline.almacenamiento.guardar import guardar_resultados
from mi_pipeline.calidad.exactitud_equipo import main, medir, valor_final


def corrida(tmp_path):
    """Una corrida mínima de dos documentos, guardada como la deja python -m mi_pipeline (tablas documentos y campos)."""
    salida = tmp_path / "resultados"
    resultados = [
        {"archivo": "OFI-9001.pdf", "tipo": "oficio", "estado": "ok", "campos": {"fecha": "2026-06-24", "plazo_dias": 15, "emisor": None},
         "fases": {"ocr": {"fecha": "2026-06-24"}, "pln": {"fecha": "2026-06-24", "plazo_dias": 15}}},
        {"archivo": "OFI-9002.pdf", "tipo": "oficio", "estado": "ok", "campos": {"fecha": "2026-07-01", "plazo_dias": 10, "emisor": "Intendencia DEMO"},
         "fases": {"pln": {"fecha": "2026-07-01", "plazo_dias": 10, "emisor": "Intendencia DEMO"}}},
    ]
    guardar_resultados(salida / "resultados.duckdb", resultados)
    respuestas = tmp_path / "respuestas"
    respuestas.mkdir()
    for doc, campos in (("OFI-9001", {"fecha": "2026-06-24", "plazo_dias": 15, "emisor": "Intendencia DEMO de Riesgos"}),
                        ("OFI-9002", {"fecha": "2026-07-02", "plazo_dias": 10, "emisor": "intendencia demo"})):
        (respuestas / f"{doc}.json").write_text(json.dumps({"doc_id": doc, "campos": campos}), encoding="utf-8")
    return salida, respuestas


def test_el_valor_final_conserva_el_numero_como_numero():
    assert valor_final({"valor": "15", "tras_ingesta": None, "tras_ocr": None, "tras_pln": "15"}) == 15
    assert valor_final({"valor": None, "tras_ingesta": None, "tras_ocr": None, "tras_pln": None}) is None


def test_la_exactitud_cuenta_correctos_y_vacios_por_campo(tmp_path):
    salida, respuestas = corrida(tmp_path)
    resumen = medir(salida, respuestas)
    assert resumen["documentos"] == 2 and resumen["esperados"] == 6
    assert resumen["correctos"] == 4   # dos plazos, una fecha y un emisor (sin importar mayúsculas)
    with open(salida / "exactitud_por_campo.csv", encoding="utf-8-sig") as f:
        filas = {fila["campo"]: fila for fila in csv.DictReader(f)}
    assert filas["emisor"]["vacios"] == "1" and filas["plazo_dias"]["exactitud"] == "1.0"


def test_un_campo_vacio_lleva_el_documento_a_revision_humana(tmp_path):
    salida, respuestas = corrida(tmp_path)
    assert medir(salida, respuestas)["revision_humana"] == 1
    salida_json = json.loads((salida / "json" / "OFI-9001.json").read_text(encoding="utf-8"))
    assert salida_json["revision_humana"] is True and salida_json["campos"]["emisor"] is None


def test_sin_la_base_mide_con_las_salidas_json_que_subio_el_lider(tmp_path):
    salida, respuestas = corrida(tmp_path)
    assert main(["--salida", str(salida), "--solo-json"]) == 0          # el líder: solo las 20 salidas JSON
    (salida / "resultados.duckdb").unlink()                             # la base no viaja por GitHub
    resumen = medir(salida, respuestas)                                 # calidad, en otra máquina
    assert resumen["correctos"] == 4 and resumen["documentos"] == 2


def test_sin_corrida_la_linea_de_comandos_avisa_y_no_inventa(tmp_path):
    assert main(["--salida", str(tmp_path / "no_existe"), "--respuestas", str(tmp_path)]) == 1
