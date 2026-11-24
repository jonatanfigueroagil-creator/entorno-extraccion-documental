"""Pruebas del inventario: PDF nativo, PDF escaneado, PDF dañado y otros formatos."""
from pathlib import Path

import pytest

from pipeline_sbs.ingesta.inventario import inventariar, tiene_capa_texto
from pipeline_sbs.tests.conftest import crear_pdf_con_texto, crear_pdf_sin_texto


def test_pdf_nativo_tiene_capa_de_texto(tmp_path):
    ruta = crear_pdf_con_texto(tmp_path / "nativo.pdf", "Oficio DEMO numero 0522-2026")
    assert tiene_capa_texto(ruta) is True


def test_pdf_escaneado_no_tiene_capa_de_texto(tmp_path):
    assert tiene_capa_texto(crear_pdf_sin_texto(tmp_path / "escaneado.pdf")) is False


def test_tiene_capa_texto_rechaza_no_pdf(tmp_path):
    archivo = tmp_path / "nota.txt"
    archivo.write_text("hola", encoding="utf-8")
    with pytest.raises(ValueError):
        tiene_capa_texto(archivo)


def test_tiene_capa_texto_archivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        tiene_capa_texto(tmp_path / "no_existe.pdf")


def test_inventariar_lote_sintetico(lote_sintetico):
    fichas = {Path(f.ruta).name: f for f in inventariar(lote_sintetico)}
    assert list(fichas) == sorted(fichas)  # orden por nombre
    assert fichas["A_nativo.pdf"].tiene_capa_texto and fichas["A_nativo.pdf"].paginas == 1
    assert not fichas["B_escaneado.pdf"].tiene_capa_texto and fichas["B_escaneado.pdf"].paginas == 2
    assert fichas["C_danado.pdf"].paginas == 0 and not fichas["C_danado.pdf"].tiene_capa_texto
    assert fichas["D_reclamo.eml"].tipo == "correo" and fichas["D_reclamo.eml"].tiene_capa_texto
    assert fichas["E_foto.png"].tipo == "imagen" and fichas["E_foto.png"].paginas == 1
    assert all(len(f.sha256) == 64 for f in fichas.values())


def test_inventariar_carpeta_inexistente(tmp_path):
    with pytest.raises(NotADirectoryError):
        inventariar(tmp_path / "no_existe")


def test_corpus_efi_nativo_y_ofi_escaneado(datos_practica):
    fichas = inventariar(datos_practica / "03_Estados_Financieros") + inventariar(datos_practica / "02_Oficios")
    por_nombre = {Path(f.ruta).name: f for f in fichas}
    assert por_nombre["EFI-0001.pdf"].tiene_capa_texto
    assert por_nombre["EFI-0031.pdf"].tiene_capa_texto is False
    assert por_nombre["OFI-0003.pdf"].tiene_capa_texto is False
    assert por_nombre["OFI-0003.pdf"].paginas == 1
