"""Pruebas de S05 sobre documentos del corpus de práctica (solo referencia; no necesitan GPU)."""
import json

from pipeline_sbs.extraccion.hibrido import FASES, pln
from pipeline_sbs.ingesta.leer_documento import campos_rotulados, leer_documento, texto_de
from pipeline_sbs.llm.esquemas import campos_de
from pipeline_sbs.llm.trozos import cabe, estimar_tokens


def test_el_expediente_mixto_marca_sus_nueve_paginas_escaneadas(datos_practica):
    doc = leer_documento(datos_practica / "13_Expedientes" / "EXP-0002.pdf")
    assert len(doc["partes"]) == 64
    assert [p["pagina"] + 1 for p in doc["pendientes"]] == [14, 32, 34, 35, 49, 55, 57, 59, 63]
    assert not cabe(texto_de(doc), 12288)


def test_el_correo_deja_el_adjunto_jpg_pendiente_y_lee_el_adjunto_pdf(datos_practica):
    con_jpg = leer_documento(datos_practica / "06_Reclamos" / "REC-0001.eml")
    con_pdf = leer_documento(datos_practica / "06_Reclamos" / "REC-0002.eml")
    assert [p["origen"] for p in con_jpg["pendientes"]] == ["adjunto imagen"]
    assert not con_pdf["pendientes"] and len(texto_de(con_pdf)) > len(con_pdf["partes"][0])


def test_los_rotulos_de_la_poliza_coinciden_con_la_respuesta_correcta(datos_practica):
    correcto = json.loads((datos_practica / "10_Ground_Truth" / "POL-0001.json").read_text(encoding="utf-8"))["campos"]
    rotulados = campos_rotulados("poliza", leer_documento(datos_practica / "05_Polizas" / "POL-0001.pdf"))
    for campo in ("numero_poliza", "aseguradora", "dni", "suma_asegurada", "prima_anual", "moneda", "vigencia_desde", "vigencia_hasta"):
        assert rotulados[campo] == correcto[campo], campo
    assert rotulados["ruc"] is None   # el RUC va entre paréntesis junto a la aseguradora: sin rótulo propio, lo halla la regla de la fase 3


def test_el_contrato_de_14_paginas_no_cabe_en_el_contexto_de_serie(datos_practica):
    texto = texto_de(leer_documento(datos_practica / "04_Contratos" / "CON-0021.pdf"))
    assert estimar_tokens(texto) > 4096 and cabe(texto, 12288) and not cabe(texto, 4096)


def test_la_fase_de_pln_completa_el_dni_y_el_ruc_del_contrato_docx(datos_practica):
    doc = leer_documento(datos_practica / "04_Contratos" / "CON-0002.docx")
    previo = {campo: campos_rotulados("contrato", doc).get(campo) for campo in campos_de("contrato")}
    campos = pln("contrato", doc, previo)
    correcto = json.loads((datos_practica / "10_Ground_Truth" / "CON-0002.json").read_text(encoding="utf-8"))["campos"]
    assert campos["dni_cliente"] == correcto["dni_cliente"] and campos["ruc"] == correcto["ruc"]
    assert FASES[-1] == "solo_llm"
