"""Pruebas del contrato Documento."""
import dataclasses

import pytest

from pipeline_sbs.documento import Documento


def crear() -> Documento:
    return Documento(ruta="EFI-0001.pdf", tipo="pdf", extension=".pdf", paginas=2,
                     tiene_capa_texto=True, sha256="0" * 64)


def test_documento_guarda_sus_campos():
    d = crear()
    assert (d.tipo, d.extension, d.paginas, d.tiene_capa_texto) == ("pdf", ".pdf", 2, True)


def test_documento_es_inmutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        crear().paginas = 5  # type: ignore[misc]


def test_documento_campos_del_contrato():
    nombres = [c.name for c in dataclasses.fields(Documento)]
    assert nombres == ["ruta", "tipo", "extension", "paginas", "tiene_capa_texto", "sha256"]
