"""Pruebas de orquestacion/etapas.py (documentos digitales: no necesitan Tesseract ni un modelo de lenguaje)."""
import pymupdf

from pipeline_sbs.orquestacion import etapas
from pipeline_sbs.orquestacion.config import cargar_config
from pipeline_sbs.orquestacion.etapas import ETAPAS, ejecutar_etapas

POLIZA = ("POLIZA DE SEGURO - CONDICIONES PARTICULARES\nPoliza: PZ-2026-000001\nAseguradora: Seguros Sur DEMO S.A.\n"
          "RUC 20992371634\nRamo: Vehicular\nDocumento ficticio con fines de capacitacion")


def crear_poliza(ruta):
    """Un PDF digital de una página con los rótulos de una póliza."""
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), POLIZA)
    pdf.save(str(ruta))
    pdf.close()
    return ruta


def test_cada_etapa_declara_su_contrato():
    assert list(ETAPAS) == ["control", "ingesta", "ocr", "pln"]
    assert all(etapa.recibe and etapa.entrega for etapa in ETAPAS.values())


def test_un_pdf_digital_recorre_las_cuatro_etapas(tmp_path):
    r = ejecutar_etapas(crear_poliza(tmp_path / "POL-0001.pdf"), "poliza", cargar_config())
    assert r["estado"] == "ok" and list(r["fases"]) == ["ingesta", "ocr", "pln"] and set(r["segundos"]) == {"control", "ingesta", "ocr", "pln"}
    assert r["campos"]["numero_poliza"] == "PZ-2026-000001" and r["campos"]["ruc"] == "20992371634"
    assert "beneficiario" in r["revisar"] and r["paginas_ocr"] == 0


def test_quitar_una_etapa_del_yaml_la_salta(tmp_path):
    cfg = cargar_config().con(etapas=["control", "ingesta"])
    r = ejecutar_etapas(crear_poliza(tmp_path / "POL-0001.pdf"), "poliza", cfg)
    assert list(r["fases"]) == ["ingesta"] and set(r["segundos"]) == {"control", "ingesta"}


def test_el_control_aparta_un_archivo_vacio_y_las_demas_etapas_no_corren(tmp_path):
    ruta = tmp_path / "LOT-0016.pdf"
    ruta.write_bytes(b"")
    r = ejecutar_etapas(ruta, "poliza", cargar_config())
    assert (r["estado"], r["motivo"]) == ("cuarentena", "archivo_vacio") and r["fases"] == {} and r["revisar"] == []


def test_el_ocr_no_reemplaza_un_campo_que_ya_venia_de_la_ingesta(monkeypatch):
    monkeypatch.setattr(etapas, "aplicar_ocr", lambda doc, motor: doc)
    monkeypatch.setattr(etapas, "campos_rotulados", lambda tipo, doc: {"nombre": "Otro Nombre DNI 99000002", "dni": "99000001"})
    d = {"tipo": "reclamo", "doc": {"pendientes": [{"parte": 1}]}, "campos": {"nombre": "Ana Paz Ruiz", "dni": None}}
    assert etapas.ocr(d, cargar_config())["campos"] == {"nombre": "Ana Paz Ruiz", "dni": "99000001"}
