"""Pruebas de orquestacion.pipeline_extraccion: correo -> OCR del adjunto -> campos -> motivo -> ruta."""
import json
import os
from pathlib import Path

import pytest

from pipeline_sbs.clasificacion.motivo import entrenar
from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.orquestacion import pipeline_extraccion
from pipeline_sbs.orquestacion.pipeline_extraccion import extraer, extraer_campos, extraer_lote, leer_adjunto
from pipeline_sbs.tests.conftest import crear_eml

CUERPO = ("Buenas, soy Jorge Fuentes Bravo, DNI 99929470. En Banco Cordillera DEMO S.A. pedi mi tarjeta hace semanas "
          "y nadie me la entrega. Fueron dos mil seiscientos cuarenta y tres soles en mi prestamo personal. "
          "Mi cel es 999 000 680.")
OCR = ("Banco Cordillera DEMO S.A.\nEstado de cuenta - prestamo personal\nCliente: Jorge Fuentes Bravo DNI 99929470\n"
       "10/09/2026 Cargo reclamado (demora en entrega) 2,643.00")


@pytest.fixture
def correo(tmp_path):
    eml = crear_eml(tmp_path / "REC-0001.eml", "Reclamo - demora en entrega", CUERPO, ("adjunto_REC-0001.jpg", b"\xff\xd8"))
    ocr = tmp_path / "ocr"
    ocr.mkdir()
    (ocr / "REC-0001.json").write_text(json.dumps({"texto": OCR, "confianza": 0.95, "score": 0.95, "decision": "aceptar"}), encoding="utf-8")
    return eml, ocr


@pytest.fixture(scope="module")
def modelo():
    frases = ["pedi mi tarjeta hace semanas y nadie me la entrega", "me cobraron una comision que nunca autorice",
              "me descontaron dos veces la misma cuota"]
    etiquetas = ["demora en entrega", "cobro indebido", "cargo duplicado"]
    return entrenar([f"{f} caso {i}" for i in range(5) for f in frases], [e for _ in range(5) for e in etiquetas])


def test_la_configuracion_trae_las_claves_de_s04():
    cfg = cargar_configuracion()
    assert cfg["extraccion"]["modelo_spacy"] == "es_core_news_md"
    assert cfg["extraccion"]["modelo_ner"] == "Davlan/xlm-roberta-base-ner-hrl"
    assert cfg["extraccion"]["dispositivo"] in ("auto", "cpu", "cuda")
    assert 0 < cfg["clasificacion"]["umbral_confianza"] <= 1 and cfg["clasificacion"]["semilla"] == 2026
    assert 0 < cfg["calidad"]["umbral_f1"] <= 1
    assert len(cfg["clasificacion"]["etiquetas_motivo"]) == 6


def test_leer_adjunto_usa_el_ocr_guardado(correo):
    _, ocr = correo
    lectura = leer_adjunto("REC-0001", [("a.jpg", b"")], cargar_configuracion(), ocr)
    assert lectura["motor"] == "ocr_guardado" and lectura["decision"] == "aceptar" and "Cargo reclamado" in lectura["texto"]


def test_leer_adjunto_sin_adjunto_rechaza():
    lectura = leer_adjunto("REC-9999", [], cargar_configuracion(), None)
    assert lectura["decision"] == "rechazar" and lectura["texto"] == ""


def test_extraer_campos_une_reglas_y_remitente():
    campos = extraer_campos("De: jorge.fuentes6@ejemplo.pe\n" + CUERPO + "\n" + OCR, cargar_configuracion())
    assert campos["dni"] == "99929470" and campos["nombre"] == "Jorge Fuentes Bravo"
    assert campos["monto_reclamado"] == 2643.0 and campos["fecha"] == "2026-09-10"
    assert campos["entidad"] == "Banco Cordillera DEMO S.A." and campos["telefono"] == "999 000 680"
    assert campos["correo"] == "jorge.fuentes6@ejemplo.pe" and campos["producto"] == "prestamo personal"
    assert "numero_reclamo" not in campos   # ninguna regla lo busca: no consta en el documento


