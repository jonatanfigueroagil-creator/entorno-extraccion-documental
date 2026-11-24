"""Fixtures comunes: PDF sintéticos creados al vuelo y localización opcional de los datos de práctica."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from pypdf import PdfWriter


def crear_pdf_con_texto(ruta: Path, texto: str) -> Path:
    """Escribe un PDF de una página con ``texto`` seleccionable (sin dependencias extra)."""
    flujo = f"BT /F1 14 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n".encode() + b"0000000000 65535 f \n"
    for pos in posiciones:
        salida += f"{pos:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode()
    ruta.write_bytes(bytes(salida))
    return ruta


def crear_pdf_sin_texto(ruta: Path, paginas: int = 1) -> Path:
    """Escribe un PDF de páginas en blanco (equivale a un escaneado sin capa de texto)."""
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=612, height=792)
    with ruta.open("wb") as f:
        escritor.write(f)
    return ruta


@pytest.fixture
def lote_sintetico(tmp_path: Path) -> Path:
    """Carpeta con un PDF nativo, un PDF sin texto, un PDF dañado, un .eml y una imagen."""
    crear_pdf_con_texto(tmp_path / "A_nativo.pdf", "Estado de situacion financiera DEMO al 31 de diciembre")
    crear_pdf_sin_texto(tmp_path / "B_escaneado.pdf", paginas=2)
    (tmp_path / "C_danado.pdf").write_bytes(b"esto no es un pdf")
    (tmp_path / "D_reclamo.eml").write_text("Subject: Reclamo DEMO\n\nTexto", encoding="utf-8")
    (tmp_path / "E_foto.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


@pytest.fixture(scope="session")
def datos_practica() -> Path:
    """Carpeta de documentos de práctica: variable SBS_DATOS_PRACTICA o la carpeta 02_Datos_Practica más cercana."""
    valor = os.environ.get("SBS_DATOS_PRACTICA")
    if valor and Path(valor).is_dir():
        return Path(valor)
    for carpeta in Path(__file__).resolve().parents:
        candidata = carpeta / "02_Datos_Practica"
        if candidata.is_dir():
            return candidata
    pytest.skip("No se encontraron los datos de práctica (define SBS_DATOS_PRACTICA)")
