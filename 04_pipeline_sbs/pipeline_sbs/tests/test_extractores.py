"""Pruebas de los extractores: un archivo sintético por formato y los errores tipificados."""
import pytest

from pipeline_sbs.ingesta.errores import (
    ErrorDocxCorrupto,
    ErrorImagenInvalida,
    ErrorPdfCifrado,
    ErrorPdfDanado,
    traducir_excepcion,
)
from pipeline_sbs.ingesta.extractores import (
    BIBLIOTECAS_PDF,
    decodificar_html,
    extraer_docx,
    extraer_eml,
    extraer_html,
    extraer_imagen,
    extraer_pdf,
    extraer_texto,
)
from pipeline_sbs.tests.conftest import (
    crear_docx,
    crear_eml,
    crear_html,
    crear_pdf_cifrado,
    crear_pdf_con_texto,
    crear_pdf_sin_texto,
    crear_png,
)

TEXTO_PDF = "Estado de situacion financiera DEMO"


@pytest.mark.parametrize("biblioteca", BIBLIOTECAS_PDF)
def test_pdf_nativo_con_las_tres_bibliotecas(tmp_path, biblioteca):
    ruta = crear_pdf_con_texto(tmp_path / "nativo.pdf", TEXTO_PDF)
    extraccion = extraer_pdf(ruta, biblioteca)
    assert extraccion.paginas == 1
    assert TEXTO_PDF in extraccion.texto
    assert extraccion.caracteres_por_pagina[0] >= len(TEXTO_PDF)


@pytest.mark.parametrize("biblioteca", BIBLIOTECAS_PDF)
def test_pdf_escaneado_devuelve_cero_caracteres_sin_error(tmp_path, biblioteca):
    extraccion = extraer_pdf(crear_pdf_sin_texto(tmp_path / "escaneado.pdf", paginas=2), biblioteca)
    assert extraccion.paginas == 2 and extraccion.caracteres == 0


def test_extraer_pdf_biblioteca_desconocida(tmp_path):
    with pytest.raises(ValueError):
        extraer_pdf(crear_pdf_con_texto(tmp_path / "a.pdf", "x"), "otra")


def test_pdf_cifrado_se_tipifica(tmp_path):
    with pytest.raises(ErrorPdfCifrado):
        extraer_pdf(crear_pdf_cifrado(tmp_path / "cifrado.pdf"), "pymupdf")


def test_pdf_truncado_se_tipifica(tmp_path):
    origen = crear_pdf_con_texto(tmp_path / "ok.pdf", TEXTO_PDF)
    truncado = tmp_path / "truncado.pdf"
    truncado.write_bytes(origen.read_bytes()[:150])
    with pytest.raises(ErrorPdfDanado):
        extraer_pdf(truncado, "pymupdf")


def test_docx_parrafos_y_tabla_sin_repetir_celdas_combinadas(tmp_path):
    ruta = crear_docx(tmp_path / "c.docx", ["Contrato DEMO"], [["Encabezado combinado", ""], ["1", "S/ 100,00"]],
                      combinar=True)
    extraccion = extraer_docx(ruta)
    lineas = extraccion.texto.split("\n")
    assert lineas[0] == "Contrato DEMO"
    assert lineas[1] == "Encabezado combinado"            # la celda combinada aparece una sola vez
    assert lineas[2] == "1 | S/ 100,00"
    assert extraccion.metadatos["tablas"] == 1


def test_docx_que_no_es_zip_se_tipifica(tmp_path):
    falso = tmp_path / "falso.docx"
    falso.write_bytes(b"%PDF-1.4 esto no es un docx")
    with pytest.raises(ErrorDocxCorrupto):
        extraer_docx(falso)


def test_eml_decodifica_tildes_y_lista_adjuntos(tmp_path):
    ruta = crear_eml(tmp_path / "r.eml", "Remisión de información DEMO", "Acción áéíóú del señor Núñez.",
                     adjunto=("../../peligro.pdf", b"%PDF-1.4"))
    extraccion = extraer_eml(ruta)
    assert "Acción áéíóú del señor Núñez." in extraccion.texto
    assert extraccion.metadatos["asunto"] == "Remisión de información DEMO"
    assert extraccion.metadatos["adjuntos"] == ["peligro.pdf"]     # el nombre del adjunto se sanea


def test_html_ignora_script_y_estilo(tmp_path):
    extraccion = extraer_html(crear_html(tmp_path / "t.html", "Aseguradora DEMO: año 2026"))
    assert "año 2026" in extraccion.texto
    assert "no soy texto" not in extraccion.texto and "color:red" not in extraccion.texto


def test_html_latin1_sin_charset_no_se_corrompe(tmp_path):
    ruta = crear_html(tmp_path / "l.html", "año de la reclamación", codificacion="latin-1", declarar=False)
    assert "año de la reclamación" in extraer_html(ruta).texto


def test_decodificar_html_usa_el_charset_declarado():
    assert decodificar_html('<meta charset="latin-1"><p>ñ</p>'.encode("latin-1")).endswith("<p>ñ</p>")
    assert decodificar_html(b"\xef\xbb\xbf<p>\xc3\xb1</p>") == "<p>ñ</p>"


def test_imagen_valida_requiere_ocr_y_trae_tamano(tmp_path):
    extraccion = extraer_imagen(crear_png(tmp_path / "v.png", lado=40))
    assert extraccion.texto == "" and extraccion.paginas == 1
    assert extraccion.metadatos["ancho"] == 40


def test_imagen_invalida_se_tipifica(tmp_path):
    falsa = tmp_path / "falsa.png"
    falsa.write_bytes(b"no soy una imagen")
    with pytest.raises(ErrorImagenInvalida):
        extraer_imagen(falsa)


def test_extraer_texto_despacha_por_formato(tmp_path):
    ruta = crear_pdf_con_texto(tmp_path / "a.pdf", TEXTO_PDF)
    assert TEXTO_PDF in extraer_texto(ruta, "pdf").texto
    from pipeline_sbs.ingesta.errores import ErrorFormatoNoSoportado

    with pytest.raises(ErrorFormatoNoSoportado):
        extraer_texto(ruta, "zip")


@pytest.mark.parametrize("error, motivo", [
    (ValueError("x"), "error_inesperado"),
    (PermissionError("bloqueado"), "archivo_inaccesible"),
])
def test_traducir_excepcion_generica(error, motivo):
    assert traducir_excepcion(error).motivo == motivo
