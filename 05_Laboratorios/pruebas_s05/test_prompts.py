"""Pruebas de llm/prompts.py (no necesitan GPU ni Ollama)."""
import json

from pydantic import BaseModel, Field

from mi_pipeline.llm.cliente_llm import RUTA_CONFIG, configuracion_llm
from mi_pipeline.llm.esquemas import Poliza, campos_de
from mi_pipeline.llm.prompts import CONTEXTO, CONTEXTO_GENERAL, CONTEXTO_LOTE_REAL, armar_mensajes, formato, ver_prompt

RUTA_EJEMPLOS = RUTA_CONFIG.parents[1] / configuracion_llm()["ejemplos"]      # la misma ruta que usa prompts.py


def rotulos(mensajes):
    """Las partes rotuladas del mensaje de sistema, en orden."""
    return [linea for linea in mensajes[0]["content"].splitlines() if linea in ("ROL", "CONTEXTO", "TAREA", "FORMATO")]


def test_cada_nivel_agrega_una_parte_del_prompt():
    esperado = {1: ["TAREA"], 2: ["ROL", "TAREA"], 3: ["ROL", "CONTEXTO", "TAREA"], 4: ["ROL", "CONTEXTO", "TAREA", "FORMATO"]}
    for nivel, partes in esperado.items():
        mensajes = armar_mensajes("Poliza: PZ-1", "poliza", nivel=nivel)
        assert rotulos(mensajes) == partes and mensajes[-1] == {"role": "user", "content": "DOCUMENTO\nPoliza: PZ-1"}


def test_un_contexto_propio_reemplaza_al_del_tipo():
    mensajes = armar_mensajes("texto", "oficio", nivel=4, contexto="Mi contexto del oficio.")
    assert "CONTEXTO\nMi contexto del oficio." in mensajes[0]["content"] and CONTEXTO["oficio"] not in mensajes[0]["content"]


def test_el_nivel_5_agrega_un_ejemplo_resuelto_salvo_en_contratos():
    poliza = armar_mensajes("Poliza: PZ-1", "poliza")              # sin nivel: toma llm.prompt_nivel del YAML (5)
    assert [m["role"] for m in poliza] == ["system", "user", "assistant", "user"]
    assert [m["role"] for m in armar_mensajes("Contrato N° CR-1", "contrato", nivel=5)] == ["system", "user"]


def test_los_ejemplos_traen_las_claves_de_su_esquema():
    for tipo, ejemplo in json.loads(RUTA_EJEMPLOS.read_text(encoding="utf-8")).items():
        assert list(ejemplo["respuesta"]) == campos_de(tipo) and ejemplo["documento"], tipo


def test_el_formato_trae_la_descripcion_de_cada_campo():
    texto = formato("poliza")
    for campo, datos in Poliza.model_json_schema()["properties"].items():
        assert f"- {campo}: {datos['description']}" in texto


class DocumentoReal(BaseModel):
    """Esquema propio, como el del laboratorio para casa."""
    empresa: str | None = Field(..., description="razón social de la empresa")


def test_un_tipo_sin_contexto_propio_usa_el_contexto_general(capsys):
    mensajes = armar_mensajes("x" * 900, "otro_tipo", nivel=5, esquema=DocumentoReal)
    assert len(mensajes) == 2 and CONTEXTO_GENERAL in mensajes[0]["content"]
    assert not any(contexto in mensajes[0]["content"] for contexto in CONTEXTO.values())
    assert "- empresa: razón social de la empresa" in mensajes[0]["content"]
    ver_prompt(mensajes, max_doc=100)
    assert "caracteres más del documento" in capsys.readouterr().out


def test_el_lote_real_no_se_presenta_como_ficticio():
    mensajes = armar_mensajes("HECHO DE IMPORTANCIA", "documento_real", nivel=5, esquema=DocumentoReal)
    texto = " ".join(m["content"] for m in mensajes)
    assert CONTEXTO_LOTE_REAL in texto and "DEMO" not in texto and "ficticio" not in texto.lower()