def test_extraer_devuelve_el_json_por_correo(correo, modelo):
    eml, ocr = correo
    resultado = extraer(eml, modelo_motivo=modelo, carpeta_ocr=ocr)
    assert set(resultado) == {"id", "archivo", "campos", "confianza_motivo", "ocr", "notas", "faltantes", "causas_revision", "ruta", "segundos"}
    assert resultado["id"] == "REC-0001" and resultado["campos"]["motivo"] == "demora en entrega"
    assert resultado["faltantes"] == [] and resultado["ruta"] == "aceptar" and resultado["causas_revision"] == []
    assert resultado["campos"]["numero_reclamo"] is None and resultado["notas"]["numero_reclamo"] == "no consta en el documento"
    assert resultado["ocr"]["decision"] == "aceptar"
    json.dumps(resultado)   # se puede guardar como JSON para S05


def test_extraer_sin_modelo_de_motivo_manda_a_revision(correo):
    eml, ocr = correo
    resultado = extraer(eml, carpeta_ocr=ocr)
    assert resultado["campos"]["motivo"] is None and resultado["confianza_motivo"] == 0.0 and resultado["ruta"] == "revisar"


def test_extraer_con_ocr_rechazado_manda_a_revision(tmp_path, modelo):
    eml = crear_eml(tmp_path / "REC-0002.eml", "Reclamo", CUERPO)
    resultado = extraer(eml, modelo_motivo=modelo, carpeta_ocr=tmp_path)
    assert resultado["ocr"]["decision"] == "rechazar" and resultado["ruta"] == "revisar"
    assert "fecha" in resultado["faltantes"]


def test_extraer_respeta_la_ruta_revisar_del_ocr_aunque_todo_lo_demas_este_bien(correo, modelo):
    eml, ocr = correo
    (ocr / "REC-0001.json").write_text(json.dumps({"texto": OCR, "confianza": 0.7, "score": 0.6, "decision": "revisar"}), encoding="utf-8")
    resultado = extraer(eml, modelo_motivo=modelo, carpeta_ocr=ocr)
    assert resultado["faltantes"] == [] and resultado["ruta"] == "revisar" and resultado["causas_revision"] == ["ruta del OCR"]


def test_extraer_registra_un_evento_por_etapa(correo, modelo, caplog):
    eml, ocr = correo
    with caplog.at_level("INFO", logger="pipeline_sbs"):
        extraer(eml, modelo_motivo=modelo, carpeta_ocr=ocr)
    assert [r.getMessage() for r in caplog.records] == ["etapa_texto", "etapa_ocr", "etapa_campos", "etapa_motivo", "etapa_ruta"]
    assert all(r.correo == "REC-0001" for r in caplog.records)


def test_extraer_lote_no_se_detiene_ante_un_correo_con_error(tmp_path, modelo, monkeypatch):
    crear_eml(tmp_path / "REC-0001.eml", "Reclamo", CUERPO, ("a.jpg", b"\xff"))
    crear_eml(tmp_path / "REC-0002.eml", "Reclamo", CUERPO, ("a.jpg", b"\xff"))

    def con_falla(id_correo, *resto):
        if id_correo == "REC-0001":
            raise OSError("adjunto ilegible")
        return {"texto": OCR, "confianza": 0.9, "score": 0.9, "decision": "aceptar", "motor": "prueba"}
    monkeypatch.setattr(pipeline_extraccion, "leer_adjunto", con_falla)
    resultados = extraer_lote(tmp_path, modelo_motivo=modelo)
    assert [r["id"] for r in resultados] == ["REC-0001", "REC-0002"]
    assert resultados[0]["ruta"] == "revisar" and "adjunto ilegible" in resultados[0]["error"]
    assert resultados[1]["ruta"] in ("aceptar", "revisar") and "error" not in resultados[1]


def test_extraer_con_ocr_real_sobre_un_reclamo_de_practica(datos_practica):
    """Corre Tesseract sobre un adjunto real del corpus (se omite si no hay Tesseract o datos)."""
    from pipeline_sbs.orquestacion.pipeline_ocr import configurar_tesseract

    try:
        configurar_tesseract(cargar_configuracion())
    except RuntimeError:
        pytest.skip("Tesseract no está instalado en esta máquina")
    eml = Path(datos_practica) / "06_Reclamos" / "REC-0001.eml"
    if not eml.is_file():
        pytest.skip("No está REC-0001.eml en los datos de práctica")
    resultado = extraer(eml)
    assert resultado["campos"]["dni"] == "99929470" and resultado["campos"]["fecha"] == "2026-09-10"
    assert resultado["ocr"]["motor"] == "tesseract" and os.path.basename(resultado["archivo"]) == "REC-0001.eml"
