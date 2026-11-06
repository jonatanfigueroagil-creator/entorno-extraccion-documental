"""Pruebas de pdf_a_imagen."""
import pymupdf

from mi_pipeline.ocr.renderizar import pdf_a_imagen


def test_pdf_a_imagen_a_300_dpi(tmp_path):
    pdf = tmp_path / "hoja.pdf"
    documento = pymupdf.open()
    documento.new_page(width=612, height=792).insert_text((72, 72), "Oficio DEMO")
    documento.save(str(pdf))
    assert pdf_a_imagen(pdf, dpi=300).shape == (3300, 2550, 3)
