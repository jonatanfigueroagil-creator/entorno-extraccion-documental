"""Pruebas del OCR. La prueba con texto real se omite si no está instalado Tesseract."""
import shutil

import pytest
import pytesseract
from PIL import Image, ImageDraw, ImageFont

from pipeline_sbs.ocr.tesseract import TesseractNoDisponibleError, ocr_imagen

HAY_TESSERACT = shutil.which(pytesseract.pytesseract.tesseract_cmd) is not None


def test_ocr_imagen_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        ocr_imagen(tmp_path / "no_existe.png")


def test_ocr_error_claro_sin_binario(tmp_path, monkeypatch):
    imagen = tmp_path / "hoja.png"
    Image.new("RGB", (50, 50), "white").save(imagen)
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract_que_no_existe")
    with pytest.raises(TesseractNoDisponibleError, match="tesseract"):
        ocr_imagen(imagen)


@pytest.mark.skipif(not HAY_TESSERACT, reason="Tesseract no está instalado en esta máquina")
def test_ocr_lee_texto_grande(tmp_path):
    imagen = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(imagen).text((30, 50), "OFICIO 0522", fill="black", font=ImageFont.load_default(size=80))
    ruta = tmp_path / "oficio.png"
    imagen.save(ruta)
    assert "OFICIO" in ocr_imagen(ruta, idioma="eng").upper()
