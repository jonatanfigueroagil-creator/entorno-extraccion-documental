"""Pruebas de los fallos silenciosos del caso (S07): no lanzan error, pero ya no pasan como «aceptar»."""
import pymupdf

from pipeline_sbs.monitoreo.registro import evento_documento
from pipeline_sbs.orquestacion.config import cargar_config
from pipeline_sbs.orquestacion.trabajo import procesar_archivo

LAYOUT_NUEVO = ["POLIZA DE SEGURO - CONDICIONES PARTICULARES", "Nro. de poliza - PZ-2026-123456",
                "Compania de seguros - Seguros Tierra Firme DEMO S.A.", "Linea de seguro - Vida", "Capital asegurado - S/ 120,000.00",
                "Prima total - S/ 1,250.50", "Inicio de cobertura - 3 de marzo de 2026", "Fin de cobertura - 3 de marzo de 2027",
                "Franquicia - 5%", "La presente poliza se rige por las condiciones generales entregadas al asegurado."]


def crear_pdf(ruta, lineas):
    """Un PDF digital de una página con estas líneas."""
    pdf = pymupdf.open()
    pagina = pdf.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((60, 72 + 16 * i), linea, fontsize=9)
    pdf.save(str(ruta))
    pdf.close()
    return ruta


def test_un_pdf_digital_con_pocos_caracteres_va_a_revision_con_su_causa(tmp_path):
    r = procesar_archivo(crear_pdf(tmp_path / "POL-0092.pdf", ["POLIZA DE SEGURO - CONDICIONES PARTICULARES", "Poliza: PZ-2026-1"]), "poliza", cargar_config())
    assert r["estado"] == "ok" and r["paginas"] == 1 and "texto_insuficiente" in r["causas_revision"]
    assert evento_documento(r, 0.85)["ruta"] == "revisar"


def test_el_layout_nuevo_se_lee_con_los_sinonimos_del_yaml(tmp_path):
    ruta = crear_pdf(tmp_path / "POL-0093.pdf", LAYOUT_NUEVO)
    cfg = cargar_config()
    sin_sinonimos = procesar_archivo(ruta, "poliza", cfg.model_copy(update={"sinonimos_rotulos": {}}))
    con_sinonimos = procesar_archivo(ruta, "poliza", cfg)
    assert sin_sinonimos["campos"]["ramo"] is None and sin_sinonimos["campos"]["suma_asegurada"] is None
    assert con_sinonimos["campos"]["ramo"] == "Vida" and con_sinonimos["campos"]["suma_asegurada"] == 120000.0
    assert con_sinonimos["campos"]["vigencia_desde"] == "2026-03-03" and "ramo" in con_sinonimos["por_sinonimo"]
    assert len(con_sinonimos["revisar"]) < len(sin_sinonimos["revisar"])


def test_un_documento_normal_no_queda_marcado(tmp_path):
    lineas = [linea.replace("Nro. de poliza -", "Poliza:").replace("Linea de seguro -", "Ramo") for linea in LAYOUT_NUEVO] + ["x" * 120]
    r = procesar_archivo(crear_pdf(tmp_path / "POL-0001.pdf", lineas), "poliza", cargar_config())
    assert r["causas_revision"] == []
