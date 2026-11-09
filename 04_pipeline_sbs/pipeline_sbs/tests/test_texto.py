"""Pruebas de extraccion.texto: lectura del correo, carga del texto y análisis con spaCy."""
import json

import pytest

from pipeline_sbs.extraccion.texto import analizar, cargar_modelo, cargar_texto, formas_base, leer_correo
from pipeline_sbs.tests.conftest import crear_eml


@pytest.fixture(scope="module")
def modelo_spacy():
    try:
        return cargar_modelo()
    except OSError:
        pytest.skip("No está instalado ningún modelo de spaCy en español")


def test_leer_correo_separa_asunto_remitente_cuerpo_y_adjunto(tmp_path):
    eml = crear_eml(tmp_path / "REC-0001.eml", "Reclamo - cobro indebido", "Soy Ana Ruiz, DNI 99123456.", ("adjunto.jpg", b"\xff\xd8datos"))
    correo = leer_correo(eml)
    assert correo["asunto"] == "Reclamo - cobro indebido"
    assert correo["remitente"] == "ana@ejemplo.pe"
    assert correo["cuerpo"] == "Soy Ana Ruiz, DNI 99123456."
    assert correo["adjuntos"] == [("adjunto.jpg", b"\xff\xd8datos")]


def test_cargar_texto_del_json_de_ocr_del_eml_y_del_txt(tmp_path):
    ocr = tmp_path / "REC-0001.json"
    ocr.write_text(json.dumps({"texto": " Banco Andino DEMO S.A.\n"}), encoding="utf-8")
    eml = crear_eml(tmp_path / "REC-0002.eml", "Reclamo", "Cuerpo del correo")
    txt = tmp_path / "nota.txt"
    txt.write_text("texto plano\n", encoding="utf-8")
    assert cargar_texto(ocr) == "Banco Andino DEMO S.A."
    assert cargar_texto(eml) == "Cuerpo del correo"
    assert cargar_texto(txt) == "texto plano"


def test_cargar_texto_rechaza_una_extension_desconocida(tmp_path):
    with pytest.raises(ValueError):
        cargar_texto(tmp_path / "archivo.xyz")


def test_analizar_divide_en_tokens_con_forma_base(modelo_spacy):
    doc = analizar("Me cobraron los cobros indebidos.")
    assert [t.text for t in doc][:2] == ["Me", "cobraron"]
    assert doc[1].lemma_ == "cobrar"


def test_cobro_y_cobros_comparten_forma_base(modelo_spacy):
    assert formas_base("cobro")[0] == formas_base("cobros")[0] == "cobro"


def test_formas_base_omite_la_puntuacion(modelo_spacy):
    assert "." not in formas_base("Hola. Gracias.")
