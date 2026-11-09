"""Pruebas de extraccion/texto.py."""
import json

from mi_pipeline.extraccion.texto import analizar, cargar_texto, formas_base


def test_cargar_texto_lee_el_campo_texto_del_json_de_ocr(tmp_path):
    archivo = tmp_path / "REC-0001.json"
    archivo.write_text(json.dumps({"texto": "Banco Andino DEMO S.A.\n"}), encoding="utf-8")
    assert cargar_texto(archivo) == "Banco Andino DEMO S.A."


def test_analizar_divide_el_texto_en_tokens():
    assert [t.text for t in analizar("Me cobraron dos veces.")][:2] == ["Me", "cobraron"]


def test_cobro_y_cobros_comparten_forma_base():
    assert formas_base("cobro")[0] == formas_base("cobros")[0]
