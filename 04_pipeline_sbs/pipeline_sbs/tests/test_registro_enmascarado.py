"""Pruebas del libro de actas (S07): los 12 casos del registro enmascarado y el registro de una corrida."""
import io
import json
import logging

import pymupdf
import pytest

from pipeline_sbs.monitoreo.registro import FormateadorJson, ejecutar_registrado, evento_documento
from pipeline_sbs.orquestacion.config import cargar_config

# (caso, mensaje, extra, campo que se mira, lo que debe verse, lo que no debe verse)
CASOS = [
    ("dni_en_el_mensaje", "cliente 99386108", {}, "mensaje", "******08", "99386108"),
    ("ruc_en_el_mensaje", "empresa RUC 20992371634", {}, "mensaje", "*********34", "20992371634"),
    ("correo", "respuesta a daniel.rojas@ejemplo.pe", {}, "mensaje", "d***@ejemplo.pe", "daniel.rojas"),
    ("cuenta", "abono en la cuenta 999-1278573731", {}, "mensaje", "999-******3731", "1278573731"),
    ("cci_de_20_digitos", "CCI 99912785737316006028", {}, "mensaje", "****************6028", "9991278573731600"),
    ("telefono", "llamar al 999 000 326", {}, "mensaje", "*** *** 326", "999 000 326"),
    ("extra_con_texto", "documento", {"detalle": "titular 99386133"}, "detalle", "******33", "99386133"),
    ("extra_con_diccionario", "documento", {"datos": {"dni": "99386133", "ruc": "20992371634", "ramo": "Vida"}}, "datos", "[OCULTO]", "20992371634"),
    ("extra_con_lista", "documento", {"lista": ["99386133", "99838098"]}, "lista", "******98", "99838098"),
    ("salto_de_linea", "linea 1\nlinea 2 inyectada", {}, "mensaje", "linea 2 inyectada", None),
    ("ocho_cifras_que_no_son_dni", "monto 99400000", {}, "mensaje", "******00", "99400000"),
    ("fecha_iso", "vigencia 2026-11-20", {}, "mensaje", "2026-11-20", None),
]


def registrar(mensaje, extra):
    """Escribe un evento con el formateador del registro y devuelve la línea escrita."""
    salida = io.StringIO()
    logger = logging.getLogger("prueba.s07.enmascarado")
    logger.handlers.clear()
    logger.propagate = False
    manejador = logging.StreamHandler(salida)
    manejador.setFormatter(FormateadorJson())
    logger.addHandler(manejador)
    logger.warning(mensaje, extra=extra)
    return salida.getvalue()


@pytest.mark.parametrize("caso", CASOS, ids=[c[0] for c in CASOS])
def test_el_registro_no_deja_pasar_datos_personales(caso):
    _, mensaje, extra, campo, debe_verse, no_debe_verse = caso
    linea = registrar(mensaje, extra)
    assert linea.count("\n") == 1, "cada evento ocupa una sola línea"
    evento = json.loads(linea)
    assert debe_verse in json.dumps(evento[campo], ensure_ascii=False)
    if no_debe_verse:
        assert no_debe_verse not in linea, f"fuga: {no_debe_verse} aparece en el registro"


def crear_bandeja(tmp_path):
    """Una póliza digital y un archivo vacío."""
    carpeta = tmp_path / "bandeja"
    carpeta.mkdir()
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "POLIZA DE SEGURO - CONDICIONES PARTICULARES\nPoliza: PZ-2026-000001\nRUC 20992371634\nDNI 99386133")
    pdf.save(str(carpeta / "POL-0001.pdf"))
    pdf.close()
    (carpeta / "LOT-0016.pdf").write_bytes(b"")
    return carpeta


def test_el_evento_de_un_documento_cuenta_campos_pero_no_lleva_sus_valores():
    resultado = {"archivo": "POL-0001.pdf", "tipo": "poliza", "estado": "ok", "campos": {"dni": "99386133", "ruc": None, "ramo": "Vida", "prima_anual": 10.5},
                 "ambiguos": [], "caracteres": 600, "paginas": 1, "paginas_ocr": 0, "segundos_total": 0.2}
    evento = evento_documento(resultado, 0.85)
    assert evento["campos"] == 4 and evento["campos_nulos"] == 1 and evento["confianza"] == 0.75
    assert evento["ruta"] == "revisar" and "confianza_baja" in evento["causas_revision"]
    assert "99386133" not in json.dumps(evento) and "Vida" not in json.dumps(evento)


def test_la_corrida_deja_inicio_un_evento_por_documento_y_fin(tmp_path):
    cfg = cargar_config().con(modo="secuencial").en_carpeta(tmp_path / "salidas")
    ruta = tmp_path / "salidas" / "registro.jsonl"
    resumen = ejecutar_registrado(crear_bandeja(tmp_path), cfg, ruta)
    eventos = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert [e["evento"] for e in eventos] == ["corrida_inicio", "documento_fallido", "documento_procesado", "corrida_fin"]
    assert all(e["corrida_id"] == resumen.corrida_id for e in eventos)
    assert eventos[0]["version"] and eventos[0]["operador"] and eventos[1]["error"]
    assert "20992371634" not in ruta.read_text(encoding="utf-8") and "99386133" not in ruta.read_text(encoding="utf-8")
